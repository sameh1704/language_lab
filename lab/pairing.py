"""وضع الربط: نافذة زمنية يسجّل فيها الطالب رقم جهازه وعنوانه تلقائيًا."""
import time

from django.core.cache import cache

KEY = "lab_pairing_until"


def seconds_left():
    until = cache.get(KEY)
    return max(0, int(until - time.time())) if until else 0


def start(minutes=10):
    cache.set(KEY, time.time() + minutes * 60, timeout=minutes * 60 + 5)


def stop():
    cache.delete(KEY)
