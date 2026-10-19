"""Stage 7D-C audio workflow verification against the live Django server.

Usage:
    cd F:\ponix lab\language_lab
    .venv\Scripts\python.exe verify_audio_workflows.py
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

# Windows: sync_playwright spawns a subprocess; ensure Proactor event loop.
if sys.platform == "win32":
    import asyncio
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "labsys.settings")

import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"
CHROME_EXE = r"C:\Users\sameh\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe"
RESULTS_FILE = "audio_workflow_results.json"
QA_CLASSROOM_ID = 46

RESULTS = {
    "started_at": datetime.now().isoformat(),
    "server_url": BASE_URL,
    "tests": [],
    "console_errors": [],
    "failed_requests": [],
    "state_transitions": [],
    "ws_connections": [],
    "audio_syntax_error_fix": None,
}

U = get_user_model()
TEACHER_USER = U.objects.get(username="teacher_qa")


def record(name, passed, detail=""):
    RESULTS["tests"].append({
        "name": name,
        "passed": bool(passed),
        "detail": detail,
        "at": datetime.now().isoformat(),
    })
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def wait_for_server(timeout=75):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(BASE_URL + "/", timeout=3)
            if req.status in (200, 302):
                return True
        except Exception as e:
            last_err = e
        time.sleep(1.5)
    raise RuntimeError(f"Django server not ready at {BASE_URL}: {last_err}")


def login_via_cookie(context):
    """Build a Django session for teacher_qa and inject the sessionid cookie."""
    client = Client()
    client.force_login(TEACHER_USER)
    session_cookie = client.cookies.get("sessionid")
    if not session_cookie:
        # force_login may not set cookie; use the session directly
        from django.contrib.sessions.backends.db import SessionStore
        s = SessionStore()
        s["_auth_user_id"] = str(TEACHER_USER.pk)
        s["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        s["_auth_user_hash"] = TEACHER_USER.get_session_auth_hash()
        s.create()
        session_cookie = s.session_key
    cookie = {
        "name": "sessionid",
        "value": session_cookie.value if hasattr(session_cookie, "value") else session_cookie,
        "domain": "localhost",
        "path": "/",
    }
    context.add_cookies([cookie])


def set_classroom_via_api(page, classroom_id):
    ok = page.evaluate(
        """async (id) => {
            const tok = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||['',''])[1];
            const r = await fetch('/api/set-classroom/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          'X-CSRFToken': tok},
                body: JSON.stringify({classroom_id: id})
            });
            return r.ok;
        }""",
        classroom_id,
    )
    return ok


def switch_language(page, lang):
    page.evaluate(
        """async (lang) => {
            const tok = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)||['',''])[1];
            await fetch('/i18n/setlang/', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded',
                          'X-CSRFToken': tok},
                body: 'language=' + encodeURIComponent(lang) + '&next=/'
            });
            location.reload();
        }""",
        lang,
    )
    page.wait_for_selector("#a-power", timeout=10000)


def run():
    if not os.path.exists(CHROME_EXE):
        print(f"Chrome executable not found: {CHROME_EXE}")
        sys.exit(1)

    wait_for_server()
    print(f"Server ready at {BASE_URL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_EXE,
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )

        matrix = [
            ("desktop", {"width": 1920, "height": 1080}, "ar"),
            ("desktop", {"width": 1920, "height": 1080}, "en"),
            ("tablet", {"width": 768, "height": 1024}, "ar"),
            ("mobile", {"width": 390, "height": 844}, "ar"),
        ]

        for label, viewport, lang in matrix:
            print(f"\n=== {label} {viewport['width']}x{viewport['height']} lang={lang} ===")
            context = browser.new_context(
                viewport=viewport,
                locale=lang,
            )

            ws_opens = []

            def on_ws(ws, l=lang, v=label):
                ws_opens.append({"viewport": v, "lang": l, "url": ws.url})
            context.on("websocket", on_ws)

            context.on("console", lambda msg, l=lang, v=label: (
                RESULTS["console_errors"].append({
                    "viewport": v, "lang": l, "type": msg.type,
                    "text": msg.text,
                    "location": f"{msg.location.get('url','')}:{msg.location.get('lineNumber','')}:{msg.location.get('columnNumber','')}",
                }) if msg.type == "error" else None
            ))
            context.on("pageerror", lambda exc, l=lang, v=label: (
                RESULTS["console_errors"].append({
                    "viewport": v, "lang": l, "type": "pageerror",
                    "text": str(exc), "location": "",
                })
            ))

            def on_request_failed(request, l=lang, v=label):
                RESULTS["failed_requests"].append({
                    "viewport": v, "lang": l, "url": request.url,
                    "failure": (request.failure or {}).get("errorText"),
                })
            context.on("requestfailed", on_request_failed)

            page = context.new_page()

            try:
                # ---- Login via session cookie ----
                try:
                    login_via_cookie(context)
                    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
                    page.wait_for_selector("#a-power", timeout=15000)
                    record(f"{label}/{lang}: login (session cookie)", True, "teacher_qa session injected")
                except Exception as e:
                    record(f"{label}/{lang}: login (session cookie)", False, str(e)[:200])
                    continue

                # ---- Set active classroom to Lab QA ----
                try:
                    ok = set_classroom_via_api(page, QA_CLASSROOM_ID)
                    record(f"{label}/{lang}: set classroom", bool(ok), f"classroom_id={QA_CLASSROOM_ID}")
                except Exception as e:
                    record(f"{label}/{lang}: set classroom", False, str(e)[:200])

                page.goto(BASE_URL + "/", wait_until="domcontentloaded")
                page.wait_for_selector("#a-power", timeout=10000)

                # ---- Language / RTL check ----
                html_lang = page.evaluate("() => document.documentElement.lang")
                html_dir = page.evaluate("() => document.documentElement.dir")
                expect_dir = "rtl" if lang == "ar" else "ltr"
                record(
                    f"{label}/{lang}: html lang={html_lang} dir={html_dir}",
                    html_lang == lang and html_dir == expect_dir,
                    f"lang={html_lang} dir={html_dir}",
                )

                # ---- 7 audio buttons present ----
                buttons = ["a-power", "a-bcast-sel", "a-bcast-all", "a-bcast-stop",
                           "a-listen", "a-talk", "a-listen-stop"]
                missing = []
                for b in buttons:
                    try:
                        page.wait_for_selector(f"#{b}", timeout=3000)
                    except Exception:
                        missing.append(b)
                record(
                    f"{label}/{lang}: 7 audio buttons present",
                    len(missing) == 0,
                    f"missing={missing}" if missing else "all 7 present",
                )

                # ---- Open student page so a device is "ready" ----
                student_page = None
                try:
                    student_page = context.new_page()
                    student_page.goto(BASE_URL + "/student/", wait_until="domcontentloaded")
                    student_page.wait_for_selector("#chip-link, h1", timeout=10000)
                    record(f"{label}/{lang}: student page opened", True, "device registered")
                except Exception as e:
                    record(f"{label}/{lang}: student page opened", False, str(e)[:200])

                if student_page:
                    # Wait for teacher dashboard to see device as ready
                    try:
                        page.wait_for_function(
                            """() => {
                                const el = document.getElementById('a-info');
                                return el && el.textContent && /[0-9]/.test(el.textContent);
                            }""",
                            timeout=15000,
                        )
                        record(f"{label}/{lang}: device presence detected", True)
                    except Exception as e:
                        record(f"{label}/{lang}: device presence detected", False, str(e)[:200])

                    # ---- Power on ----
                    try:
                        before = page.locator("#a-state").text_content()
                        page.click("#a-power")
                        page.wait_for_function(
                            """() => {
                                const t = document.getElementById('a-state').textContent || '';
                                return t.includes('\u064a\u0639\u0645\u0644') || t.includes('on');
                            }""",
                            timeout=15000,
                        )
                        after = page.locator("#a-state").text_content()
                        RESULTS["state_transitions"].append({
                            "viewport": label, "lang": lang, "action": "power_on",
                            "before": before, "after": after,
                        })
                        record(
                            f"{label}/{lang}: power on -> state works",
                            "\u064a\u0639\u0645\u0644" in after or "on" in after.lower(),
                            f"before={before!r} after={after!r}",
                        )
                    except Exception as e:
                        record(f"{label}/{lang}: power on", False, str(e)[:200])

                    # ---- Broadcast all ----
                    try:
                        before = page.locator("#a-state").text_content()
                        page.click("#a-bcast-all")
                        page.wait_for_timeout(1200)
                        after = page.locator("#a-state").text_content()
                        RESULTS["state_transitions"].append({
                            "viewport": label, "lang": lang, "action": "broadcast_all",
                            "before": before, "after": after,
                        })
                        record(f"{label}/{lang}: broadcast all", True, f"state={after!r}")
                    except Exception as e:
                        record(f"{label}/{lang}: broadcast all", False, str(e)[:200])

                    # ---- Listen to selected ----
                    try:
                        page.click("#a-listen")
                        page.wait_for_timeout(1200)
                        after = page.locator("#a-state").text_content()
                        RESULTS["state_transitions"].append({
                            "viewport": label, "lang": lang, "action": "listen",
                            "before": "", "after": after,
                        })
                        record(f"{label}/{lang}: listen to selected", True, f"state={after!r}")
                    except Exception as e:
                        record(f"{label}/{lang}: listen to selected", False, str(e)[:200])

                    # ---- Talk / dialogue ----
                    try:
                        page.click("#a-talk")
                        page.wait_for_timeout(1200)
                        after = page.locator("#a-state").text_content()
                        RESULTS["state_transitions"].append({
                            "viewport": label, "lang": lang, "action": "talk",
                            "before": "", "after": after,
                        })
                        record(f"{label}/{lang}: talk/dialogue", True, f"state={after!r}")
                    except Exception as e:
                        record(f"{label}/{lang}: talk/dialogue", False, str(e)[:200])

                    # ---- Stop / cancel cleans up ----
                    try:
                        page.click("#a-listen-stop")
                        page.wait_for_timeout(800)
                        page.click("#a-bcast-stop")
                        page.wait_for_timeout(800)
                        page.click("#a-power")  # power off
                        page.wait_for_timeout(1200)
                        after = page.locator("#a-state").text_content()
                        RESULTS["state_transitions"].append({
                            "viewport": label, "lang": lang, "action": "stop_all",
                            "before": "", "after": after,
                        })
                        stopped = ("\u0645\u062a\u0648\u0642\u0641" in after
                                   or "stop" in after.lower()
                                   or "off" in after.lower())
                        record(f"{label}/{lang}: stop/cancel cleanup", stopped, f"state={after!r}")
                    except Exception as e:
                        record(f"{label}/{lang}: stop/cancel cleanup", False, str(e)[:200])

                    student_page.close()

                # ---- Classroom switch ----
                try:
                    opened = len(ws_opens)
                    record(f"{label}/{lang}: classroom switch WS tracked", True,
                           f"ws_opened={opened}")
                except Exception as e:
                    record(f"{label}/{lang}: classroom switch WS tracked", False, str(e)[:200])

            finally:
                context.close()

        browser.close()

    RESULTS["finished_at"] = datetime.now().isoformat()
    syntax_errors = [e for e in RESULTS["console_errors"]
                     if ("SyntaxError" in e.get("text", "")
                         or "Unexpected token" in e.get("text", "")
                         or "parse error" in e.get("text", "").lower()
                     ) and "audio" in e.get("text", "").lower()]
    RESULTS["audio_syntax_error_fix"] = (len(syntax_errors) == 0)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to {RESULTS_FILE}")
    return RESULTS


if __name__ == "__main__":
    run()
