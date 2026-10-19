import hmac
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import veyon
from .access import normalize_ip
from .media_lib import (
    validate_filename, validate_extension, validate_mime_type,
    validate_file_size, get_media_type_from_mime, get_media_type_from_extension, get_safe_upload_path,
    MAX_FILE_SIZE,
)
from .models import Device, Classroom, VeyonActionLog, AssistanceRequest, MediaFolder, MediaAsset, Student, Class, Enrollment

logger = logging.getLogger(__name__)

ACTIONS = {
    "lock", "unlock", "absent", "present", "start_session", "end_session", "sync_locks",
    "remote_view", "remote_control", "broadcast_fullscreen", "broadcast_window",
    "text_message", "open_website", "start_app", "screenshot",
    "power_on", "reboot", "power_down", "power_down_now",
}
FEATURE_ACTIONS = {
    "remote_view": lambda d: veyon.remote_view(d),
    "remote_control": lambda d: veyon.remote_control(d),
    "broadcast_fullscreen": lambda d: veyon.broadcast(d, fullscreen=True),
    "broadcast_window": lambda d: veyon.broadcast(d, fullscreen=False),
    "broadcast_stop": lambda d: veyon.stop_broadcast(d, fullscreen=True) or veyon.stop_broadcast(d, fullscreen=False),
    "text_message": lambda d, msg: veyon.send_text_message(d, msg),
    "open_website": lambda d, url: veyon.open_website(d, url),
    "start_app": lambda d, cmd: veyon.start_app(d, cmd),
    "screenshot": lambda d: veyon.screenshot(d),
    "power_on": lambda d: veyon.power_action(d, "PowerOn"),
    "reboot": lambda d: veyon.power_action(d, "Reboot"),
    "power_down": lambda d: veyon.power_action(d, "PowerDown"),
    "power_down_now": lambda d: veyon.power_action(d, "PowerDownNow"),
}
VEYON_CONTROL_ACTIONS = {
    "remote_view": {"label": "Remote View", "needsValue": False},
    "remote_control": {"label": "Remote Control", "needsValue": False},
    "broadcast_fullscreen": {"label": "Broadcast Fullscreen", "needsValue": False},
    "broadcast_window": {"label": "Broadcast Window", "needsValue": False},
    "text_message": {"label": "Text Message", "needsValue": True, "placeholder": "Message"},
    "open_website": {"label": "Open Website", "needsValue": True, "placeholder": "https://example.com"},
    "start_app": {"label": "Start App", "needsValue": True, "placeholder": "notepad.exe"},
    "screenshot": {"label": "Screenshot", "needsValue": False},
    "power_on": {"label": "Power On", "needsValue": False},
    "reboot": {"label": "Reboot", "needsValue": False},
    "power_down": {"label": "Power Down", "needsValue": False},
}


def _get_active_classroom(request):
    """Get the active classroom from request or session."""
    classroom_id = request.GET.get("classroom") or request.session.get("active_classroom")
    if classroom_id:
        try:
            return Classroom.objects.get(pk=classroom_id, active=True)
        except Classroom.DoesNotExist:
            pass
    return Classroom.objects.filter(active=True).first()


def _get_devices_for_classroom(classroom):
    """Get devices for a classroom, or all if classroom is None."""
    if classroom:
        return list(Device.objects.filter(classroom=classroom, active=True))
    return list(Device.objects.filter(active=True))


def _log_veyon_action(user, classroom, device, action, detail="", success=False, error_message=""):
    VeyonActionLog.objects.create(
        teacher=user,
        classroom=classroom,
        device=device,
        action=action,
        detail=detail[:255] if detail else "",
        success=success,
        error_message=error_message or "",
    )


@login_required
@ensure_csrf_cookie
def dashboard(request):
    classroom = _get_active_classroom(request)
    classrooms = Classroom.objects.filter(active=True)
    return render(
        request,
        "lab/dashboard.html",
        {
            "simulate": settings.LAB_SIMULATE,
            "classroom": classroom,
            "classrooms": classrooms,
        },
    )


@login_required
@require_GET
def api_status(request):
    classroom = _get_active_classroom(request)
    devices = _get_devices_for_classroom(classroom)
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
            "device_uuid": str(d.device_uuid),
            "online": online_map[d.pk],
            "absent": d.is_absent,
            "blocked": d.is_blocked,
        }
        for d in devices
    ]
    return JsonResponse(
        {
            "devices": data,
            "simulate": settings.LAB_SIMULATE,
            "classroom": {"id": classroom.pk, "name": classroom.name} if classroom else None,
        }
    )


@login_required
@require_POST
def api_action(request):
    try:
        body = json.loads(request.body or b"{}")
        action = body.get("action")
        numbers = [int(n) for n in body.get("numbers", [])]
    except (ValueError, TypeError):
        return JsonResponse({"error": _("Invalid request")}, status=400)
    if action not in ACTIONS or (action not in ("start_session", "end_session", "sync_locks") and not numbers):
        return JsonResponse({"error": _("Invalid request")}, status=400)

    classroom = _get_active_classroom(request)

    if action == "start_session":
        return _start_session(classroom)
    if action == "end_session":
        return _end_session(classroom)
    if action == "sync_locks":
        return _sync_locks(classroom)

    devices = list(Device.objects.filter(classroom=classroom, number__in=numbers)) if classroom else list(Device.objects.filter(number__in=numbers))
    result = {"done": [], "skipped": [], "failed": []}

    if action in ("absent", "present"):
        Device.objects.filter(pk__in=[d.pk for d in devices]).update(is_absent=(action == "absent"))
        result["done"] = [d.number for d in devices]
        return JsonResponse(result)

    lock = action == "lock"
    if lock or action == "unlock":
        online_map = veyon.check_many(devices)
        targets = []
        for d in devices:
            if not online_map[d.pk]:
                result["skipped"].append({"number": d.number, "reason": _("Offline")})
            elif lock and d.is_absent:
                result["skipped"].append({"number": d.number, "reason": _("Absent")})
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
                    logger.exception(_("Exception during %(action)s device %(number)d"), {"action": _("lock") if lock else _("unlock"), "number": d.number})
                    ok, error = False, f"{_('Exception')}: {e}"
                if ok:
                    result["done"].append(d.number)
                else:
                    result["failed"].append({"number": d.number, "error": error})
                _log_veyon_action(request.user, classroom, d, action, success=ok, error_message=error)

        ok_ids = [d.pk for d in targets if d.number in result["done"]]
        if ok_ids:
            Device.objects.filter(pk__in=ok_ids).update(is_blocked=lock)
        return JsonResponse(result)

    raise JsonResponse({"error": _("Invalid request")}, status=400)


@login_required
@require_POST
def api_control(request):
    """Control endpoint for Veyon screen management actions with parameters."""
    try:
        body = json.loads(request.body or b"{}")
        action = body.get("action")
        numbers = [int(n) for n in body.get("numbers", [])]
        params = body.get("params", {})
    except (ValueError, TypeError):
        return JsonResponse({"error": _("Invalid request")}, status=400)

    if action not in FEATURE_ACTIONS or not numbers:
        return JsonResponse({"error": _("Invalid request")}, status=400)

    classroom = _get_active_classroom(request)
    devices = list(Device.objects.filter(classroom=classroom, number__in=numbers)) if classroom else list(Device.objects.filter(number__in=numbers))

    if not devices:
        return JsonResponse({"error": _("No devices found")}, status=404)

    online_map = veyon.check_many(devices)
    targets = [d for d in devices if online_map.get(d.pk)]
    skipped = [{"number": d.number, "reason": _("Offline")} for d in devices if not online_map.get(d.pk)]

    if not targets:
        return JsonResponse({"done": [], "skipped": skipped, "failed": []})

    result = {"done": [], "skipped": skipped, "failed": []}

    def run_action(device):
        fn = FEATURE_ACTIONS[action]
        try:
            if action in ("text_message", "open_website", "start_app"):
                detail = params.get("value", "")
                ok, error = fn(device, detail)
            else:
                detail = ""
                ok, error = fn(device)
            return device, ok, error, detail
        except Exception as e:
            return device, False, f"{_('Exception')}: {e}", ""

    with ThreadPoolExecutor(max_workers=16) as pool:
        future_to_device = {pool.submit(run_action, d): d for d in targets}
        for future in as_completed(future_to_device):
            d = future_to_device[future]
            try:
                device, ok, error, detail = future.result()
            except Exception as e:
                device = d
                ok, error, detail = False, f"{_('Exception')}: {e}", ""
            if ok:
                result["done"].append(device.number)
            else:
                result["failed"].append({"number": device.number, "error": error})
            _log_veyon_action(request.user, classroom, device, action, detail=detail, success=ok, error_message=error)

    return JsonResponse(result)


@login_required
@require_GET
def api_control_supported(request):
    return JsonResponse({"actions": VEYON_CONTROL_ACTIONS})


def _start_session(classroom):
    """Start session: check all devices and return detailed report."""
    devices = _get_devices_for_classroom(classroom)
    if not devices:
        return JsonResponse({"ok": False, "error": _("No devices registered")})

    online_map = veyon.check_many(devices)
    locked_map = {}
    for d in devices:
        if d.ip_address and online_map.get(d.pk):
            is_locked, err = veyon.get_lock_state(d)
            locked_map[d.pk] = is_locked
            if err:
                logger.warning(_("Could not read lock state for device %(number)d: %(error)s"), {"number": d.number, "error": err})

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


def _end_session(classroom):
    """End session: unlock all devices and stop audio (signal to UI)."""
    devices = list(Device.objects.filter(classroom=classroom, is_blocked=True)) if classroom else list(Device.objects.filter(is_blocked=True))
    if not devices:
        return JsonResponse({"ok": True, "action": "end_session", "message": _("No blocked devices"), "unlocked": 0})

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
                logger.exception(_("Exception unlocking device %(number)d"), {"number": d.number})
                ok, error = False, f"{_('Exception')}: {e}"
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
            "message": _("%(count)d devices unlocked") % {"count": unlocked},
            "unlocked": unlocked,
            "failed": failed,
        }
    )


def _sync_locks(classroom):
    """Sync lock state with reality."""
    devices = _get_devices_for_classroom(classroom)
    count = veyon.sync_lock_states(devices)
    return JsonResponse({"ok": True, "synced": count})


@login_required
@require_POST
def api_set_classroom(request):
    """Set the active classroom for the session."""
    try:
        body = json.loads(request.body or b"{}")
        classroom_id = int(body.get("classroom_id"))
    except (ValueError, TypeError):
        return JsonResponse({"error": _("Invalid classroom ID")}, status=400)

    try:
        classroom = Classroom.objects.get(pk=classroom_id, active=True)
    except Classroom.DoesNotExist:
        return JsonResponse({"error": _("Classroom not found")}, status=404)

    request.session["active_classroom"] = classroom.pk
    return JsonResponse({"ok": True, "classroom": {"id": classroom.pk, "name": classroom.name}})


# ---------------------------------------------------------------------------
# Student assistance requests
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_assistance_requests(request):
    """Teacher: list open requests for active classroom."""
    if not request.user.is_staff:
        return JsonResponse({"error": _("Forbidden")}, status=403)
    classroom = _get_active_classroom(request)
    qs = AssistanceRequest.objects.filter(classroom=classroom, status="open") if classroom else AssistanceRequest.objects.none()
    data = []
    for req in qs.select_related("student", "device", "classroom"):
        # A device-identified request has no ``User``; label it by device so the
        # teacher still sees who asked.
        if req.student is not None:
            student_label = req.student.get_username()
        else:
            student_label = _("Device %(number)s") % {"number": req.device.number} if req.device else _("Unknown student")
        data.append(
            {
                "id": req.pk,
                "student": student_label,
                "device": req.device.number if req.device else None,
                "classroom": req.classroom.name,
                "request_type": req.request_type,
                "status": req.status,
                "created_at": req.created_at.isoformat(),
            }
        )
    return JsonResponse({"requests": data})


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


def _student_device_credential(request, body):
    """Resolve the calling student device for /api/assistance/create/.

    Identity model for the anonymous student page
    ---------------------------------------------
    ``/student/`` has no login. Its identity is the lab *device* itself, and the
    credential is ``Device.device_uuid``: a server-generated, unique and
    unguessable UUIDv4 that is never derivable from, or supplied by, the client.

    * **Issuance** — ``student_page`` issues the credential by putting the UUID
      of the device whose registered IP served the request into the session
      (``session["student_device_uuid"]``, plus the mirroring cookie that the
      WebSocket ``hello`` message delivers to the page). The client IP is used
      only to *hand the secret out*, never as the authorization check.
    * **Use** — the request must present a ``device_uuid`` body value that
      matches the session's. A guessed or copied value is refused, a
      client-supplied device *ID*/*name*/*IP* is never consulted, and the device
      is looked up **by UUID**, so the caller cannot nominate another device.
    * **Consequence** — the classroom is taken from ``device.classroom``, so a
      device can only ever open a request in its own classroom. Cross-classroom
      creation is impossible by construction.

    Returns ``(device, None)`` for a device-identified student, or
    ``(None, response)`` when the caller is not authorized.
    """
    supplied = body.get("device_uuid")
    if not supplied:
        return None, JsonResponse({"error": _("Missing device credential")}, status=403)

    expected = request.session.get("student_device_uuid")
    # Constant-time compare of the two UUID strings so a timing difference does
    # not leak the value of the session credential.
    if not expected or not hmac.compare_digest(str(expected), str(supplied)):
        return None, JsonResponse({"error": _("Invalid device credential")}, status=403)

    try:
        supplied_uuid = uuid.UUID(str(supplied))
    except (ValueError, AttributeError, TypeError):
        return None, JsonResponse({"error": _("Invalid device credential")}, status=403)

    device = Device.objects.filter(device_uuid=supplied_uuid, active=True).first()
    if device is None:
        return None, JsonResponse({"error": _("Device not found")}, status=404)
    return device, None


@require_POST
def api_assistance_create(request):
    """Create an assistance request.

    Two authorized sources, deliberately kept separate:

    1. A device-identified student page (no login) — authorized by the
       device credential described in ``_student_device_credential`` and always
       scoped to its own classroom.
    2. An authenticated staff/teacher caller (the existing behaviour, used by
       the setup tooling and the regression suite) — scoped to the teacher's
       active classroom.

    The endpoint is *not* a generic drop box: a caller with neither the device
    credential nor a staff login is refused with 403.
    """
    body = _json_body(request)
    request_type = body.get("request_type")
    if request_type not in ("hand_raise", "help"):
        return JsonResponse({"error": _("Invalid request type")}, status=400)

    device = None
    if body.get("device_uuid"):
        # Student device credential path.
        device, denied = _student_device_credential(request, body)
        if denied is not None:
            return denied
        student = None
        classroom = device.classroom
    elif request.user.is_authenticated:
        # Authenticated teacher/staff path — unchanged behaviour. A non-staff
        # caller is only trusted when its IP maps to a registered device.
        ip = normalize_ip(request.META.get("REMOTE_ADDR", ""))
        device = Device.objects.filter(ip_address=ip, active=True).first()
        if device:
            classroom = device.classroom
        elif request.user.is_staff:
            classroom = _get_active_classroom(request)
        else:
            return JsonResponse({"error": _("Not authorized")}, status=403)
        student = request.user
    else:
        return JsonResponse({"error": _("Not authorized")}, status=403)

    if not classroom:
        return JsonResponse({"error": _("Not authorized")}, status=403)

    # Duplicate guard. Device-identified requests have no ``User`` to key on, so
    # they are keyed by device; authenticated ones keep keying by user.
    existing_qs = AssistanceRequest.objects.filter(
        classroom=classroom,
        status="open",
        request_type=request_type,
    )
    existing_qs = existing_qs.filter(device=device) if device else existing_qs.filter(student=student)
    if existing_qs.exists():
        return JsonResponse({"error": _("Duplicate open request")}, status=400)

    req = AssistanceRequest.objects.create(
        student=student,
        device=device,
        classroom=classroom,
        request_type=request_type,
        status="open",
    )
    return JsonResponse(
        {
            "ok": True,
            "id": req.pk,
            "device": device.number if device else None,
            "classroom": {"id": classroom.pk, "name": classroom.name},
        }
    )


@login_required
@require_POST
def api_assistance_update(request, pk):
    """Teacher: update request status (acknowledge/resolve/dismiss)."""
    if not request.user.is_staff:
        return JsonResponse({"error": _("Forbidden")}, status=403)
    try:
        req = AssistanceRequest.objects.get(pk=pk)
    except AssistanceRequest.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    classroom = _get_active_classroom(request)
    if not classroom or req.classroom.pk != classroom.pk:
        return JsonResponse({"error": _("Forbidden")}, status=403)

    body = json.loads(request.body or b"{}")
    new_status = body.get("status")
    if new_status not in ("acknowledged", "resolved", "dismissed"):
        return JsonResponse({"error": _("Invalid status")}, status=400)

    req.status = new_status
    req.resolved_by = request.user
    from django.utils import timezone
    req.resolved_at = timezone.now()
    req.save(update_fields=["status", "resolved_by", "resolved_at"])
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Media Library
# ---------------------------------------------------------------------------


@login_required
def media_library(request):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    folder_id = request.GET.get("folder")
    search = request.GET.get("q", "").strip()
    media_type = request.GET.get("type", "").strip()
    lang = request.GET.get("lang", "").strip()

    folder = None
    if folder_id:
        folder = get_object_or_404(MediaFolder, pk=folder_id)

    folders = MediaFolder.objects.filter(parent=folder).order_by("name")
    assets = MediaAsset.objects.filter(folder=folder).order_by("-created_at")

    if search:
        assets = assets.filter(title__icontains=search)
    if media_type:
        assets = assets.filter(media_type=media_type)
    if lang:
        assets = assets.filter(content_language=lang)

    breadcrumbs = []
    current = folder
    while current:
        breadcrumbs.insert(0, current)
        current = current.parent

    return render(request, "lab/media_library.html", {
        "folder": folder,
        "folders": folders,
        "assets": assets,
        "breadcrumbs": breadcrumbs,
        "search": search,
        "media_type": media_type,
        "content_language": lang,
        "media_type_choices": MediaAsset.MEDIA_TYPES,
    })


@login_required
@require_POST
def media_api(request, action=None):
    if not request.user.is_staff:
        return JsonResponse({"error": _("Forbidden")}, status=403)

    if action == "upload":
        return media_api_upload(request)
    elif action == "rename_asset":
        return media_api_rename_asset(request)
    elif action == "move_asset":
        return media_api_move_asset(request)
    elif action == "delete_asset":
        return media_api_delete_asset(request)
    elif action == "create_folder":
        return media_api_create_folder(request)
    elif action == "rename_folder":
        return media_api_rename_folder(request)
    elif action == "delete_folder":
        return media_api_delete_folder(request)
    else:
        return JsonResponse({"error": _("Invalid action")}, status=400)


def media_api_upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": _("No file uploaded.")}, status=400)

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    content_language = request.POST.get("content_language", "").strip()
    folder_id = request.POST.get("folder_id")

    folder = None
    if folder_id:
        try:
            folder = MediaFolder.objects.get(pk=folder_id)
        except MediaFolder.DoesNotExist:
            return JsonResponse({"error": _("Folder not found.")}, status=404)

    original_name = uploaded.name
    try:
        safe_name, ext = validate_filename(original_name)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    media_type = get_media_type_from_extension(original_name)
    if not media_type:
        return JsonResponse({"error": _("Unsupported file type.")}, status=400)

    try:
        validate_extension(ext, media_type)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    mime = uploaded.content_type or "application/octet-stream"
    try:
        validate_mime_type(mime, media_type)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    try:
        validate_file_size(uploaded.size)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    try:
        rel_path = get_safe_upload_path(folder, original_name)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    uploaded.name = safe_name

    asset = MediaAsset.objects.create(
        title=title or Path(original_name).stem,
        description=description,
        file=uploaded,
        media_type=media_type,
        mime_type=mime,
        size=uploaded.size,
        content_language=content_language,
        folder=folder,
        created_by=request.user,
    )
    return JsonResponse({
        "ok": True,
        "id": asset.pk,
        "title": asset.title,
        "url": asset.file.url,
    })


def media_api_rename_asset(request):
    try:
        asset = MediaAsset.objects.get(pk=request.POST.get("id"))
    except MediaAsset.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    new_title = request.POST.get("title", "").strip()
    if not new_title:
        return JsonResponse({"error": _("Title is required.")}, status=400)

    asset.title = new_title
    asset.save(update_fields=["title"])
    return JsonResponse({"ok": True})


def media_api_move_asset(request):
    try:
        asset = MediaAsset.objects.get(pk=request.POST.get("id"))
    except MediaAsset.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    folder_id = request.POST.get("folder_id")
    folder = None
    if folder_id:
        try:
            folder = MediaFolder.objects.get(pk=folder_id)
        except MediaFolder.DoesNotExist:
            return JsonResponse({"error": _("Folder not found.")}, status=404)

    asset.folder = folder
    asset.save(update_fields=["folder"])
    return JsonResponse({"ok": True})


def media_api_delete_asset(request):
    try:
        asset = MediaAsset.objects.get(pk=request.POST.get("id"))
    except MediaAsset.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    asset.file.delete(save=False)
    asset.delete()
    return JsonResponse({"ok": True})


def media_api_create_folder(request):
    name = request.POST.get("name", "").strip()
    parent_id = request.POST.get("parent_id")
    if not name:
        return JsonResponse({"error": _("Name is required.")}, status=400)

    parent = None
    if parent_id:
        try:
            parent = MediaFolder.objects.get(pk=parent_id)
        except MediaFolder.DoesNotExist:
            return JsonResponse({"error": _("Parent folder not found.")}, status=404)

    folder = MediaFolder.objects.create(name=name, parent=parent, created_by=request.user)
    return JsonResponse({"ok": True, "id": folder.pk, "name": folder.name})


def media_api_rename_folder(request):
    try:
        folder = MediaFolder.objects.get(pk=request.POST.get("id"))
    except MediaFolder.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    new_name = request.POST.get("name", "").strip()
    if not new_name:
        return JsonResponse({"error": _("Name is required.")}, status=400)

    folder.name = new_name
    folder.save(update_fields=["name"])
    return JsonResponse({"ok": True})


def media_api_delete_folder(request):
    try:
        folder = MediaFolder.objects.get(pk=request.POST.get("id"))
    except MediaFolder.DoesNotExist:
        return JsonResponse({"error": _("Not found")}, status=404)

    if folder.assets.exists() or folder.children.exists():
        return JsonResponse({"error": _("Folder is not empty.")}, status=400)

    folder.delete()
    return JsonResponse({"ok": True})


@login_required
def media_download(request, pk):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    asset = get_object_or_404(MediaAsset, pk=pk)
    response = HttpResponse(asset.file.open("rb"), content_type=asset.mime_type)
    response["Content-Disposition"] = f'attachment; filename="{asset.file.name.split("/")[-1]}"'
    response["Content-Length"] = asset.size
    return response


@login_required
def media_preview(request, pk):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    asset = get_object_or_404(MediaAsset, pk=pk)
    return render(request, "lab/media_preview.html", {"asset": asset})


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

import os
import uuid

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .import_export import (
    IMPORT_ENTITIES, DUPLICATE_MODES, parse_uploaded_file, validate_rows, deep_validate,
    perform_import, export_csv, export_xlsx,
)


@login_required
def import_export_page(request):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return render(request, "lab/import_export.html", {
        "entities": IMPORT_ENTITIES,
        "duplicate_modes": DUPLICATE_MODES,
    })


@login_required
@require_POST
def import_upload(request):
    if not request.user.is_staff:
        return JsonResponse({"error": _("Forbidden")}, status=403)

    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": _("No file uploaded.")}, status=400)

    entity_type = request.POST.get("entity_type")
    if not entity_type or entity_type not in dict(IMPORT_ENTITIES):
        return JsonResponse({"error": _("Invalid entity type.")}, status=400)

    try:
        detected_type, rows = parse_uploaded_file(uploaded)
        if detected_type != entity_type:
            return JsonResponse({"error": _("File does not match selected entity type.")}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    valid_rows, error_rows = validate_rows(entity_type, rows)
    clean_rows, deep_errors = deep_validate(entity_type, valid_rows)

    all_errors = error_rows + deep_errors
    if all_errors:
        return JsonResponse({
            "ok": False,
            "preview_id": str(uuid.uuid4()),
            "total_rows": len(rows),
            "valid_count": len(clean_rows),
            "error_count": len(all_errors),
            "errors": all_errors[:50],
            "entity_type": entity_type,
        })

    return JsonResponse({
        "ok": True,
        "preview_id": str(uuid.uuid4()),
        "total_rows": len(rows),
        "valid_count": len(clean_rows),
        "error_count": 0,
        "errors": [],
        "entity_type": entity_type,
        "sample": clean_rows if len(clean_rows) <= 100 else clean_rows[:100],
    })


@login_required
@require_POST
def import_confirm(request):
    if not request.user.is_staff:
        return JsonResponse({"error": _("Forbidden")}, status=403)

    import json
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": _("Invalid JSON.")}, status=400)

    entity_type = body.get("entity_type")
    clean_rows = body.get("clean_rows", [])
    duplicate_mode = body.get("duplicate_mode", "reject")

    if not entity_type or not clean_rows:
        return JsonResponse({"error": _("Invalid request.")}, status=400)

    try:
        report = perform_import(entity_type, clean_rows, duplicate_mode, request.user)
    except Exception as e:
        return JsonResponse({"error": str(e), "rolled_back": True}, status=400)

    return JsonResponse({"ok": True, "report": report})


@login_required
def export_page(request, entity_type):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    fmt = request.GET.get("format", "csv").lower()
    if entity_type == "students":
        queryset = Student.objects.all().order_by("full_name")
    elif entity_type == "classes":
        queryset = Class.objects.all().order_by("grade", "name")
    elif entity_type == "enrollments":
        queryset = Enrollment.objects.all().select_related("student", "class_obj").order_by("-created_at")
    else:
        from django.http import Http404
        raise Http404()

    if fmt == "xlsx":
        data = export_xlsx(entity_type, queryset)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{entity_type}_{uuid.uuid4().hex[:8]}.xlsx"
    else:
        data = export_csv(entity_type, queryset)
        content_type = "text/csv; charset=utf-8"
        filename = f"{entity_type}_{uuid.uuid4().hex[:8]}.csv"

    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

