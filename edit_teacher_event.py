import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == 'async def teacher_event(self, event):':
        # Insert print after this line
        indent = len(line) - len(line.lstrip())
        new_lines.append(' ' * indent + 'print(f"[DEBUG] TeacherConsumer.teacher_event: received event={event}")\n')
    i += 1

with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
