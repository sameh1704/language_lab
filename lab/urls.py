from django.urls import path

from . import setup_views, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/status/", views.api_status, name="api_status"),
    path("api/action/", views.api_action, name="api_action"),
    # إعداد الاتصال (المعلم)
    path("setup/", setup_views.setup_page, name="setup"),
    path("api/setup/status/", setup_views.api_setup_status, name="api_setup_status"),
    path("api/setup/ip/", setup_views.api_setup_ip, name="api_setup_ip"),
    path("api/setup/fill/", setup_views.api_setup_fill, name="api_setup_fill"),
    path("api/setup/pairing/", setup_views.api_setup_pairing, name="api_setup_pairing"),
    path("api/setup/lock-features/", setup_views.api_setup_lock_features, name="api_setup_lock_features"),
    path("api/setup/test-lock/", setup_views.api_setup_test_lock, name="api_setup_test_lock"),
    path("api/setup/refresh-lock-states/", setup_views.api_setup_refresh_lock_states, name="api_setup_refresh_lock_states"),
    # صفحة الطالب (مفتوحة لأجهزة الشبكة)
    path("student/", setup_views.student_page, name="student"),
    path("student/pair/", setup_views.student_pair, name="student_pair"),
]
