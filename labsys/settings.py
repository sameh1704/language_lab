import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me-before-real-use")
DEBUG = env_bool("DJANGO_DEBUG", True)
# الشبكة داخلية، والطلاب يفتحون الصفحة عبر عنوان جهاز المعلم. الحماية الفعلية في lab/access.py
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",")]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "lab",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "lab.access.LocalOnlyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "labsys.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "labsys.wsgi.application"
ASGI_APPLICATION = "labsys.asgi.application"

# طبقة قنوات في الذاكرة: تكفي لأن النظام يعمل كعملية واحدة على جهاز المعلم (لا حاجة لـ Redis)
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "ar"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# ---------------------------------------------------------------------------
# إعدادات معمل اللغات / Veyon
# ---------------------------------------------------------------------------
# True  = وضع تجريبي: لا يتصل بأي جهاز حقيقي (للتجربة على أي جهاز بدون Veyon)
# False = وضع التشغيل الفعلي على جهاز المعلم
LAB_SIMULATE = env_bool("LAB_SIMULATE", True)

# مسار veyon-cli على جهاز المعلم (Windows)
VEYON_CLI = os.environ.get(
    "VEYON_CLI",
    r"C:\Program Files\Veyon\veyon-cli.exe" if os.name == "nt" else "veyon-cli",
)
# المنفذ الذي تستمع عليه خدمة Veyon على أجهزة الطلاب
VEYON_PORT = int(os.environ.get("VEYON_PORT", "11100"))
# أسماء ميزات Veyon المستخدمة في الحظر (تحقق منها بالأمر: veyon-cli feature list)
VEYON_LOCK_FEATURES = [
    f.strip() for f in os.environ.get("VEYON_LOCK_FEATURES", "ScreenLock").split(",") if f.strip()
]
# مهلة فحص الاتصال بالجهاز بالثواني
LAB_CHECK_TIMEOUT = float(os.environ.get("LAB_CHECK_TIMEOUT", "0.8"))
