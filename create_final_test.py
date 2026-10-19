import sys

with open('test_webrtc_signaling.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Fix test 2 assertion
    if 'check("Presence list has classroom_id", msg.get("classroom_id") == 1)' in line:
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + 'check("Presence list has classroom_id", msg.get("classroom_id") == classroom.id)\n')
        i += 1
        continue
    # Fix test 3: after draining presence_list, drain assistance_list
    if line.strip() == '# Drain initial presence_list':
        # Keep the comment line
        new_lines.append(line)
        i += 1
        if i < len(lines):
            new_lines.append(lines[i])  # msg = await teacher_comm2.receive_json_from()
            i += 1
        if i < len(lines):
            new_lines.append(lines[i])  # check line
            i += 1
        # Insert assistance_list drain
        indent = len(lines[i-3]) - len(lines[i-3].lstrip()) if i>=3 else 0
        new_lines.append(' ' * indent + '# Drain assistance_list (sent after presence_list on teacher connect)\n')
        new_lines.append(' ' * indent + 'assistance = await teacher_comm2.receive_json_from()\n')
        new_lines.append(' ' * indent + '# Optionally verify it'"'"'s an assistance list (could be empty)\n')
        new_lines.append(' ' * indent + '# if assistance.get("type") != "assistance_list":\n')
        new_lines.append(' ' * indent + '    print(f"Warning: drained unexpected message: {assistance}")\n')
        continue
    # Replace device creation with unique IP and delete existing
    if line.strip().startswith('device = await Device.objects.acreate'):
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + '# Remove any existing devices with this IP to avoid collisions\n')
        new_lines.append(' ' * indent + 'await Device.objects.filter(ip_address=ip_address).delete()\n')
        new_lines.append(' ' * indent + 'device = await Device.objects.acreate(classroom=classroom, number=1, ip_address=ip_address, name="Test Device", active=True)\n')
        i += 1
        continue
    # We also need to ensure the ip_address variable is defined before this line.
    # We'll insert the ip_address generation before the device creation.
    # We'll look for the line that creates the device and insert before it.
    # We'll do it by checking if the next line is the device creation line.
    # We'll handle it by inserting before the line when we see the device creation line.
    # But we need to generate ip_address using unique_suffix.
    # We'll insert two lines before the device creation line.
    # We'll do it when we see the line that creates the device, we will have already inserted the ip_address lines earlier? Let's do a different approach: we will insert the ip_address generation lines after the classroom and teacher/student users are created, before the device creation.
    # We'll find the line after the student user creation.
    # For simplicity, we will insert the ip_address generation lines right before the device creation line, and we will also need to ensure the unique_suffix variable is in scope (it is).
    # We'll do it by checking if the line is the device creation line, and if we haven't yet inserted the ip_address lines, we insert them now.
    # We'll keep a flag.
    if line.strip().startswith('device = await Device.objects.acreate'):
        # Insert ip_address generation lines before this line
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + '# Generate unique IP based on unique_suffix to avoid collisions\n')
        new_lines.append(' ' * indent + 'ip_suffix = int(unique_suffix[:2], 16) % 256\n')
        new_lines.append(' ' * indent + 'ip_address = f"127.0.0.{ip_suffix}"\n')
        # Now add the device creation lines (we already handled the device creation line above? Actually we are in the if block, so we will not add the original line; we need to add our modified device creation lines)
        # We'll add the delete and create lines
        new_lines.append(' ' * indent + '# Remove any existing devices with this IP to avoid collisions\n')
        new_lines.append(' ' * indent + 'await Device.objects.filter(ip_address=ip_address).delete()\n')
        new_lines.append(' ' * indent + 'device = await Device.objects.acreate(classroom=classroom, number=1, ip_address=ip_address, name="Test Device", active=True)\n')
        # Skip the original line (we already added our version)
        i += 1
        continue
    new_lines.append(line)
    i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
