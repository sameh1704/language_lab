"""من فتح صفحة الطالب الآن. يعمل داخل عملية واحدة (جهاز المعلم)، لذلك يكفي ذاكرة بسيطة."""

_students = {}   # رقم الجهاز -> مجموعة قنوات WebSocket
_teachers = set()


def add_student(number, channel):
    _students.setdefault(number, set()).add(channel)


def other_student_channels(number, channel):
    return [c for c in _students.get(number, ()) if c != channel]


def remove_student(number, channel):
    """يرجع True إذا لم يبقَ أي اتصال لهذا الجهاز."""
    channels = _students.get(number)
    if channels is None:
        return True
    channels.discard(channel)
    if not channels:
        del _students[number]
        return True
    return False


def online_numbers():
    return set(_students)


def add_teacher(channel):
    _teachers.add(channel)


def other_teacher_channels(channel):
    return [c for c in _teachers if c != channel]


def remove_teacher(channel):
    _teachers.discard(channel)
