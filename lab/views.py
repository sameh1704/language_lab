import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import veyon
from .models import Device

logger = logging.getLogger(__name__)

ACTIONS = {"lock", "unlock", "absent", "present", "start_session", "end_session", "sync_locks"}


@login_required
@ensure_csrf_cookie
def dashboard(request):
    return render(request, "lab/dashboard.html", {"simulate": settings.LAB_SIMULATE})


@login_required
@require_GET
def api_status(request):
    devices = list(Device.objects.all())
    online_map = veyon.check_many(devices)

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
    if action not in ACTIONS or (action not in ("start_session", "end_session", "sync_locks") and not numbers):
        return JsonResponse({"error": "طلب غير صالح"}, status=400)

    if action == "start_session":
        return _start_session()
    if action == "end_session":
        return _end_session()
    if action == "sync_locks":
        return _sync_locks()

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

    if not targets:
        return JsonResponse(result)

    with ThreadPoolExecutor(max_workers=16) as pool:
        future_to_device = {pool.submit(veyon.set_lock, d, lock): d for d in targets}
        for future in as_completed(future_to_device):
            d = future_to_device[future]
            try:
                ok, error = future.result()
            except Exception as e:
                logger.exception("استثناء أثناء %s الجهاز %d", "الحظر" if lock else "الفتح", d.number)
                ok, error = False, f"استثناء: {e}"
            if ok:
                result["done"].append(d.number)
            else:
                result["failed"].append({"number": d.number, "error": error})

    ok_ids = [d.pk for d in targets if d.number in result["done"]]
    if ok_ids:
        Device.objects.filter(pk__in=ok_ids).update(is_blocked=lock)
    return JsonResponse(result)


def _start_session():
    """بدء الحصة: فحص كل الأجهزة وإرجاع تقرير مفصل."""
    devices = list(Device.objects.all())
    if not devices:
        return JsonResponse({"ok": False, "error": "لا توجد أجهزة مسجلة"})

    online_map = veyon.check_many(devices)
    locked_map = {}
    for d in devices:
        if d.ip_address and online_map.get(d.pk):
            is_locked, err = veyon.get_lock_state(d)
            locked_map[d.pk] = is_locked
            if err:
                logger.warning("تعذر قراءة حالة القفل للجهاز %d: %s", d.number, err)

    report = {
        "total": len(devices),
        "online": sum(1 for v in online_map.values() if v),
        "offline": sum(1 for v in online_map.values() if not v),
        "already_locked": sum(1 for v in locked_map.values() if v),
        "devices": [],
    }
    for d in devices:
        online = online_map.get(d.pk, False)
        locked = locked_map.get(d.pk, False)
        report["devices"].append(
            {
                "number": d.number,
                "name": d.name,
                "ip": d.ip_address or "",
                "online": online,
                "locked": locked,
                "absent": d.is_absent,
            }
        )

    return JsonResponse({"ok": True, "action": "start_session", "report": report})


def _end_session():
    """إنهاء الحصة: فتح كل الأجهزة وإيقاف الصوت (إشارة للواجهة)."""
    devices = list(Device.objects.filter(is_blocked=True))
    if not devices:
        return JsonResponse({"ok": True, "action": "end_session", "message": "لا توجد أجهزة محظورة", "unlocked": 0})

    online_map = veyon.check_many(devices)
    targets = [d for d in devices if online_map.get(d.pk)]
    unlocked = 0
    failed = []

    with ThreadPoolExecutor(max_workers=16) as pool:
        future_to_device = {pool.submit(veyon.set_lock, d, False): d for d in targets}
        for future in as_completed(future_to_device):
            d = future_to_device[future]
            try:
                ok, error = future.result()
            except Exception as e:
                logger.exception("استثناء أثناء فتح الجهاز %d", d.number)
                ok, error = False, f"استثناء: {e}"
            if ok:
                unlocked += 1
            else:
                failed.append({"number": d.number, "error": error})

    if unlocked:
        Device.objects.filter(pk__in=[d.pk for d in targets if d.number not in [f["number"] for f in failed]]).update(is_blocked=False)

    return JsonResponse(
        {
            "ok": True,
            "action": "end_session",
            "message": f"تم فتح {unlocked} جهاز",
            "unlocked": unlocked,
            "failed": failed,
        }
    )


def _sync_locks():
    """مزامنة حالة القفل مع الواقع."""
    devices = list(Device.objects.all())
    count = veyon.sync_lock_states(devices)
    return JsonResponse({"ok": True, "synced": count})