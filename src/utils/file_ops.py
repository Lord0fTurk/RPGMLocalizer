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
    
    # Create temp file in the same directory to ensure atomic move works
    # (os.replace across different filesystems might not be atomic)
    temp_name = f".{file_name}.tmp"
    temp_path = os.path.join(dir_name, temp_name)
    
    f = None
    try:
        # Open the temporary file
        if 'b' in mode:
            f = open(temp_path, mode, **kwargs)
        else:
            f = open(temp_path, mode, encoding=encoding, **kwargs)
            
        yield f
        
        # Close file before moving
        f.flush()
        os.fsync(f.fileno())
        f.close()
        f = None  # Prevent double closing in finally
        
        # Atomic replace
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
