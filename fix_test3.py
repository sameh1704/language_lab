import sys

with open('test_webrtc_signaling.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    # Fix test 2 assertion
    if 'check("Presence list has classroom_id", msg.get("classroom_id") == 1)' in line:
        # Keep indentation
        indent = len(line) - len(line.lstrip())
        newline = ' ' * indent + 'check("Presence list has classroom_id", msg.get("classroom_id") == classroom.id)\n'
        out.append(newline)
        i += 1
        continue
    # Fix test 3: after draining presence_list, drain assistance_list
    if line.strip() == '# Drain initial presence_list':
        # We are in test 3? We'll assume this is the one in test 3 (the other is in test 2 but we don't want to modify test 2)
        # We'll check ahead to see if we see '# Now connect student' before we see 'await teacher_comm2.disconnect()'
        # Look ahead up to 20 lines
        found_student = False
        found_disconnect = False
        for j in range(i+1, min(i+21, len(lines))):
            if '# Now connect student' in lines[j]:
                found_student = True
                break
            if 'await teacher_comm2.disconnect()' in lines[j]:
                found_disconnect = True
                break
        if found_student:
            # This is test 3
            out.append(line)  # keep the comment line
            i += 1
            # next line is the msg line
            if i < len(lines):
                out.append(lines[i])
                i += 1
            # next line is the check line
            if i < len(lines):
                out.append(lines[i])
                i += 1
            # Now insert after the check line: drain assistance_list
            # Use same indentation as the comment line
            indent = len(lines[i-3]) - len(lines[i-3].lstrip())  # Actually we lost original; let's compute from the comment line we just added
            # Better: we can get indent from the line we just added (the comment line) which is lines[i-3]? Actually we have just added the comment line, then msg line, then check line.
            # Let's compute indent from the comment line we added (which is out[-3])
            if len(out) >= 3:
                indent_line = out[-3]
                indent = len(indent_line) - len(indent_line.lstrip())
            else:
                indent = 0
            out.append(' ' * indent + '# Drain assistance_list (sent after presence_list on teacher connect)\n')
            out.append(' ' * indent + 'assistance = await teacher_comm2.receive_json_from()\n')
            out.append(' ' * indent + '# Optionally verify it\'s an assistance list (could be empty)\n')
            out.append(' ' * indent + '# if assistance.get("type") != "assistance_list":\n')
            out.append(' ' * indent + '    print(f"Warning: drained unexpected message: {assistance}")\n')
            continue
    out.append(line)
    i += 1

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(out)
