from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/teacher/$", consumers.TeacherConsumer.as_asgi()),
    re_path(r"^ws/student/$", consumers.StudentConsumer.as_asgi()),
]
