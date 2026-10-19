import django.db.models.deletion
from django.conf import settings

from django.db import migrations, models


class Migration(migrations.Migration):
    """Allow assistance requests from anonymous, device-identified students.

    The student page (``/student/``) is opened by a lab device without a login:
    its identity is the device itself, not an ``auth.User``. Making ``student``
    nullable lets such a request be recorded against its ``Device`` and
    ``Classroom`` without inventing a fake user or weakening the
    non-null ``classroom`` / ``device`` references.

    This is a non-destructive widening (DROP NOT NULL only); existing rows all
    already have a student, so no backfill is required and no data is removed.
    """

    dependencies = [
        ("lab", "0007_mediafolder_mediaasset_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assistancerequest",
            name="student",
            field=models.ForeignKey(
                blank=True,
                help_text="Null when the request comes from a device-identified student page (no login); the Device and Classroom are authoritative.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assistance_requests",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Student",
            ),
        ),
    ]
