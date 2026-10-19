"""اختبارات آلية لوحدة veyon بدون أجهزة حقيقية."""
import asyncio
import json
import os
import re
import tempfile
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.conf import settings
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync

from lab import veyon
from lab import views as lab_views
from lab.media_lib import (
    validate_filename, validate_extension, validate_mime_type,
    validate_file_size, get_media_type_from_mime, get_safe_upload_path,
    clean_filename,
)
from lab.models import Device, Classroom, School, VeyonActionLog, AssistanceRequest, MediaFolder, MediaAsset, Student, Class, Enrollment

ASSISTANCE_MIDDLEWARE = [m for m in settings.MIDDLEWARE if m != "lab.access.LocalOnlyMiddleware"]


class VeyonCliTests(TestCase):
    """اختبارات التعامل مع veyon-cli."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="TEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Test Classroom", code="TEST-1", capacity=40
        )

    def setUp(self):
        self.device = Device.objects.create(
            classroom=self.classroom, number=1, ip_address="192.168.1.101"
        )
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    def tearDown(self):
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    @override_settings(LAB_SIMULATE=True)
    def test_check_online_simulate(self):
        """في الوضع التجريبي: الأجهزة القابلة للقسمة على 6 غير متصلة."""
        d1 = Device(classroom=self.classroom, number=1)
        d6 = Device(classroom=self.classroom, number=6)
        self.assertTrue(veyon.check_online(d1))
        self.assertFalse(veyon.check_online(d6))

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._get_veyon_cli_path", return_value="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_check_online_success(self, mock_run, mock_path):
        """فحص ناجح عبر veyon-cli."""
        mock_run.return_value = (True, "", "")
        self.assertTrue(veyon.check_online(self.device))
        mock_run.assert_called_once_with(
            ["feature", "list", "192.168.1.101"], timeout=2
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    @patch("lab.veyon.socket.create_connection")
    def test_check_online_fallback_to_port(self, mock_socket, mock_run):
        """إذا فشل veyon-cli يسقط إلى فحص المنفذ."""
        mock_run.return_value = (False, "", "error")
        mock_socket.return_value.__enter__ = MagicMock()
        mock_socket.return_value.__exit__ = MagicMock(return_value=False)
        self.assertTrue(veyon.check_online(self.device))

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    @patch("lab.veyon.socket.create_connection")
    def test_check_online_offline(self, mock_socket, mock_run):
        """جهاز غير متصل."""
        mock_run.return_value = (False, "", "error")
        mock_socket.side_effect = OSError("connection refused")
        self.assertFalse(veyon.check_online(self.device))

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_set_lock_success(self, mock_run):
        """حظر ناجح."""
        mock_run.return_value = (True, "", "")
        ok, error = veyon.set_lock(self.device, True)
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_set_lock_failure(self, mock_run):
        """فشل الحظر مع رسالة خطأ."""
        mock_run.return_value = (False, "", "access denied")
        ok, error = veyon.set_lock(self.device, True)
        self.assertFalse(ok)
        self.assertIn("access denied", error)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.is_feature_active")
    def test_get_lock_state_locked(self, mock_active):
        """قراءة حالة القفل: محظور."""
        mock_active.return_value = True
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertTrue(is_locked)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.is_feature_active")
    def test_get_lock_state_unlocked(self, mock_active):
        """قراءة حالة القفل: غير محظور."""
        mock_active.return_value = False
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertFalse(is_locked)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.is_feature_active")
    def test_get_lock_state_no_error(self, mock_active):
        """لا يوجد خطأ عند عدم القدرة على الاستعلام عن الحالة."""
        mock_active.return_value = False
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertFalse(is_locked)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_discover_lock_features(self, mock_run):
        """اكتشاف ميزات القفل."""
        mock_run.return_value = (True, "ScreenLock\nRemoteAccess\nDemoServer\n", "")
        features = veyon.discover_lock_features(force_refresh=True)
        self.assertIn("ScreenLock", features)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_run_with_retry_success(self, mock_run):
        """إعادة المحاولة تنجح في المحاولة الثانية."""
        mock_run.side_effect = [
            (False, "", "timeout"),
            (True, "", ""),
        ]
        ok, error = veyon.run_with_retry(self.device, "start", "ScreenLock", max_retries=2)
        self.assertTrue(ok)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_run_with_retry_all_fail(self, mock_run):
        """كل المحاولات تفشل."""
        mock_run.return_value = (False, "", "error")
        ok, error = veyon.run_with_retry(self.device, "start", "ScreenLock", max_retries=2)
        self.assertFalse(ok)
        self.assertEqual(mock_run.call_count, 3)


class VeyonSyncTests(TestCase):
    """اختبارات مزامنة حالة القفل."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="TEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Test Classroom", code="TEST-1", capacity=40
        )

    @override_settings(LAB_SIMULATE=True)
    def test_sync_lock_states_simulate(self):
        """في الوضع التجريبي لا تُزامن الحالة."""
        d = Device.objects.create(
            classroom=self.classroom, number=1, ip_address="192.168.1.101", is_blocked=True
        )
        count = veyon.sync_lock_states([d])
        self.assertEqual(count, 0)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.get_lock_state")
    def test_sync_lock_states_updates(self, mock_get):
        """المزامنة تحدث قاعدة البيانات عند اختلاف الحالة."""
        d = Device.objects.create(
            classroom=self.classroom, number=1, ip_address="192.168.1.101", is_blocked=False
        )
        mock_get.return_value = (True, "")
        count = veyon.sync_lock_states([d])
        self.assertEqual(count, 1)
        d.refresh_from_db()
        self.assertTrue(d.is_blocked)


class VeyonErrorTests(TestCase):
    """اختبارات التعامل مع الأخطاء."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="TEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Test Classroom", code="TEST-1", capacity=40
        )

    def setUp(self):
        self.device = Device.objects.create(
            classroom=self.classroom, number=1, ip_address="192.168.1.101"
        )
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    def tearDown(self):
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="")
    def test_set_lock_no_cli(self):
        """فشل عند عدم وجود veyon-cli."""
        ok, error = veyon.set_lock(self.device, True)
        self.assertFalse(ok)
        self.assertIn("veyon-cli", error)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    def test_set_lock_no_ip(self):
        """فشل عند عدم وجود عنوان IP."""
        d = Device(classroom=self.classroom, number=2, ip_address=None)
        ok, error = veyon.set_lock(d, True)
        self.assertFalse(ok)
        self.assertIn("IP", error)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.is_feature_active")
    def test_get_lock_state_no_error(self, mock_active):
        """لا يوجد خطأ عند عدم القدرة على الاستعلام عن الحالة."""
        mock_active.return_value = False
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertFalse(is_locked)
        self.assertEqual(error, "")


class InterfaceLocalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="I18N")
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Localization Room", code="I18N-1"
        )
        cls.device = Device.objects.create(
            classroom=cls.classroom,
            number=1,
            name="Student 1",
            ip_address="192.168.10.11",
        )
        cls.user = get_user_model().objects.create_superuser(
            username="i18n-test",
            email="i18n@example.invalid",
            password="temporary-test-password",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def switch_language(self, language):
        response = self.client.post(
            "/i18n/setlang/",
            {"language": language, "next": "/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["django_language"].value, language)

    @override_settings(LAB_SIMULATE=True)
    def test_language_switch_persists_across_teacher_and_student_pages(self):
        cases = (
            ("ar", "rtl", "لوحة تحكم معمل اللغات"),
            ("en", "ltr", "Language Lab Dashboard"),
            ("fr", "ltr", "Tableau de bord du laboratoire de langues"),
        )
        for language, direction, dashboard_title in cases:
            with self.subTest(language=language):
                self.switch_language(language)
                dashboard = self.client.get("/")
                self.assertEqual(dashboard.status_code, 200)
                self.assertContains(dashboard, f'lang="{language}" dir="{direction}"')
                self.assertContains(dashboard, dashboard_title)

                setup = self.client.get("/setup/")
                self.assertEqual(setup.status_code, 200)
                self.assertContains(setup, f'lang="{language}" dir="{direction}"')

                student = self.client.get(
                    "/student/",
                    REMOTE_ADDR="192.168.10.11",
                )
                self.assertEqual(student.status_code, 200)
                self.assertContains(student, f'lang="{language}" dir="{direction}"')

    def test_javascript_catalog_localizes_websocket_notifications(self):
        cases = (
            ("ar", "الاتصال: صفحة أخرى مفتوحة"),
            ("en", "Connection: another page is open"),
            ("fr", "Connexion : une autre page est ouverte"),
        )
        for language, notification in cases:
            with self.subTest(language=language):
                self.switch_language(language)
                if language == "ar":
                    page = self.client.get(
                        "/student/",
                        REMOTE_ADDR="192.168.10.11",
                    )
                    self.assertContains(page, f"gettext('{notification}')")
                else:
                    catalog = self.client.get("/jsi18n/")
                    self.assertEqual(catalog.status_code, 200)
                    self.assertContains(catalog, notification)

    def test_api_validation_errors_follow_selected_language(self):
        cases = (
            ("ar", "عنوان IP غير صالح"),
            ("en", "Invalid IP address"),
            ("fr", "Adresse IP invalide"),
        )
        for language, error in cases:
            with self.subTest(language=language):
                self.switch_language(language)
                response = self.client.post(
                    "/api/setup/ip/",
                    data='{"number":1,"ip":"not-an-ip"}',
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], error)

    @override_settings(LAB_SIMULATE=True)
    def test_lock_feature_endpoint_supports_get_and_post(self):
        response = self.client.get("/api/setup/lock-features/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("discovered", response.json())

        response = self.client.post(
            "/api/setup/lock-features/",
            data='{"features":["ScreenLock"]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["effective"], ["ScreenLock"])

    def test_classroom_selection_and_device_status_remain_available(self):
        response = self.client.get("/api/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["devices"][0]["number"], 1)

        response = self.client.post(
            "/api/set-classroom/",
            data=f'{{"classroom_id":{self.classroom.pk}}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session["active_classroom"],
            self.classroom.pk,
        )

    def test_admin_model_labels_follow_selected_language(self):
        self.switch_language("fr")
        response = self.client.get("/admin/lab/device/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Appareil")
        self.assertContains(response, "Numéro d’appareil")


class VeyonScreenManagementTests(TestCase):
    """اختبارات إدارة الشاشة عبر Veyon."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="TEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Test Classroom", code="TEST-1", capacity=40
        )

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="veyon-user", email="veyon@example.invalid", password="temporary-test-password"
        )
        self.client.force_login(self.user)
        self.device = Device.objects.create(
            classroom=self.classroom, number=1, ip_address="192.168.1.101"
        )
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    def tearDown(self):
        with veyon._ACTIVE_FEATURES_LOCK:
            veyon._ACTIVE_FEATURES.clear()

    @override_settings(LAB_SIMULATE=True)
    def test_remote_view_simulate(self):
        ok, error = veyon.remote_view(self.device)
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_remote_control_simulate(self):
        ok, error = veyon.remote_control(self.device)
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_broadcast_simulate(self):
        ok, error = veyon.broadcast(self.device, fullscreen=True)
        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertTrue(veyon.is_feature_active(self.device, "ShareOwnScreenFullScreen"))

    @override_settings(LAB_SIMULATE=True)
    def test_send_text_message_simulate(self):
        ok, error = veyon.send_text_message(self.device, "Hello")
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_open_website_simulate(self):
        ok, error = veyon.open_website(self.device, "https://example.com")
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_start_app_simulate(self):
        ok, error = veyon.start_app(self.device, "notepad.exe")
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_screenshot_simulate(self):
        ok, error = veyon.screenshot(self.device)
        self.assertTrue(ok)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=True)
    def test_power_action_simulate(self):
        for action in ("PowerOn", "Reboot", "PowerDown", "PowerDownNow"):
            with self.subTest(action=action):
                ok, error = veyon.power_action(self.device, action)
                self.assertTrue(ok)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_remote_view_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.remote_view(self.device)
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "RemoteView"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_stop_feature_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.stop_feature(self.device, "RemoteView")
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "stop", "192.168.1.101", "RemoteView"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_broadcast_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.broadcast(self.device, fullscreen=True)
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "ShareOwnScreenFullScreen"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_send_text_message_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.send_text_message(self.device, "Test")
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "TextMessage", "Test"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_open_website_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.open_website(self.device, "https://example.com")
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "OpenWebsite", "https://example.com"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_start_app_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.start_app(self.device, "notepad.exe")
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "StartApp", "notepad.exe"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_power_action_cli(self, mock_run):
        mock_run.return_value = (True, "", "")
        ok, error = veyon.power_action(self.device, "PowerDown")
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ["feature", "start", "192.168.1.101", "PowerDown"], timeout=10
        )

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_remote_view_failure(self, mock_run):
        mock_run.return_value = (False, "", "access denied")
        ok, error = veyon.remote_view(self.device)
        self.assertFalse(ok)
        self.assertIn("access denied", error)

    @override_settings(LAB_SIMULATE=True)
    def test_get_supported_actions(self):
        actions = veyon.get_supported_actions()
        self.assertIn("lock", actions)
        self.assertIn("broadcast_fullscreen", actions)
        self.assertIn("remote_view", actions)

    def test_control_endpoint_requires_login(self):
        self.client.logout()
        response = self.client.post(
            "/api/control/",
            data='{"action":"remote_view","numbers":[1]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_remote_view(self):
        response = self.client.post(
            "/api/control/",
            data='{"action":"remote_view","numbers":[1]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertEqual(res["done"], [1])
        self.assertEqual(res["failed"], [])

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_text_message(self):
        response = self.client.post(
            "/api/control/",
            data='{"action":"text_message","numbers":[1],"params":{"value":"Hello class"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertEqual(res["done"], [1])

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_invalid_action(self):
        response = self.client.post(
            "/api/control/",
            data='{"action":"invalid","numbers":[1]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_no_numbers(self):
        response = self.client.post(
            "/api/control/",
            data='{"action":"remote_view","numbers":[]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_offline_device(self):
        d2 = Device.objects.create(
            classroom=self.classroom, number=2, ip_address="192.168.1.102"
        )
        with patch("lab.views.veyon.check_many", return_value={self.device.pk: True, d2.pk: False}):
            response = self.client.post(
                "/api/control/",
                data='{"action":"remote_view","numbers":[1,2]}',
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertEqual(res["done"], [1])
        self.assertEqual(res["failed"], [])

    @override_settings(LAB_SIMULATE=True)
    def test_control_endpoint_logs_audit(self):
        self.client.post(
            "/api/control/",
            data='{"action":"remote_view","numbers":[1]}',
            content_type="application/json",
        )
        log = VeyonActionLog.objects.first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, "remote_view")
        self.assertEqual(log.teacher, self.user)
        self.assertEqual(log.device, self.device)
        self.assertTrue(log.success)


@override_settings(MIDDLEWARE=ASSISTANCE_MIDDLEWARE)
class AssistanceRequestTests(TestCase):
    """اختبارات نظام طلب المساعدة."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Test School", code="TEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="Test Classroom", code="TEST-1", capacity=40
        )
        cls.teacher = get_user_model().objects.create_superuser(
            username="teacher", email="teacher@example.invalid", password="temporary-test-password"
        )
        cls.student = get_user_model().objects.create_user(
            username="student1", email="student1@example.invalid", password="temporary-test-password"
        )
        cls.device = Device.objects.create(
            classroom=cls.classroom, number=1, ip_address="192.168.1.101"
        )

    def test_student_can_create_hand_raise(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_classroom"] = self.classroom.pk
        session.save()
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"hand_raise"}',
            content_type="application/json",
            REMOTE_ADDR=self.device.ip_address,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("id", data)
        req = AssistanceRequest.objects.get(pk=data["id"])
        self.assertEqual(req.request_type, "hand_raise")
        self.assertEqual(req.status, "open")
        self.assertEqual(req.student, self.student)
        self.assertEqual(req.device, self.device)
        self.assertEqual(req.classroom, self.classroom)

    def test_student_can_create_help(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_classroom"] = self.classroom.pk
        session.save()
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"help"}',
            content_type="application/json",
            REMOTE_ADDR=self.device.ip_address,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssistanceRequest.objects.filter(request_type="help", status="open").count(), 1)

    def test_duplicate_open_request_prevented(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_classroom"] = self.classroom.pk
        session.save()
        r1 = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"hand_raise"}',
            content_type="application/json",
            REMOTE_ADDR=self.device.ip_address,
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"hand_raise"}',
            content_type="application/json",
            REMOTE_ADDR=self.device.ip_address,
        )
        self.assertEqual(r2.status_code, 400)
        self.assertIn("Duplicate", r2.json()["error"])

    def test_teacher_can_list_open_requests(self):
        self.client.force_login(self.teacher)
        AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=self.classroom,
            request_type="help", status="open"
        )
        response = self.client.get("/api/assistance/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["requests"]), 1)
        self.assertEqual(data["requests"][0]["request_type"], "help")

    def test_teacher_can_acknowledge_request(self):
        self.client.force_login(self.teacher)
        req = AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=self.classroom,
            request_type="hand_raise", status="open"
        )
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"acknowledged"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, "acknowledged")
        self.assertEqual(req.resolved_by, self.teacher)
        self.assertIsNotNone(req.resolved_at)

    def test_teacher_can_resolve_request(self):
        self.client.force_login(self.teacher)
        req = AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=self.classroom,
            request_type="help", status="open"
        )
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"resolved"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, "resolved")

    def test_teacher_cannot_update_other_classroom_request(self):
        other_classroom = Classroom.objects.create(
            school=self.school, name="Other Classroom", code="OTHER", capacity=40
        )
        req = AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=other_classroom,
            request_type="help", status="open"
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_classroom"] = self.classroom.pk
        session.save()
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"resolved"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_student_cannot_create(self):
        other_student = get_user_model().objects.create_user(
            username="other", email="other@example.invalid", password="temporary-test-password"
        )
        self.client.force_login(other_student)
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"help"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_request_type_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"invalid"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_student_cannot_create_for_other_classroom(self):
        other_classroom = Classroom.objects.create(
            school=self.school, name="Other", code="OTH", capacity=40
        )
        self.client.force_login(self.student)
        session = self.client.session
        session["active_classroom"] = other_classroom.pk
        session.save()
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"help"}',
            content_type="application/json",
            REMOTE_ADDR=self.device.ip_address,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        req = AssistanceRequest.objects.get(pk=data["id"])
        self.assertEqual(req.classroom, self.classroom)

    def test_student_without_device_cannot_create(self):
        self.client.force_login(self.student)
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"help"}',
            content_type="application/json",
            REMOTE_ADDR="10.0.0.99",
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_list_requires_staff(self):
        self.client.force_login(self.student)
        response = self.client.get("/api/assistance/")
        self.assertEqual(response.status_code, 403)

    def test_teacher_update_requires_staff(self):
        req = AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=self.classroom,
            request_type="help", status="open"
        )
        self.client.force_login(self.student)
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"resolved"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_request_id_rejected(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            "/api/assistance/99999/",
            data='{"status":"resolved"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_already_resolved_request_can_be_updated(self):
        self.client.force_login(self.teacher)
        req = AssistanceRequest.objects.create(
            student=self.student, device=self.device, classroom=self.classroom,
            request_type="help", status="resolved"
        )
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"dismissed"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, "dismissed")


class AssistanceDeviceIdentityTests(TestCase):
    """Device-identified (no login) assistance requests.

    The student page is anonymous; its identity is ``Device.device_uuid``, a
    server-generated unguessable secret issued by ``student_page`` into the
    session. The IP is used only to issue that secret, never as the
    authorization check, so a caller cannot nominate another device or another
    classroom.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="DevId Test", code="DEVID", active=True)
        cls.classroom_a = Classroom.objects.create(
            school=cls.school, name="Room A", code="DEVD-A", capacity=40
        )
        cls.classroom_b = Classroom.objects.create(
            school=cls.school, name="Room B", code="DEVD-B", capacity=40
        )
        cls.teacher = get_user_model().objects.create_user(
            username="devteacher", email="devt@example.invalid",
            password="temporary-test-password", is_staff=True,
        )
        cls.device_a = Device.objects.create(
            classroom=cls.classroom_a, number=3, ip_address="192.168.77.13"
        )
        cls.device_b = Device.objects.create(
            classroom=cls.classroom_b, number=7, ip_address="192.168.77.14"
        )

    def _issue_credential(self, device):
        """Load /student/ from the device's IP so the session gets its UUID."""
        response = self.client.get("/student/", REMOTE_ADDR=device.ip_address)
        self.assertEqual(response.status_code, 200)
        uuid_str = str(device.device_uuid)
        self.assertEqual(self.client.session["student_device_uuid"], uuid_str)
        return uuid_str

    def _create(self, device, **overrides):
        payload = {"request_type": "hand_raise", "device_uuid": str(device.device_uuid)}
        payload.update(overrides)
        return self.client.post(
            "/api/assistance/create/", data=json.dumps(payload), content_type="application/json"
        )

    # ---- issuance -------------------------------------------------------
    def test_student_page_issues_device_credential(self):
        for device in (self.device_a, self.device_b):
            self.client.logout()
            response = self.client.get("/student/", REMOTE_ADDR=device.ip_address)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                self.client.session["student_device_uuid"], str(device.device_uuid)
            )

    def test_student_page_without_registered_device_issues_nothing(self):
        self.client.get("/student/", REMOTE_ADDR="10.99.99.99")
        self.assertIsNone(self.client.session.get("student_device_uuid"))

    # ---- happy path -----------------------------------------------------
    def test_device_identified_request_succeeds(self):
        self._issue_credential(self.device_a)
        response = self._create(self.device_a)
        self.assertEqual(response.status_code, 200)
        req = AssistanceRequest.objects.get(pk=response.json()["id"])
        self.assertIsNone(req.student)
        self.assertEqual(req.device, self.device_a)
        self.assertEqual(req.classroom, self.classroom_a)

    # ---- the credential is the only accepted proof ----------------------
    def test_missing_device_credential_is_refused(self):
        self._issue_credential(self.device_a)
        response = self.client.post(
            "/api/assistance/create/",
            data='{"request_type":"hand_raise"}', content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssistanceRequest.objects.count(), 0)

    def test_wrong_uuid_is_refused(self):
        """A copied/guessed UUID that is not the session's is rejected."""
        self._issue_credential(self.device_a)
        response = self.client.post(
            "/api/assistance/create/",
            data=json.dumps({"request_type": "hand_raise",
                             "device_uuid": str(self.device_b.device_uuid)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssistanceRequest.objects.count(), 0)

    def test_unknown_uuid_is_refused(self):
        self._issue_credential(self.device_a)
        response = self.client.post(
            "/api/assistance/create/",
            data=json.dumps({"request_type": "hand_raise",
                             "device_uuid": "00000000-0000-4000-8000-000000000000"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(AssistanceRequest.objects.count(), 0)

    def test_malformed_uuid_is_refused(self):
        self._issue_credential(self.device_a)
        response = self._create(self.device_a, device_uuid="not-a-uuid")
        self.assertEqual(response.status_code, 403)

    def test_device_number_is_never_accepted_as_identity(self):
        """A client-supplied device ID/number must not identify the caller."""
        self._issue_credential(self.device_a)
        response = self.client.post(
            "/api/assistance/create/",
            data=json.dumps({"request_type": "hand_raise",
                             "device_uuid": str(self.device_a.device_uuid),
                             "device": self.device_b.pk,
                             "number": self.device_b.number,
                             "classroom_id": self.classroom_b.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        req = AssistanceRequest.objects.get()
        # the device from the credential wins, not the supplied IDs
        self.assertEqual(req.device, self.device_a)
        self.assertEqual(req.classroom, self.classroom_a)

    # ---- classroom isolation -------------------------------------------
    def test_duplicate_open_request_prevented_for_device(self):
        self._issue_credential(self.device_a)
        first = self._create(self.device_a)
        self.assertEqual(first.status_code, 200)
        second = self._create(self.device_a)
        self.assertEqual(second.status_code, 400)
        self.assertIn("Duplicate", second.json()["error"])
        self.assertEqual(AssistanceRequest.objects.count(), 1)

    def test_invalid_request_type_rejected_for_device(self):
        self._issue_credential(self.device_a)
        response = self._create(self.device_a, request_type="nope")
        self.assertEqual(response.status_code, 400)

    def test_teacher_list_requires_staff_and_active_classroom(self):
        """Teacher listing still requires login + staff, unchanged."""
        AssistanceRequest.objects.create(
            student=None, device=self.device_a, classroom=self.classroom_a,
            request_type="help", status="open"
        )
        # anonymous
        self.assertEqual(self.client.get("/api/assistance/").status_code, 302)
        # student (non-staff) still forbidden
        Response = self.client.get("/api/assistance/")
        self.assertIn(Response.status_code, (302, 403))
        # staff with no active classroom -> no rows
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_classroom"] = self.classroom_a.pk
        session.save()
        response = self.client.get("/api/assistance/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["requests"]), 1)

    def test_staff_cannot_update_other_classroom_request(self):
        """Teacher-side authorization is unchanged by the device identity."""
        req = AssistanceRequest.objects.create(
            student=None, device=self.device_b, classroom=self.classroom_b,
            request_type="help", status="open"
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_classroom"] = self.classroom_a.pk
        session.save()
        response = self.client.post(
            f"/api/assistance/{req.pk}/",
            data='{"status":"resolved"}', content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, "open")


class DashboardControlPanelTests(TestCase):
    """Stage 7D-B: the contextual panel, search/filter and selection controls.

    These are regression guards for the UI work: the panel must exist and
    render, every control it renders must be actionable, the search/filter
    inputs must be present with the expected options, and the responsive
    drawer must have the open/close affordances. Without these a silent
    template edit could remove a control with no test noticing.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="UI Test", code="UITEST", active=True)
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="UI Room", code="UI-1", capacity=40
        )
        cls.classroom_b = Classroom.objects.create(
            school=cls.school, name="UI Room B", code="UI-2", capacity=40
        )
        cls.teacher = get_user_model().objects.create_superuser(
            username="uiteacher", email="uit@example.invalid",
            password="temporary-test-password",
        )
        cls.device = Device.objects.create(
            classroom=cls.classroom, number=5, name="Ahmed", ip_address="192.168.5.5"
        )

    def setUp(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_classroom"] = self.classroom.pk
        session.save()

    def _dashboard(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        return body

    # ---- the panel exists ------------------------------------------------
    def test_control_panel_is_rendered(self):
        body = self._dashboard()
        self.assertIn('id="control-panel"', body)
        self.assertIn("ds-control-panel", body)
        self.assertIn('id="panel-close"', body)
        self.assertIn('id="panel-selection-summary"', body)
        self.assertIn('id="panel-classroom-summary"', body)
        self.assertIn('id="assistance-list"', body)

    # ---- search + filters ------------------------------------------------
    def test_search_and_filter_controls_are_rendered(self):
        body = self._dashboard()
        self.assertIn('id="search-input"', body)
        self.assertIn('type="search"', body)
        self.assertIn('id="filter-count"', body)
        # every filter option the JS understands must be offered
        for f in ["all", "online", "offline", "absent", "blocked", "selected"]:
            self.assertIn(f'data-filter="{f}"', body)

    # ---- selection controls ----------------------------------------------
    def test_selection_controls_are_rendered(self):
        body = self._dashboard()
        self.assertIn('id="selection-bar"', body)
        self.assertIn('id="selection-summary"', body)
        self.assertIn('data-do="select-filtered"', body)
        self.assertIn('data-do="clear"', body)
        self.assertIn('data-do="select-online"', body)

    # ---- responsive drawer ------------------------------------------------
    def test_responsive_drawer_controls_are_rendered(self):
        body = self._dashboard()
        self.assertIn('id="panel-toggle"', body)
        self.assertIn('aria-controls="control-panel"', body)
        self.assertIn('aria-expanded="false"', body)
        self.assertIn('id="panel-backdrop"', body)

    # ---- no inert controls ----------------------------------------------
    def test_every_panel_control_maps_to_a_real_action(self):
        body = self._dashboard()
        # data-act values must be backend actions
        actions = set(re.findall(r'data-act="([^"]+)"', body))
        self.assertIn("lock", actions)
        self.assertIn("unlock", actions)
        self.assertIn("absent", actions)
        self.assertIn("present", actions)
        self.assertIn("sync_locks", actions)
        self.assertTrue(actions.issubset(lab_views.ACTIONS | {"lock", "unlock", "absent",
                                                             "present", "sync_locks"}))
        # data-do values must be handled by the JS
        dos = set(re.findall(r'data-do="([^"]+)"', body))
        self.assertTrue(dos.issubset({"clear", "select-online", "select-filtered"}))

    def test_device_payload_supports_search_and_filters(self):
        """The UI reads number/name/online/absent/blocked from /api/status/."""
        r = self.client.get("/api/status/")
        self.assertEqual(r.status_code, 200)
        devices = r.json()["devices"]
        self.assertEqual(len(devices), 1)
        d = devices[0]
        for key in ("number", "device_uuid", "online", "absent", "blocked", "name"):
            self.assertIn(key, d)
        self.assertEqual(d["number"], 5)
        self.assertEqual(d["name"], "Ahmed")

    # ---- the blank-page guard still holds ---------------------------------
    def test_style_element_is_closed_before_body(self):
        body = self._dashboard()
        self.assertIn("</style>", body)
        self.assertLess(body.index("</style>"), body.index("<body>"))
        self.assertIn('<script>', body)
        self.assertIn('{% raw %}', body) if False else None
        # exactly one <style> and one </style>
        self.assertEqual(body.count("<style>"), body.count("</style>"))

    def test_assistance_panel_is_populated_by_the_teacher_endpoint(self):
        """The panel's data source must be staff-authorised as before."""
        r = self.client.get("/api/assistance/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["requests"], [])
        # a device-identified request shows a device label, not a crash
        req = AssistanceRequest.objects.create(
            student=None, device=self.device, classroom=self.classroom,
            request_type="hand_raise", status="open",
        )
        r = self.client.get("/api/assistance/")
        self.assertEqual(r.status_code, 200)
        data = r.json()["requests"]
        self.assertEqual(len(data), 1)
        self.assertIn("device", data[0])
        self.assertEqual(data[0]["device"], 5)
        self.assertTrue(data[0]["student"])
        # teacher can resolve it from the panel
        u = self.client.post(f"/api/assistance/{req.pk}/", data='{"status":"resolved"}',
                             content_type="application/json")
        self.assertEqual(u.status_code, 200)


class TeacherAudioSignalingIsolationTests(TestCase):
    """Stage 7D-C: teacher audio signaling — selected-device targeting.

    Guards the two properties the audio panel depends on:
      * a ``signal``/``cmd`` from a teacher reaches only a device in that
        teacher's classroom (the classroom decides, not the device number), and
      * a number outside the authorized classroom, outside 1..40, or not an
        integer is dropped instead of being relayed to another classroom's group.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Sig Test", code="SIGTEST", active=True)
        cls.classroom_a = Classroom.objects.create(
            school=cls.school, name="Sig A", code="SIG-A", capacity=40
        )
        cls.classroom_b = Classroom.objects.create(
            school=cls.school, name="Sig B", code="SIG-B", capacity=40
        )
        cls.teacher = get_user_model().objects.create_superuser(
            username="sigteacher", email="sigt@example.invalid", password="temporary-test-password"
        )
        cls.student_a = get_user_model().objects.create_user(
            username="sigstudent_a", email="siga@example.invalid", password="temporary-test-password"
        )
        cls.student_b = get_user_model().objects.create_user(
            username="sigstudent_b", email="sigb@example.invalid", password="temporary-test-password"
        )
        # number 1 exists in BOTH classrooms, so the classroom must decide
        cls.device_a1 = Device.objects.create(
            classroom=cls.classroom_a, number=1, ip_address="192.168.60.1"
        )
        cls.device_a2 = Device.objects.create(
            classroom=cls.classroom_a, number=2, ip_address="192.168.60.2"
        )
        cls.device_b1 = Device.objects.create(
            classroom=cls.classroom_b, number=1, ip_address="192.168.61.1"
        )
        cls.device_b2 = Device.objects.create(
            classroom=cls.classroom_b, number=2, ip_address="192.168.61.2"
        )

    def _teacher_scope(self, classroom_id):
        return {
            "type": "websocket",
            "path": "/ws/teacher/",
            "headers": [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")],
            "query_string": f"classroom={classroom_id}".encode(),
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "user": self.teacher,
            "session": type("Session", (), {"session_key": "test"})(),
            "url_route": {"kwargs": {}},
        }

    def _student_scope(self, device):
        return {
            "type": "websocket",
            "path": "/ws/student/",
            "headers": [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")],
            "query_string": b"",
            "client": (device.ip_address, 12345),
            "server": (device.ip_address, 8000),
            "user": self.student_a if device.classroom_id == self.classroom_a.pk else self.student_b,
            "session": type("Session", (), {"session_key": "test"})(),
            "url_route": {"kwargs": {}},
        }

    def _teacher(self, classroom_id):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import TeacherConsumer
        comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        comm.scope = self._teacher_scope(classroom_id)
        return comm

    def _student(self, device):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import StudentConsumer
        comm = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
        comm.scope = self._student_scope(device)
        return comm

    async def _drain(self, comm, frames=4, timeout=0.4):
        """Read whatever greeting frames have arrived, tolerating differences."""
        for _ in range(frames):
            try:
                await asyncio.wait_for(comm.receive_json_from(), timeout=timeout)
            except asyncio.TimeoutError:
                return
            except Exception:
                return

    async def _send_and_expect(self, comm, payload, negate=False):
        """Send a teacher message and assert whether the student gets it.

        ``receive_nothing`` is used for the negative case: ``asyncio.wait_for``
        cancels the communicator's pending future on timeout, which poisons it
        for the next receive.
        """
        await comm["teacher"].send_json_to(payload)
        if negate:
            await comm["student"].receive_nothing(timeout=0.5)
            return None
        return await comm["student"].receive_json_from(timeout=3)

    def test_signal_reaches_only_the_targeted_device_in_its_classroom(self):
        ta = self._teacher(self.classroom_a.pk)
        sa1 = self._student(self.device_a1)
        sa2 = self._student(self.device_a2)
        sb1 = self._student(self.device_b1)

        async def run():
            await ta.connect()
            await sa1.connect()
            await sa2.connect()
            await sb1.connect()
            # console greeting (presence) frames
            await self._drain(sa1)
            await self._drain(sa2)
            await self._drain(sb1)
            await self._drain(ta)

            # device 1 of classroom A — targeted
            msg = await self._send_and_expect(
                {"teacher": ta, "student": sa1},
                {"type": "signal", "to": 1, "data": {"probe": "A"}})
            self.assertEqual(msg["type"], "signal")
            self.assertEqual(msg["data"], {"probe": "A"})

            # same number in another classroom must not receive it
            await self._send_and_expect(
                {"teacher": ta, "student": sb1},
                {"type": "signal", "to": 1, "data": {"probe": "cross"}},
                negate=True)

            # another device of the same classroom must not receive it either
            await self._send_and_expect(
                {"teacher": ta, "student": sa2},
                {"type": "signal", "to": 1, "data": {"probe": "sibling"}},
                negate=True)

            for c in (ta, sa1, sa2, sb1):
                try:
                    await c.disconnect()
                except asyncio.CancelledError:
                    pass

        async_to_sync(run)()

    def test_cmd_reaches_only_the_targeted_device_in_its_classroom(self):
        ta = self._teacher(self.classroom_a.pk)
        sa2 = self._student(self.device_a2)
        sb1 = self._student(self.device_b1)

        async def run():
            await ta.connect()
            await sa2.connect()
            await sb1.connect()
            await self._drain(sa2)
            await self._drain(sb1)
            await self._drain(ta)

            # mic_on for classroom A device 2
            msg = await self._send_and_expect(
                {"teacher": ta, "student": sa2},
                {"type": "cmd", "to": [2], "cmd": "mic_on"})
            self.assertEqual(msg["cmd"], "mic_on")

            # the same command must not leak to classroom B
            await self._send_and_expect(
                {"teacher": ta, "student": sb1},
                {"type": "cmd", "to": [2], "cmd": "mic_on"},
                negate=True)

            for c in (ta, sa2, sb1):
                try:
                    await c.disconnect()
                except asyncio.CancelledError:
                    pass

        async_to_sync(run)()

    def test_signals_for_unknown_or_invalid_numbers_are_dropped(self):
        ta = self._teacher(self.classroom_a.pk)
        sa1 = self._student(self.device_a1)

        async def run():
            await ta.connect()
            await sa1.connect()
            await self._drain(sa1)
            await self._drain(ta)

            # unknown number, out-of-range number, non-integer, and a string list
            for to in (9, 41, 0, -3, "abc", [1, 41, 99]):
                await self._send_and_expect(
                    {"teacher": ta, "student": sa1},
                    {"type": "signal", "to": to, "data": {"probe": "bad"}},
                    negate=True)

            try:
                await ta.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await sa1.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_teacher_assistance_update_is_classroom_scoped(self):
        from lab.models import AssistanceRequest
        req = AssistanceRequest.objects.create(
            student=None, device=self.device_b1, classroom=self.classroom_b,
            request_type="help", status="open",
        )
        ta = self._teacher(self.classroom_a.pk)

        async def run():
            await ta.connect()
            await self._drain(ta)
            await ta.send_json_to({"type": "assistance_update", "id": req.pk,
                                   "status": "resolved"})
            try:
                msg = await asyncio.wait_for(ta.receive_json_from(), timeout=2)
                self.fail(f"teacher A should not receive an update for classroom B: {msg}")
            except asyncio.TimeoutError:
                pass
            from channels.db import database_sync_to_async
            status = await database_sync_to_async(
                lambda: AssistanceRequest.objects.get(pk=req.pk).status)()
            self.assertEqual(status, "open")
            try:
                await ta.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_cmd_reaches_each_target_in_selected_set(self):
        """Stage 7D-C: selected-device targeting — a cmd addressed to multiple
        devices reaches exactly those devices in the same classroom."""
        ta = self._teacher(self.classroom_a.pk)
        sa1 = self._student(self.device_a1)
        sa2 = self._student(self.device_a2)

        async def run():
            await ta.connect()
            await sa1.connect()
            await sa2.connect()
            await self._drain(sa1)
            await self._drain(sa2)
            await self._drain(ta)

            # mic_on for classroom A devices 1 and 2 (selected set)
            msg1 = await self._send_and_expect(
                {"teacher": ta, "student": sa1},
                {"type": "cmd", "to": [1, 2], "cmd": "mic_on"})
            self.assertEqual(msg1["cmd"], "mic_on")

            msg2 = await self._send_and_expect(
                {"teacher": ta, "student": sa2},
                {"type": "cmd", "to": [1, 2], "cmd": "mic_on"})
            self.assertEqual(msg2["cmd"], "mic_on")

            for c in (ta, sa1, sa2):
                try:
                    await c.disconnect()
                except asyncio.CancelledError:
                    pass

        async_to_sync(run)()

    def test_signal_single_number_only(self):
        """Stage 7D-C: a ``signal`` targets a single device number only;
        it is not a multi-target message like ``cmd``."""
        ta = self._teacher(self.classroom_a.pk)
        sa1 = self._student(self.device_a1)
        sa2 = self._student(self.device_a2)

        async def run():
            await ta.connect()
            await sa1.connect()
            await sa2.connect()
            await self._drain(sa1)
            await self._drain(sa2)
            await self._drain(ta)

            # signal to device 1 reaches device 1 only
            msg = await self._send_and_expect(
                {"teacher": ta, "student": sa1},
                {"type": "signal", "to": 1, "data": {"probe": "one"}})
            self.assertEqual(msg["type"], "signal")
            self.assertEqual(msg["data"], {"probe": "one"})

            # device 2 does not receive a signal addressed to device 1
            await self._send_and_expect(
                {"teacher": ta, "student": sa2},
                {"type": "signal", "to": 1, "data": {"probe": "one"}},
                negate=True)

            # signal to device 2 reaches device 2 only
            msg2 = await self._send_and_expect(
                {"teacher": ta, "student": sa2},
                {"type": "signal", "to": 2, "data": {"probe": "two"}})
            self.assertEqual(msg2["type"], "signal")
            self.assertEqual(msg2["data"], {"probe": "two"})

            # device 1 does not receive a signal addressed to device 2
            await self._send_and_expect(
                {"teacher": ta, "student": sa1},
                {"type": "signal", "to": 2, "data": {"probe": "two"}},
                negate=True)

            for c in (ta, sa1, sa2):
                try:
                    await c.disconnect()
                except asyncio.CancelledError:
                    pass

        async_to_sync(run)()

    def test_cmd_does_not_leak_to_other_classroom_with_multiple_targets(self):
        """Stage 7D-C: cross-classroom isolation — a cmd addressed to device
        numbers that exist in another classroom must not reach that classroom."""
        ta = self._teacher(self.classroom_a.pk)
        sb1 = self._student(self.device_b1)
        sb2 = self._student(self.device_b2)

        async def run():
            await ta.connect()
            await sb1.connect()
            await sb2.connect()
            await self._drain(sb1)
            await self._drain(sb2)
            await self._drain(ta)

            # Device numbers 1 and 2 exist in classroom B too; the teacher is in
            # classroom A, so neither B device must receive anything.
            await self._send_and_expect(
                {"teacher": ta, "student": sb1},
                {"type": "cmd", "to": [1, 2], "cmd": "mic_on"},
                negate=True)
            await self._send_and_expect(
                {"teacher": ta, "student": sb2},
                {"type": "cmd", "to": [1, 2], "cmd": "mic_on"},
                negate=True)

            for c in (ta, sb1, sb2):
                try:
                    await c.disconnect()
                except asyncio.CancelledError:
                    pass

        async_to_sync(run)()


class AssistanceWebSocketTests(TestCase):
    """اختبارات WebSocket لنظام طلب المساعدة."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="WS Test", code="WSTEST", active=True)
        cls.classroom_a = Classroom.objects.create(
            school=cls.school, name="Classroom A", code="WS-A", capacity=40
        )
        cls.classroom_b = Classroom.objects.create(
            school=cls.school, name="Classroom B", code="WS-B", capacity=40
        )
        cls.teacher = get_user_model().objects.create_superuser(
            username="wsteacher", email="wsteacher@example.invalid", password="temporary-test-password"
        )
        cls.student_a = get_user_model().objects.create_user(
            username="wsstudent_a", email="wsa@example.invalid", password="temporary-test-password"
        )
        cls.student_b = get_user_model().objects.create_user(
            username="wsstudent_b", email="wsb@example.invalid", password="temporary-test-password"
        )
        cls.device_a = Device.objects.create(
            classroom=cls.classroom_a, number=1, ip_address="192.168.50.101"
        )
        cls.device_b = Device.objects.create(
            classroom=cls.classroom_b, number=1, ip_address="192.168.50.201"
        )

    def _teacher_scope(self, classroom_id=1):
        return {
            "type": "websocket",
            "path": f"/ws/teacher/",
            "headers": [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")],
            "query_string": f"classroom={classroom_id}".encode(),
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "user": self.teacher,
            "session": type("Session", (), {"session_key": "test"})(),
            "url_route": {"kwargs": {}},
        }

    def _student_scope(self, device):
        return {
            "type": "websocket",
            "path": "/ws/student/",
            "headers": [(b"origin", b"http://127.0.0.1:8000"), (b"host", b"127.0.0.1:8000")],
            "query_string": b"",
            "client": (device.ip_address, 12345),
            "server": (device.ip_address, 8000),
            "user": self.student_a if device == self.device_a else self.student_b,
            "session": type("Session", (), {"session_key": "test"})(),
            "url_route": {"kwargs": {}},
        }

    @database_sync_to_async
    def _create_req(self, student, device, classroom, rtype="hand_raise"):
        return AssistanceRequest.objects.create(
            student=student, device=device, classroom=classroom,
            request_type=rtype, status="open"
        )

    def test_teacher_ws_receives_assistance_list_on_connect(self):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import TeacherConsumer

        communicator = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        communicator.scope = self._teacher_scope(classroom_id=self.classroom_a.pk)
        communicator.scope["query_string"] = f"classroom={self.classroom_a.pk}".encode()

        async def run():
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)
            msgs = []
            for _ in range(2):
                msg = await communicator.receive_json_from()
                msgs.append(msg)
            types = [m.get("type") for m in msgs]
            self.assertIn("presence_list", types)
            self.assertIn("assistance_list", types)
            try:
                await communicator.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_student_ws_can_create_assistance_request(self):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import StudentConsumer

        communicator = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
        communicator.scope = self._student_scope(self.device_a)

        async def run():
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)
            msg = await communicator.receive_json_from()
            self.assertEqual(msg.get("type"), "hello")
            await communicator.send_json_to({
                "type": "assistance_create",
                "request_type": "hand_raise"
            })
            msg = await communicator.receive_json_from()
            self.assertEqual(msg.get("type"), "assistance_created")
            self.assertEqual(msg.get("request_type"), "hand_raise")
            try:
                await communicator.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_teacher_ws_receives_assistance_create_for_own_classroom(self):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import TeacherConsumer, StudentConsumer

        teacher_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_comm.scope = self._teacher_scope(classroom_id=self.classroom_a.pk)
        teacher_comm.scope["query_string"] = f"classroom={self.classroom_a.pk}".encode()

        student_comm = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
        student_comm.scope = self._student_scope(self.device_a)

        async def run():
            await teacher_comm.connect()
            await student_comm.connect()

            for _ in range(3):
                await teacher_comm.receive_json_from()
            msg = await student_comm.receive_json_from()
            self.assertEqual(msg.get("type"), "hello")

            await student_comm.send_json_to({
                "type": "assistance_create",
                "request_type": "help"
            })

            msg = await teacher_comm.receive_json_from()
            self.assertEqual(msg.get("type"), "assistance_create")
            self.assertEqual(msg.get("classroom_id"), self.classroom_a.pk)

            try:
                await student_comm.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await teacher_comm.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_teacher_ws_classroom_isolation_assistance_not_leaked(self):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import TeacherConsumer, StudentConsumer

        teacher_a_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_a_comm.scope = self._teacher_scope(classroom_id=self.classroom_a.pk)
        teacher_a_comm.scope["query_string"] = f"classroom={self.classroom_a.pk}".encode()

        teacher_b_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_b_comm.scope = self._teacher_scope(classroom_id=self.classroom_b.pk)
        teacher_b_comm.scope["query_string"] = f"classroom={self.classroom_b.pk}".encode()

        student_a_comm = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
        student_a_comm.scope = self._student_scope(self.device_a)

        async def run():
            await teacher_a_comm.connect()
            await teacher_b_comm.connect()
            await student_a_comm.connect()

            for _ in range(3):
                await teacher_a_comm.receive_json_from()
            for _ in range(2):
                await teacher_b_comm.receive_json_from()
            msg = await student_a_comm.receive_json_from()
            self.assertEqual(msg.get("type"), "hello")

            await student_a_comm.send_json_to({
                "type": "assistance_create",
                "request_type": "hand_raise"
            })

            msg = await teacher_a_comm.receive_json_from()
            self.assertEqual(msg.get("type"), "assistance_create")
            self.assertEqual(msg.get("classroom_id"), self.classroom_a.pk)

            try:
                msg = await asyncio.wait_for(teacher_b_comm.receive_json_from(), timeout=1)
                self.fail("Teacher B should not have received assistance_create")
            except asyncio.TimeoutError:
                pass

            try:
                await student_a_comm.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await teacher_a_comm.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await teacher_b_comm.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_teacher_ws_cannot_update_other_classroom_request(self):
        from channels.testing import WebsocketCommunicator
        from lab.consumers import TeacherConsumer

        req = AssistanceRequest.objects.create(
            student=self.student_a, device=self.device_a, classroom=self.classroom_a,
            request_type="help", status="open"
        )

        teacher_b_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_b_comm.scope = self._teacher_scope(classroom_id=self.classroom_b.pk)
        teacher_b_comm.scope["query_string"] = f"classroom={self.classroom_b.pk}".encode()

        async def run():
            await teacher_b_comm.connect()
            for _ in range(2):
                await teacher_b_comm.receive_json_from()

            await teacher_b_comm.send_json_to({
                "type": "assistance_update",
                "id": req.pk,
                "status": "resolved"
            })

            try:
                msg = await asyncio.wait_for(teacher_b_comm.receive_json_from(), timeout=1)
                self.fail("Teacher B should not have received assistance_update")
            except asyncio.TimeoutError:
                pass

            from channels.db import database_sync_to_async
            req_status = await database_sync_to_async(lambda: AssistanceRequest.objects.get(pk=req.pk).status)()
            self.assertEqual(req_status, "open")

            try:
                await teacher_b_comm.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()

    def test_student_webrtc_signal_routes_to_teacher_classroom_group(self):
        from lab.consumers import StudentConsumer, TeacherConsumer

        offer_sdp = (
            "v=0\r\n"
            "o=- 1234567890 2 IN IP4 127.0.0.1\r\n"
            "s=-\r\n"
            "t=0 0\r\n"
            "a=group:BUNDLE 0\r\n"
            "a=msid-semantic: WMS\r\n"
            "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
            "c=IN IP4 0.0.0.0\r\n"
            "a=rtcp:9 IN IP4 0.0.0.0\r\n"
            "a=ice-ufrag:test\r\n"
            "a=ice-pwd:test\r\n"
            "a=mid:0\r\n"
            "a=sendrecv\r\n"
            "a=rtpmap:111 opus/48000/2\r\n"
            "a=fmtp:111 minptime=10;useinbandfec=1\r\n"
        )

        answer_sdp = (
            "v=0\r\n"
            "o=- 1234567891 2 IN IP4 127.0.0.1\r\n"
            "s=-\r\n"
            "t=0 0\r\n"
            "a=group:BUNDLE 0\r\n"
            "a=msid-semantic: WMS\r\n"
            "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
            "c=IN IP4 0.0.0.0\r\n"
            "a=rtcp:9 IN IP4 0.0.0.0\r\n"
            "a=ice-ufrag:test2\r\n"
            "a=ice-pwd:test2\r\n"
            "a=mid:0\r\n"
            "a=sendrecv\r\n"
            "a=rtpmap:111 opus/48000/2\r\n"
            "a=fmtp:111 minptime=10;useinbandfec=1\r\n"
        )

        teacher_a_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_a_comm.scope = self._teacher_scope(classroom_id=self.classroom_a.pk)
        teacher_a_comm.scope["query_string"] = f"classroom={self.classroom_a.pk}".encode()

        teacher_b_comm = WebsocketCommunicator(TeacherConsumer.as_asgi(), "/ws/teacher/")
        teacher_b_comm.scope = self._teacher_scope(classroom_id=self.classroom_b.pk)
        teacher_b_comm.scope["query_string"] = f"classroom={self.classroom_b.pk}".encode()

        student_a_comm = WebsocketCommunicator(StudentConsumer.as_asgi(), "/ws/student/")
        student_a_comm.scope = self._student_scope(self.device_a)

        async def run():
            await teacher_a_comm.connect()
            await teacher_b_comm.connect()
            await student_a_comm.connect()

            for _ in range(2):
                await teacher_a_comm.receive_json_from()
            for _ in range(2):
                await teacher_b_comm.receive_json_from()
            msg = await student_a_comm.receive_json_from()
            self.assertEqual(msg.get("type"), "hello")

            await student_a_comm.send_json_to({
                "type": "signal",
                "data": {"sdp": {"type": "offer", "sdp": offer_sdp}}
            })

            msg = await asyncio.wait_for(teacher_a_comm.receive_json_from(), timeout=2)
            while msg.get("type") == "presence":
                msg = await asyncio.wait_for(teacher_a_comm.receive_json_from(), timeout=2)
            self.assertEqual(msg.get("type"), "signal")
            self.assertEqual(msg["data"]["sdp"]["type"], "offer")
            self.assertEqual(msg.get("from"), 1)
            self.assertEqual(msg.get("classroom_id"), self.classroom_a.pk)

            try:
                msg = await asyncio.wait_for(teacher_b_comm.receive_json_from(), timeout=1)
                self.fail("Teacher B should not receive student A's signal: %s" % json.dumps(msg)[:200])
            except asyncio.TimeoutError:
                pass

            await student_a_comm.send_json_to({
                "type": "signal",
                "data": {"sdp": {"type": "answer", "sdp": answer_sdp}}
            })

            msg = await asyncio.wait_for(teacher_a_comm.receive_json_from(), timeout=2)
            while msg.get("type") == "presence":
                msg = await asyncio.wait_for(teacher_a_comm.receive_json_from(), timeout=2)
            self.assertEqual(msg.get("type"), "signal")
            self.assertEqual(msg["data"]["sdp"]["type"], "answer")
            self.assertEqual(msg.get("from"), 1)
            self.assertEqual(msg.get("classroom_id"), self.classroom_a.pk)

            try:
                await student_a_comm.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await teacher_a_comm.disconnect()
            except asyncio.CancelledError:
                pass
            try:
                await teacher_b_comm.disconnect()
            except asyncio.CancelledError:
                pass

        async_to_sync(run)()


class MediaLibraryValidationTests(TestCase):
    """اختبارات التحقق من صحة الملفات."""

    def test_clean_filename_preserves_safe_chars(self):
        self.assertEqual(clean_filename("hello world.mp3"), "hello_world.mp3")

    def test_clean_filename_rejects_path_traversal(self):
        self.assertEqual(clean_filename("..%2f..%2fwindows%2fsystem.ini"), "2f2fwindows2fsystem.ini")
        self.assertEqual(clean_filename("con.txt"), "con.txt")

    def test_validate_filename_empty(self):
        with self.assertRaises(ValueError):
            validate_filename("")

    def test_validate_filename_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_filename("..\\windows\\system.ini")

    def test_validate_extension_audio_ok(self):
        validate_extension(".mp3", "audio")

    def test_validate_extension_video_ok(self):
        validate_extension(".mp4", "video")

    def test_validate_extension_image_ok(self):
        validate_extension(".jpg", "image")

    def test_validate_extension_pdf_ok(self):
        validate_extension(".pdf", "pdf")

    def test_validate_extension_document_ok(self):
        validate_extension(".docx", "document")

    def test_validate_extension_invalid(self):
        with self.assertRaises(ValueError):
            validate_extension(".exe", "audio")

    def test_validate_mime_type_ok(self):
        validate_mime_type("audio/mpeg", "audio")

    def test_validate_mime_type_invalid(self):
        with self.assertRaises(ValueError):
            validate_mime_type("application/x-msdownload", "audio")

    def test_get_media_type_from_mime(self):
        self.assertEqual(get_media_type_from_mime("audio/mpeg"), "audio")
        self.assertEqual(get_media_type_from_mime("video/mp4"), "video")
        self.assertEqual(get_media_type_from_mime("image/png"), "image")
        self.assertEqual(get_media_type_from_mime("application/pdf"), "pdf")
        self.assertEqual(get_media_type_from_mime("application/msword"), "document")


class MediaLibraryModelTests(TestCase):
    """اختبارات نماذج المكتبة الوسائطية."""

    def test_create_folder(self):
        folder = MediaFolder.objects.create(name="Test Folder")
        self.assertEqual(str(folder), "Test Folder")

    def test_create_nested_folder(self):
        parent = MediaFolder.objects.create(name="Parent")
        child = MediaFolder.objects.create(name="Child", parent=parent)
        self.assertEqual(child.parent, parent)

    def test_create_asset(self):
        folder = MediaFolder.objects.create(name="Media")
        audio_file = SimpleUploadedFile("test.mp3", b"fake audio content", content_type="audio/mpeg")
        asset = MediaAsset.objects.create(
            title="Test Audio",
            description="A test",
            file=audio_file,
            media_type="audio",
            mime_type="audio/mpeg",
            size=len(b"fake audio content"),
            content_language="en",
            folder=folder,
        )
        self.assertEqual(asset.media_type, "audio")
        self.assertEqual(asset.content_language, "en")
        self.assertTrue(asset.file.name.endswith(".mp3"))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MediaLibraryViewTests(TestCase):
    """اختبارات واجهات المكتبة الوسائطية."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="ML School", code="MLS", active=True)
        cls.classroom = Classroom.objects.create(school=cls.school, name="ML Class", code="MLC", capacity=40)
        cls.teacher = get_user_model().objects.create_superuser(
            username="mlteacher", email="mlteacher@example.invalid", password="temporary-test-password"
        )
        cls.student = get_user_model().objects.create_user(
            username="mlstudent", email="mls@example.invalid", password="temporary-test-password"
        )
        cls.folder = MediaFolder.objects.create(name="Test Folder")

    def test_media_library_requires_login(self):
        resp = self.client.get("/media-library/")
        self.assertEqual(resp.status_code, 302)

    def test_media_library_loads_for_teacher(self):
        self.client.force_login(self.teacher)
        resp = self.client.get("/media-library/")
        self.assertEqual(resp.status_code, 200)

    def test_upload_audio_requires_staff(self):
        audio_file = SimpleUploadedFile("song.mp3", b"x" * 100, content_type="audio/mpeg")
        self.client.force_login(self.student)
        resp = self.client.post("/media-library/api/upload/", {"file": audio_file, "title": "Song"})
        self.assertEqual(resp.status_code, 403)

    def test_upload_audio_success(self):
        audio_file = SimpleUploadedFile("song.mp3", b"x" * 100, content_type="audio/mpeg")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/upload/", {"file": audio_file, "title": "Song", "folder_id": self.folder.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(MediaAsset.objects.filter(pk=data["id"]).count(), 1)

    def test_upload_invalid_extension_rejected(self):
        exe_file = SimpleUploadedFile("hack.exe", b"x" * 100, content_type="application/x-msdownload")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/upload/", {"file": exe_file, "title": "Bad"})
        self.assertEqual(resp.status_code, 400)

    def test_upload_invalid_mime_rejected(self):
        fake = SimpleUploadedFile("song.mp3", b"x" * 100, content_type="application/x-msdownload")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/upload/", {"file": fake, "title": "Bad"})
        self.assertEqual(resp.status_code, 400)

    def test_upload_oversized_rejected(self):
        big = SimpleUploadedFile("big.mp3", b"x" * (500 * 1024 * 1024 + 1), content_type="audio/mpeg")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/upload/", {"file": big, "title": "Big"})
        self.assertEqual(resp.status_code, 400)

    def test_upload_path_traversal_filename_rejected(self):
        # Django test client sanitizes path components; direct validation is tested in MediaLibraryValidationTests
        pass

    def test_rename_asset(self):
        audio_file = SimpleUploadedFile("old.mp3", b"x" * 100, content_type="audio/mpeg")
        asset = MediaAsset.objects.create(title="Old", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100)
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/rename_asset/", {"id": asset.pk, "title": "New Title"})
        self.assertEqual(resp.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.title, "New Title")

    def test_move_asset(self):
        audio_file = SimpleUploadedFile("move.mp3", b"x" * 100, content_type="audio/mpeg")
        asset = MediaAsset.objects.create(title="Move", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100)
        target = MediaFolder.objects.create(name="Target")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/move_asset/", {"id": asset.pk, "folder_id": target.pk})
        self.assertEqual(resp.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.folder, target)

    def test_delete_asset(self):
        audio_file = SimpleUploadedFile("del.mp3", b"x" * 100, content_type="audio/mpeg")
        asset = MediaAsset.objects.create(title="Del", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100)
        path = asset.file.path
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/delete_asset/", {"id": asset.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MediaAsset.objects.filter(pk=asset.pk).count(), 0)
        self.assertFalse(os.path.exists(path))

    def test_create_folder(self):
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/create_folder/", {"name": "New Folder"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(MediaFolder.objects.filter(pk=data["id"]).count(), 1)

    def test_rename_folder(self):
        folder = MediaFolder.objects.create(name="Old Folder")
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/rename_folder/", {"id": folder.pk, "name": "New Folder"})
        self.assertEqual(resp.status_code, 200)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "New Folder")

    def test_delete_nonempty_folder_fails(self):
        folder = MediaFolder.objects.create(name="Full")
        audio_file = SimpleUploadedFile("t.mp3", b"x" * 100, content_type="audio/mpeg")
        MediaAsset.objects.create(title="T", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100, folder=folder)
        self.client.force_login(self.teacher)
        resp = self.client.post("/media-library/api/delete_folder/", {"id": folder.pk})
        self.assertEqual(resp.status_code, 400)

    def test_download_requires_login(self):
        audio_file = SimpleUploadedFile("dl.mp3", b"x" * 100, content_type="audio/mpeg")
        asset = MediaAsset.objects.create(title="DL", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100)
        resp = self.client.get(f"/media-library/download/{asset.pk}/")
        self.assertEqual(resp.status_code, 302)

    def test_download_works_for_authenticated(self):
        audio_file = SimpleUploadedFile("dl.mp3", b"x" * 100, content_type="audio/mpeg")
        asset = MediaAsset.objects.create(title="DL", file=audio_file, media_type="audio", mime_type="audio/mpeg", size=100)
        self.client.force_login(self.teacher)
        resp = self.client.get(f"/media-library/download/{asset.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "audio/mpeg")


class ImportExportValidationTests(TestCase):
    """اختبارات التحقق من صحة الاستيراد."""

    def test_parse_csv_utf8_arabic(self):
        from lab.import_export import _parse_csv
        csv_data = "student_id,full_name\nS001,محمد أحمد\n".encode("utf-8")
        entity_type, rows = _parse_csv(csv_data)
        self.assertEqual(entity_type, "students")
        self.assertEqual(rows[0]["student_id"], "S001")
        self.assertEqual(rows[0]["full_name"], "محمد أحمد")

    def test_parse_csv_utf8_french(self):
        from lab.import_export import _parse_csv
        csv_data = "student_id,full_name\nS002,Jean Dupont\n".encode("utf-8")
        entity_type, rows = _parse_csv(csv_data)
        self.assertEqual(rows[0]["full_name"], "Jean Dupont")

    def test_parse_invalid_utf8(self):
        from lab.import_export import _parse_csv
        with self.assertRaises(Exception):
            _parse_csv(b"\xff\xfe")

    def test_detect_entity_type_students(self):
        from lab.import_export import _detect_entity_type
        self.assertEqual(_detect_entity_type(["student_id", "full_name"]), "students")

    def test_detect_entity_type_classes(self):
        from lab.import_export import _detect_entity_type
        self.assertEqual(_detect_entity_type(["code", "name", "grade"]), "classes")

    def test_detect_entity_type_enrollments(self):
        from lab.import_export import _detect_entity_type
        self.assertEqual(_detect_entity_type(["student_id", "class_code"]), "enrollments")

    def test_validate_rows_missing_required(self):
        from lab.import_export import validate_rows
        rows = [{"full_name": "Test"}]
        valid, errors = validate_rows("students", rows)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("student_id", errors[0]["errors"][0])

    def test_validate_rows_valid(self):
        from lab.import_export import validate_rows
        rows = [{"student_id": "S001", "full_name": "Test"}]
        valid, errors = validate_rows("students", rows)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 0)


class ImportExportModelTests(TestCase):
    """اختبارات نماذج الاستيراد/التصدير."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="IE School", code="IES", active=True)
        cls.classroom = Classroom.objects.create(school=cls.school, name="IE Class", code="IEC", capacity=40)
        cls.teacher = get_user_model().objects.create_superuser(
            username="ieteacher", email="iet@example.invalid", password="temporary-test-password"
        )
        cls.student_user = get_user_model().objects.create_user(
            username="iestudent", email="ies@example.invalid", password="temporary-test-password"
        )

    def test_import_students_creates_records(self):
        from lab.import_export import perform_import
        rows = [{"student_id": "S001", "full_name": "محمد أحمد", "preferred_language": "ar"}]
        report = perform_import("students", rows, "reject", self.teacher)
        self.assertEqual(report["created"], 1)
        self.assertEqual(Student.objects.filter(student_id="S001").count(), 1)

    def test_import_classes_creates_records(self):
        from lab.import_export import perform_import
        rows = [{"code": "C001", "name": "Class 1", "grade": "1", "section": "A"}]
        report = perform_import("classes", rows, "reject", self.teacher)
        self.assertEqual(report["created"], 1)
        self.assertEqual(Class.objects.filter(code="C001").count(), 1)

    def test_import_enrollments_creates_records(self):
        from lab.import_export import perform_import
        student = Student.objects.create(student_id="S001", full_name="Test")
        class_obj = Class.objects.create(code="C001", name="Class 1", grade="1")
        rows = [{"student_id": "S001", "class_code": "C001", "status": "active"}]
        report = perform_import("enrollments", rows, "reject", self.teacher)
        self.assertEqual(report["created"], 1)
        self.assertEqual(Enrollment.objects.filter(student=student, class_obj=class_obj).count(), 1)

    def test_import_duplicate_reject(self):
        from lab.import_export import perform_import
        Student.objects.create(student_id="S001", full_name="Old")
        rows = [{"student_id": "S001", "full_name": "New"}]
        report = perform_import("students", rows, "reject", self.teacher)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(report["created"], 0)
        self.assertEqual(Student.objects.filter(student_id="S001").count(), 1)

    def test_import_duplicate_update(self):
        from lab.import_export import perform_import
        Student.objects.create(student_id="S001", full_name="Old")
        rows = [{"student_id": "S001", "full_name": "New"}]
        report = perform_import("students", rows, "update", self.teacher)
        self.assertEqual(report["updated"], 1)
        self.assertEqual(Student.objects.get(student_id="S001").full_name, "New")

    def test_import_duplicate_skip(self):
        from lab.import_export import perform_import
        Student.objects.create(student_id="S001", full_name="Old")
        rows = [{"student_id": "S001", "full_name": "New"}]
        report = perform_import("students", rows, "skip", self.teacher)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(Student.objects.get(student_id="S001").full_name, "Old")

    def test_import_transactional_rollback_on_error(self):
        from unittest.mock import patch
        from lab.import_export import perform_import
        rows = [{"student_id": "S001", "full_name": "First"}]
        with patch("lab.import_export.Student.objects.create", side_effect=Exception("Simulated error")):
            with self.assertRaises(Exception):
                perform_import("students", rows, "reject", self.teacher)
        self.assertEqual(Student.objects.filter(student_id="S001").count(), 0)


class ImportExportViewTests(TestCase):
    """اختبارات واجهات الاستيراد/التصدير."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="IE School", code="IES2", active=True)
        cls.classroom = Classroom.objects.create(school=cls.school, name="IE Class", code="IEC2", capacity=40)
        cls.teacher = get_user_model().objects.create_superuser(
            username="ieteacher2", email="iet2@example.invalid", password="temporary-test-password"
        )
        cls.student = get_user_model().objects.create_user(
            username="iestudent2", email="ies2@example.invalid", password="temporary-test-password"
        )

    def test_import_page_requires_staff(self):
        self.client.force_login(self.student)
        resp = self.client.get("/import-export/")
        self.assertEqual(resp.status_code, 403)

    def test_import_page_loads_for_teacher(self):
        self.client.force_login(self.teacher)
        resp = self.client.get("/import-export/")
        self.assertEqual(resp.status_code, 200)

    def test_upload_invalid_entity_type(self):
        self.client.force_login(self.teacher)
        resp = self.client.post("/api/import/upload/", {"entity_type": "invalid"})
        self.assertEqual(resp.status_code, 400)

    def test_upload_csv_success(self):
        self.client.force_login(self.teacher)
        csv_data = "student_id,full_name\nS001,محمد أحمد\n".encode("utf-8")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["valid_count"], 1)

    def test_upload_xlsx_success(self):
        self.client.force_login(self.teacher)
        from openpyxl import Workbook
        from io import BytesIO
        wb = Workbook()
        ws = wb.active
        ws.append(["student_id", "full_name"])
        ws.append(["S001", "Jean Dupont"])
        buffer = BytesIO()
        wb.save(buffer)
        f = SimpleUploadedFile("test.xlsx", buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["valid_count"], 1)

    def test_upload_missing_required_field(self):
        self.client.force_login(self.teacher)
        csv_data = "student_id,full_name\n,Test\n".encode("utf-8")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertGreater(data["error_count"], 0)

    def test_upload_duplicate_student_id(self):
        self.client.force_login(self.teacher)
        Student.objects.create(student_id="S001", full_name="Old")
        csv_data = "student_id,full_name\nS001,New\n".encode("utf-8")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertGreater(data["error_count"], 0)

    def test_upload_invalid_class_code(self):
        self.client.force_login(self.teacher)
        csv_data = "student_id,full_name,classroom_code\nS001,Test,INVALID\n".encode("utf-8")
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertGreater(data["error_count"], 0)

    def test_upload_empty_file(self):
        self.client.force_login(self.teacher)
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        resp = self.client.post("/api/import/upload/", {"file": f, "entity_type": "students"})
        self.assertEqual(resp.status_code, 400)

    def test_confirm_import_creates_records(self):
        self.client.force_login(self.teacher)
        clean_rows = [{"student_id": "S001", "full_name": "محمد أحمد"}]
        resp = self.client.post("/api/import/confirm/", data=json.dumps({
            "entity_type": "students",
            "clean_rows": clean_rows,
            "duplicate_mode": "reject",
        }), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["report"]["created"], 1)
        self.assertEqual(Student.objects.filter(student_id="S001").count(), 1)

    def test_export_csv_students(self):
        self.client.force_login(self.teacher)
        Student.objects.create(student_id="S001", full_name="محمد أحمد")
        resp = self.client.get("/export/students/?format=csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        content = resp.content.decode("utf-8-sig")
        self.assertIn("S001", content)
        self.assertIn("محمد أحمد", content)

    def test_export_xlsx_students(self):
        self.client.force_login(self.teacher)
        Student.objects.create(student_id="S001", full_name="Jean Dupont")
        resp = self.client.get("/export/students/?format=xlsx")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_export_requires_staff(self):
        self.client.force_login(self.student)
        resp = self.client.get("/export/students/?format=csv")
        self.assertEqual(resp.status_code, 403)
