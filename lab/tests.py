"""اختبارات آلية لوحدة veyon بدون أجهزة حقيقية."""
import os
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from lab import veyon
from lab.models import Device


class VeyonCliTests(TestCase):
    """اختبارات التعامل مع veyon-cli."""

    def setUp(self):
        self.device = Device.objects.create(number=1, ip_address="192.168.1.101")

    @override_settings(LAB_SIMULATE=True)
    def test_check_online_simulate(self):
        """في الوضع التجريبي: الأجهزة القابلة للقسمة على 6 غير متصلة."""
        d1 = Device(number=1)
        d6 = Device(number=6)
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
    @patch("lab.veyon._run_veyon_cli")
    def test_get_lock_state_locked(self, mock_run):
        """قراءة حالة القفل: محظور."""
        mock_run.return_value = (True, "ScreenLock: on", "")
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertTrue(is_locked)
        self.assertEqual(error, "")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_get_lock_state_unlocked(self, mock_run):
        """قراءة حالة القفل: غير محظور."""
        mock_run.return_value = (True, "ScreenLock: off", "")
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertFalse(is_locked)

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

    @override_settings(LAB_SIMULATE=True)
    def test_sync_lock_states_simulate(self):
        """في الوضع التجريبي لا تُزامن الحالة."""
        d = Device.objects.create(number=1, ip_address="192.168.1.101", is_blocked=True)
        count = veyon.sync_lock_states([d])
        self.assertEqual(count, 0)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon.get_lock_state")
    def test_sync_lock_states_updates(self, mock_get):
        """المزامنة تحدث قاعدة البيانات عند اختلاف الحالة."""
        d = Device.objects.create(number=1, ip_address="192.168.1.101", is_blocked=False)
        mock_get.return_value = (True, "")
        count = veyon.sync_lock_states([d])
        self.assertEqual(count, 1)
        d.refresh_from_db()
        self.assertTrue(d.is_blocked)


class VeyonErrorTests(TestCase):
    """اختبارات التعامل مع الأخطاء."""

    def setUp(self):
        self.device = Device.objects.create(number=1, ip_address="192.168.1.101")

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="")
    def test_set_lock_no_cli(self):
        """فشل عند عدم وجود veyon-cli."""
        ok, error = veyon.set_lock(self.device, True)
        self.assertFalse(ok)
        self.assertIn("veyon-cli", error)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    def test_set_lock_no_ip(self):
        """فشل عند عدم وجود عنوان IP."""
        d = Device(number=2, ip_address=None)
        ok, error = veyon.set_lock(d, True)
        self.assertFalse(ok)
        self.assertIn("IP", error)

    @override_settings(LAB_SIMULATE=False, VEYON_CLI="veyon-cli")
    @patch("lab.veyon._run_veyon_cli")
    def test_get_lock_state_error(self, mock_run):
        """خطأ عند قراءة الحالة."""
        mock_run.return_value = (False, "", "timeout")
        is_locked, error = veyon.get_lock_state(self.device)
        self.assertFalse(is_locked)
        self.assertIn("timeout", error)
