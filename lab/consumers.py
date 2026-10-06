"""قنوات الإشارة (Signaling) بين جهاز المعلم وأجهزة الطلاب.

الصوت نفسه لا يمر من هنا: يمر مباشرة بين المتصفحين عبر WebRTC.
هذه القنوات تنقل فقط رسائل التفاوض (SDP) وأوامر تشغيل/إيقاف ميكروفون الطالب.
"""
from urllib.parse import urlparse

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import presence
from .access import is_teacher_machine, normalize_ip
from .models import Device

TEACHER_GROUP = "teacher"
STUDENT_COMMANDS = {"mic_on", "mic_off"}


def _client_ip(scope):
    client = scope.get("client") or ("", 0)
    return normalize_ip(client[0])


def _origin_ok(scope):
    """يمنع صفحة غريبة مفتوحة في متصفح المعلم من الاتصال بقناة المعلم."""
    headers = dict(scope.get("headers", []))
    origin = headers.get(b"origin")
    if not origin:
        return True
    host = headers.get(b"host")
    return bool(host) and urlparse(origin.decode()).netloc == host.decode()


def _numbers(value):
    out = []
    for n in value if isinstance(value, list) else []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 40:
            out.append(n)
    return out


@database_sync_to_async
def _device_by_ip(ip):
    return Device.objects.filter(ip_address=ip).first()


class TeacherConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        user = self.scope.get("user")
        allowed = bool(
            user
            and user.is_authenticated
            and is_teacher_machine(_client_ip(self.scope))
            and _origin_ok(self.scope)
        )
        if not allowed:
            await self.close(code=4403)
            return
        # نافذة معلم واحدة فقط، وإلا اختلطت إجابات الطلاب بين النوافذ
        for channel in presence.other_teacher_channels(self.channel_name):
            await self.channel_layer.send(channel, {"type": "replaced"})
        presence.add_teacher(self.channel_name)
        await self.channel_layer.group_add(TEACHER_GROUP, self.channel_name)
        await self.send_json({"type": "presence_list", "numbers": sorted(presence.online_numbers())})

    async def disconnect(self, code):
        presence.remove_teacher(self.channel_name)
        await self.channel_layer.group_discard(TEACHER_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if kind == "signal":
            numbers = _numbers([content.get("to")])
            if numbers:
                await self.channel_layer.group_send(
                    f"student_{numbers[0]}",
                    {"type": "relay", "payload": {"type": "signal", "data": content.get("data")}},
                )
        elif kind == "cmd" and content.get("cmd") in STUDENT_COMMANDS:
            for number in _numbers(content.get("to")):
                await self.channel_layer.group_send(
                    f"student_{number}",
                    {"type": "relay", "payload": {"type": "cmd", "cmd": content["cmd"]}},
                )

    async def teacher_event(self, event):
        await self.send_json(event["payload"])

    async def replaced(self, event):
        await self.close(code=4409)


class StudentConsumer(AsyncJsonWebsocketConsumer):
    number = None

    async def connect(self):
        await self.accept()
        device = await _device_by_ip(_client_ip(self.scope))
        if device is None:
            await self.close(code=4404)
            return
        self.number = device.number
        self.group = f"student_{self.number}"

        # فتح الصفحة في نافذتين لنفس الجهاز: تبقى الأحدث فقط
        for channel in presence.other_student_channels(self.number, self.channel_name):
            await self.channel_layer.send(channel, {"type": "replaced"})
        presence.add_student(self.number, self.channel_name)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.send_json({"type": "hello", "number": self.number})
        await self._tell_teacher({"type": "presence", "number": self.number, "online": True})

    async def disconnect(self, code):
        if self.number is None:
            return
        await self.channel_layer.group_discard(self.group, self.channel_name)
        if presence.remove_student(self.number, self.channel_name):
            await self._tell_teacher({"type": "presence", "number": self.number, "online": False})

    async def receive_json(self, content, **kwargs):
        if self.number is not None and content.get("type") == "signal":
            await self._tell_teacher(
                {"type": "signal", "from": self.number, "data": content.get("data")}
            )
        elif self.number is not None and content.get("type") == "quality":
            await self._tell_teacher(
                {"type": "quality", "from": self.number, "data": content.get("data")}
            )

    async def _tell_teacher(self, payload):
        await self.channel_layer.group_send(TEACHER_GROUP, {"type": "teacher_event", "payload": payload})

    async def relay(self, event):
        await self.send_json(event["payload"])

    async def replaced(self, event):
        await self.close(code=4409)
