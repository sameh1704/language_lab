import sys

lines = []
with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line index for '# Drain initial presence_list' in test 3 section.
# We'll search for it after we have passed test 2.
# Simpler: find all occurrences and pick the one that is in test 3 by checking context.
# We'll just find the first occurrence and hope it's the one in test 3? There are two.
# Let's find the occurrence that is followed by 'check("Teacher gets initial presence_list", ...)' and then later by '# Now connect student'.
for i in range(len(lines)):
    if lines[i].strip() == '# Drain initial presence_list':
        # Check if next line contains 'msg = await teacher_comm2.receive_json_from()'
        if i+1 < len(lines) and 'msg = await teacher_comm2.receive_json_from()' in lines[i+1]:
            # Check if the line after that contains the check
            if i+2 < len(lines) and 'check("Teacher gets initial presence_list", msg.get("type") == "presence_list")' in lines[i+2]:
                # We found the target in test 3? We need to ensure it's not the one in test 2.
                # Look ahead a few lines to see if we see '# Now connect student' before we see 'await teacher_comm2.disconnect()' (test 2 disconnect)
                # We'll search ahead up to 20 lines for either pattern.
                found = False
                for j in range(i+3, min(i+23, len(lines))):
                    if '# Now connect student' in lines[j]:
                        found = True
                        break
                    if 'await teacher_comm2.disconnect()' in lines[j] and j < i+20:
                        # This is likely test 2 disconnect
                        break
                if found:
                    # This is the one in test 3.
                    # Indentation of the first line
                    indent = len(lines[i]) - len(lines[i].lstrip())
                    # Build new lines to insert after the check line (i+2)
                    new_lines = [
                        lines[i],  # comment
                        lines[i+1], # msg line
                        lines[i+2], # check line
                        ' ' * indent + '# Drain assistance_list (sent after presence_list on teacher connect)\n',
                        ' ' * indent + 'assistance = await teacher_comm2.receive_json_from()\n',
                        ' ' * indent + '# Optionally verify it\'s an assistance list (could be empty)\n',
                        ' ' * indent + '# if assistance.get("type") != "assistance_list":\n',
                        ' ' * indent + '    print(f"Warning: drained unexpected message: {assistance}")\n'
                    ]
                    # Replace lines[i] through lines[i+2] with new_lines, and keep the rest.
                    lines = lines[:i] + new_lines + lines[i+3:]
                    break

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
