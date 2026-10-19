import sys

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip().startswith('print(f"Warning: drained unexpected message: {assistance}")'):
        indent = len(line) - len(line.lstrip())
        # We want exactly 4 spaces indent? Let's just make it 4 spaces.
        new_lines.append('    print(f"Warning: drained unexpected message: {assistance}")\n')
    else:
        new_lines.append(line)

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
