"""التعامل مع أجهزة الطلاب: فحص الاتصال وحظر/فتح الجهاز عبر Veyon."""
import logging
import os
import shutil
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

_VEYON_CLI_PATH = None
_VEYON_CLI_LOCK = threading.Lock()
_LOCK_FEATURES_CACHE = None
_LOCK_FEATURES_CACHE_LOCK = threading.Lock()


def _get_veyon_cli_path():
    """الحصول على مسار veyon-cli مع تخزين مؤقت."""
    global _VEYON_CLI_PATH
    if _VEYON_CLI_PATH is not None:
        return _VEYON_CLI_PATH
    with _VEYON_CLI_LOCK:
        if _VEYON_CLI_PATH is not None:
            return _VEYON_CLI_PATH
        path = settings.VEYON_CLI
        if os.path.exists(path):
            _VEYON_CLI_PATH = path
        elif shutil.which(path):
            _VEYON_CLI_PATH = path
        else:
            _VEYON_CLI_PATH = ""
        return _VEYON_CLI_PATH


def cli_available():
    """هل veyon-cli موجود على جهاز المعلم؟ (None في الوضع التجريبي)"""
    if settings.LAB_SIMULATE:
        return None
    return bool(_get_veyon_cli_path())


def _run_veyon_cli(args, timeout=5):
    """تشغيل أمر veyon-cli وإرجاع (نجاح, مخرجات_قياسية, مخرجات_خطأ)."""
    cli = _get_veyon_cli_path()
    if not cli:
        return False, "", "veyon-cli غير موجود، راجع إعداد VEYON_CLI"
    cmd = [cli] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode == 0, proc.stdout, proc.stderr
    except FileNotFoundError:
        return False, "", "veyon-cli غير موجود، راجع VEYON_CLI"
    except subprocess.TimeoutExpired:
        return False, "", "انتهت المهلة أثناء تنفيذ أمر Veyon"
    except Exception as e:
        logger.exception("خطأ غير متوقع في veyon-cli")
        return False, "", f"خطأ غير متوقع: {e}"


def discover_lock_features(force_refresh=False):
    """اكتشاف ميزات القفل المتاحة من Veyon. يخزن النتيجة مؤقتًا."""
    global _LOCK_FEATURES_CACHE
    if settings.LAB_SIMULATE:
        return ["ScreenLock (محاكاة)"]
    with _LOCK_FEATURES_CACHE_LOCK:
        if _LOCK_FEATURES_CACHE is not None and not force_refresh:
            return _LOCK_FEATURES_CACHE
        ok, stdout, stderr = _run_veyon_cli(["feature", "list"], timeout=10)
        if not ok:
            logger.warning("فشل اكتشاف ميزات Veyon: %s", stderr)
            _LOCK_FEATURES_CACHE = ["ScreenLock"]
            return _LOCK_FEATURES_CACHE
        features = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                features.append(parts[0])
        lock_features = [f for f in features if "lock" in f.lower() or "screen" in f.lower()]
        if not lock_features:
            lock_features = ["ScreenLock"]
        _LOCK_FEATURES_CACHE = lock_features
        logger.info("ميزات القفل المكتشفة: %s", lock_features)
        return _LOCK_FEATURES_CACHE


def get_effective_lock_features():
    """الميزات الفعالة للقفل: من الإعدادات إن وُجدت، وإلا المكتشفة."""
    configured = [f.strip() for f in settings.VEYON_LOCK_FEATURES if f.strip()]
    if configured:
        return configured
    return discover_lock_features()


def check_online(device):
    """
    فحص اتصال حقيقي: يتحقق من استجابة Veyon عبر veyon-cli ping أو feature list على الجهاز البعيد.
    يسقط إلى فحص المنفذ إذا فشل veyon-cli.
    """
    if settings.LAB_SIMULATE:
        return device.number % 6 != 0
    if not device.ip_address:
        return False

    cli = _get_veyon_cli_path()
    if cli:
        ok, _, _ = _run_veyon_cli(["feature", "list", device.ip_address], timeout=2)
        if ok:
            return True

    try:
        with socket.create_connection(
            (device.ip_address, settings.VEYON_PORT), timeout=settings.LAB_CHECK_TIMEOUT
        ):
            return True
    except OSError:
        return False


def check_many(devices):
    """يفحص كل الأجهزة بالتوازي مع مهلة إجمالية لا تتجاوز ثانيتين لـ 40 جهازًا."""
    devices = list(devices)
    if not devices:
        return {}
    results = {}
    max_workers = min(40, len(devices))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_device = {pool.submit(check_online, d): d for d in devices}
        for future in as_completed(future_to_device, timeout=2.5):
            d = future_to_device[future]
            try:
                results[d.pk] = future.result()
            except Exception:
                results[d.pk] = False
    for d in devices:
        if d.pk not in results:
            results[d.pk] = False
    return results


def get_lock_state(device):
    """
    قراءة حالة القفل الفعلية من الجهاز البعيد.
    يرجع: (is_locked, error_message) حيث error_message فارغ عند النجاح.
    """
    if settings.LAB_SIMULATE:
        return device.is_blocked, ""
    if not device.ip_address:
        return False, "لا يوجد عنوان IP"

    features = get_effective_lock_features()
    for feature in features:
        ok, stdout, stderr = _run_veyon_cli(["feature", "status", device.ip_address, feature], timeout=3)
        if not ok:
            return False, f"فشل قراءة حالة {feature}: {stderr or stdout}"
        out = (stdout or "").strip().lower()
        if "on" in out or "active" in out or "running" in out or "true" in out:
            return True, ""
    return False, ""


def set_lock(device, lock):
    """
    يحظر الجهاز (lock=True) أو يفتحه (lock=False).
    يرجع (نجاح, رسالة_خطأ).
    """
    if settings.LAB_SIMULATE:
        return True, ""
    if not device.ip_address:
        return False, "لا يوجد عنوان IP"

    action = "start" if lock else "stop"
    features = get_effective_lock_features()
    errors = []

    for feature in features:
        ok, stdout, stderr = _run_veyon_cli(["feature", action, device.ip_address, feature], timeout=10)
        if not ok:
            err = (stderr or stdout or "فشل الأمر").strip()
            logger.warning("فشل %s ميزة %s على %s: %s", action, feature, device.ip_address, err)
            errors.append(f"{feature}: {err}")

    if errors:
        return False, "؛ ".join(errors)
    return True, ""


def sync_lock_states(devices):
    """
    مزامنة حالة القفل لكل الأجهزة مع الواقع.
    يحدث حقل is_blocked في قاعدة البيانات.
    يرجع عدد الأجهزة التي تم تحديثها.
    """
    if settings.LAB_SIMULATE:
        return 0
    devices = list(devices)
    if not devices:
        return 0
    updated = 0
    to_update = []
    for d in devices:
        if not d.ip_address:
            continue
        is_locked, err = get_lock_state(d)
        if err:
            logger.warning("تعذر قراءة حالة القفل للجهاز %s (%s): %s", d.number, d.ip_address, err)
            continue
        if d.is_blocked != is_locked:
            d.is_blocked = is_locked
            to_update.append(d)
    if to_update:
        Device = __import__("lab.models", fromlist=["Device"]).Device
        Device.objects.bulk_update(to_update, ["is_blocked"])
        updated = len(to_update)
        logger.info("تم مزامنة حالة القفل لـ %d جهاز", updated)
    return updated


class VeyonError(Exception):
    """استثناء موحد لأخطاء Veyon مع رسالة عربية."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def run_with_retry(device, action, feature, max_retries=2, base_timeout=5):
    """
    تنفيذ أمر Veyon مع إعادة محاولة.
    action: 'start' أو 'stop'
    """
    last_error = ""
    for attempt in range(max_retries + 1):
        timeout = base_timeout * (attempt + 1)
        ok, stdout, stderr = _run_veyon_cli(["feature", action, device.ip_address, feature], timeout=timeout)
        if ok:
            return True, ""
        last_error = (stderr or stdout or "فشل الأمر").strip()
        if attempt < max_retries:
            logger.info("إعادة محاولة %d/%d لـ %s على %s", attempt + 1, max_retries, feature, device.ip_address)
    return False, last_error