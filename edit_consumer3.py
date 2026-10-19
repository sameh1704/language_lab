import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == 'async def teacher_event(self, event):':
        # Look ahead for the line with await self.send_json(event["payload"])
        i += 1
        while i < len(lines):
            new_lines.append(lines[i])
            if 'await self.send_json(event["payload"])' in lines[i]:
                # Insert print before this line
                indent = len(lines[i]) - len(lines[i].lstrip())
                new_lines.append(' ' * indent + 'print(f"[DEBUG] TeacherConsumer.teacher_event: received event={event}")\n')
            i += 1
        break
    i += 1

if i < len(lines):
    new_lines.extend(lines[i:])

with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
