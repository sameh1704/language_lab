"""التعامل مع أجهزة الطلاب: فحص الاتصال وحظر/فتح الجهاز عبر Veyon."""
import os
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings


def check_online(device):
    """الجهاز يعتبر متصلاً إذا كانت خدمة Veyon تستجيب على منفذها."""
    if settings.LAB_SIMULATE:
        # وضع تجريبي: الأجهزة 6 و12 و18 ... تظهر غير متصلة
        return device.number % 6 != 0
    if not device.ip_address:
        return False
    try:
        with socket.create_connection(
            (device.ip_address, settings.VEYON_PORT), timeout=settings.LAB_CHECK_TIMEOUT
        ):
            return True
    except OSError:
        return False


def cli_available():
    """هل veyon-cli موجود على جهاز المعلم؟ (None في الوضع التجريبي)"""
    if settings.LAB_SIMULATE:
        return None
    return bool(shutil.which(settings.VEYON_CLI) or os.path.exists(settings.VEYON_CLI))


def check_many(devices):
    """يفحص كل الأجهزة بالتوازي ويرجع {pk: True/False}."""
    devices = list(devices)
    if not devices:
        return {}
    with ThreadPoolExecutor(max_workers=40) as pool:
        results = list(pool.map(check_online, devices))
    return {d.pk: ok for d, ok in zip(devices, results)}


def set_lock(device, lock):
    """يحظر الجهاز (lock=True) أو يفتحه (lock=False). يرجع (نجاح, رسالة_خطأ)."""
    if settings.LAB_SIMULATE:
        return True, ""
    if not device.ip_address:
        return False, "لا يوجد عنوان IP"
    action = "start" if lock else "stop"
    for feature in settings.VEYON_LOCK_FEATURES:
        cmd = [settings.VEYON_CLI, "feature", action, device.ip_address, feature]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            return False, "veyon-cli غير موجود، راجع VEYON_CLI"
        except subprocess.TimeoutExpired:
            return False, "انتهت المهلة"
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout).strip() or "فشل الأمر"
    return True, ""
