from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT_DIR / "icon.png"
WINDOWS_ICON = ROOT_DIR / "icon.ico"
MACOS_ICON = ROOT_DIR / "icon.icns"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ICNS_BASE_SIZES = [16, 32, 128, 256, 512]


def build_windows_icon(source_icon: Path, output_icon: Path) -> None:
    """Generate a multi-size Windows ICO file from the source PNG icon."""
    with Image.open(source_icon) as image:
        converted = image.convert("RGBA")
        output_icon.parent.mkdir(parents=True, exist_ok=True)
        converted.save(output_icon, format="ICO", sizes=ICO_SIZES)


def run_command(command: list[str]) -> None:
    """Run a subprocess command and raise on failure."""
    subprocess.run(command, check=True, capture_output=True)


def build_macos_icon(source_icon: Path, output_icon: Path) -> bool:
    """Generate a macOS ICNS icon using native macOS tooling when available."""
    if sys.platform != "darwin":
        return False

    if not shutil.which("sips") or not shutil.which("iconutil"):
        return False

    with tempfile.TemporaryDirectory() as temp_dir:
        iconset_dir = Path(temp_dir) / "icon.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        for size in ICNS_BASE_SIZES:
            normal_path = iconset_dir / f"icon_{size}x{size}.png"
            run_command(["sips", "-z", str(size), str(size), str(source_icon), "--out", str(normal_path)])

            if size <= 256:
                retina_size = size * 2
                retina_path = iconset_dir / f"icon_{size}x{size}@2x.png"
                run_command(["sips", "-z", str(retina_size), str(retina_size), str(source_icon), "--out", str(retina_path)])

        output_icon.parent.mkdir(parents=True, exist_ok=True)
        run_command(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icon)])
        return True


def main() -> int:
    """Generate platform-specific icon files from icon.png."""
    if not SOURCE_ICON.exists():
        raise FileNotFoundError(f"Source icon not found: {SOURCE_ICON}")

    build_windows_icon(SOURCE_ICON, WINDOWS_ICON)
    print(f"Generated Windows icon: {WINDOWS_ICON}")

    if build_macos_icon(SOURCE_ICON, MACOS_ICON):
        print(f"Generated macOS icon: {MACOS_ICON}")
    else:
        print("Skipped macOS icon generation on this platform")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
