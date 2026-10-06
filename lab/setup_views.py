"""صفحة إعداد الاتصال (للمعلم) وصفحة الطالب."""
import ipaddress
import json
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import pairing, presence, veyon
from .access import lan_ips, normalize_ip
from .models import Device

HINTS = {
    "no_ip": "لا يوجد عنوان IP: اكتبه هنا أو استخدم وضع الربط.",
    "veyon_down": "Veyon لا يستجيب على المنفذ %d: الجهاز مغلق، أو خدمة Veyon متوقفة، أو الجدار الناري يمنع الاتصال.",
    "page_missing": "Veyon يعمل. افتح صفحة الطالب على هذا الجهاز لتفعيل الصوت.",
    "page_only": "صفحة الطالب تعمل لكن Veyon لا يستجيب، فلن يعمل الحظر على هذا الجهاز.",
    "ready": "جاهز",
}


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
        return body if isinstance(body, dict) else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- المعلم


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
        hint = HINTS[state] % settings.VEYON_PORT if state == "veyon_down" else HINTS[state]
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
        return JsonResponse({"error": "رقم الجهاز غير صالح"}, status=400)
    device = Device.objects.filter(number=number).first()
    if device is None:
        return JsonResponse({"error": "الجهاز غير موجود"}, status=404)

    ip = str(body.get("ip") or "").strip()
    if ip:
        try:
            ip = str(ipaddress.IPv4Address(ip))
        except ValueError:
            return JsonResponse({"error": "عنوان IP غير صالح"}, status=400)
        clash = Device.objects.filter(ip_address=ip).exclude(pk=device.pk).first()
        if clash:
            return JsonResponse({"error": f"العنوان مستخدم في جهاز {clash.number}"}, status=400)
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
        return JsonResponse({"error": "رقم البداية غير صالح"}, status=400)
    if not re.fullmatch(r"(\d{1,3}\.){3}", prefix) or any(int(x) > 255 for x in prefix.split(".")[:3]):
        return JsonResponse({"error": "البداية يجب أن تكون مثل 192.168.1."}, status=400)

    devices = list(Device.objects.all())
    if start < 1 or start + len(devices) - 1 > 254:
        return JsonResponse({"error": "النطاق يتجاوز 254"}, status=400)
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


# ---------------------------------------------------------------- الطالب


def _client_ip(request):
    return normalize_ip(request.META.get("REMOTE_ADDR", ""))


@ensure_csrf_cookie
def student_page(request):
    ip = _client_ip(request)
    device = Device.objects.filter(ip_address=ip).first()
    left = pairing.seconds_left()
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
        return JsonResponse({"error": "وضع الربط غير مفعّل. اطلب من المعلم تفعيله."}, status=403)
    try:
        number = int(_json_body(request).get("number"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "رقم الجهاز غير صالح"}, status=400)
    device = Device.objects.filter(number=number).first()
    if device is None:
        return JsonResponse({"error": "الجهاز غير موجود"}, status=404)

    ip = _client_ip(request)
    Device.objects.filter(ip_address=ip).exclude(pk=device.pk).update(ip_address=None)
    device.ip_address = ip
    device.save(update_fields=["ip_address"])
    return JsonResponse({"ok": True})
