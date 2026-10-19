import subprocess
import sys

# Run the test and capture output
result = subprocess.run([sys.executable, "test_webrtc_signaling_fixed.py"], 
                       capture_output=True, text=True)

# Print the output
print(result.stdout)

# Print any errors
if result.stderr:
    print("\nSTDERR:", result.stderr)

# Check exit code
if result.returncode == 0:
    print("\n✅ Test PASSED")
else:
    print(f"\n❌ Test FAILED with exit code: {result.returncode}")