import os
import shutil
import tempfile
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

@contextmanager
def safe_write(filepath, mode='w', encoding='utf-8', **kwargs):
    """
    Safely write to a file using a temporary file first.
    If the write fails (exception occurs), the original file is untouched.
    If the write succeeds, the temporary file atomically replaces the original.
    
    Args:
        filepath: Path to the target file
        mode: Open mode ('w', 'wb', etc.)
        encoding: Encoding for text mode (default: utf-8)
        **kwargs: Additional arguments passed to open()
    """
    dir_name = os.path.dirname(filepath)
    file_name = os.path.basename(filepath)
    
    # Avoid hidden files (leading dot) which can be problematic on some Mac/Network drives
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
            pass # Some filesystems don't support fsync
        f.close()
        f = None
        
        # Safety check: Prevent replacing with an empty file if that wasn't intended
        if os.path.getsize(temp_path) == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.error(f"Aborting safe_write to {filepath}: Temp file is empty but original is not.")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise IOError(f"Aborting safe_write to {filepath}: temp file is empty but original is not.")

        # Preserve original permissions if possible
        if os.path.exists(filepath):
            try:
                shutil.copymode(filepath, temp_path)
            except Exception:
                pass

        # Atomic replacement: os.replace uses MoveFileExW(MOVEFILE_REPLACE_EXISTING)
        # on Windows, which is atomic even when the destination file already exists.
        # shutil.move falls back to a non-atomic copy+delete on Windows when the
        # destination exists, which can leave the file partially written on failure.
        os.replace(temp_path, filepath)
        
    except Exception as e:
        logger.error(f"Failed to safe_write to {filepath}: {e}")
        # If writing failed, cleanup temp file
        if f:
            try:
                f.close()
            except Exception as close_err:
                logger.debug(f"Error closing temp file: {close_err}")
        
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as os_err:
                logger.warning(f"Failed to remove temp file {temp_path}: {os_err}")
        raise e
    finally:
        # Ensure file is closed if something went wrong inside yield but wasn't caught
        if f:
            try:
                f.close()
            except Exception as close_err:
                logger.debug(f"Error closing file in finally: {close_err}")
