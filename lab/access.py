"""من يحق له فتح لوحة المعلم؟ جهاز المعلم فقط. أجهزة الطلاب تصل لصفحة الطالب فقط."""
import time
import socket

from django.http import HttpResponseForbidden, HttpResponseRedirect

LOOPBACK = {"127.0.0.1", "::1"}
_cache = {"at": 0.0, "ips": []}


def normalize_ip(ip):
    ip = (ip or "").strip()
    return ip[7:] if ip.startswith("::ffff:") else ip


def lan_ips():
    """عناوين IPv4 لجهاز المعلم على الشبكة (الأرجح أولاً)."""
    if _cache["ips"] and time.time() - _cache["at"] < 30:
        return list(_cache["ips"])
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # لا يرسل شيئًا، فقط يحدد واجهة الشبكة
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
    """كل الصفحات (اللوحة، الإعدادات، الإدارة، الواجهات) متاحة من جهاز المعلم فقط،
    عدا /student/ التي تفتحها أجهزة الطلاب."""

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
                "هذه الصفحة متاحة من جهاز المعلم فقط.", content_type="text/plain; charset=utf-8"
            )
        return self.get_response(request)
