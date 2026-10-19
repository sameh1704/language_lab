import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from lab.models import School, Classroom, Device

# Run a quick test to see what IP address is being used
import uuid
unique_suffix = uuid.uuid4().hex[:8]
school = School.objects.create(name=f"Test School {unique_suffix}", code=f"TS{unique_suffix[:4]}", active=True)
classroom = Classroom.objects.create(school=school, name="Lab A", code=f"LAB-TEST-{unique_suffix[:4]}", capacity=40, active=True)

ip_suffix = int(unique_suffix[:2], 16) % 256
ip_address = f"127.0.0.{ip_suffix}"
print(f"Device IP address: {ip_address}")
print(f"Expected client IP: 127.0.0.1")
print(f"Match: {ip_address == '127.0.0.1'}")