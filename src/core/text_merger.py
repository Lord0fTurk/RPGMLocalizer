import re
import logging
from typing import List, Tuple, Dict, Any, Optional
from src.core.constants import (TOKEN_LINE_BREAK, REGEX_LINE_SPLIT, DEFAULT_BATCH_SIZE, 
                        DEFAULT_MAX_CHARS, TEXT_MERGER_MAX_SAFE_CHARS, 
                        TOKEN_MERGE_SEPARATOR, REGEX_MERGE_SPLIT, TOKEN_BATCH_SEPARATOR)

logger = logging.getLogger(__name__)

class TextMerger:
    """
    Manages the merging of multiple text entries into single translation blocks
    using invisible Ghost Tokens as separators.
    """
    
    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size
        self.current_block: List[Tuple[str, str, str]] = [] # context, key, text
        self.merged_requests: List[Dict[str, Any]] = []
        
        # Safe limit slightly lower than Google's 5000 char hard limit
        self.MAX_SAFE_CHARS = TEXT_MERGER_MAX_SAFE_CHARS 

    @staticmethod
    def _is_mergeable_tag(tag: str) -> bool:
        if not tag:
            return False
        return any(tag.startswith(prefix) for prefix in ("dialogue_block", "message_dialogue", "scroll_text"))

    def add(self, key: str, text: str, context_info: str = ""):
        """Add a text entry to be merged to the current block."""
        if not text.strip():
            return

        # Calculate predicted size
        current_char_count = sum(len(e[2]) for e in self.current_block)
        from src.core.constants import SAFE_MERGE_SEPARATOR
        separator_overhead = len(self.current_block) * len(SAFE_MERGE_SEPARATOR)
        total_predicted = current_char_count + len(text) + separator_overhead
        
        if len(self.current_block) >= self.batch_size or total_predicted > self.MAX_SAFE_CHARS:
            self.flush_block()
            
        self.current_block.append((context_info, key, text))

    def flush_block(self):
        """Finalize the current block and wrap it for translation."""
        if not self.current_block:
            return
            
        if len(self.current_block) == 1:
            context, key, text = self.current_block[0]
            self.merged_requests.append({
                'text': text,
                'metadata': {
                    'description': context,
                    'key': key,
                    'is_merged': False
                }
            })
        else:
            # Join items with our Safe Structural Separator (Tungsten Armor)
            from src.core.constants import SAFE_MERGE_SEPARATOR
            merged_text = SAFE_MERGE_SEPARATOR.join(e[2] for e in self.current_block)
            first_entry = self.current_block[0]
            
            self.merged_requests.append({
                'text': merged_text,
                'metadata': {
                    'description': f"Merged Batch ({len(self.current_block)} items)",
                    'key': first_entry[1],
                    'is_merged': True,
                    'original_entries': self.current_block.copy()
                }
            })
        self.current_block = []

    def get_requests(self) -> List[Dict[str, Any]]:
        self.flush_block()
        return self.merged_requests
        
    def reset(self):
        self.current_block = []
        self.merged_requests = []

    def split_merged_result(self, merged_text: str, original_entries: List[Tuple[str, str, str]]) -> List[Tuple[str, str]]:
        """Splits the merged result and returns a list of (key, text) pairs."""
        lines, expected_count, mismatch = self._split_lines(merged_text, original_entries)

        if mismatch:
            if len(lines) > expected_count:
                # Extra separators injected by translator — trim surplus.
                lines = lines[:expected_count]
            else:
                # Fewer parts than expected — pad with original texts to avoid data loss.
                for i in range(len(lines), expected_count):
                    lines.append(original_entries[i][2])

        results = []
        for i, line in enumerate(lines):
            if i < len(original_entries):
                results.append((original_entries[i][1], line))
        return results

    def split_merged_result_checked(self, merged_text: str, original_entries: Any) -> Tuple[List[Tuple[str, str]], bool]:
        """Backward compatibility wrapper for existing tests and UI."""
        formatted_orig = []
        for entry in original_entries:
            if len(entry) == 3:
                formatted_orig.append(entry)
            else:
                formatted_orig.append(("", str(entry[1]), str(entry[2])))

        res = self.split_merged_result(merged_text, formatted_orig)
        _, _, mismatch = self._split_lines(merged_text, formatted_orig)
        return res, mismatch

    def _split_lines(self, merged_text: str, original_entries: List[Tuple[str, str, str]]) -> Tuple[List[str], int, bool]:
        """
        Split translated merged block into entries using the Ghost Token.
        Crucial: No longer falls back to splitlines() as it causes context shifts.
        """
        expected_count = len(original_entries)
        
        # Normalize separators for splitting.
        # Primary: |||RPGMSEP_M||| (ASCII, Google-safe, already matched by REGEX_MERGE_SPLIT).
        # Legacy: Unicode ⟦_M_⟧ bracket mutations → normalize to canonical ASCII form.
        merged_text = re.sub(r'[?\[(\{【⟦]\s*_\s*[mM]\s*_\s*[?\])\}】⟧]', '|||RPGMSEP_M|||', merged_text)

        # Use regex to find separators
        if not hasattr(self, '_merge_split_pattern'):
            self._merge_split_pattern = re.compile(REGEX_MERGE_SPLIT, re.IGNORECASE | re.DOTALL)
            
        if self._merge_split_pattern.search(merged_text):
            lines = self._merge_split_pattern.split(merged_text)
        else:
            lines = [merged_text]

        # Cleanup whitespace and drop blank lines created by leading/trailing separators
        lines = [l.strip() for l in lines if l.strip()]
        
        # Exact match check
        mismatch = len(lines) != expected_count
        return lines, expected_count, mismatch

    def create_merged_requests(self, entries: List[Tuple]) -> Tuple[List[Dict[str, Any]], Dict[str, List]]:
        if not entries:
            return [], {}
        
        file_groups: Dict[str, List[Tuple]] = {}
        for file_path, path, text, tag in entries:
            file_groups.setdefault(file_path, []).append((path, text, tag))
        
        requests_list = []
        merged_map = {}
        
        for file_path, file_entries in file_groups.items():
            self.reset()
            for path, text, tag in file_entries:
                if self._is_mergeable_tag(tag):
                    self.add(key=path, text=text, context_info=tag)
                else:
                    self.flush_block()
                    self.merged_requests.append({
                        'text': text,
                        'metadata': {'description': tag, 'key': path, 'is_merged': False, 'file': file_path}
                    })
            
            for req in self.get_requests():
                req['metadata']['file'] = file_path
                if req['metadata'].get('is_merged'):
                    lookup_key = f"{file_path}::{req['metadata']['key']}"
                    merged_map[lookup_key] = req['metadata']['original_entries']
                requests_list.append(req)
        return requests_list, merged_map

    @staticmethod
    def merge_consecutive(entries: List[Tuple[str, str, str]], max_batch_size: int = DEFAULT_BATCH_SIZE) -> List[Dict[str, Any]]:
        if not entries: return []
        requests = []
        current_block = []
        
        def _flush():
            nonlocal current_block
            if not current_block: return
            if len(current_block) == 1:
                f, k, t = current_block[0]
                requests.append({'text': t, 'metadata': {'file': f, 'key': k, 'is_merged': False}})
            else:
                from src.core.constants import SAFE_MERGE_SEPARATOR
                txt = SAFE_MERGE_SEPARATOR.join(e[2] for e in current_block)
                requests.append({'text': txt, 'metadata': {'file': current_block[0][0], 'key': current_block[0][1], 'is_merged': True, 'original_entries': current_block.copy()}})
            current_block = []

        for f, k, t, tag in entries:
            is_dialogue = any(tag.startswith(p) for p in ("dialogue_block", "message_dialogue", "scroll_text"))
            if not is_dialogue:
                _flush()
                requests.append({'text': t, 'metadata': {'file': f, 'key': k, 'is_merged': False}})
            else:
                if len(current_block) >= max_batch_size: _flush()
                current_block.append((f, k, t))
        _flush()
        return requests
