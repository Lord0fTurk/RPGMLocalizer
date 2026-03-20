from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess
import sys
from typing import Callable


APP_USER_MODEL_ID = "LordOfTurk.RPGMLocalizer"
QT_RENDER_MODE_ENV = "RPGMLOCALIZER_QT_RENDER_MODE"
QT_PLATFORM_HINT_ENV = "RPGMLOCALIZER_QT_PLATFORM_HINT"
QT_DEBUG_ENV = "RPGMLOCALIZER_QT_DEBUG"
VALID_RENDER_MODES = {"native", "opengl", "software"}
VALID_PLATFORM_HINTS = {"xcb", "wayland", "xcb;wayland", "wayland;xcb", "cocoa"}
STARTUP_DIAGNOSTICS: dict[str, str] = {}


def debug_enabled() -> bool:
    """Return True when verbose Qt bootstrap diagnostics are enabled."""
    return os.environ.get(QT_DEBUG_ENV, "").strip() == "1"


def choose_windows_render_mode(scale_percent: int, override: str | None) -> tuple[str, str]:
    """Pick the safest Qt render mode for the current Windows environment."""
    normalized_override = (override or "").strip().lower()
    if normalized_override in VALID_RENDER_MODES:
        return normalized_override, "user_override"
    if scale_percent >= 125:
        return "software", "hidpi_auto_fallback"
    return "opengl", "safe_default"


def detect_windows_scale_percent() -> int:
    """Detect the current Windows scale percentage without importing Qt."""
    if sys.platform != "win32":
        return 100

    try:
        user32 = ctypes.windll.user32
        get_dpi_for_system = getattr(user32, "GetDpiForSystem", None)
        if get_dpi_for_system is not None:
            dpi = int(get_dpi_for_system())
            if dpi > 0:
                return max(100, int(round(dpi * 100 / 96)))
    except Exception:
        pass

    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        if hdc:
            dpi = int(gdi32.GetDeviceCaps(hdc, 88))
            user32.ReleaseDC(0, hdc)
            if dpi > 0:
                return max(100, int(round(dpi * 100 / 96)))
    except Exception:
        pass

    return 100


def _clear_qt_graphics_overrides() -> None:
    """Clear graphics-related Qt environment overrides before selecting a mode."""
    for key in (
        "QT_OPENGL",
        "QT_QUICK_BACKEND",
        "QSG_RHI_BACKEND",
        "QSG_RHI_PREFER_SOFTWARE_RENDERER",
    ):
        os.environ.pop(key, None)


def apply_windows_qt_mode(mode: str) -> None:
    """Apply pre-Qt environment variables for the selected Windows render mode."""
    _clear_qt_graphics_overrides()

    if mode == "opengl":
        os.environ["QT_OPENGL"] = "desktop"
        os.environ["QSG_RHI_BACKEND"] = "opengl"
    elif mode == "software":
        os.environ["QT_OPENGL"] = "software"
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["QSG_RHI_PREFER_SOFTWARE_RENDERER"] = "1"


def apply_unix_qt_mode(mode: str) -> None:
    """Apply pre-Qt environment variables for Linux/macOS render mode selection."""
    _clear_qt_graphics_overrides()

    if mode == "opengl":
        os.environ["QSG_RHI_BACKEND"] = "opengl"
    elif mode == "software":
        os.environ["QT_OPENGL"] = "software"
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["QSG_RHI_PREFER_SOFTWARE_RENDERER"] = "1"


def _probe_linux_glx_available() -> bool:
    """Return True when Linux GLX context creation looks viable."""
    if sys.platform != "linux":
        return True

    display_env = os.environ.get("DISPLAY", "")
    wayland_env = os.environ.get("WAYLAND_DISPLAY", "")
    if not display_env and wayland_env:
        return True
    if not display_env:
        return True

    try:
        libgl_name = ctypes.util.find_library("GL")
        libx11_name = ctypes.util.find_library("X11")
        if not libgl_name or not libx11_name:
            return False

        libgl = ctypes.cdll.LoadLibrary(libgl_name)
        libx11 = ctypes.cdll.LoadLibrary(libx11_name)
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]

        display = libx11.XOpenDisplay(display_env.encode("utf-8"))
        if not display:
            return False

        try:
            glx_query = getattr(libgl, "glXQueryExtension", None)
            if glx_query is None:
                return False

            glx_query.restype = ctypes.c_int
            glx_query.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            error_base = ctypes.c_int(0)
            event_base = ctypes.c_int(0)
            if not glx_query(display, ctypes.byref(error_base), ctypes.byref(event_base)):
                return False
        finally:
            libx11.XCloseDisplay(display)
    except Exception:
        return False

    try:
        probe = subprocess.run(
            ["glxinfo"],
            capture_output=True,
            timeout=5,
            env={**os.environ, "DISPLAY": display_env},
        )
        if probe.returncode != 0:
            return False
    except FileNotFoundError:
        return True
    except Exception:
        return False

    return True


def choose_linux_render_mode(frozen: bool, override: str | None) -> tuple[str, str]:
    """Pick the safest Qt render mode for Linux."""
    normalized_override = (override or "").strip().lower()
    if normalized_override in VALID_RENDER_MODES:
        return normalized_override, "user_override"
    if frozen and not _probe_linux_glx_available():
        return "software", "glx_probe_failed"
    return "native", "safe_default"


def detect_qt_platform_hint() -> str | None:
    """Return a preferred Qt platform plugin hint when the session is ambiguous."""
    requested_hint = os.environ.get(QT_PLATFORM_HINT_ENV, "").strip().lower()
    if requested_hint in VALID_PLATFORM_HINTS:
        return requested_hint

    if sys.platform == "linux":
        if os.environ.get("DISPLAY") and os.environ.get("WAYLAND_DISPLAY"):
            return "xcb;wayland"
        return None

    if sys.platform == "darwin":
        return "cocoa"

    return None


def set_windows_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> None:
    """Set a stable Windows AppUserModelID so the taskbar icon resolves correctly."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def bootstrap_qt_environment() -> dict[str, str]:
    """Configure Qt-related environment variables before importing PyQt6."""
    os.environ.setdefault("QT_API", "pyqt6")

    diagnostics = {
        "platform": sys.platform,
        "selected_mode": "native",
        "selection_reason": "safe_default",
        "scale_percent": "100",
        "qt_opengl": os.environ.get("QT_OPENGL", "<default>"),
        "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", "<default>"),
        "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", "<default>"),
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", "<default>"),
    }

    if sys.platform == "win32":
        scale_percent = detect_windows_scale_percent()
        mode, reason = choose_windows_render_mode(
            scale_percent=scale_percent,
            override=os.environ.get(QT_RENDER_MODE_ENV),
        )
        apply_windows_qt_mode(mode)
        set_windows_app_user_model_id()
        diagnostics.update(
            {
                "selected_mode": mode,
                "selection_reason": reason,
                "scale_percent": str(scale_percent),
                "qt_opengl": os.environ.get("QT_OPENGL", "<default>"),
                "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", "<default>"),
                "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", "<default>"),
                "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", "<default>"),
            }
        )
    elif sys.platform == "linux":
        mode, reason = choose_linux_render_mode(
            frozen=bool(getattr(sys, "frozen", False)),
            override=os.environ.get(QT_RENDER_MODE_ENV),
        )
        apply_unix_qt_mode(mode)

        platform_hint = detect_qt_platform_hint()
        if platform_hint and "QT_QPA_PLATFORM" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = platform_hint

        diagnostics.update(
            {
                "selected_mode": mode,
                "selection_reason": reason,
                "qt_opengl": os.environ.get("QT_OPENGL", "<default>"),
                "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", "<default>"),
                "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", "<default>"),
                "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", "<default>"),
            }
        )
    elif sys.platform == "darwin":
        mode_override = (os.environ.get(QT_RENDER_MODE_ENV) or "").strip().lower()
        if mode_override in VALID_RENDER_MODES:
            apply_unix_qt_mode(mode_override)
            diagnostics["selected_mode"] = mode_override
            diagnostics["selection_reason"] = "user_override"

        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

        diagnostics.update(
            {
                "qt_opengl": os.environ.get("QT_OPENGL", "<default>"),
                "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND", "<default>"),
                "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND", "<default>"),
                "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", "<default>"),
            }
        )

    STARTUP_DIAGNOSTICS.clear()
    STARTUP_DIAGNOSTICS.update(diagnostics)

    if debug_enabled():
        print(format_startup_diagnostics("Qt bootstrap"))

    return STARTUP_DIAGNOSTICS.copy()


def apply_qt_application_attributes() -> None:
    """Apply Qt application attributes after PyQt6 import but before QApplication."""
    from PyQt6.QtCore import QCoreApplication, Qt

    selected_mode = STARTUP_DIAGNOSTICS.get("selected_mode", "native")
    if selected_mode == "opengl":
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)
    elif selected_mode == "software":
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)


def format_startup_diagnostics(prefix: str = "Qt startup") -> str:
    """Render a compact startup diagnostics string for logging."""
    platform = STARTUP_DIAGNOSTICS.get("platform", sys.platform)
    scale_percent = STARTUP_DIAGNOSTICS.get("scale_percent", "100")
    selected_mode = STARTUP_DIAGNOSTICS.get("selected_mode", "native")
    selection_reason = STARTUP_DIAGNOSTICS.get("selection_reason", "unknown")
    qt_opengl = STARTUP_DIAGNOSTICS.get("qt_opengl", "<default>")
    qt_quick_backend = STARTUP_DIAGNOSTICS.get("qt_quick_backend", "<default>")
    qsg_rhi_backend = STARTUP_DIAGNOSTICS.get("qsg_rhi_backend", "<default>")
    qt_qpa_platform = STARTUP_DIAGNOSTICS.get("qt_qpa_platform", "<default>")

    return (
        f"{prefix}: platform={platform}, scale={scale_percent}%, mode={selected_mode}, "
        f"reason={selection_reason}, QT_OPENGL={qt_opengl}, "
        f"QT_QUICK_BACKEND={qt_quick_backend}, QSG_RHI_BACKEND={qsg_rhi_backend}, "
        f"QT_QPA_PLATFORM={qt_qpa_platform}"
    )


def emit_runtime_diagnostics(log_callback: Callable[[str, str], None] | None = None) -> str:
    """Log or print runtime diagnostics after QApplication creation."""
    from PyQt6.QtGui import QGuiApplication

    platform_name = QGuiApplication.platformName() or "unknown"
    message = f"{format_startup_diagnostics('Qt runtime')}, qpa={platform_name}"

    if log_callback is not None:
        log_callback("info", message)

    if debug_enabled():
        print(message)

    return message
