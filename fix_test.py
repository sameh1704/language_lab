import re

with open('test_webrtc_signaling_fixed.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix test 2 assertion
content = re.sub(r'check\("Presence list has classroom_id", msg\.get\("classroom_id"\) == 1\)', 
                 r'check("Presence list has classroom_id", msg.get("classroom_id") == classroom.id)', content)

# Fix test 3: drain assistance_list after presence_list
# We'll replace the three lines: comment, msg line, check line
pattern = r'# Drain initial presence_list\s+msg = await teacher_comm2\.receive_json_from\(\)\s+check\("Teacher gets initial presence_list", msg\.get\("type"\) == "presence_list"\)'
replacement = '''# Drain initial presence_list
msg = await teacher_comm2.receive_json_from()
check("Teacher gets initial presence_list", msg.get("type") == "presence_list")
# Drain assistance_list (sent after presence_list on teacher connect)
assistance = await teacher_comm2.receive_json_from()
# Optionally verify it's an assistance list (could be empty)
# if assistance.get("type") != "assistance_list":
#     print(f"Warning: drained unexpected message: {assistance}")'''
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('test_webrtc_signaling_fixed.py', 'w', encoding='utf-8') as f:
    f.write(content)
