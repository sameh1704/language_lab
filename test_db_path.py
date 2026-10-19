import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from lab.models import School, Classroom, Device, Student
from django.contrib.auth import get_user_model

# Check if database file exists
import glob
for path in ['db.sqlite3', 'F:/ponix lab/language_lab/db.sqlite3']:
    if os.path.exists(path):
        print(f"Found database at: {path}")
        from django.db import connection
        print(f"Database connection: {connection.settings_dict['NAME']}")
        break
else:
    print("No database file found, will create new one")