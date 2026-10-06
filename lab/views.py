import json
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import veyon
from .models import Device

ACTIONS = {"lock", "unlock", "absent", "present"}


@login_required
@ensure_csrf_cookie
def dashboard(request):
    return render(request, "lab/dashboard.html", {"simulate": settings.LAB_SIMULATE})


@login_required
@require_GET
def api_status(request):
    devices = list(Device.objects.all())
    online_map = veyon.check_many(devices)

    # الجهاز الذي انقطع اتصاله فقد الحظر (الحظر يزول عند إطفائه)، فنصفّر الحالة
    stale = [d for d in devices if d.is_blocked and not online_map[d.pk]]
    if stale:
        Device.objects.filter(pk__in=[d.pk for d in stale]).update(is_blocked=False)
        for d in stale:
            d.is_blocked = False

    data = [
        {
            "number": d.number,
            "name": d.name,
            "online": online_map[d.pk],
            "absent": d.is_absent,
            "blocked": d.is_blocked,
        }
        for d in devices
    ]
    return JsonResponse({"devices": data, "simulate": settings.LAB_SIMULATE})


@login_required
@require_POST
def api_action(request):
    try:
        body = json.loads(request.body or b"{}")
        action = body.get("action")
        numbers = [int(n) for n in body.get("numbers", [])]
    except (ValueError, TypeError):
        return JsonResponse({"error": "طلب غير صالح"}, status=400)
    if action not in ACTIONS or not numbers:
        return JsonResponse({"error": "طلب غير صالح"}, status=400)

    devices = list(Device.objects.filter(number__in=numbers))
    result = {"done": [], "skipped": [], "failed": []}

    if action in ("absent", "present"):
        Device.objects.filter(pk__in=[d.pk for d in devices]).update(is_absent=(action == "absent"))
        result["done"] = [d.number for d in devices]
        return JsonResponse(result)

    lock = action == "lock"
    online_map = veyon.check_many(devices)
    targets = []
    for d in devices:
        if not online_map[d.pk]:
            result["skipped"].append({"number": d.number, "reason": "غير متصل"})
        elif lock and d.is_absent:
            result["skipped"].append({"number": d.number, "reason": "غائب"})
        else:
            targets.append(d)

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda d: veyon.set_lock(d, lock), targets))

    ok_ids = []
    for d, (ok, error) in zip(targets, outcomes):
        if ok:
            ok_ids.append(d.pk)
            result["done"].append(d.number)
        else:
            result["failed"].append({"number": d.number, "error": error})
    Device.objects.filter(pk__in=ok_ids).update(is_blocked=lock)
    return JsonResponse(result)
