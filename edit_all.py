import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    stripped = line.strip()
    if stripped == 'async def connect(self):':
        # TeacherConsumer.connect
        # We need to find the line where self.teacher_group is set (after the if/else block)
        # We'll just add a print after the block that sets self.teacher_group.
        # We'll look ahead for the line that contains 'self.teacher_group =' and insert after it.
        i += 1
        while i < len(lines):
            new_lines.append(lines[i])
            if 'self.teacher_group =' in lines[i]:
                indent = len(lines[i]) - len(lines[i].lstrip())
                new_lines.append(' ' * indent + 'print(f"[DEBUG] TeacherConsumer.connect: teacher_group={self.teacher_group}, classroom_id={self.classroom_id}")\n')
            i += 1
        break
    i += 1

if i < len(lines):
    new_lines.extend(lines[i:])

# Now modify StudentConsumer._tell_teacher
lines2 = []
for line in new_lines:
    if line.strip() == 'async def _tell_teacher(self, payload):':
        lines2.append(line)
        # We will look for the await line and insert print before it
        # We'll set a flag to indicate we are inside this method
        pass
    else:
        lines2.append(line)

# Actually we need to do a stateful scan. Let's just do a second pass on new_lines.
# We'll do a simple approach: replace the await line with print + await.
# We'll do it on the whole text using regex but careful.
# Let's just write the lines back to a string and do a regex replacement.

import re
text = ''.join(new_lines)
# Replace await self.channel_layer.group_send(teacher_group, {"type": "teacher_event", "payload": payload})
# with print + await
# We need to capture the indentation.
def repl(m):
    # m.group(0) is the whole match
    # We want to keep the indentation of the line
    line = m.group(0)
    indent = len(line) - len(line.lstrip())
    return line[:-1] + '\\n' + ' ' * indent + 'print(f"[DEBUG] StudentConsumer._tell_teacher: sending to group {teacher_group}, payload={payload}")\\n' + line
# But easier: we just add a print line before the match.
# We'll use a lookbehind? Not needed.
# We'll do: replace the pattern with '\\n' + indent + print + '\\n' + match
# Let's do a substitution that inserts before the match.
# We'll use re.sub with a function that returns the insertion + match.
def repl2(m):
    match = m.group(0)
    indent = len(match) - len(match.lstrip())
    return ' ' * indent + 'print(f"[DEBUG] StudentConsumer._tell_teacher: sending to group {teacher_group}, payload={payload}")\\n' + match
text = re.sub(r'(\s*)await self\.channel_layer\.group_send\(teacher_group, \{"type": "teacher_event", "payload": payload\}\)', repl2, text)
# Now modify teacher_event: add print at start of method
# We'll replace 'async def teacher_event(self, event):' with itself plus a print line after it.
def repl3(m):
    match = m.group(0)
    indent = len(match) - len(match.lstrip())
    return match + '\\n' + ' ' * indent + 'print(f"[DEBUG] TeacherConsumer.teacher_event: received event={event}")'
text = re.sub(r'async def teacher_event\(self, event\):', repl3, text)

with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.write(text)
