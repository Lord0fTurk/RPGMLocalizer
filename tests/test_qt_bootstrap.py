import os
import unittest
from unittest.mock import patch

from src.utils import qt_bootstrap


class TestQtBootstrap(unittest.TestCase):
    def test_choose_windows_render_mode_defaults_to_opengl(self) -> None:
        mode, reason = qt_bootstrap.choose_windows_render_mode(scale_percent=100, override=None)
        self.assertEqual(mode, "opengl")
        self.assertEqual(reason, "safe_default")

    def test_choose_windows_render_mode_uses_software_for_hidpi(self) -> None:
        mode, reason = qt_bootstrap.choose_windows_render_mode(scale_percent=150, override=None)
        self.assertEqual(mode, "software")
        self.assertEqual(reason, "hidpi_auto_fallback")

    def test_choose_windows_render_mode_honors_user_override(self) -> None:
        mode, reason = qt_bootstrap.choose_windows_render_mode(scale_percent=150, override="native")
        self.assertEqual(mode, "native")
        self.assertEqual(reason, "user_override")

    def test_apply_windows_qt_mode_opengl(self) -> None:
        with patch.dict(os.environ, {"QT_OPENGL": "software", "QT_QUICK_BACKEND": "software"}, clear=False):
            qt_bootstrap.apply_windows_qt_mode("opengl")
            self.assertEqual(os.environ.get("QT_OPENGL"), "desktop")
            self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "opengl")
            self.assertNotIn("QT_QUICK_BACKEND", os.environ)

    def test_apply_windows_qt_mode_software(self) -> None:
        with patch.dict(os.environ, {"QSG_RHI_BACKEND": "opengl"}, clear=False):
            qt_bootstrap.apply_windows_qt_mode("software")
            self.assertEqual(os.environ.get("QT_OPENGL"), "software")
            self.assertEqual(os.environ.get("QT_QUICK_BACKEND"), "software")
            self.assertNotIn("QSG_RHI_BACKEND", os.environ)

    @patch("src.utils.qt_bootstrap.detect_windows_scale_percent", return_value=150)
    @patch("src.utils.qt_bootstrap.set_windows_app_user_model_id")
    @patch("src.utils.qt_bootstrap.sys.platform", "win32")
    def test_bootstrap_qt_environment_sets_windows_fallback(
        self,
        mock_set_app_id,
        mock_detect_scale,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            diagnostics = qt_bootstrap.bootstrap_qt_environment()
            self.assertEqual(os.environ.get("QT_API"), "pyqt6")

        self.assertEqual(diagnostics["selected_mode"], "software")
        self.assertEqual(diagnostics["selection_reason"], "hidpi_auto_fallback")
        self.assertEqual(diagnostics["qt_opengl"], "software")
        mock_set_app_id.assert_called_once()

    @patch("src.utils.qt_bootstrap._probe_linux_glx_available", return_value=False)
    @patch.object(qt_bootstrap.sys, "frozen", True, create=True)
    @patch("src.utils.qt_bootstrap.sys.platform", "linux")
    def test_bootstrap_qt_environment_sets_linux_software_fallback(
        self,
        mock_probe,
    ) -> None:
        with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
            diagnostics = qt_bootstrap.bootstrap_qt_environment()
            self.assertEqual(os.environ.get("QT_QUICK_BACKEND"), "software")

        self.assertEqual(diagnostics["selected_mode"], "software")
        self.assertEqual(diagnostics["selection_reason"], "glx_probe_failed")
        mock_probe.assert_called_once()

    @patch("src.utils.qt_bootstrap._probe_linux_glx_available", return_value=True)
    @patch.object(qt_bootstrap.sys, "frozen", True, create=True)
    @patch("src.utils.qt_bootstrap.sys.platform", "linux")
    def test_bootstrap_qt_environment_sets_linux_platform_hint_on_mixed_session(
        self,
        mock_probe,
    ) -> None:
        with patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            diagnostics = qt_bootstrap.bootstrap_qt_environment()
            self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "xcb;wayland")

        self.assertEqual(diagnostics["selected_mode"], "native")
        mock_probe.assert_called_once()

    @patch("src.utils.qt_bootstrap.sys.platform", "darwin")
    def test_bootstrap_qt_environment_sets_mac_layer_backing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            diagnostics = qt_bootstrap.bootstrap_qt_environment()
            self.assertEqual(os.environ.get("QT_MAC_WANTS_LAYER"), "1")

        self.assertEqual(diagnostics["selected_mode"], "native")


if __name__ == "__main__":
    unittest.main()
