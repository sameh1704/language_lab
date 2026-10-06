from django.core.management.base import BaseCommand, CommandError

from lab.models import Device


class Command(BaseCommand):
    help = "ينشئ أجهزة المعمل المرقمة من 1 إلى 40 مع عناوين IP متتالية"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=40, help="عدد الأجهزة (حتى 40)")
        parser.add_argument("--ip-prefix", default="192.168.1.", help="بداية عنوان IP مثل 192.168.1.")
        parser.add_argument("--ip-start", type=int, default=101, help="آخر رقم في IP للجهاز 1")

    def handle(self, *args, **opts):
        count, prefix, start = opts["count"], opts["ip_prefix"], opts["ip_start"]
        if not 1 <= count <= 40:
            raise CommandError("العدد يجب أن يكون بين 1 و40")
        if start + count - 1 > 254:
            raise CommandError("نطاق عناوين IP يتجاوز 254، قلّل --ip-start")

        created = 0
        for n in range(1, count + 1):
            _, was_created = Device.objects.get_or_create(
                number=n,
                defaults={"name": f"جهاز {n}", "ip_address": f"{prefix}{start + n - 1}"},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"تم إنشاء {created} جهاز (الموجود مسبقًا لم يُعدَّل)"))
