import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from lab.models import School, Classroom, Device, Student
from django.contrib.auth import get_user_model

import uuid

# Replicate the test setup
unique_suffix = uuid.uuid4().hex[:8]
school = School.objects.create(name=f"Test School {unique_suffix}", code=f"TS{unique_suffix[:4]}", active=True)
classroom = Classroom.objects.create(school=school, name="Lab A", code=f"LAB-TEST-{unique_suffix[:4]}", capacity=40, active=True)

ip_suffix = int(unique_suffix[:2], 16) % 256
ip_address = f"127.0.0.{ip_suffix}"

print(f"Device IP: {ip_address}")
print(f"Device classroom_id: {classroom.id}")

from lab.access import is_teacher_machine, normalize_ip

# Test the teacher machine check
print(f"\nTesting is_teacher_machine for 127.0.0.1: {is_teacher_machine('127.0.0.1')}")
print(f"Testing is_teacher_machine for {ip_address}: {is_teacher_machine(ip_address)}")

# Test normalize_ip
print(f"\nTesting normalize_ip:")
print(f"normalize_ip('127.0.0.1'): {normalize_ip('127.0.0.1')}")
print(f"normalize_ip('127.0.0.{ip_suffix}'): {normalize_ip(ip_address)}")