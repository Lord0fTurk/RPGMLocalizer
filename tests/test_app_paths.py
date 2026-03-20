import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ui.interfaces.home_interface import HomeInterface
from src.utils import app_paths, paths
from src.utils.backup import BackupManager
from src.utils.settings_store import SettingsStore


class TestAppPaths(unittest.TestCase):
    def test_linux_uses_xdg_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.app_paths.sys.platform", "linux"):
                with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}, clear=False):
                    resolved = app_paths.get_data_dir()

        self.assertEqual(resolved, Path(tmpdir) / app_paths.APP_NAME)

    def test_portable_marker_overrides_system_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir)
            (app_dir / app_paths.PORTABLE_MARKER).write_text("", encoding="utf-8")

            with patch("src.utils.app_paths.sys.platform", "linux"):
                with patch("src.utils.app_paths.get_app_dir", return_value=app_dir):
                    resolved = app_paths.get_data_dir()

        self.assertEqual(resolved, app_dir)

    def test_resource_path_uses_app_dir_in_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.paths.get_app_dir", return_value=Path(tmpdir)):
                resolved = paths.resource_path("icon.png")

        self.assertEqual(resolved, os.path.join(tmpdir, "icon.png"))

    def test_settings_store_uses_app_path_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            with patch("src.utils.settings_store.get_settings_path", return_value=settings_path):
                store = SettingsStore()

        self.assertEqual(store.path, os.fspath(settings_path))

    def test_relative_backup_dir_resolves_under_app_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.utils.backup.get_data_dir", return_value=Path(tmpdir)):
                manager = BackupManager("backups")

        self.assertEqual(manager.backup_dir, os.path.join(tmpdir, "backups"))


class TestHomeInterfacePathNormalization(unittest.TestCase):
    def test_normalize_project_path_converts_file_to_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game_exe = Path(tmpdir) / "Game.exe"
            game_exe.write_text("", encoding="utf-8")

            normalized = HomeInterface._normalize_project_path(os.fspath(game_exe))

        self.assertEqual(normalized, tmpdir)

    def test_normalize_project_path_keeps_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            normalized = HomeInterface._normalize_project_path(tmpdir)

        self.assertEqual(normalized, tmpdir)


if __name__ == "__main__":
    unittest.main()
