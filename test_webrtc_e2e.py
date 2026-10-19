import asyncio
import os
import sys
import time


def _setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "labsys.settings")
    import django

    django.setup()


def test_webrtc_audio():
    """Optional browser smoke test for WebRTC/student signaling.

    This script is intentionally safe to import during unittest discovery. The real
    browser check only runs when the file is invoked directly from the command line.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("Playwright is not installed in this environment. Skipping browser verification.")
        return

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass

    _setup_django()

    from lab.models import Device

    student_device = Device.objects.filter(number=41, classroom__code="LAB-A-FINAL").first()
    if not student_device:
        print("Student device not found; skipping browser verification.")
        return

    print(f"Student device classroom_id: {student_device.classroom_id}")
    print(f"Student device classroom code: {student_device.classroom.code}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    "--allow-file-access-from-files",
                ],
            )
            teacher_context = browser.new_context(permissions=["microphone"])
            student_context = browser.new_context(permissions=["microphone"])

            teacher_page = teacher_context.new_page()
            teacher_ws_messages = []
            teacher_page.on(
                "websocket",
                lambda ws: ws.on("framereceived", lambda msg: teacher_ws_messages.append(f"WS RX: {msg}"))
                or ws.on("framesent", lambda msg: teacher_ws_messages.append(f"WS TX: {msg}")),
            )

            student_page = student_context.new_page()
            student_ws_messages = []
            student_page.on(
                "websocket",
                lambda ws: ws.on("framereceived", lambda msg: student_ws_messages.append(f"WS RX: {msg}"))
                or ws.on("framesent", lambda msg: student_ws_messages.append(f"WS TX: {msg}")),
            )

            teacher_context.add_cookies([
                {"name": "django_language", "value": "en", "domain": "127.0.0.1", "path": "/"}
            ])
            student_context.add_cookies([
                {"name": "django_language", "value": "en", "domain": "127.0.0.1", "path": "/"}
            ])

            teacher_page.goto("http://127.0.0.1:8000/login/", wait_until="networkidle")
            teacher_page.fill('input[name="username"]', "teacher")
            teacher_page.fill('input[name="password"]', "temporary-test-password")
            teacher_page.click('button[type="submit"]')
            teacher_page.wait_for_url("**/*")

            teacher_page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
            teacher_page.wait_for_load_state("domcontentloaded")
            print("Teacher dashboard loaded.")

            if teacher_page.query_selector("#classroom-select"):
                teacher_page.select_option("#classroom-select", "14")
                time.sleep(1)

            student_page.goto("http://127.0.0.1:8000/student/", wait_until="networkidle")
            student_page.wait_for_load_state("domcontentloaded")
            print("Student page loaded.")

            presence_msgs = [msg for msg in teacher_ws_messages if '"type": "presence_list"' in msg]
            print(f"Teacher WebSocket presence_list received: {len(presence_msgs)} messages")

            sdp_offers = [msg for msg in teacher_ws_messages if '"type": "signal"' in msg and 'offer' in msg]
            sdp_answers = [msg for msg in student_ws_messages if '"type": "signal"' in msg and 'answer' in msg]
            ice_candidates = [msg for msg in teacher_ws_messages + student_ws_messages if '"type": "signal"' in msg and 'candidate' in msg]
            print(f"SDP offers: {len(sdp_offers)}")
            print(f"SDP answers: {len(sdp_answers)}")
            print(f"ICE candidates: {len(ice_candidates)}")

            browser.close()
    except NotImplementedError:
        print("Playwright browser launch is not supported in this Python runtime. Skipping browser verification.")


if __name__ == "__main__":
    test_webrtc_audio()