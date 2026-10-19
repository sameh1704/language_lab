import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labsys.settings')
import django
django.setup()

from lab import veyon
from lab.models import Device

# Test Veyon simulation mode
print('LAB_SIMULATE env:', os.environ.get('LAB_SIMULATE', 'not set'))
from django.conf import settings
print('LAB_SIMULATE setting:', settings.LAB_SIMULATE)

# Test check_online in simulation
for i in range(1, 13):
    d = Device(number=i)
    online = veyon.check_online(d)
    print(f'Device {i}: online={online}')

# Test cli_available in simulation
print('CLI available (sim):', veyon.cli_available())

# Test discover_lock_features in simulation
features = veyon.discover_lock_features()
print('Lock features (sim):', features)

# Test set_lock in simulation
d = Device(number=1, ip_address='192.168.1.101')
ok, err = veyon.set_lock(d, True)
print(f'Set lock (sim): ok={ok}, err="{err}"')

# Test get_lock_state in simulation
locked, err = veyon.get_lock_state(d)
print(f'Get lock state (sim): locked={locked}, err="{err}"')