"""The editor must wait for a user action before scanning a selected project."""
from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal

from src.backend.editor_backend import EditorBackend


class FakeAppBackend(QObject):
    projectPathChanged = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    cacheAboutToBeCleared = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.projectPath = ""

    def setProjectPath(self, path: str) -> None:
        self.projectPath = path
        self.projectPathChanged.emit(path)


class FakeSettingsBackend:
    def get_dict(self) -> dict:
        return {}


class EditorExplicitLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_project_change_waits_but_editor_selection_loads(self) -> None:
        app_backend = FakeAppBackend()
        editor = EditorBackend(app_backend, FakeSettingsBackend())
        with tempfile.TemporaryDirectory() as project_path:
            with patch.object(editor, "loadProject") as load:
                app_backend.setProjectPath(project_path)
                load.assert_not_called()
                self.assertFalse(editor.scanAttempted)
                editor.setProjectPath(project_path)
                load.assert_called_once_with(force_rescan=False)
