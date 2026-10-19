import sys

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == '# Remove any existing devices with this IP to avoid collisions':
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + '# Generate unique IP based on unique_suffix to avoid collisions\n')
        new_lines.append(' ' * indent + 'ip_suffix = int(unique_suffix[:2], 16) % 256\n')
        new_lines.append(' ' * indent + 'ip_address = f"127.0.0.{ip_suffix}"\n')
    i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
