import sys
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from test_webrtc_signaling_fixed import test_webrtc_signaling
import asyncio

async def run_test():
    try:
        await test_webrtc_signaling()
        print("\n=== TEST SUMMARY ===")
        print("✅ Test PASSED - All WebRTC signaling tests completed successfully")
        print("Note: Actual audio media transmission requires:")
        print("  - Real browser with microphone hardware")
        print("  - HTTPS or localhost context")
        print("  - Physical microphone device")
        print("  - Browser WebRTC implementation")
        print("\nSee docs/runtime/stage-7b-webrtc-runtime.md for full evidence table.")
        return True
    except Exception as e:
        print(f"\n=== TEST FAILED ===")
        print(f"❌ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)