import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Modify _tell_teacher
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    if line.strip() == 'async def _tell_teacher(self, payload):':
        # We will look for the line with 'await self.channel_layer.group_send' and insert print before it
        i += 1
        while i < len(lines):
            new_lines.append(lines[i])
            if 'await self.channel_layer.group_send' in lines[i]:
                # Insert print before this line
                indent = len(lines[i]) - len(lines[i].lstrip())
                new_lines.append(' ' * indent + 'print(f"[DEBUG] StudentConsumer._tell_teacher: sending to group {teacher_group}, payload={payload}")\n')
            i += 1
        break
    i += 1

# If we broke out early, we need to add the remaining lines
if i < len(lines):
    new_lines.extend(lines[i:])

# Now modify teacher_event
lines2 = []
for line in new_lines:
    if line.strip() == 'async def teacher_event(self, event):':
        lines2.append(line)
        # Find the line with 'await self.send_json(event["payload"])'
        # We'll just add print before the next line that contains that
        # We'll continue to add lines until we see it
    else:
        lines2.append(line)
        # We'll do a separate pass
# Let's do a simpler approach: just replace the line directly using regex on the whole text.
# We'll write the modified lines back to a string and then do a regex replacement for teacher_event.

with open('lab/consumers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
