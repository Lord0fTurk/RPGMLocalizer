import tempfile
import time
import unittest

from PyQt6.QtCore import QCoreApplication

from src.backend.settings_backend import SettingsBackend
from src.backend.app_backend import AppBackend


class TestQmlBackend(unittest.TestCase):
    """Unit tests for QML backend bridge classes."""

    def setUp(self):
        self.settings = SettingsBackend()
        self.app = AppBackend(self.settings)

    def test_settings_backend_defaults_and_properties(self):
        """Test default settings properties and getter/setter slots."""
        self.assertTrue(len(self.settings.targetLang) > 0)
        self.assertTrue(len(self.settings.engine) > 0)
        self.assertTrue(self.settings.useMultiEndpoint)

        # Update property
        self.settings.targetLang = "ja"
        self.assertEqual(self.settings.targetLang, "ja")

        # Dictionary export for pipeline
        d = self.settings.get_dict()
        self.assertEqual(d["target_lang"], "ja")

    def test_app_backend_project_path_and_state(self):
        """Test AppBackend initial properties and path setting."""
        self.assertFalse(self.app.isRunning)
        self.assertEqual(self.app.stageText, "Idle")

        self.app.setProjectPath("/tmp/test_project")
        self.assertEqual(self.app.projectPath, "/tmp/test_project")


class TestAppBackendThreadLifecycle(unittest.TestCase):
    """Exercises the real QThread + moveToThread + QueuedConnection wiring in
    `AppBackend.startPipeline()` end to end (no network: pipeline fails fast
    because the temp dir has no RPG Maker `Data` folder).
    """

    @classmethod
    def setUpClass(cls):
        # QueuedConnection delivery requires a live Qt event loop to pump.
        cls.qapp = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.settings = SettingsBackend()
        self.app = AppBackend(self.settings)

    def _pump_until(self, predicate, timeout_s: float = 5.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.qapp.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_start_pipeline_rejects_missing_project_path(self):
        self.app.setProjectPath("")
        notices = []
        self.app.infoNotice.connect(lambda *args: notices.append(args))

        self.app.startPipeline()

        self.assertFalse(self.app.isRunning)
        self.assertTrue(any(n[0] == "warning" for n in notices))

    def test_start_pipeline_runs_thread_and_cleans_up_on_finish(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.app.setProjectPath(tmpdir)

            finished_calls = []
            self.app.finished.connect(lambda success, summary: finished_calls.append((success, summary)))

            self.app.startPipeline()

            # Signals fire synchronously in-thread; state must flip immediately.
            self.assertTrue(self.app.isRunning)
            self.assertIsNotNone(self.app._thread)
            self.assertIsNotNone(self.app._pipeline)

            completed = self._pump_until(lambda: not self.app.isRunning and self.app._thread is None)

        self.assertTrue(completed, "Pipeline did not finish within timeout")
        self.assertEqual(len(finished_calls), 1)
        success, summary = finished_calls[0]
        self.assertFalse(success)
        self.assertIn("Data folder", summary)

        # _cleanup_thread must have run via the queued QThread.finished connection.
        self.assertIsNone(self.app._thread)
        self.assertIsNone(self.app._pipeline)


if __name__ == "__main__":
    unittest.main()
