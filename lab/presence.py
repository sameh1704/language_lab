"""من فتح صفحة الطالب الآن. يعمل داخل عملية واحدة (جهاز المعلم)، لذلك يكفي ذاكرة بسيطة."""

from collections import defaultdict

# device_uuid -> {channel, number, classroom_id}
_students = {}
# teacher_group -> set of channels
_teachers = defaultdict(set)


def add_student(device_uuid, channel, number=None, classroom_id=None):
    _students[device_uuid] = {"channel": channel, "number": number, "classroom_id": classroom_id}


def other_student_channels(device_uuid, channel):
    student = _students.get(device_uuid)
    if not student or student["channel"] == channel:
        return []
    return [student["channel"]]


def remove_student(device_uuid, channel):
    """يرجع True إذا لم يبقَ أي اتصال لهذا الجهاز."""
    student = _students.get(device_uuid)
    if student is None:
        return True
    if student["channel"] != channel:
        return False
    del _students[device_uuid]
    return True


def online_numbers():
    """جميع أرقام الأجهزة المتصلة (للحالة القديمة/التوافق)."""
    return {s["number"] for s in _students.values() if s["number"] is not None}


def online_numbers_for_classroom(classroom_id):
    """أرقام الأجهزة المتصلة في قاعة معينة."""
    if classroom_id is None:
        return online_numbers()
    return {s["number"] for s in _students.values() if s["number"] is not None and s.get("classroom_id") == classroom_id}


def add_teacher(teacher_group, channel):
    _teachers[teacher_group].add(channel)


def other_teacher_channels(teacher_group, channel):
    return [c for c in _teachers.get(teacher_group, set()) if c != channel]


def remove_teacher(teacher_group, channel):
    _teachers[teacher_group].discard(channel)