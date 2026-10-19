"""Setup page (teacher) and student page."""
import ipaddress
import json
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import pairing, presence, veyon
from .access import lan_ips, normalize_ip
from .models import Device


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
        return body if isinstance(body, dict) else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- Teacher


@login_required
@ensure_csrf_cookie
def setup_page(request):
    return render(request, "lab/setup.html", {"simulate": settings.LAB_SIMULATE})


@login_required
@require_GET
def api_setup_status(request):
    devices = list(Device.objects.all())
    veyon_map = veyon.check_many(devices)
    present = presence.online_numbers()

    rows = []
    for d in devices:
        v, p = veyon_map[d.pk], d.number in present
        if not d.ip_address:
            state = "no_ip"
        elif p and not v:
            state = "page_only"
        elif not v:
            state = "veyon_down"
        elif not p:
            state = "page_missing"
        else:
            state = "ready"

        hints = {
            "no_ip": _("No IP address: enter it here or use pairing mode."),
            "veyon_down": _("Veyon not responding on port %(port)d: device off, Veyon service stopped, or firewall blocking.") % {"port": settings.VEYON_PORT},
            "page_missing": _("Veyon works. Open student page on this device to enable audio."),
            "page_only": _("Student page works but Veyon not responding, so lock won't work on this device."),
            "ready": _("Ready"),
        }
        hint = hints[state]
        rows.append(
            {
                "number": d.number,
                "ip": d.ip_address or "",
                "veyon": v,
                "page": p,
                "state": state,
                "hint": hint,
            }
        )

    host = request.get_host().split(":")[0]
    return JsonResponse(
        {
            "teacher": {
                "lan_ips": lan_ips(),
                "secure_origin": host in ("localhost", "127.0.0.1"),
                "veyon_cli": veyon.cli_available(),
                "veyon_cli_path": settings.VEYON_CLI,
                "veyon_port": settings.VEYON_PORT,
                "simulate": settings.LAB_SIMULATE,
            },
            "pairing_left": pairing.seconds_left(),
            "devices": rows,
        }
    )


@login_required
@require_POST
def api_setup_ip(request):
    body = _json_body(request)
    try:
        number = int(body.get("number"))
    except (TypeError, ValueError):
        return JsonResponse({"error": _("Invalid device number")}, status=400)
    device = Device.objects.filter(number=number).first()
    if device is None:
        return JsonResponse({"error": _("Device not found")}, status=404)

    ip = str(body.get("ip") or "").strip()
    if ip:
        try:
            ip = str(ipaddress.IPv4Address(ip))
        except ValueError:
            return JsonResponse({"error": _("Invalid IP address")}, status=400)
        clash = Device.objects.filter(ip_address=ip).exclude(pk=device.pk).first()
        if clash:
            return JsonResponse({"error": _("IP address already used by device %(number)d") % {"number": clash.number}}, status=400)
    device.ip_address = ip or None
    device.save(update_fields=["ip_address"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_setup_fill(request):
    body = _json_body(request)
    prefix = str(body.get("prefix") or "")
    try:
        start = int(body.get("start"))
    except (TypeError, ValueError):
        return JsonResponse({"error": _("Invalid start number")}, status=400)
    if not re.fullmatch(r"(\d{1,3}\.){3}", prefix) or any(int(x) > 255 for x in prefix.split(".")[:3]):
        return JsonResponse({"error": _("Prefix must be like 192.168.1.")}, status=400)

    devices = list(Device.objects.all())
    if start < 1 or start + len(devices) - 1 > 254:
        return JsonResponse({"error": _("Range exceeds 254")}, status=400)
    for i, d in enumerate(devices):
        d.ip_address = f"{prefix}{start + i}"
    Device.objects.bulk_update(devices, ["ip_address"])
    return JsonResponse({"ok": True, "count": len(devices)})


@login_required
@require_POST
def api_setup_pairing(request):
    body = _json_body(request)
    if body.get("on"):
        pairing.start(10)
    else:
        pairing.stop()
    return JsonResponse({"pairing_left": pairing.seconds_left()})


@login_required
@require_http_methods(["GET", "POST"])
def api_setup_lock_features(request):
    if request.method == "GET":
        discovered = veyon.discover_lock_features()
        effective = veyon.get_effective_lock_features()
        return JsonResponse(
            {
                "discovered": discovered,
                "effective": effective,
                "configured": [f.strip() for f in settings.VEYON_LOCK_FEATURES if f.strip()],
                "simulate": settings.LAB_SIMULATE,
            }
        )

    body = _json_body(request)
    features = body.get("features", [])
    if not isinstance(features, list):
        return JsonResponse({"error": _("Invalid features format")}, status=400)
    cleaned = [str(f).strip() for f in features if str(f).strip()]
    request.session["veyon_lock_features"] = cleaned
    return JsonResponse({"ok": True, "effective": cleaned})


@login_required
@require_POST
def api_setup_test_lock(request):
    """Test lock on a single device."""
    body = _json_body(request)
    try:
        number = int(body.get("number"))
    except (TypeError, ValueError):
        return JsonResponse({"error": _("Invalid device number")}, status=400)
    device = Device.objects.filter(number=number).first()
    if device is None:
        return JsonResponse({"error": _("Device not found")}, status=404)
    if not device.ip_address:
        return JsonResponse({"error": _("Device has no IP address")}, status=400)

    action = body.get("action", "lock")
    if action not in ("lock", "unlock"):
        return JsonResponse({"error": _("Action must be lock or unlock")}, status=400)

    lock = action == "lock"
    ok, error = veyon.set_lock(device, lock)
    if ok:
        device.is_blocked = lock
        device.save(update_fields=["is_blocked"])
        return JsonResponse({"ok": True, "message": _("Device %(action)s successfully") % {"action": _("locked") if lock else _("unlocked")}})
    return JsonResponse({"ok": False, "error": error}, status=400)


@login_required
@require_POST
def api_setup_refresh_lock_states(request):
    """Sync lock state for all devices with reality."""
    devices = list(Device.objects.all())
    count = veyon.sync_lock_states(devices)
    return JsonResponse({"ok": True, "synced": count})


# ---------------------------------------------------------------- Student


def _client_ip(request):
    return normalize_ip(request.META.get("REMOTE_ADDR", ""))


@ensure_csrf_cookie
def student_page(request):
    ip = _client_ip(request)
    device = Device.objects.filter(ip_address=ip).first()
    left = pairing.seconds_left()

    # Issue the device credential for the anonymous student page.
    #
    # The student page has no login: its identity is the lab *device* itself.
    # We hand the device's own ``device_uuid`` (a server-generated, unique,
    # unguessable UUIDv4) to the browser in two ways, both derived from the
    # device whose registered IP is making this request:
    #
    #   * the session, so an HTTP caller must present the same value back, and
    #   * the WebSocket ``hello`` message, which the page already consumes.
    #
    # The IP is used only to *issue* the secret. Authorization on
    # ``/api/assistance/create/`` is by possession of the secret, never by the
    # IP and never by a client-supplied device identifier.
    request.session["student_device_uuid"] = str(device.device_uuid) if device else None

    return render(
        request,
        "lab/student.html",
        {
            "device": device,
            "ip": ip,
            "pairing": left > 0,
            "numbers": list(Device.objects.values_list("number", flat=True)) if left else [],
        },
    )


@require_POST
def student_pair(request):
    if not pairing.seconds_left():
        return JsonResponse({"error": _("Pairing mode not enabled. Ask teacher to enable it.")}, status=403)
    try:
        number = int(_json_body(request).get("number"))
    except (TypeError, ValueError):
        return JsonResponse({"error": _("Invalid device number")}, status=400)
    device = Device.objects.filter(number=number).first()
    if device is None:
        return JsonResponse({"error": _("Device not found")}, status=404)

    ip = _client_ip(request)
    Device.objects.filter(ip_address=ip).exclude(pk=device.pk).update(ip_address=None)
    device.ip_address = ip
    device.save(update_fields=["ip_address"])
    return JsonResponse({"ok": True})