import os
import shutil
import time
import sys
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Windows atomic replacement via pywin32 (ReplaceFileW) — more reliable
# than os.replace() against antivirus locks and cross-volume edge cases.
_WIN32_REPLACE = None
_WIN32_SHARING_VIOLATION = 32


def _ensure_win32_replace():
    global _WIN32_REPLACE
    if _WIN32_REPLACE is None and sys.platform == 'win32':
        try:
            import win32file
            _WIN32_REPLACE = win32file.ReplaceFile
        except ImportError:
            _WIN32_REPLACE = False
    return _WIN32_REPLACE


def _atomic_replace(src: str, dst: str, retries: int = 3) -> None:
    """Replace *dst* with *src* atomically, with retry for lock contention.

    Strategy
    --------
    1. Try ``os.replace()`` first — works for both new and existing files.
    2. When pywin32 is available and ``os.replace()`` fails with a sharing
       violation (antivirus lock), retry via ``ReplaceFileW`` with
       exponential backoff (0.1s, 0.2s, 0.4s).
    """
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except OSError as e:
            winerr = getattr(e, 'winerror', None)
            if winerr == _WIN32_SHARING_VIOLATION:
                _replace = _ensure_win32_replace()
                if _replace and os.path.exists(dst):
                    try:
                        # ReplaceFileW(dst, src, backup, flags, ...) — designed
                        # for replacing existing files; handles AV locks better
                        # than os.replace() on Windows.
                        _replace(dst, src, None, 1, None, None)
                        return
                    except OSError:
                        pass  # fall through to retry
                if attempt == retries - 1:
                    raise
                delay = 0.1 * (2 ** attempt)
                logger.debug(
                    "File lock contention %s→%s, retrying in %.1fs (attempt %d/%d)",
                    os.path.basename(src), os.path.basename(dst), delay,
                    attempt + 1, retries,
                )
                time.sleep(delay)
            else:
                raise


@contextmanager
def safe_write(filepath, mode='w', encoding='utf-8', **kwargs):
    """
    Safely write to a file using a temporary file + atomic replace.

    If the write fails (exception from the caller), the original file is
    untouched.  If it succeeds, the temporary file atomically replaces the
    original via ``ReplaceFileW`` (Windows) or ``os.replace()`` (POSIX).

    Args:
        filepath: Path to the target file.
        mode: Open mode ('w', 'wb', …).
        encoding: Encoding for text mode (default: utf-8).
        **kwargs: Additional arguments for ``open()``.
    """
    dir_name = os.path.dirname(filepath)
    file_name = os.path.basename(filepath)

    temp_name = f"tmp_{file_name}_{os.urandom(4).hex()}.tmp"
    temp_path = os.path.join(dir_name, temp_name)

    f = None
    try:
        if 'b' in mode:
            f = open(temp_path, mode, **kwargs)
        else:
            f = open(temp_path, mode, encoding=encoding, **kwargs)

        yield f

        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
        f.close()
        f = None

        # Safety: don't silently replace with an empty file
        if os.path.getsize(temp_path) == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.error("Aborting safe_write to %s: temp file is empty but original is not.", filepath)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise IOError(f"Aborting safe_write to {filepath}: temp file is empty but original is not.")

        # Preserve original metadata where possible
        if os.path.exists(filepath):
            try:
                shutil.copymode(filepath, temp_path)
            except Exception:
                pass

        _atomic_replace(temp_path, filepath)

    except Exception as e:
        logger.error("Failed to safe_write to %s: %s", filepath, e)
        if f:
            try:
                f.close()
            except Exception as ce:
                logger.debug("Error closing temp file: %s", ce)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as oe:
                logger.warning("Failed to remove temp file %s: %s", temp_path, oe)
        raise
    finally:
        if f:
            try:
                f.close()
            except Exception as ce:
                logger.debug("Error closing file in finally: %s", ce)


def safe_extract_zip(zip_path: str, target_dir: str) -> list[str]:
    """Safely extract a ZIP archive with strict Zip Slip / Path Traversal prevention.

    Raises:
        ValueError: When a zip member attempts to write outside target_dir.
    """
    import zipfile
    from pathlib import Path

    dest = Path(target_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    extracted_files: list[str] = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            target_file = (dest / member).resolve()
            if not target_file.is_relative_to(dest):
                raise ValueError(
                    f"Security Exception (Zip Slip): Attempted path traversal via '{member}'"
                )

            # Extract safely
            zf.extract(member, dest)
            extracted_files.append(str(target_file))

    return extracted_files


def read_text_file(file_path: str | os.PathLike[str]) -> tuple[str, str]:
    """Read a text file with multi-encoding fallback.

    Tries UTF-8-SIG, UTF-8, CP932, Shift-JIS, EUC-JP, Latin-1 in order to safely
    handle Japanese RPG Maker plugins and legacy localization assets.

    Returns:
        tuple[str, str]: (decoded_content, detected_encoding)
    """
    with open(file_path, "rb") as handle:
        raw_bytes = handle.read()

    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp", "latin-1"):
        try:
            return raw_bytes.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue

    return raw_bytes.decode("latin-1", errors="replace"), "latin-1"

