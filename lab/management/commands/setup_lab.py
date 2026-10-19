from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _

from lab.models import Device, School, Classroom


class Command(BaseCommand):
    help = _("Creates lab devices numbered 1 to 40 with sequential IP addresses")

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=40, help=_("Number of devices (up to 40)"))
        parser.add_argument("--ip-prefix", default="192.168.1.", help=_("IP prefix like 192.168.1."))
        parser.add_argument("--ip-start", type=int, default=101, help=_("Last octet of IP for device 1"))
        parser.add_argument("--classroom-code", default="LAB-A", help=_("Classroom code (will be created if not exists)"))
        parser.add_argument("--school-code", default="LLS", help=_("School code"))

    def handle(self, *args, **opts):
        count = opts["count"]
        prefix = opts["ip_prefix"]
        start = opts["ip_start"]
        classroom_code = opts["classroom_code"]
        school_code = opts["school_code"]

        if not 1 <= count <= 40:
            raise CommandError(_("Count must be between 1 and 40"))
        if start + count - 1 > 254:
            raise CommandError(_("IP range exceeds 254, reduce --ip-start"))

        # Get or create school
        school, _ = School.objects.get_or_create(
            code=school_code,
            defaults={"name": _("Language Lab School"), "active": True},
        )

        # Get or create classroom
        classroom, _ = Classroom.objects.get_or_create(
            code=classroom_code,
            defaults={
                "school": school,
                "name": f"{_('Language Lab')} {classroom_code[-1] if classroom_code else 'A'}",
                "capacity": 40,
                "active": True,
            },
        )

        created = 0
        for n in range(1, count + 1):
            _, was_created = Device.objects.get_or_create(
                classroom=classroom,
                number=n,
                defaults={"name": f"{_('Device')} {n}", "ip_address": f"{prefix}{start + n - 1}"},
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                _("%(count)d devices created in classroom %(classroom)s (existing unchanged)") % {"count": created, "classroom": classroom.name}
            )
        )