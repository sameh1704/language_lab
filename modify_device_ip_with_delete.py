import sys

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().startswith('device = await Device.objects.acreate'):
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + '# Remove any existing devices with this IP to avoid collisions\n')
        new_lines.append(' ' * indent + 'await Device.filter(ip_address=ip_address).delete()\n')
        new_lines.append(' ' * indent + 'device = await Device.objects.acreate(classroom=classroom, number=1, ip_address=ip_address, name="Test Device", active=True)\n')
        i += 1
    else:
        new_lines.append(line)
        i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
