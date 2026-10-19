from django.urls import path

from . import setup_views, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/status/", views.api_status, name="api_status"),
    path("api/action/", views.api_action, name="api_action"),
    path("api/control/", views.api_control, name="api_control"),
    path("api/control/supported/", views.api_control_supported, name="api_control_supported"),
    path("api/set-classroom/", views.api_set_classroom, name="api_set_classroom"),
    path("api/assistance/", views.api_assistance_requests, name="api_assistance_requests"),
    path("api/assistance/create/", views.api_assistance_create, name="api_assistance_create"),
    path("api/assistance/<int:pk>/", views.api_assistance_update, name="api_assistance_update"),
    # Media Library
    path("media-library/", views.media_library, name="media_library"),
    path("media-library/api/<str:action>/", views.media_api, name="media_api"),
    path("media-library/download/<int:pk>/", views.media_download, name="media_download"),
    path("media-library/preview/<int:pk>/", views.media_preview, name="media_preview"),
    # Import / Export
    path("import-export/", views.import_export_page, name="import_export_page"),
    path("api/import/upload/", views.import_upload, name="import_upload"),
    path("api/import/confirm/", views.import_confirm, name="import_confirm"),
    path("export/<str:entity_type>/", views.export_page, name="export_page"),
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
