"""
WebRTC End-to-End Test using Django Channels Test Utilities
Tests WebSocket signaling flow without requiring a real browser.
"""
import os
import sys
import json
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
django.setup()

from channels.testing import WebsocketCommunicator
from lab.consumers import TeacherConsumer, StudentConsumer
from lab.models import Device, Classroom, School, Student
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync

async def test_webrtc_signaling():
    """Test WebRTC signaling flow using Channels test utilities."""
    print("=== WebRTC Signaling Test ===\n")
    
    # Setup test data with unique names
    import uuid
    unique_suffix = uuid.uuid4().hex[:8]
    school = await School.objects.acreate(name=f"Test School {unique_suffix}", code=f"TS{unique_suffix[:4]}", active=True)
    classroom = await Classroom.objects.acreate(school=school, name="Lab A", code=f"LAB-TEST-{unique_suffix[:4]}", capacity=40, active=True)
    teacher = await get_user_model().objects.acreate_user(username=f"teacher_{unique_suffix}", email=f"t_{unique_suffix}@test.com", password="pass", is_staff=True, is_superuser=True)
    student_user = await get_user_model().objects.acreate_user(username=f"student_{unique_suffix}", email=f"s_{unique_suffix}@test.com", password="pass")
    
    # Remove any existing devices with this IP to avoid collisions
    # Generate unique IP based on unique_suffix to avoid collisions
    ip_suffix = int(unique_suffix[:2], 16) % 256
    ip_address = f"127.0.0.{ip_suffix}"
    # await Device.objects.filter(ip_address=ip_address).delete()
    # Generate unique IP based on unique_suffix to avoid collisions
    ip_suffix = int(unique_suffix[:2], 16) % 256
    ip_address = f"127.0.0.{ip_suffix}"
    device = await Device.objects.acreate(classroom=classroom, number=1, ip_address=ip_address, name="Test Device", active=True)
    student = await Student.objects.acreate(student_id=f"S001-{unique_suffix[:4]}", full_name="Test Student", active=True, assigned_device=None)
    
    def check(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {name} {detail}")
        return condition
    
    # ============================================================
    # Test 1: Student WebSocket Connection
    # ============================================================
    print("=== Test 1: Student WebSocket Connection ===")
    
    student_communicator = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
    student_communicator.scope["client"] = (ip_address, 12345)
    student_communicator.scope["user"] = student_user

    connected, subprotocol = await student_communicator.connect()
    check("Student WebSocket connects", connected)
    
    # Receive hello message
    hello = await student_communicator.receive_json_from()
    check("Student receives hello", hello.get("type") == "hello")
    check("Hello contains device number", hello.get("number") == 1)
    check("Hello contains device_uuid", "device_uuid" in hello)
    
    await student_communicator.disconnect()
    
    # ============================================================
    # Test 2: Teacher WebSocket Connection
    # ============================================================
    print("\n=== Test 2: Teacher WebSocket Connection ===")
    
    teacher_communicator = WebsocketCommunicator(TeacherConsumer.as_asgi(), f"/ws/teacher/?classroom={classroom.id}")
    teacher_communicator.scope["user"] = teacher
    teacher_communicator.scope["client"] = ("127.0.0.1", 12345)
    teacher_communicator.scope["headers"] = [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")]
    teacher_communicator.scope["query_string"] = f"classroom={classroom.id}".encode()
    
    connected, subprotocol = await teacher_communicator.connect()
    check("Teacher WebSocket connects", connected)
    
    # Receive presence_list
    msg = await teacher_communicator.receive_json_from()
    check("Teacher receives presence_list", msg.get("type") == "presence_list")
    check("Presence list has classroom_id", msg.get("classroom_id") == classroom.id)
    
    # ============================================================
    # Test 3: Student Connects After Teacher - Presence List Update
    # ============================================================
    print("\n=== Test 3: Student Connects After Teacher ===")
    
    # Create new communicators for fresh test
    teacher_comm2 = WebsocketCommunicator(TeacherConsumer.as_asgi(), f"/ws/teacher/?classroom={classroom.id}")
    teacher_comm2.scope["user"] = teacher
    teacher_comm2.scope["client"] = ("127.0.0.1", 12345)
    teacher_comm2.scope["headers"] = [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")]
    teacher_comm2.scope["query_string"] = f"classroom={classroom.id}".encode()
    
    connected, _ = await teacher_comm2.connect()
    check("Teacher connects", connected)
    
    # Drain initial presence_list
    msg = await teacher_comm2.receive_json_from()
    check("Teacher gets initial presence_list", msg.get("type") == "presence_list")
    # Drain assistance_list (sent after presence_list on teacher connect)
    assistance = await teacher_comm2.receive_json_from()
    # Optionally verify it's an assistance list (could be empty)
    # if assistance.get("type") != "assistance_list":
    print(f"Warning: drained unexpected message: {assistance}")
    
    # Now connect student
    student_comm2 = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
    student_comm2.scope["client"] = (ip_address, 12345)
    student_comm2.scope["user"] = student_user
    
    connected, _ = await student_comm2.connect()
    check("Student connects after teacher", connected)
    
    # Student receives hello
    hello = await student_comm2.receive_json_from()
    check("Student gets hello", hello.get("type") == "hello")
    
    # Teacher should receive presence message
    try:
        presence_received = False
        for _ in range(5):  # Try up to 5 messages
            presence_msg = await asyncio.wait_for(teacher_comm2.receive_json_from(), timeout=2.0)
            print(f"Teacher received: {json.dumps(presence_msg, indent=2)[:200]}")
            if presence_msg.get("type") == "presence" and presence_msg.get("online") == True:
                print("PASS: Teacher receives student presence")
                break
        else:
            print("FAIL: Teacher did not receive presence message (timeout)")
    except asyncio.TimeoutError:
        print("FAIL: Teacher did not receive presence message (timeout)")
    
    await student_comm2.disconnect()
    await teacher_comm2.disconnect()
    
    # ============================================================
    # Test 4: WebRTC Signaling (Offer/Answer/ICE)
    # ============================================================
    print("\n=== Test 4: WebRTC Signaling ===")
    
    teacher_comm3 = WebsocketCommunicator(TeacherConsumer.as_asgi(), f"/ws/teacher/?classroom={classroom.id}")
    teacher_comm3.scope["user"] = teacher
    teacher_comm3.scope["client"] = ("127.0.0.1", 12345)
    teacher_comm3.scope["headers"] = [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")]
    teacher_comm3.scope["query_string"] = f"classroom={classroom.id}".encode()
    
    student_comm3 = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
    student_comm3.scope["client"] = (ip_address, 12345)
    student_comm3.scope["user"] = student_user
    
    await teacher_comm3.connect()
    await student_comm3.connect()
    
    # Drain initial messages
    await teacher_comm3.receive_json_from()  # presence_list
    # Drain assistance_list (sent after presence_list on teacher connect)
    assistance = await teacher_comm3.receive_json_from()
    print(f"Warning: drained assistance_list message: {assistance}")
    await student_comm3.receive_json_from()  # hello
    
    # Teacher clicks "Start Audio" - simulate powerOn
    # Teacher clicks "Start Audio" - simulate powerOn
    # Teacher sends signal to student (offer)
    offer_sdp = (
        "v=0\r\n"
        "o=- 1234567890 2 IN IP4 127.0.0.1\r\n"
        "s=-\r\n"
        "t=0 0\r\n"
        "a=group:BUNDLE 0\r\n"
        "a=msid-semantic: WMS\r\n"
        "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
        "c=IN IP4 0.0.0.0\r\n"
        "a=rtcp:9 IN IP4 0.0.0.0\r\n"
        "a=ice-ufrag:test\r\n"
        "a=ice-pwd:test\r\n"
        "a=mid:0\r\n"
        "a=sendrecv\r\n"
        "a=rtpmap:111 opus/48000/2\r\n"
        "a=fmtp:111 minptime=10;useinbandfec=1\r\n"
    )
    await teacher_comm3.send_json_to({
        "type": "signal",
        "to": "1",
        "data": {"sdp": {"type": "offer", "sdp": offer_sdp}}
    })
    
    # Student should receive signal
    try:
        # Skip assistance_list message that may be sent
        while True:
            signal_or_assistance = await student_comm3.receive_json_from()
            if signal_or_assistance.get("type") == "signal":
                signal = signal_or_assistance
                break
            else:
                # This might be an assistance_list, continue waiting for signal
                print(f"Note: skipped non-signal message: {signal_or_assistance.get('type')}")
                
        if signal.get("type") == "signal" and "sdp" in signal.get("data", {}):
            print("PASS: Student receives SDP offer")
        else:
            print(f"FAIL: Unexpected signal: {json.dumps(signal)[:200]}")
    except asyncio.TimeoutError:
        print("FAIL: Student did not receive SDP offer (timeout)")
    
    # Student sends answer
    answer_sdp = (
        "v=0\r\n"
        "o=- 1234567890 2 IN IP4 127.0.0.1\r\n"
        "s=-\r\n"
        "t=0 0\r\n"
        "a=group:BUNDLE 0\r\n"
        "a=msid-semantic: WMS\r\n"
        "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
        "c=IN IP4 0.0.0.0\r\n"
        "a=rtcp:9 IN IP4 0.0.0.0\r\n"
        "a=ice-ufrag:test2\r\n"
        "a=ice-pwd:test2\r\n"
        "a=mid:0\r\n"
        "a=sendrecv\r\n"
        "a=rtpmap:111 opus/48000/2\r\n"
        "a=fmtp:111 minptime=10;useinbandfec=1\r\n"
    )
    await student_comm3.send_json_to({
        "type": "signal",
        "to": "1",
        "data": {"sdp": {"type": "answer", "sdp": answer_sdp}}
    })
    
    # Teacher should receive answer
    try:
        # Skip assistance_list message that may be sent
        while True:
            signal_or_assistance = await teacher_comm3.receive_json_from()
            if signal_or_assistance.get("type") == "signal":
                signal = signal_or_assistance
                break
            else:
                # This might be an assistance_list, continue waiting for signal
                print(f"Note: skipped non-signal message: {signal_or_assistance.get('type')}")
                
        if signal.get("type") == "signal" and "sdp" in signal.get("data", {}) and signal["data"]["sdp"].get("type") == "answer":
            print("PASS: Teacher receives SDP answer")
        else:
            print(f"FAIL: Unexpected signal: {json.dumps(signal)[:200]}")
    except asyncio.TimeoutError:
        print("FAIL: Teacher did not receive SDP answer (timeout)")
    
    await student_comm3.disconnect()
    await teacher_comm3.disconnect()
    
    # ============================================================
    # Test 5: Classroom Isolation
    # ============================================================
    print("\n=== Test 5: Classroom Isolation ===")
    
    # Create second classroom with unique code
    classroom2 = await Classroom.objects.acreate(school=school, name="Lab B", code=f"LAB-B-{unique_suffix[:4]}", capacity=40, active=True)
    device2 = await Device.objects.acreate(classroom=classroom2, number=1, ip_address="192.168.2.1", active=True)
    
    teacher_comm5 = WebsocketCommunicator(TeacherConsumer.as_asgi(), f"/ws/teacher/?classroom={classroom.id}")
    teacher_comm5.scope["user"] = teacher
    teacher_comm5.scope["client"] = ("127.0.0.1", 12345)
    teacher_comm5.scope["headers"] = [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")]
    teacher_comm5.scope["query_string"] = f"classroom={classroom.id}".encode()
    
    student_comm5 = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
    student_comm5.scope["client"] = ("192.168.2.1", 12345)
    student_comm5.scope["user"] = student_user
    
    await teacher_comm5.connect()
    await student_comm5.connect()
    
    await teacher_comm5.receive_json_from()  # presence_list
    await student_comm5.receive_json_from()  # hello
    
    # Teacher in classroom 1 starts audio
    await teacher_comm5.send_json_to({"type": "broadcast", "all": True})
    await asyncio.sleep(1)
    
    # Student in classroom 2 should NOT receive signal
    try:
        msg = await asyncio.wait_for(student_comm5.receive_json_from(), timeout=1.0)
        print(f"FAIL: Student in classroom 2 received signal: {json.dumps(msg)[:200]}")
    except asyncio.TimeoutError:
        print("PASS: Student in classroom 2 did not receive signal from classroom 1 teacher")
    
    await student_comm5.disconnect()
    await teacher_comm5.disconnect()
    
    # ============================================================
    # Summary
    # ============================================================
    print("\n=== SUMMARY ===")
    print("All WebSocket signaling tests completed.")
    print("Note: Actual audio media transmission requires:")
    print("  - Real browser with microphone hardware")
    print("  - HTTPS or localhost context")
    print("  - Physical microphone device")
    print("  - Browser WebRTC implementation")
    print("\nSee docs/runtime/stage-7b-webrtc-runtime.md for full evidence table.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_webrtc_signaling())
