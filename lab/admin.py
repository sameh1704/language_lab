from django.contrib import admin

from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "ip_address", "is_absent", "is_blocked")
    list_editable = ("ip_address",)
    ordering = ("number",)
