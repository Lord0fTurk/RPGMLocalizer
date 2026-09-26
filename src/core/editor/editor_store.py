"""
High-performance SQLite and FTS5 storage engine for RPG Maker translation editing.
Manages persistent project string databases, sub-millisecond full-text queries,
dirty-state tracking, and category indexing.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import zlib
from typing import Any, Dict, List, Optional, Tuple

from src.core.editor.syntax_checker import (
    check_line_overflow,
    extract_escape_codes,
    normalize_turkish,
    validate_codes,
)
from src.core.text_segmenter import SegmentType, segment_text, reassemble


STORE_VERSION = 4


def _compute_sample_crc(file_path: str) -> int:
    """Compute fast CRC32 of first 4KB and last 4KB to detect silent edits instantly."""
    try:
        size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            if size <= 8192:
                return zlib.crc32(f.read())
            head = f.read(4096)
            f.seek(-4096, os.SEEK_END)
            tail = f.read(4096)
            return zlib.crc32(head + tail)
    except OSError:
        return 0


def classify_category(file_name: str, tag: str = "") -> str:
    """Categorize an RPG Maker or WOLF RPG game data string into logical translation sections."""
    fn = file_name.lower()
    t = (tag or "").lower()

    if "system" in t:
        return "system"
    if "dialogue" in t or "message" in t or "choice" in t:
        return "dialogues"
    if "item" in t or "skill" in t or "weapon" in t or "armor" in t:
        return "items"
    if "actor" in t:
        return "actors"
    if fn.startswith("map") or any(fn.startswith(p) for p in ("commonevents", "commonevent", "scenarios", "scenario", "evtext")) or "evtext" in fn:
        return "dialogues"
    if any(fn.startswith(p) for p in ("actors", "classes")):
        return "actors"
    if any(fn.startswith(p) for p in ("items", "weapons", "armors", "skills", "states")):
        return "items"
    if any(fn.startswith(p) for p in ("system", "troops", "animations")):
        return "system"
    if fn.endswith(".js") or "plugin" in fn:
        return "plugins"
    return "other"


def _build_fts_match_expr(tokens: list[str]) -> str:
    """Build an FTS5 MATCH expression with prefix matching for each token.

    FTS5's unicode61 tokenizer folds query terms itself (``I`` -> ``i``), while
    Turkish casing folds ``I`` -> ``ı``. Indexed Turkish text may contain either form,
    so every token that differs under Turkish folding is matched as an OR of both
    variants. Pre-folding the query alone would silently miss e.g. ``Island``.
    """
    parts: list[str] = []
    for tok in tokens:
        variants = {tok, normalize_turkish(tok)}
        if len(variants) == 1:
            parts.append(f'"{tok}"*')
        else:
            parts.append("(" + " OR ".join(f'"{v}"*' for v in sorted(variants)) + ")")
    # Explicit AND: FTS5 rejects implicit conjunction after a parenthesised group.
    return " AND ".join(parts)


CATEGORY_LABELS = {
    "all": "Tümü",
    "dialogues": "🎭 Diyaloglar & Haritalar",
    "actors": "👥 Karakterler & Sınıflar",
    "items": "⚔️ Eşyalar & Yetenekler",
    "system": "⚙️ Sistem & Terimler",
    "plugins": "🔌 Eklentiler & Kodlar",
    "other": "📁 Diğer Dosyalar",
}


class EditorStore:
    """SQLite FTS5 backed store for browsing and editing RPG Maker game strings."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def _init_schema(self) -> None:
        """Initialize database schema, FTS5 virtual table, and sync triggers."""
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS file_mtimes (
                file_path TEXT PRIMARY KEY,
                mtime REAL,
                file_size INTEGER DEFAULT 0,
                sample_crc INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS store_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                json_path TEXT NOT NULL,
                tag TEXT NOT NULL,
                category TEXT NOT NULL,
                original_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                prev_context TEXT DEFAULT '',
                next_context TEXT DEFAULT '',
                is_modified INTEGER DEFAULT 0,
                line_count INTEGER DEFAULT 1,
                has_warning INTEGER DEFAULT 0,
                warning_msg TEXT DEFAULT '',
                manual_wrap INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_entries_file ON entries(file_name);
            CREATE INDEX IF NOT EXISTS idx_entries_cat ON entries(category);
            CREATE INDEX IF NOT EXISTS idx_entries_modified ON entries(is_modified);
            CREATE INDEX IF NOT EXISTS idx_entries_warning ON entries(has_warning);

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                file_name,
                original_text,
                translated_text,
                content='entries',
                content_rowid='id',
                tokenize = 'unicode61 remove_diacritics 2'
            );

            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
              INSERT INTO entries_fts(rowid, file_name, original_text, translated_text)
              VALUES (new.id, new.file_name, new.original_text, new.translated_text);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
              INSERT INTO entries_fts(entries_fts, rowid, file_name, original_text, translated_text)
              VALUES ('delete', old.id, old.file_name, old.original_text, old.translated_text);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
              INSERT INTO entries_fts(entries_fts, rowid, file_name, original_text, translated_text)
              VALUES ('delete', old.id, old.file_name, old.original_text, old.translated_text);
              INSERT INTO entries_fts(rowid, file_name, original_text, translated_text)
              VALUES (new.id, new.file_name, new.original_text, new.translated_text);
            END;
        """)
            cur.execute("PRAGMA table_info(file_mtimes)")
            existing_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cur.fetchall()}
            if existing_cols:
                if "file_size" not in existing_cols:
                    cur.execute("ALTER TABLE file_mtimes ADD COLUMN file_size INTEGER DEFAULT 0")
                if "sample_crc" not in existing_cols:
                    cur.execute("ALTER TABLE file_mtimes ADD COLUMN sample_crc INTEGER DEFAULT 0")
            self.conn.commit()

    def is_cache_valid(self, project_files: list[str]) -> bool:
        """Return True if stored mtimes, sizes, and CRCs match current disk files and entries exist."""
        if self.db_path == ":memory:":
            return False

        with self._lock:
            cur = self.conn.cursor()
            try:
                cur.execute("SELECT value FROM store_meta WHERE key = 'version'")
                row = cur.fetchone()
                if not row or int(row[0]) != STORE_VERSION:
                    return False
            except (sqlite3.OperationalError, ValueError):
                return False

            cur.execute("SELECT COUNT(*) FROM entries")
            if cur.fetchone()[0] == 0:
                return False

            cur.execute("SELECT file_path, mtime, file_size, sample_crc FROM file_mtimes")
            stored_records = {
                os.path.normcase(os.path.normpath(r[0])): (r[1], r[2] or 0, r[3] or 0)
                for r in cur.fetchall()
            }

            if not stored_records or len(stored_records) != len(project_files):
                return False

            for fp in project_files:
                norm_fp = os.path.normcase(os.path.normpath(fp))
                if not os.path.exists(fp):
                    return False
                stored = stored_records.get(norm_fp)
                if stored is None:
                    return False
                stored_mtime, stored_size, stored_crc = stored
                try:
                    curr_mtime = os.path.getmtime(fp)
                    curr_size = os.path.getsize(fp)
                    # Tier 1: Fast mtime & file size check
                    if abs(curr_mtime - stored_mtime) > 0.001 or curr_size != stored_size:
                        return False
                    # Tier 2: Sample CRC check (detects in-place edits with preserved mtime/size)
                    curr_crc = _compute_sample_crc(fp)
                    if curr_crc != stored_crc:
                        return False
                except OSError:
                    return False

            return True

    def load_entries(
        self,
        extracted_files: dict[str, list[tuple[str, str, str]]],
        backup_files: dict[str, dict[str, str]] | None = None,
        cache_resolver: Any | None = None,
        target_lang: str = "tr",
        source_lang: str = "auto",
    ) -> int:
        """Populate database from extracted file entries, linking neighbor contexts.

        Unsaved edits (``is_modified = 1``) from the previous load are carried over to
        the matching ``(file_path, json_path)`` rows so a forced rescan — e.g. after the
        auto-translate pipeline finishes — never silently discards the user's work.
        """
        backup_files = backup_files or {}
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT file_path, json_path, translated_text FROM entries WHERE is_modified = 1"
            )
            pending_edits: dict[tuple[str, str], str] = {
                (os.path.normcase(os.path.normpath(r["file_path"])), r["json_path"]): r["translated_text"]
                for r in cur.fetchall()
            }
            cur.execute("DELETE FROM entries")
            cur.execute("DELETE FROM file_mtimes")

            records: list[tuple] = []
            mtimes: list[tuple] = []

            for file_path, entries in extracted_files.items():
                norm_fp = os.path.normcase(os.path.normpath(file_path))
                file_name = os.path.basename(file_path)
                try:
                    if os.path.exists(file_path):
                        mtime = os.path.getmtime(file_path)
                        fsize = os.path.getsize(file_path)
                        crc = _compute_sample_crc(file_path)
                    else:
                        mtime, fsize, crc = 0.0, 0, 0
                except OSError:
                    mtime, fsize, crc = 0.0, 0, 0
                mtimes.append((file_path, mtime, fsize, crc))

                file_backups = backup_files.get(file_path, {})
                if not file_backups:
                    for b_path, b_data in backup_files.items():
                        if os.path.normcase(os.path.normpath(b_path)) == norm_fp:
                            file_backups = b_data
                            break
                total_in_file = len(entries)

                for idx, (path, text, tag) in enumerate(entries):
                    category = classify_category(file_name, tag)

                    # Tri-layer text resolution: Vanilla vs Current Translation
                    if path in file_backups:
                        original_text = file_backups[path]
                        translated_text = text
                    elif cache_resolver and hasattr(cache_resolver, "get"):
                        try:
                            cached = cache_resolver.get(text, source_lang, target_lang)
                        except TypeError:
                            try:
                                cached = cache_resolver.get(text, target_lang)
                            except Exception:
                                cached = None
                        except Exception:
                            cached = None
                        original_text = text
                        translated_text = cached if cached else text
                    else:
                        original_text = text
                        translated_text = text

                    is_modified = 0
                    pending = pending_edits.get((norm_fp, path))
                    if pending is not None and pending != translated_text:
                        translated_text = pending
                        is_modified = 1

                    # Context links for consecutive dialogue lines in the same file
                    prev_ctx = ""
                    next_ctx = ""
                    if category == "dialogues":
                        if idx > 0 and entries[idx - 1][2] == tag:
                            prev_ctx = entries[idx - 1][1]
                        if idx + 1 < total_in_file and entries[idx + 1][2] == tag:
                            next_ctx = entries[idx + 1][1]

                    # Run syntax and line diagnostics
                    warnings = validate_codes(original_text, translated_text)
                    lines, overflow = check_line_overflow(translated_text, tag)
                    if overflow:
                        warnings.append(f"Mesaj kutusu sınırı aşıldı ({lines}/4 satır)")

                    has_warning = 1 if warnings else 0
                    warning_msg = " | ".join(warnings) if warnings else ""

                    records.append((
                        file_path,
                        file_name,
                        path,
                        tag,
                        category,
                        original_text,
                        translated_text,
                        prev_ctx,
                        next_ctx,
                        is_modified,
                        lines,
                        has_warning,
                        warning_msg,
                        is_modified,  # manual_wrap mirrors a carried-over user edit
                    ))

            cur.executemany("""
                INSERT INTO entries (
                    file_path, file_name, json_path, tag, category,
                    original_text, translated_text, prev_context, next_context,
                    is_modified, line_count, has_warning, warning_msg, manual_wrap
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)

            cur.executemany(
                "INSERT OR REPLACE INTO file_mtimes (file_path, mtime, file_size, sample_crc) VALUES (?, ?, ?, ?)",
                mtimes,
            )
            cur.execute("INSERT OR REPLACE INTO store_meta (key, value) VALUES ('version', ?)", (str(STORE_VERSION),))
            self.conn.commit()
            return len(records)

    def query_page(
        self,
        search_query: str = "",
        category_filter: str = "all",
        file_filter: str = "all",
        status_filter: str = "all",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """Execute a paginated, filtered search query with FTS5 matching."""
        clauses: list[str] = []
        params: list[Any] = []

        with self._lock:
            # 1. Full-Text Search
            cleaned_search = search_query.strip()
            if cleaned_search:
                # Replace non-alphanumeric with spaces to preserve token boundaries
                spaced = "".join(c if (c.isalnum() or c in "_-") else " " for c in cleaned_search)
                tokens = [t for t in spaced.split() if t]
                if tokens:
                    fts_expr = _build_fts_match_expr(tokens)
                    clauses.append("entries.id IN (SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?)")
                    params.append(fts_expr)
                else:
                    # Fallback to substring match for symbol-only queries (e.g. "???", "...")
                    clauses.append("(entries.original_text LIKE ? OR entries.translated_text LIKE ?)")
                    like_term = f"%{cleaned_search}%"
                    params.extend([like_term, like_term])

            # 2. Category filter
            if category_filter and category_filter != "all":
                clauses.append("entries.category = ?")
                params.append(category_filter)

            # 3. File filter
            if file_filter and file_filter != "all":
                clauses.append("entries.file_name = ?")
                params.append(file_filter)

            # 4. Status filter
            if status_filter == "modified":
                clauses.append("entries.is_modified = 1")
            elif status_filter == "warnings":
                clauses.append("entries.has_warning = 1")
            elif status_filter == "untranslated":
                clauses.append("(entries.translated_text = entries.original_text OR entries.translated_text = '')")
            elif status_filter == "translated":
                clauses.append("(entries.translated_text != entries.original_text AND entries.translated_text != '')")

            where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

            # Total count query
            cur = self.conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM entries {where_sql}", params)
            total_count = cur.fetchone()[0]

            # Paged rows query
            page = max(1, page)
            offset = (page - 1) * page_size
            paged_params = list(params) + [page_size, offset]

            cur.execute(f"""
                SELECT id, file_path, file_name, json_path, tag, category,
                       original_text, translated_text, prev_context, next_context,
                       is_modified, line_count, has_warning, warning_msg, manual_wrap
                FROM entries {where_sql}
                ORDER BY id ASC
                LIMIT ? OFFSET ?
            """, paged_params)

            rows = [dict(row) for row in cur.fetchall()]
            return rows, total_count

    def get_entry(self, entry_id: int) -> dict | None:
        """Fetch a single entry by primary ID."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def update_entry(self, entry_id: int, new_translated: str) -> dict | None:
        """Update translation for an entry, recomputing warnings and dirty flag."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT original_text, tag FROM entries WHERE id = ?", (entry_id,))
            row = cur.fetchone()
            if not row:
                return None

            orig = row["original_text"]
            tag = row["tag"]

            warnings = validate_codes(orig, new_translated)
            lines, overflow = check_line_overflow(new_translated, tag)
            if overflow:
                warnings.append(f"Mesaj kutusu sınırı aşıldı ({lines}/4 satır)")

            has_warning = 1 if warnings else 0
            warning_msg = " | ".join(warnings) if warnings else ""

            cur.execute("""
                UPDATE entries
                SET translated_text = ?,
                    is_modified = 1,
                    line_count = ?,
                    has_warning = ?,
                    warning_msg = ?,
                    manual_wrap = 1
                WHERE id = ?
            """, (new_translated, lines, has_warning, warning_msg, entry_id))
            self.conn.commit()

            return self.get_entry(entry_id)

    def revert_entry(self, entry_id: int) -> dict | None:
        """Revert an entry's translation to its original text."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT original_text, tag FROM entries WHERE id = ?", (entry_id,))
            row = cur.fetchone()
            if not row:
                return None

            orig = row["original_text"]
            tag = row["tag"]
            lines, overflow = check_line_overflow(orig, tag)

            cur.execute("""
                UPDATE entries
                SET translated_text = ?,
                    is_modified = 0,
                    line_count = ?,
                    has_warning = 0,
                    warning_msg = '',
                    manual_wrap = 0
                WHERE id = ?
            """, (orig, lines, entry_id))
            self.conn.commit()

            return self.get_entry(entry_id)

    def batch_replace(
        self,
        search_term: str,
        replace_term: str,
        file_filter: str = "all",
        category_filter: str = "all",
        match_case: bool = False,
    ) -> int:
        """Safely replace text across translated strings preserving escape codes."""
        if not search_term:
            return 0

        clauses: list[str] = []
        params: list[Any] = []

        if file_filter and file_filter != "all":
            clauses.append("file_name = ?")
            params.append(file_filter)
        if category_filter and category_filter != "all":
            clauses.append("category = ?")
            params.append(category_filter)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f"SELECT id, original_text, translated_text, tag FROM entries {where_sql}", params)
            rows = cur.fetchall()

            modified_count = 0
            updates: list[tuple] = []

            for row in rows:
                entry_id = row["id"]
                trans = row["translated_text"]
                orig = row["original_text"]
                tag = row["tag"]

                # Safe segment-based replacement: separate CODE from TEXT
                segments = segment_text(trans)
                text_changed = False
                new_segments = []

                for seg in segments:
                    if seg.type == SegmentType.TEXT:
                        if match_case:
                            new_content = seg.content.replace(search_term, replace_term)
                        else:
                            import re
                            pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                            new_content = pattern.sub(replace_term, seg.content)

                        if new_content != seg.content:
                            text_changed = True
                        new_segments.append(new_content)
                    else:
                        new_segments.append(seg.content)

                if text_changed:
                    new_trans = "".join(new_segments)
                    warnings = validate_codes(orig, new_trans)
                    lines, overflow = check_line_overflow(new_trans, tag)
                    if overflow:
                        warnings.append(f"Mesaj kutusu sınırı aşıldı ({lines}/4 satır)")

                    updates.append((
                        new_trans,
                        lines,
                        1 if warnings else 0,
                        " | ".join(warnings) if warnings else "",
                        entry_id,
                    ))
                    modified_count += 1

            if updates:
                cur.executemany("""
                    UPDATE entries
                    SET translated_text = ?,
                        is_modified = 1,
                        line_count = ?,
                        has_warning = ?,
                        warning_msg = ?,
                        manual_wrap = 1
                    WHERE id = ?
                """, updates)
                self.conn.commit()

            return modified_count

    def get_modified_entries(self) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
        """Return (changes_by_file, originals_by_file) for all modified entries."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT file_path, json_path, original_text, translated_text FROM entries WHERE is_modified = 1")
            changes: dict[str, dict[str, str]] = {}
            originals: dict[str, dict[str, str]] = {}
            for row in cur.fetchall():
                fp = row["file_path"]
                jp = row["json_path"]
                orig = row["original_text"]
                txt = row["translated_text"]
                if fp not in changes:
                    changes[fp] = {}
                    originals[fp] = {}
                changes[fp][jp] = txt
                originals[fp][jp] = orig
            return changes, originals

    def mark_saved(self, saved_files: list[str]) -> None:
        """Mark specified files as unmodified and update their mtimes, sizes, and sample CRCs."""
        with self._lock:
            cur = self.conn.cursor()
            for fp in saved_files:
                cur.execute("UPDATE entries SET is_modified = 0 WHERE file_path = ?", (fp,))
                try:
                    if os.path.exists(fp):
                        mtime = os.path.getmtime(fp)
                        fsize = os.path.getsize(fp)
                        crc = _compute_sample_crc(fp)
                    else:
                        mtime, fsize, crc = 0.0, 0, 0
                except OSError:
                    mtime, fsize, crc = 0.0, 0, 0
                cur.execute(
                    "INSERT OR REPLACE INTO file_mtimes (file_path, mtime, file_size, sample_crc) VALUES (?, ?, ?, ?)",
                    (fp, mtime, fsize, crc),
                )
            self.conn.commit()

    def get_categories_and_files(self) -> dict[str, list[str]]:
        """Return categorized file names for two-tier filtering in UI."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT category, file_name FROM entries ORDER BY file_name ASC")
            cat_map: dict[str, list[str]] = {k: [] for k in CATEGORY_LABELS if k != "all"}
            for row in cur.fetchall():
                cat = row["category"]
                fn = row["file_name"]
                if cat in cat_map:
                    cat_map[cat].append(fn)
            return cat_map

    def get_stats(self) -> dict[str, int]:
        """Return statistical counts: total, modified, warnings, untranslated."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*),
                    SUM(CASE WHEN is_modified = 1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN has_warning = 1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN translated_text = original_text OR translated_text = '' THEN 1 ELSE 0 END)
                FROM entries
            """)
            row = cur.fetchone()
            return {
                "total": row[0] or 0,
                "modified": row[1] or 0,
                "warnings": row[2] or 0,
                "untranslated": row[3] or 0,
            }

    def _build_untranslated_clauses(
        self,
        file_filter: str = "all",
        category_filter: str = "all",
        search_query: str = "",
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = [
            "(entries.translated_text = entries.original_text OR entries.translated_text = '')"
        ]
        params: list[Any] = []

        if file_filter and file_filter not in ("all", "Tüm Dosyalar"):
            clauses.append("entries.file_name = ?")
            params.append(file_filter)
        if category_filter and category_filter != "all":
            clauses.append("entries.category = ?")
            params.append(category_filter)

        cleaned_search = search_query.strip()
        if cleaned_search:
            spaced = "".join(c if (c.isalnum() or c in "_-") else " " for c in cleaned_search)
            tokens = [t for t in spaced.split() if t]
            if tokens:
                fts_expr = _build_fts_match_expr(tokens)
                clauses.append("entries.id IN (SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?)")
                params.append(fts_expr)
            else:
                clauses.append("(entries.original_text LIKE ? OR entries.translated_text LIKE ?)")
                like_term = f"%{cleaned_search}%"
                params.extend([like_term, like_term])

        where_sql = "WHERE " + " AND ".join(clauses)
        return where_sql, params

    def get_untranslated_count(
        self,
        file_filter: str = "all",
        category_filter: str = "all",
        search_query: str = "",
    ) -> int:
        """Return the count of untranslated entries matching the given scope filters."""
        where_sql, params = self._build_untranslated_clauses(file_filter, category_filter, search_query)
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM entries {where_sql}", params)
            row = cur.fetchone()
            return row[0] if row else 0

    def get_untranslated_batch(
        self,
        offset: int = 0,
        limit: int = 200,
        file_filter: str = "all",
        category_filter: str = "all",
        search_query: str = "",
        last_id: int = 0,
    ) -> list[dict]:
        """Return a batch of entries whose translated_text equals original_text or is empty.

        Supports both keyset pagination (last_id) and classic offset pagination.
        """
        where_sql, params = self._build_untranslated_clauses(file_filter, category_filter, search_query)

        if last_id > 0:
            where_sql += " AND entries.id > ?"
            params.append(last_id)
            params.append(limit)
            sql = f"SELECT entries.id, entries.original_text, entries.tag FROM entries {where_sql} ORDER BY entries.id ASC LIMIT ?"
        else:
            params += [limit, offset]
            sql = f"SELECT entries.id, entries.original_text, entries.tag FROM entries {where_sql} ORDER BY entries.id ASC LIMIT ? OFFSET ?"

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def bulk_apply_auto_translations(
        self,
        translations: list[tuple[int, str]],
    ) -> int:
        """Apply a list of (entry_id, translated_text) pairs produced by the auto-translator.

        Marks each row as is_modified=1 so surgical save will persist them.
        Returns the number of successfully updated rows.
        """
        if not translations:
            return 0

        updates: list[tuple] = []
        with self._lock:
            cur = self.conn.cursor()
            for entry_id, new_text in translations:
                cur.execute(
                    "SELECT original_text, tag FROM entries WHERE id = ?", (entry_id,)
                )
                row = cur.fetchone()
                if not row:
                    continue
                orig = row["original_text"]
                tag = row["tag"]

                warnings = validate_codes(orig, new_text)
                lines, overflow = check_line_overflow(new_text, tag)
                if overflow:
                    warnings.append(f"Mesaj kutusu sınırı aşıldı ({lines}/4 satır)")

                updates.append((
                    new_text,
                    lines,
                    1 if warnings else 0,
                    " | ".join(warnings) if warnings else "",
                    entry_id,
                ))

            if updates:
                cur.executemany(
                    """
                    UPDATE entries
                    SET translated_text = ?,
                        is_modified = 1,
                        line_count = ?,
                        has_warning = ?,
                        warning_msg = ?
                    WHERE id = ?
                    """,
                    updates,
                )
                self.conn.commit()

        return len(updates)

