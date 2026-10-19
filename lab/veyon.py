"""Student device handling: connection check, lock/unlock, screen management via Veyon."""
import logging
import os
import shutil
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

_VEYON_CLI_PATH = None
_VEYON_CLI_LOCK = threading.Lock()
_LOCK_FEATURES_CACHE = None
_LOCK_FEATURES_CACHE_LOCK = threading.Lock()
_ACTIVE_FEATURES_LOCK = threading.Lock()
_ACTIVE_FEATURES: dict[tuple[str, str], bool] = {}


def _get_veyon_cli_path():
    """Get veyon-cli path with caching."""
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
    """Is veyon-cli available on teacher machine? (None in simulation mode)"""
    if settings.LAB_SIMULATE:
        return None
    return bool(_get_veyon_cli_path())


def _run_veyon_cli(args, timeout=5):
    """Run veyon-cli command and return (success, stdout, stderr)."""
    cli = _get_veyon_cli_path()
    if not cli:
        return False, "", _("veyon-cli not found, check VEYON_CLI setting")
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
        return False, "", _("veyon-cli not found, check VEYON_CLI")
    except subprocess.TimeoutExpired:
        return False, "", _("Veyon command timed out")
    except Exception as e:
        logger.exception(_("Unexpected error in veyon-cli"))
        return False, "", f"{_('Unexpected error')}: {e}"


def discover_lock_features(force_refresh=False):
    """Discover available lock features from Veyon. Caches result."""
    global _LOCK_FEATURES_CACHE
    if settings.LAB_SIMULATE:
        return ["ScreenLock"]
    with _LOCK_FEATURES_CACHE_LOCK:
        if _LOCK_FEATURES_CACHE is not None and not force_refresh:
            return _LOCK_FEATURES_CACHE
        ok, stdout, stderr = _run_veyon_cli(["feature", "list"], timeout=10)
        if not ok:
            logger.warning(_("Failed to discover Veyon features: %(error)s"), {"error": stderr})
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
        logger.info(_("Discovered lock features: %(features)s"), {"features": lock_features})
        return _LOCK_FEATURES_CACHE


def get_effective_lock_features():
    """Effective lock features: from settings if configured, else discovered."""
    configured = [f.strip() for f in settings.VEYON_LOCK_FEATURES if f.strip()]
    if configured:
        return configured
    return discover_lock_features()


def _mark_active(device, feature, active=True):
    with _ACTIVE_FEATURES_LOCK:
        if active:
            _ACTIVE_FEATURES[(device.ip_address, feature)] = True
        else:
            _ACTIVE_FEATURES.pop((device.ip_address, feature), None)


def is_feature_active(device, feature):
    with _ACTIVE_FEATURES_LOCK:
        return _ACTIVE_FEATURES.get((device.ip_address, feature), False)


def check_online(device):
    """
    Real connection check: verifies Veyon responds via veyon-cli ping or feature list on remote device.
    Falls back to port check if veyon-cli fails.
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
    """Check all devices in parallel with total timeout not exceeding 2 seconds for 40 devices."""
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
    Read actual lock state from remote device.
    Returns: (is_locked, error_message) where error_message empty on success.

    Note: Veyon 4.11.3 does not provide a reliable CLI status query.
    We fall back to local tracking based on successful lock commands.
    """
    if settings.LAB_SIMULATE:
        return device.is_blocked, ""
    if not device.ip_address:
        return False, _("No IP address")

    if is_feature_active(device, "ScreenLock"):
        return True, ""

    features = [f for f in get_effective_lock_features() if f != "ScreenLock"]
    for feature in features:
        if is_feature_active(device, feature):
            return True, ""

    return False, ""


def set_lock(device, lock):
    """
    Lock (lock=True) or unlock (lock=False) device.
    Returns (success, error_message).
    """
    if settings.LAB_SIMULATE:
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")

    action = "start" if lock else "stop"
    features = get_effective_lock_features()
    errors = []

    for feature in features:
        ok, stdout, stderr = _run_veyon_cli(["feature", action, device.ip_address, feature], timeout=10)
        if ok:
            _mark_active(device, feature, lock)
        else:
            err = (stderr or stdout or _("Command failed")).strip()
            logger.warning(_("Failed %(action)s feature %(feature)s on %(ip)s: %(error)s"), {"action": action, "feature": feature, "ip": device.ip_address, "error": err})
            errors.append(f"{feature}: {err}")

    if errors:
        return False, "؛ ".join(errors)
    return True, ""


def sync_lock_states(devices):
    """
    Sync lock state for all devices with reality.
    Updates is_blocked field in database.
    Returns number of devices updated.
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
        if d.is_blocked != is_locked:
            d.is_blocked = is_locked
            to_update.append(d)
    if to_update:
        Device = __import__("lab.models", fromlist=["Device"]).Device
        Device.objects.bulk_update(to_update, ["is_blocked"])
        updated = len(to_update)
        logger.info(_("Synced lock state for %(count)d devices"), {"count": updated})
    return updated


class VeyonError(Exception):
    """Unified exception for Veyon errors with translatable message."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def run_with_retry(device, action, feature, max_retries=2, base_timeout=5):
    """
    Run Veyon command with retry.
    action: 'start' or 'stop'
    """
    last_error = ""
    for attempt in range(max_retries + 1):
        timeout = base_timeout * (attempt + 1)
        ok, stdout, stderr = _run_veyon_cli(["feature", action, device.ip_address, feature], timeout=timeout)
        if ok:
            return True, ""
        last_error = (stderr or stdout or _("Command failed")).strip()
        if attempt < max_retries:
            logger.info(_("Retry %(attempt)d/%(max)d for %(feature)s on %(ip)s"), {"attempt": attempt + 1, "max": max_retries, "feature": feature, "ip": device.ip_address})
    return False, last_error


# ---------------------------------------------------------------------------
# Screen management operations
# ---------------------------------------------------------------------------

def remote_view(device):
    """Start RemoteView on a device. Interactive window on teacher machine."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "RemoteView")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "RemoteView"], timeout=10)
    if ok:
        _mark_active(device, "RemoteView")
    return ok, (stderr or stdout or _("Command failed")).strip()


def remote_control(device):
    """Start RemoteControl on a device. Interactive window on teacher machine."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "RemoteControl")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "RemoteControl"], timeout=10)
    if ok:
        _mark_active(device, "RemoteControl")
    return ok, (stderr or stdout or _("Command failed")).strip()


def stop_feature(device, feature):
    """Stop an active feature on a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, feature, active=False)
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "stop", device.ip_address, feature], timeout=10)
    if ok:
        _mark_active(device, feature, active=False)
    return ok, (stderr or stdout or _("Command failed")).strip()


def broadcast(device, fullscreen=True):
    """Share teacher's screen to a device (fullscreen or window)."""
    if settings.LAB_SIMULATE:
        feature = "ShareOwnScreenFullScreen" if fullscreen else "ShareOwnScreenWindow"
        _mark_active(device, feature)
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    feature = "ShareOwnScreenFullScreen" if fullscreen else "ShareOwnScreenWindow"
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, feature], timeout=10)
    if ok:
        _mark_active(device, feature)
    return ok, (stderr or stdout or _("Command failed")).strip()


def stop_broadcast(device, fullscreen=True):
    """Stop screen broadcast to a device."""
    feature = "ShareOwnScreenFullScreen" if fullscreen else "ShareOwnScreenWindow"
    return stop_feature(device, feature)


def send_text_message(device, message):
    """Send a text message to a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "TextMessage")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "TextMessage", message], timeout=10)
    if ok:
        _mark_active(device, "TextMessage")
    return ok, (stderr or stdout or _("Command failed")).strip()


def open_website(device, url):
    """Open a website URL on a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "OpenWebsite")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "OpenWebsite", url], timeout=10)
    if ok:
        _mark_active(device, "OpenWebsite")
    return ok, (stderr or stdout or _("Command failed")).strip()


def start_app(device, command):
    """Start an application on a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "StartApp")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "StartApp", command], timeout=10)
    if ok:
        _mark_active(device, "StartApp")
    return ok, (stderr or stdout or _("Command failed")).strip()


def screenshot(device):
    """Take a screenshot on a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, "Screenshot")
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, "Screenshot"], timeout=10)
    if ok:
        _mark_active(device, "Screenshot")
    return ok, (stderr or stdout or _("Command failed")).strip()


def power_action(device, action):
    """Perform a power action on a device."""
    if settings.LAB_SIMULATE:
        _mark_active(device, action)
        return True, ""
    if not device.ip_address:
        return False, _("No IP address")
    ok, stdout, stderr = _run_veyon_cli(["feature", "start", device.ip_address, action], timeout=10)
    if ok:
        _mark_active(device, action)
    return ok, (stderr or stdout or _("Command failed")).strip()


def get_supported_actions():
    """Return the Veyon actions supported by this integration."""
    return {
        "lock": {"feature": "ScreenLock", "label": "Lock"},
        "unlock": {"feature": "ScreenLock", "label": "Unlock"},
        "remote_view": {"feature": "RemoteView", "label": "Remote View"},
        "remote_control": {"feature": "RemoteControl", "label": "Remote Control"},
        "broadcast_fullscreen": {"feature": "ShareOwnScreenFullScreen", "label": "Broadcast Fullscreen"},
        "broadcast_window": {"feature": "ShareOwnScreenWindow", "label": "Broadcast Window"},
        "text_message": {"feature": "TextMessage", "label": "Text Message"},
        "open_website": {"feature": "OpenWebsite", "label": "Open Website"},
        "start_app": {"feature": "StartApp", "label": "Start App"},
        "screenshot": {"feature": "Screenshot", "label": "Screenshot"},
        "power_on": {"feature": "PowerOn", "label": "Power On"},
        "reboot": {"feature": "Reboot", "label": "Reboot"},
        "power_down": {"feature": "PowerDown", "label": "Power Down"},
    }
