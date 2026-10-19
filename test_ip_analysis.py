#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from lab.models import School, Classroom, Device

import uuid

# Test the IP address calculation from the test
unique_suffix = uuid.uuid4().hex[:8]
ip_suffix = int(unique_suffix[:2], 16) % 256
ip_address = f"127.0.0.{ip_suffix}"

print(f"unique_suffix: {unique_suffix}")
print(f"ip_suffix (int from first 2 hex chars): {ip_suffix}")
print(f"Calculated device IP: {ip_address}")
print(f"Hardcoded client IP in test: 127.0.0.1")
print(f"Match: {ip_address == '127.0.0.1'}")
print(f"Are they likely to match often? No, only when ip_suffix = 1")
print(f"Probability: 1/256 = {1/256:.2%}")