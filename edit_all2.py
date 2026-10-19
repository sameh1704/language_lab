import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Modification 1: TeacherConsumer.connect
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == 'async def connect(self):':
        # We'll look for the line that sets self.teacher_group
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

# Modification 2: StudentConsumer._tell_teacher
lines2 = []
for line in new_lines:
    if line.strip() == 'async def _tell_teacher(self, payload):':
        # We are now inside the method; we will look for the await line
        lines2.append(line)
        # We'll set a flag to indicate we are in this method
        in_method = True
        # We'll continue to add lines until we find the await line
    elif 'in_method' in locals() and in_method:
        # We are inside the method
        lines2.append(line)
        if 'await self.channel_layer.group_send' in line:
            # Insert print before this line
            indent = len(line) - len(line.lstrip())
            lines2.append(' ' * indent + 'print(f"[DEBUG] StudentConsumer._tell_teacher: sending to group {teacher_group}, payload={payload}")\n')
            in_method = False  # reset after inserting
    else:
        lines2.append(line)

# Write back
with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.writelines(lines2)
