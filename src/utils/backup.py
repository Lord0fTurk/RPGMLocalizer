"""
Backup utilities for safe file modification.
Creates backups before any write operation to prevent data loss.
"""
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import logging

from src.utils.app_paths import get_data_dir

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages backups for game files before modification.
    """
    
    def __init__(self, backup_dir: Optional[str] = None):
        """
        Initialize backup manager.
        
        Args:
            backup_dir: Directory to store backups. If None, uses .rpgm_backup
                       in the same directory as the original file.
        """
        self.backup_dir = self._resolve_backup_dir(backup_dir)
        self.backup_log: List[tuple] = []  # (original, backup_path, timestamp)
        self._lock = threading.Lock()

    def _resolve_backup_dir(self, backup_dir: Optional[str]) -> Optional[str]:
        """Resolve explicit backup directories in a cross-platform-safe way."""
        if not backup_dir:
            return None
        if os.path.isabs(backup_dir):
            return backup_dir
        return os.path.join(os.fspath(get_data_dir()), backup_dir)
    
    def is_backed_up(self, file_path: str) -> bool:
        """Check if a file has already been backed up in this session."""
        with self._lock:
            norm = os.path.normcase(os.path.abspath(file_path))
            return any(os.path.normcase(os.path.abspath(orig)) == norm for orig, _, _ in self.backup_log)

    def get_backup_path_for_file(self, file_path: str) -> Optional[str]:
        """Return the most recent backup path for a file if backed up."""
        with self._lock:
            norm = os.path.normcase(os.path.abspath(file_path))
            for orig, bak, _ in reversed(self.backup_log):
                if os.path.normcase(os.path.abspath(orig)) == norm and os.path.exists(bak):
                    return bak
            return None

    def create_backup(self, file_path: str, use_timestamp: bool = True, only_once: bool = True) -> Optional[str]:
        """
        Create a backup of a file.
        
        Args:
            file_path: Path to the file to backup
            use_timestamp: If True, add timestamp to backup filename
            only_once: If True and the file has already been backed up in this session,
                       returns the existing backup path without overwriting it.
            
        Returns:
            Path to the backup file, or None if backup failed
        """
        if only_once and self.is_backed_up(file_path):
            return self.get_backup_path_for_file(file_path)

        if not os.path.exists(file_path):
            logger.error(f"Cannot backup non-existent file: {file_path}")
            return None
        
        with self._lock:
            try:
                # Determine backup directory
                if self.backup_dir:
                    backup_base = self.backup_dir
                else:
                    file_dir = os.path.dirname(file_path)
                    backup_base = os.path.join(file_dir, '.rpgm_backup')
                
                # Create backup directory if needed
                os.makedirs(backup_base, exist_ok=True)
                
                # Generate backup filename
                filename = os.path.basename(file_path)
                if use_timestamp:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    name, ext = os.path.splitext(filename)
                    backup_name = f"{name}_{timestamp}{ext}"
                else:
                    backup_name = f"{filename}.bak"
                
                backup_path = os.path.join(backup_base, backup_name)
                
                # Don't overwrite existing backup with same name
                if os.path.exists(backup_path):
                    counter = 1
                    while os.path.exists(backup_path):
                        name, ext = os.path.splitext(backup_name)
                        backup_path = os.path.join(backup_base, f"{name}_{counter}{ext}")
                        counter += 1
                
                # Copy file
                shutil.copy2(file_path, backup_path)
                
                # Log the backup
                self.backup_log.append((file_path, backup_path, datetime.now()))
                logger.info(f"Created backup: {backup_path}")
                
                return backup_path
                
            except Exception as e:
                logger.error(f"Failed to create backup for {file_path}: {e}")
                return None
    
    def restore_backup(self, backup_path: str, original_path: Optional[str] = None) -> bool:
        """
        Restore a file from backup.
        
        Args:
            backup_path: Path to the backup file
            original_path: Path to restore to. If None, attempts to infer from backup log.
            
        Returns:
            True if restoration succeeded
        """
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        # Find original path from log if not provided
        if not original_path:
            for orig, bak, _ in self.backup_log:
                if bak == backup_path:
                    original_path = orig
                    break
        
        if not original_path:
            logger.error("Cannot determine original path for restoration")
            return False
        
        try:
            shutil.copy2(backup_path, original_path)
            logger.info(f"Restored {original_path} from {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def restore_all(self) -> int:
        """
        Restore all files from backups in the log.
        
        Returns:
            Number of files restored
        """
        restored = 0
        for original, backup, _ in reversed(self.backup_log):
            if self.restore_backup(backup, original):
                restored += 1
        return restored
    
    def cleanup_old_backups(self, max_age_days: int = 7, keep_latest: int = 3):
        """
        Clean up old backup files.
        
        Args:
            max_age_days: Delete backups older than this many days
            keep_latest: Always keep at least this many recent backups per file
        """
        if not self.backup_dir or not os.path.exists(self.backup_dir):
            return
        
        now = datetime.now()
        file_backups: dict = {}  # original_name -> list of (path, mtime)
        
        # Collect all backups
        for entry in os.scandir(self.backup_dir):
            if entry.is_file():
                mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                # Extract original filename (remove timestamp suffix)
                name = entry.name
                # Pattern: name_YYYYMMDD_HHMMSS.ext
                parts = name.rsplit('_', 2)
                if len(parts) >= 2:
                    base_name = parts[0]
                else:
                    base_name = name
                
                if base_name not in file_backups:
                    file_backups[base_name] = []
                file_backups[base_name].append((entry.path, mtime))
        
        # Process each file's backups
        for base_name, backups in file_backups.items():
            # Sort by modification time (newest first)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            for i, (path, mtime) in enumerate(backups):
                # Keep latest N
                if i < keep_latest:
                    continue
                
                # Check age
                age = (now - mtime).days
                if age > max_age_days:
                    try:
                        os.remove(path)
                        logger.info(f"Deleted old backup: {path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete backup {path}: {e}")
    
    def get_backups_for_file(self, file_path: str) -> List[str]:
        """Get list of available backups for a file."""
        backups = []
        for original, backup, _ in self.backup_log:
            if original == file_path and os.path.exists(backup):
                backups.append(backup)
        return backups
    
    def get_backup_stats(self) -> dict:
        """Get statistics about backups."""
        return {
            'total_backups': len(self.backup_log),
            'backup_dir': self.backup_dir,
            'files_backed_up': len(set(orig for orig, _, _ in self.backup_log))
        }

    def create_session_manifest(self, session_name: Optional[str] = None) -> Optional[str]:
        """
        Export a JSON manifest containing records of all files modified/backed up in this session,
        including their SHA-256 hashes and backup paths.
        """
        with self._lock:
            if not self.backup_log:
                return None

            import hashlib
            import json

            def _calc_sha256(path: str) -> Optional[str]:
                if not os.path.exists(path):
                    return None
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                return h.hexdigest()

            target_dir = self.backup_dir
            if not target_dir:
                target_dir = os.path.join(os.path.dirname(self.backup_log[0][0]), '.rpgm_backup')
            os.makedirs(target_dir, exist_ok=True)

            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = session_name or f"manifest_{timestamp_str}.json"
            manifest_path = os.path.join(target_dir, name)

            records = []
            for orig, bak, ts in self.backup_log:
                records.append({
                    "original": orig,
                    "backup": bak,
                    "timestamp": ts.isoformat(),
                    "backup_sha256": _calc_sha256(bak),
                    "original_sha256": _calc_sha256(orig),
                })

            manifest_data = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "total_files": len(records),
                "records": records,
            }

            try:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest_data, f, indent=2, ensure_ascii=False)
                logger.info(f"Created backup session manifest: {manifest_path}")
                return manifest_path
            except Exception as exc:
                logger.error(f"Failed to create session manifest {manifest_path}: {exc}")
                return None

    def rollback_manifest(self, manifest_path: str) -> int:
        """
        Restore all files specified in a session manifest.
        Returns the number of successfully restored files.
        """
        if not os.path.exists(manifest_path):
            logger.error(f"Manifest not found: {manifest_path}")
            return 0

        import json
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to read manifest {manifest_path}: {exc}")
            return 0

        restored_count = 0
        records = manifest_data.get("records", [])
        for record in reversed(records):
            orig = record.get("original")
            bak = record.get("backup")
            if orig and bak and os.path.exists(bak):
                if self.restore_backup(bak, orig):
                    restored_count += 1

        logger.info(f"Rollback completed: {restored_count}/{len(records)} files restored from {manifest_path}")
        return restored_count



# Global backup manager instance
_backup_manager: Optional[BackupManager] = None


def get_backup_manager(backup_dir: Optional[str] = None) -> BackupManager:
    """Get or create the global backup manager."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager(backup_dir)
    elif backup_dir is not None:
        requested_dir = os.path.normcase(os.path.abspath(backup_dir))
        current_dir = (
            os.path.normcase(os.path.abspath(_backup_manager.backup_dir))
            if _backup_manager.backup_dir
            else None
        )
        if requested_dir != current_dir:
            _backup_manager = BackupManager(backup_dir)
    return _backup_manager


def reset_backup_manager() -> None:
    """Reset the global backup manager singleton."""
    global _backup_manager
    _backup_manager = None


def backup_file(file_path: str) -> Optional[str]:
    """Convenience function to backup a single file."""
    return get_backup_manager().create_backup(file_path)


def restore_file(backup_path: str, original_path: Optional[str] = None) -> bool:
    """Convenience function to restore a file from backup."""
    return get_backup_manager().restore_backup(backup_path, original_path)
