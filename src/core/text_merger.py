import re
import logging
from typing import List, Tuple, Dict, Any, Optional
from .constants import (TOKEN_LINE_BREAK, REGEX_LINE_SPLIT, DEFAULT_BATCH_SIZE, 
                        DEFAULT_MAX_CHARS, TEXT_MERGER_MAX_SAFE_CHARS)

logger = logging.getLogger(__name__)

class TextMerger:
    """
    Manages the merging of multiple text entries into single translation blocks
    to optimize API usage and maintain context.
    """
    
    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size
        self.current_block: List[Tuple[str, str, str]] = [] # context, key, text
        self.merged_requests: List[Dict[str, Any]] = []
        
        # Safe limit slightly lower than Google's 5000 char hard limit
        self.MAX_SAFE_CHARS = TEXT_MERGER_MAX_SAFE_CHARS 

    def add(self, key: str, text: str, context_info: str = ""):
        """
        Add a text entry to be merged.
        Checks both item count and character limit before adding.
        """
        if not text.strip():
            return

        # Calculate potential new size
        current_char_count = sum(len(e[2]) for e in self.current_block)
        
        # Overhead: Each item except the last adds a separator
        # If we add this item, we'll have (len+1) items, so (len) separators
        # But for safety, let's assume worst case
        separator_overhead = (len(self.current_block) + 1) * (len(TOKEN_LINE_BREAK) + 2)
        
        total_predicted = current_char_count + len(text) + separator_overhead
        
        # If buffer is full or size limit reached, flush first
        if len(self.current_block) >= self.batch_size or total_predicted > self.MAX_SAFE_CHARS:
            self.flush_block()
            
        self.current_block.append((context_info, key, text))

    def flush_block(self):
        """Finalize the current block and add to requests."""
        if not self.current_block:
            return
            
        if len(self.current_block) == 1:
            # Single entry - no separator needed
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
            # Merging multiple entries
            # Use double-bracket format so placeholder.py detects it as an EXT token.
            merged_text = f"\n{TOKEN_LINE_BREAK}\n".join(e[2] for e in self.current_block)
            
            # Use the first key as the identifier
            first_entry = self.current_block[0]
            
            self.merged_requests.append({
                'text': merged_text,
                'metadata': {
                    'description': f"Merged Batch ({len(self.current_block)} items) - Start: {first_entry[0]}",
                    'key': first_entry[1],
                    'is_merged': True,
                    'original_entries': self.current_block.copy() # Store for splitting later
                }
            })
            
        self.current_block = []

    def get_requests(self) -> List[Dict[str, Any]]:
        """Flush remaining items and return all requests."""
        self.flush_block()
        return self.merged_requests
        
    def reset(self):
        """Clear all state."""
        self.current_block = []
        self.merged_requests = []

    def split_merged_result(self, merged_text: str, original_entries: List[Tuple[str, str, str]]) -> List[Tuple[str, str]]:
        """
        Split a translated merged block back into individual lines.
        Returns list of (key, translated_line_text).
        """
        lines, expected_count, mismatch = self._split_lines(merged_text, original_entries)
        
        results = []
        
        if len(lines) == expected_count:
            # Perfect match
            for i, line in enumerate(lines):
                results.append((original_entries[i][1], line)) # key, text
            return results
            
        # Mismatch Handling
        path_info = original_entries[0][1] if original_entries else "Unknown"
        logger.warning(f"Merge Split Mismatch: Got {len(lines)} lines, expected {expected_count}. Path: {path_info}")
        
        # Alignment Strategy: Sequential assignment with padding
        for i in range(expected_count):
            entry_key = original_entries[i][1]
            if i < len(lines):
                results.append((entry_key, lines[i]))
            else:
                # Missing lines: fallback to original text
                logger.error(f"Missing translation for line {i} in merged block. Reverting to original.")
                results.append((entry_key, original_entries[i][2]))
                 
        return results

    def split_merged_result_checked(self, merged_text: str, original_entries: List[Tuple[str, str, str]]) -> Tuple[List[Tuple[str, str]], bool]:
        """
        Split a merged result and return (pairs, mismatch).
        mismatch=True indicates the translated block did NOT split into the expected count.
        """
        lines, expected_count, mismatch = self._split_lines(merged_text, original_entries)
        results = []

        if len(lines) == expected_count:
            for i, line in enumerate(lines):
                results.append((original_entries[i][1], line))
            return results, False

        # Mismatch Handling (same behavior as split_merged_result)
        path_info = original_entries[0][1] if original_entries else "Unknown"
        logger.warning(f"Merge Split Mismatch: Got {len(lines)} lines, expected {expected_count}. Path: {path_info}")

        for i in range(expected_count):
            entry_key = original_entries[i][1]
            if i < len(lines):
                results.append((entry_key, lines[i]))
            else:
                logger.error(f"Missing translation for line {i} in merged block. Reverting to original.")
                results.append((entry_key, original_entries[i][2]))

        return results, True

    def _split_lines(self, merged_text: str, original_entries: List[Tuple[str, str, str]]) -> Tuple[List[str], int, bool]:
        """Split merged text into lines and return (lines, expected_count, mismatch)."""
        expected_count = len(original_entries)
        merged_text = self._normalize_line_break_tokens(merged_text)

        if TOKEN_LINE_BREAK in merged_text:
            lines = re.split(REGEX_LINE_SPLIT, merged_text, flags=re.IGNORECASE)
        elif "[[XRPYX_LB_XRPYX]]" in merged_text:
            lines = re.split(r'\s*\[\[XRPYX_LB_XRPYX\]\]\s*', merged_text, flags=re.IGNORECASE)
        else:
            lines = merged_text.splitlines()

        lines = [l.strip() for l in lines]

        if len(lines) > expected_count and not lines[-1]:
            lines = lines[:expected_count]

        mismatch = len(lines) != expected_count
        return lines, expected_count, mismatch

    @staticmethod
    def _normalize_line_break_tokens(text: str) -> str:
        """Normalize line break tokens to improve split robustness."""
        if not text:
            return text

        normalized = text

        # Legacy format 1: [[XRPYX_LB_XRPYX]]
        if "[[XRPYX_LB_XRPYX]]" in normalized:
            normalized = normalized.replace("[[XRPYX_LB_XRPYX]]", TOKEN_LINE_BREAK)

        # Legacy format 2: |||XRPYXLB||| (long pipe format)
        # Collapse spaced-out letters (e.g., "X R P Y X L B")
        normalized = re.sub(r'X\s*R\s*P\s*Y\s*X\s*L\s*B', 'XRPYXLB', normalized, flags=re.IGNORECASE)
        
        # Normalize long pipe format to short format
        if "XRPYXLB" in normalized:
            normalized = re.sub(r'\|{2,}\s*XRPYXLB\s*\|{2,}', TOKEN_LINE_BREAK, normalized)
            normalized = normalized.replace("XRPYXLB", TOKEN_LINE_BREAK)
        
        # Legacy format 3: <XRPYX_LB> (XML attempt - didn't work with web endpoints)
        normalized = re.sub(r'<\s*XRPYX_LB\s*>', TOKEN_LINE_BREAK, normalized)
        normalized = re.sub(r'<\s*X\s*R\s*P\s*Y\s*X\s*_?\s*L\s*B\s*>', TOKEN_LINE_BREAK, normalized, flags=re.IGNORECASE)
        
        # Normalize spacing in current format: ||| XLB |||, |||XLB|||, etc.
        normalized = re.sub(r'\|{2,}\s*XLB\s*\|{2,}', TOKEN_LINE_BREAK, normalized, flags=re.IGNORECASE)

        return normalized

    def create_merged_requests(self, entries: List[Tuple]) -> Tuple[List[Dict[str, Any]], Dict[str, List]]:
        """
        Process pipeline entries and create optimized translation requests.
        
        Args:
            entries: List of (file_path, path, text, tag) tuples from extraction
            
        Returns:
            Tuple of (requests_list, merged_map)
            - requests_list: List[Dict] with 'text' and 'metadata' keys
            - merged_map: Dict mapping "file::key" to original_entries for splitting
        """
        if not entries:
            return [], {}
        
        # Group entries by file for better merging
        file_groups: Dict[str, List[Tuple]] = {}
        for file_path, path, text, tag in entries:
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append((path, text, tag))
        
        requests_list = []
        merged_map = {}
        
        # Process each file group
        for file_path, file_entries in file_groups.items():
            # Reset for each file
            self.reset()
            
            # Add entries using the existing add() method
            for path, text, tag in file_entries:
                # Use path as key and tag as context
                self.add(key=path, text=text, context_info=tag)
            
            # Get the merged requests for this file
            file_requests = self.get_requests()
            
            # Add file path to metadata and build merged_map
            for req in file_requests:
                req['metadata']['file'] = file_path
                
                # If merged, store in merged_map for later splitting
                if req['metadata'].get('is_merged'):
                    original_entries = req['metadata'].get('original_entries', [])
                    # Create lookup key: "file::path"
                    lookup_key = f"{file_path}::{req['metadata']['key']}"
                    merged_map[lookup_key] = original_entries
                
                requests_list.append(req)
        
        return requests_list, merged_map

    @staticmethod
    def merge_consecutive(entries: List[Tuple[str, str, str]], max_batch_size: int = 50) -> List[Dict[str, Any]]:
        """
        Static utility to merge consecutive dialogue lines from a raw list.
        Used by Parsers to pre-process dialogue blocks.
        """
        if not entries:
            return []
            
        requests = []
        current_block = []
        
        MAX_CHAR_LIMIT = 4000
        
        def _flush_local():
            nonlocal current_block
            if not current_block:
                return
                
            if len(current_block) == 1:
                # Single
                file_path, key, text = current_block[0]
                requests.append({
                    'text': text,
                    'metadata': {
                        'file': file_path,
                        'key': key,
                        'is_merged': False
                    }
                })
            else:
                # Merged
                merged_txt = f"\n{TOKEN_LINE_BREAK}\n".join(e[2] for e in current_block)
                first = current_block[0]
                requests.append({
                    'text': merged_txt,
                    'metadata': {
                        'file': first[0],
                        'key': first[1],
                        'is_merged': True,
                        'original_entries': [(e[0], e[1], e[2]) for e in current_block]
                    }
                })
            current_block = []

        for entry in entries:
            file_path, key, text, tag = entry
            
            # If not a dialogue block, force flush and add as single
            if tag != "dialogue_block":
                _flush_local()
                requests.append({
                    'text': text,
                    'metadata': {
                        'file': file_path,
                        'key': key,
                        'is_merged': False
                    }
                })
                continue
                
            # Logic for Dialogue Blocks
            
            # Calculate predicted size
            current_chars = sum(len(e[2]) for e in current_block)
            overhead = (len(current_block) + 1) * (len(TOKEN_LINE_BREAK) + 2)
            predicted_total = current_chars + len(text) + overhead
            
            # Check mergeability (Same file?) - Simplified here, assuming parser groups by file
            # Check limits
            if len(current_block) >= max_batch_size or predicted_total > MAX_CHAR_LIMIT:
                _flush_local()
                
            current_block.append((file_path, key, text))
            
        _flush_local()
        return requests
