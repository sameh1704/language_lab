import sys

with open('lab/consumers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    if line.strip() == 'async def _tell_teacher(self, payload):':
        # We will look ahead to find the line that sets teacher_group
        # We'll add the print after the teacher_group line
        i += 1
        while i < len(lines):
            out.append(lines[i])
            if 'teacher_group =' in lines[i]:
                # Next line after this is the else line? Actually we want to insert after the else block? 
                # Simpler: insert after the line that contains 'teacher_group = f\"{TEACHER_GROUP_PREFIX}{classroom_id}\"' or the else line.
                # We'll just insert after the next line (which is the else line) and before the await.
                # But we need to know where the await line is.
                # Let's just insert after the line that contains 'teacher_group =' and before the line that contains 'await self.channel_layer.group_send'.
                # We'll continue to add lines until we see the await line, then insert our print before it.
                pass
            i += 1
        # This is getting messy.
        break
    i += 1

# Let's do a simpler approach: just replace the whole method with a new version.
# We'll replace from the line 'async def _tell_teacher(self, payload):' up to the line before the next method (which starts with 'async def ' or 'def ').
# We'll find the end index.
