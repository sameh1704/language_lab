import sys

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip().startswith('device = await Device.objects.acreate'):
        # Insert print after this line
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + 'print(f"[TEST] Created classroom id: {classroom.id}, device classroom_id: {device.classroom_id}")\n')
    i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
