import sys

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().startswith('device = await Device.objects.acreate'):
        indent = len(line) - len(line.lstrip())
        # Insert ip_address generation lines before this line
        new_lines.append(' ' * indent + '# Generate unique IP based on unique_suffix to avoid collisions\n')
        new_lines.append(' ' * indent + 'ip_suffix = int(unique_suffix[:2], 16) % 256\n')
        new_lines.append(' ' * indent + 'ip_address = f"127.0.0.{ip_suffix}"\n')
        # Now add the original line
        new_lines.append(line)
    else:
        new_lines.append(line)
    i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
