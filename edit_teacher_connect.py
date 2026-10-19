import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == 'async def connect(self):':
        # We will look for the line where self.teacher_group is set and add a print after it
        i += 1
        while i < len(lines):
            new_lines.append(lines[i])
            if 'self.teacher_group =' in lines[i]:
                # Insert print after this line
                indent = len(lines[i]) - len(lines[i].lstrip())
                new_lines.append(' ' * indent + 'print(f"[DEBUG] TeacherConsumer.connect: teacher_group={self.teacher_group}, classroom_id={self.classroom_id}")\n')
            i += 1
        break
    i += 1

if i < len(lines):
    new_lines.extend(lines[i:])

with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
