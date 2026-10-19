"""Who can open teacher dashboard? Teacher machine only. Student devices access student page only."""
import time
import socket

from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.utils.translation import gettext as _

LOOPBACK = {"127.0.0.1", "::1"}
_cache = {"at": 0.0, "ips": []}


def normalize_ip(ip):
    ip = (ip or "").strip()
    return ip[7:] if ip.startswith("::ffff:") else ip


def lan_ips():
    """Teacher machine IPv4 addresses on LAN (most likely first)."""
    if _cache["ips"] and time.time() - _cache["at"] < 30:
        return list(_cache["ips"])
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # doesn't send, just picks interface
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    ips = []
    for ip in found:
        if ip not in ips and not ip.startswith(("127.", "169.254.", "0.")):
            ips.append(ip)
    _cache.update(at=time.time(), ips=ips)
    return list(ips)


def is_teacher_machine(ip):
    ip = normalize_ip(ip)
    return ip in LOOPBACK or ip in lan_ips()


class LocalOnlyMiddleware:
    """All pages (dashboard, setup, admin, APIs) only from teacher machine,
    except /student/ opened by student devices."""

    PUBLIC_PREFIXES = ("/student/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_teacher_machine(request.META.get("REMOTE_ADDR", "")) and not request.path.startswith(
            self.PUBLIC_PREFIXES
        ):
            if request.path == "/":
                return HttpResponseRedirect("/student/")
            return HttpResponseForbidden(
                _("This page is only accessible from the teacher machine."), content_type="text/plain; charset=utf-8"
            )
        return self.get_response(request)