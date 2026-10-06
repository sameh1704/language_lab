from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Device(models.Model):
    """جهاز طالب في المعمل (رقم من 1 إلى 40)."""

    number = models.PositiveSmallIntegerField(
        "رقم الجهاز",
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(40)],
    )
    name = models.CharField("الاسم", max_length=60, blank=True)
    ip_address = models.GenericIPAddressField("عنوان IP", null=True, blank=True)
    is_absent = models.BooleanField("الطالب غائب", default=False)
    is_blocked = models.BooleanField("محظور (مقفول)", default=False)

    class Meta:
        ordering = ["number"]
        verbose_name = "جهاز"
        verbose_name_plural = "الأجهزة"

    def __str__(self):
        return f"جهاز {self.number}"
