#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from test_webrtc_signaling_fixed import test_webrtc_signaling
import asyncio

async def run_test():
    print("=== Running WebRTC Signaling Test ===")
    print("Testing WebRTC signaling flow with fixed implementation...")
    print()
    
    try:
        await test_webrtc_signaling()
        print()
        print("=" * 50)
        print("TEST SUMMARY")
        print("=" * 50)
        print("✅ WebRTC signaling test PASSED")
        print()
        print("The test successfully validates:")
        print("1. Student WebSocket connection with correct IP")
        print("2. Teacher WebSocket connection with proper classroom isolation")
        print("3. Student connecting after teacher with presence list updates")
        print("4. WebRTC signaling (Offer/Answer/ICE) with proper message drainage")
        print("5. Classroom isolation (students in different classrooms don't interfere)")
        print()
        print("Note: Actual audio media transmission requires:")
        print("  - Real browser with microphone hardware")
        print("  - HTTPS or localhost context")
        print("  - Physical microphone device")
        print("  - Browser WebRTC implementation")
        print()
        print("See docs/runtime/stage-7b-webrtc-runtime.md for full evidence table.")
        print("=" * 50)
        return True
        
    except Exception as e:
        print()
        print("=" * 50)
        print("TEST FAILED")
        print("=" * 50)
        print(f"❌ Test FAILED with error: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_test())
    exit(0 if success else 1)