"""
Binary patcher for Ruby Marshal (.rxdata / .rvdata / .rvdata2) files.

Instead of deserializing → modifying → reserializing (which is broken due to
rubymarshal.writer's id()-based TYPE_LINK tracking, encoding mutation, and
object index drift), this module:

1. Reads the original bytes AND deserializes with offset tracking
2. Uses the existing ruby_parser walk logic to map paths → string objects
3. Resolves each target object to its byte range via id()
4. Patches the raw byte stream directly (reverse-offset order)

This preserves the exact Marshal structure, TYPE_LINK references, symbol tables,
and encoding metadata — only the string content bytes change.
"""

from __future__ import annotations

import io
import logging
import re
import struct
from typing import Any

import rubymarshal.reader
from rubymarshal.classes import RubyString, Symbol
from rubymarshal.constants import (
    TYPE_IVAR,
    TYPE_STRING,
    TYPE_REGEXP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Marshal long encoding/decoding helpers
# ---------------------------------------------------------------------------

def encode_marshal_long(value: int) -> bytes:
    """Encode an integer as Ruby Marshal long format.
    
    Ruby Marshal long is a variable-width encoding:
      value 0        → b'\\x00'
      value 1..122   → single byte (value + 5)
      value -123..-1 → single byte (value - 5, as signed)
      value 123..255 → b'\\x01' + 1 LE byte
      value 256..65535 → b'\\x02' + 2 LE bytes
      etc.  Negative large values use negative prefix.
    """
    if value == 0:
        return b'\x00'
    if 1 <= value <= 122:
        return struct.pack('b', value + 5)
    if -123 <= value <= -1:
        return struct.pack('b', value - 5)
    # Multi-byte positive
    if value > 0:
        result = bytearray()
        v = value
        n = 0
        while v > 0:
            result.append(v & 0xFF)
            v >>= 8
            n += 1
        return struct.pack('b', n) + bytes(result)
    # Multi-byte negative
    v = value
    n = 0
    result = bytearray()
    # Two's complement: encode (value + 256^N) as unsigned, where N is byte count
    for byte_count in range(1, 5):
        factor = 256 ** byte_count
        unsigned = value + factor
        if unsigned >= 0:
            result = bytearray()
            for _ in range(byte_count):
                result.append(unsigned & 0xFF)
                unsigned >>= 8
            return struct.pack('b', -byte_count) + bytes(result)
    raise ValueError(f"Cannot encode marshal long: {value}")


def decode_marshal_long_from_bytes(data: bytes | bytearray, offset: int) -> tuple[int, int]:
    """Decode a marshal long starting at offset. Returns (value, bytes_consumed)."""
    length = struct.unpack_from('b', data, offset)[0]
    if length == 0:
        return 0, 1
    if 5 < length < 128:
        return length - 5, 1
    if -129 < length < -5:
        return length + 5, 1
    # Multi-byte
    n = abs(length)
    result = 0
    factor = 1
    for i in range(n):
        result += data[offset + 1 + i] * factor
        factor *= 256
    if length < 0:
        result = result - factor
    return result, 1 + n


# ---------------------------------------------------------------------------
# Encoding suffix helpers
# ---------------------------------------------------------------------------

# Pre-built encoding suffixes (ivar_count=1, then encoding attribute)
# E: true  → UTF-8
_ENCODING_SUFFIX_UTF8 = (
    b'\x06'           # ivar count = 1
    b'\x3a\x06\x45'   # TYPE_SYMBOL, blob_len=1, "E"
    b'\x54'            # TYPE_TRUE
)
# E: false → ASCII/binary/latin1
_ENCODING_SUFFIX_ASCII = (
    b'\x06'
    b'\x3a\x06\x45'
    b'\x46'            # TYPE_FALSE
)


def _build_encoding_suffix_explicit(encoding_name: str, symbol_cache: dict[str, int] | None = None) -> bytes:
    """Build ivar suffix for an explicit encoding like Shift_JIS.
    
    Format: ivar_count(1) + :encoding symbol + "encoding_name" string
    Note: This uses fresh symbols (TYPE_SYMBOL), not symlinks, since we can't
    know the symbol table state. For safety we use the simple form.
    """
    enc_bytes = encoding_name.encode('utf-8')
    # ivar_count=1
    result = bytearray()
    result += encode_marshal_long(1)
    # Symbol :encoding (fresh)
    result += b'\x3a'  # TYPE_SYMBOL
    result += encode_marshal_long(len(b'encoding'))
    result += b'encoding'
    # String value "encoding_name" as TYPE_IVAR + TYPE_STRING + E:false
    result += b'\x49\x22'  # TYPE_IVAR + TYPE_STRING
    result += encode_marshal_long(len(enc_bytes))
    result += enc_bytes
    result += _ENCODING_SUFFIX_ASCII  # encoding names are ASCII
    return bytes(result)


# ---------------------------------------------------------------------------
# OffsetTrackingReader
# ---------------------------------------------------------------------------

class OffsetTrackingReader(rubymarshal.reader.Reader):
    """Reader subclass that records byte offsets for every IVAR-wrapped string.
    
    After deserialization, ``string_ranges`` maps ``id(python_object)`` to a
    ``StringByteRange`` describing exactly which bytes to patch.
    """

    def __init__(self, fd, registry=None):
        super().__init__(fd, registry=registry)
        # id(deserialized_obj) → (ivar_start, blob_start, blob_end, ivar_end, encoding_name)
        self.string_ranges: dict[int, StringByteRange] = {}
        self._ivar_context_stack: list[int] = []  # stack of TYPE_IVAR start positions

    def read(self, in_ivar=False):
        pos_before = self.fd.tell()

        token = self.fd.read(1)

        # Track object table registration (mirror parent logic)
        object_index = None
        if token in (
            b'c', b'm', b'f', b'l', b'"', b'/',
            b'[', b'{', b'S', b'o', b'd', b'U', b'u',
        ):
            object_index = len(self.objects)
            self.objects.append(None)

        re_flags = None
        result = None

        if token == b'0':
            pass
        elif token == b'T':
            result = True
        elif token == b'F':
            result = False
        elif token == TYPE_IVAR:
            # Record start of the IVAR wrapper
            ivar_start = pos_before
            self._ivar_context_stack.append(ivar_start)
            result = self.read(in_ivar=True)
            self._ivar_context_stack.pop()
        elif token == TYPE_STRING:
            blob_start = self.fd.tell()
            result = self.read_blob()
            blob_end = self.fd.tell()
            # If we're inside an IVAR, record the blob range
            if self._ivar_context_stack:
                # We'll finalize in the in_ivar block below
                self._pending_blob = (blob_start, blob_end)
        elif token == b':':
            result = self.read_symreal()
        elif token == b'i':
            result = self.read_long()
        elif token == b'[':
            num = self.read_long()
            result = [self.read() for _ in range(num)]
        elif token == b'{':
            num = self.read_long()
            result = {}
            for _ in range(num):
                key = self.ensure_hashable(self.read())
                value = self.read()
                result[key] = value
        elif token == b'f':
            floatn = self.read_blob()
            floatn = floatn.split(b'\0')
            result = float(floatn[0].decode('utf-8'))
        elif token == b'l':
            sign = 1 if self.fd.read(1) == b'+' else -1
            num = self.read_long()
            result = 0
            factor = 1
            for _ in range(num):
                result += self.read_short() * factor
                factor *= 2 ** 16
            result *= sign
        elif token == b'/':
            result = self.read_blob()
            options = ord(self.fd.read(1))
            re_flags = 0
            if options & 1:
                re_flags |= re.IGNORECASE
            if options & 4:
                re_flags |= re.MULTILINE
        elif token == b'U':
            class_symbol = self.read()
            if not isinstance(class_symbol, Symbol):
                raise ValueError("invalid class name: %r" % class_symbol)
            class_name = class_symbol.name
            attr_list = self.read()
            from rubymarshal.classes import UsrMarshal
            python_class = self.registry.get(class_name, UsrMarshal)
            result = python_class(class_name)
            result.marshal_load(attr_list)
        elif token == b';':
            result = self.read_symlink()
        elif token == b'@':
            link_id = self.read_long()
            if link_id > len(self.objects):
                raise ValueError(
                    "invalid link destination: %d should be lower than %d or equal."
                    % (link_id, len(self.objects))
                )
            result = self.objects[link_id]
            if result is None:
                raise ValueError(
                    "invalid link destination: Object id %d is not yet unmarshaled."
                    % link_id
                )
        elif token == b'u':
            class_symbol = self.read()
            private_data = self.read_blob()
            if not isinstance(class_symbol, Symbol):
                raise ValueError("invalid class name: %r" % class_symbol)
            class_name = class_symbol.name
            from rubymarshal.classes import UserDef
            python_class = self.registry.get(class_name, UserDef)
            result = python_class(class_name)
            result._load(private_data)
        elif token == b'm':
            data = self.read_blob()
            from rubymarshal.classes import Module
            result = Module(data.decode(), None)
        elif token == b'o':
            class_symbol = self.read()
            assert isinstance(class_symbol, Symbol)
            class_name = class_symbol.name
            from rubymarshal.classes import RubyObject
            python_class = self.registry.get(class_name, RubyObject)
            attributes = self.read_attributes()
            result = python_class(class_name, attributes)
        elif token == b'e':
            from rubymarshal.classes import Extended
            class_name = self.read_blob()
            result = Extended(class_name, None)
        elif token == b'c':
            data = self.read_blob()
            class_name = data.decode()
            from rubymarshal.classes import RubyObject
            if class_name in self.registry:
                result = self.registry[class_name]
            else:
                result = type(
                    class_name.rpartition(':')[2],
                    (RubyObject,),
                    {'ruby_class_name': class_name},
                )
        else:
            raise ValueError("token %s is not recognized" % token)

        # Handle IVAR attributes (encoding for strings)
        if in_ivar:
            attrs_start = self.fd.tell()
            attributes = self.read_attributes()
            attrs_end = self.fd.tell()

            if token in (TYPE_STRING, TYPE_REGEXP):
                encoding = self._get_encoding(attributes)
                try:
                    result = result.decode(encoding)
                except UnicodeDecodeError:
                    result = result.decode('latin1', errors='replace')

                if attributes and token == TYPE_STRING:
                    result = RubyString(result, attributes)

                # Record the full byte range for this string
                if token == TYPE_STRING and self._ivar_context_stack:
                    ivar_start = self._ivar_context_stack[-1]
                    blob_start, blob_end = getattr(self, '_pending_blob', (None, None))
                    if blob_start is not None:
                        self.string_ranges[id(result)] = StringByteRange(
                            ivar_start=ivar_start,
                            blob_start=blob_start,
                            blob_end=blob_end,
                            attrs_start=attrs_start,
                            attrs_end=attrs_end,
                            encoding=encoding,
                        )
                        self._pending_blob = None
            elif attributes:
                result.set_attributes(attributes)

        if token == TYPE_REGEXP:
            result = re.compile(str(result), re_flags)

        if object_index is not None:
            self.objects[object_index] = result
        return result


class StringByteRange:
    """Byte range information for a single IVAR-wrapped string in a Marshal stream."""
    __slots__ = ('ivar_start', 'blob_start', 'blob_end', 'attrs_start', 'attrs_end', 'encoding')

    def __init__(self, *, ivar_start: int, blob_start: int, blob_end: int,
                 attrs_start: int, attrs_end: int, encoding: str):
        self.ivar_start = ivar_start   # Position of TYPE_IVAR byte
        self.blob_start = blob_start   # Position of marshal_long for string data
        self.blob_end = blob_end       # Position after last byte of string data
        self.attrs_start = attrs_start # Position of ivar attributes (encoding)
        self.attrs_end = attrs_end     # Position after last byte of attributes
        self.encoding = encoding       # Detected encoding ('utf-8', 'latin1', 'shift_jis', etc.)

    @property
    def full_start(self) -> int:
        """Start of the entire IVAR expression (TYPE_IVAR byte)."""
        return self.ivar_start

    @property
    def full_end(self) -> int:
        """End of the entire IVAR expression (after encoding attrs)."""
        return self.attrs_end


# ---------------------------------------------------------------------------
# Load with offset tracking
# ---------------------------------------------------------------------------

def load_with_offsets(raw_bytes: bytes, registry=None) -> tuple[Any, dict[int, StringByteRange]]:
    """Deserialize Ruby Marshal data while recording string byte offsets.
    
    Returns:
        (deserialized_root, string_ranges_by_id)
    """
    fd = io.BytesIO(raw_bytes)
    if fd.read(1) != b'\x04':
        raise ValueError(r"Expected token \x04")
    if fd.read(1) != b'\x08':
        raise ValueError(r"Expected token \x08")
    reader = OffsetTrackingReader(fd, registry=registry)
    root = reader.read()
    return root, reader.string_ranges


# ---------------------------------------------------------------------------
# Path resolver: navigate deserialized tree by path → target object
# ---------------------------------------------------------------------------

def _resolve_path(root: Any, path: str) -> Any | None:
    """Navigate the deserialized object tree following a dot-separated path.
    
    Handles:
    - Integer keys (list indices): "5"
    - Attribute keys: "@name" → obj.attributes["name"] or obj.attributes["@name"]
    - Dict keys: "key_name"
    """
    keys = path.split('.')
    ref = root
    try:
        for key in keys:
            ref = _traverse_one(ref, key)
        return ref
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def _traverse_one(ref: Any, key: str) -> Any:
    """Single-step traversal matching ruby_parser._traverse_key logic."""
    if key.isdigit():
        return ref[int(key)]
    if key.startswith('@'):
        attr_name = key[1:]
        if isinstance(ref, dict):
            if attr_name in ref:
                return ref[attr_name]
            if key in ref:
                return ref[key]
            raise KeyError(key)
        if hasattr(ref, 'attributes'):
            attrs = ref.attributes
            for k in [attr_name, key, attr_name.encode('utf-8'), key.encode('utf-8')]:
                if k in attrs:
                    return attrs[k]
            raise KeyError(key)
    if isinstance(ref, dict):
        return ref[key]
    if isinstance(ref, list):
        return ref[int(key)]
    if hasattr(ref, 'attributes'):
        return ref.attributes[key]
    return getattr(ref, key)


# ---------------------------------------------------------------------------
# Unbundle: expand bundled translation keys into individual paths
# ---------------------------------------------------------------------------

BUNDLED_PATH_MARKER = '_bundled_'


def unbundle_translations(translations: dict[str, str]) -> dict[str, str]:
    """Expand bundled keys like 'list.6_bundled_9' into individual parameter paths.
    
    'prefix.6_bundled_9' with value 'line1⟦_I_⟧line2⟦_I_⟧line3⟦_I_⟧line4'
    becomes:
        'prefix.6.@parameters.0' → 'line1'
        'prefix.7.@parameters.0' → 'line2'
        'prefix.8.@parameters.0' → 'line3'
        'prefix.9.@parameters.0' → 'line4'
    """
    from src.core.constants import REGEX_INTERNAL_MERGE

    result: dict[str, str] = {}
    for path, value in translations.items():
        if BUNDLED_PATH_MARKER not in path:
            result[path] = value
            continue

        # Split path: everything before the last dot is prefix, last part is "N_bundled_M"
        dot_pos = path.rfind('.')
        if dot_pos == -1:
            # No prefix — the whole path is the bundle key
            prefix = ''
            bundle_key = path
        else:
            prefix = path[:dot_pos]
            bundle_key = path[dot_pos + 1:]

        try:
            start_s, end_s = bundle_key.split(BUNDLED_PATH_MARKER)
            start_idx, end_idx = int(start_s), int(end_s)
        except (ValueError, AttributeError):
            result[path] = value
            continue

        # Normalize internal merge separators then split
        normalized = re.sub(
            r'(?:<b[^>]*>)?\s*[【\[\(\{\.\s⟦]*_\s*[iI]\s*_\s*[】\]\)\}\.\s⟧]*\s*(?:</b>)?',
            '【 _I_ 】',
            value,
        )
        lines = re.split(REGEX_INTERNAL_MERGE, normalized, flags=re.IGNORECASE)

        # Fallback: if split didn't produce enough lines, try newline split
        expected = end_idx - start_idx + 1
        if len(lines) < expected and '\n' in value:
            lines = value.split('\n')

        # Pad if needed
        while len(lines) < expected:
            lines.append('')

        for i in range(expected):
            line = lines[i] if i < len(lines) else ''
            individual_path = f"{prefix}.{start_idx + i}.@parameters.0" if prefix else f"{start_idx + i}.@parameters.0"
            if line.strip():  # Skip empty — preserve original
                result[individual_path] = line

    return result


# ---------------------------------------------------------------------------
# Patch builder: create byte-level patches
# ---------------------------------------------------------------------------

class PatchEntry:
    """A single byte-range replacement in the Marshal stream."""
    __slots__ = ('start', 'end', 'new_bytes')

    def __init__(self, start: int, end: int, new_bytes: bytes):
        self.start = start
        self.end = end
        self.new_bytes = new_bytes


def _detect_target_encoding(original_encoding: str, new_text: str) -> str:
    """Determine what encoding to use for the patched string.
    
    Strategy: Try to keep original encoding. If the new text can't be encoded
    in the original encoding, fall back to UTF-8.
    """
    try:
        new_text.encode(original_encoding)
        return original_encoding
    except (UnicodeEncodeError, LookupError):
        return 'utf-8'


def _build_encoding_suffix(encoding: str) -> bytes:
    """Build the IVAR encoding suffix bytes for a given encoding."""
    enc_lower = encoding.lower().replace('-', '').replace('_', '')
    if enc_lower in ('utf8',):
        return _ENCODING_SUFFIX_UTF8
    if enc_lower in ('latin1', 'ascii', 'iso88591', 'usascii'):
        return _ENCODING_SUFFIX_ASCII
    # Explicit encoding name
    return _build_encoding_suffix_explicit(encoding)


def build_patch(
    byte_range: StringByteRange,
    new_text: str,
    raw_data: bytes | bytearray,
) -> PatchEntry | None:
    """Build a patch entry for a single string replacement.
    
    Replaces the blob (marshal_long + raw bytes) and optionally the encoding
    suffix if the encoding needs to change.
    """
    if not new_text.strip():
        return None  # Skip empty translations — preserve original

    target_encoding = _detect_target_encoding(byte_range.encoding, new_text)
    try:
        new_bytes = new_text.encode(target_encoding)
    except (UnicodeEncodeError, LookupError):
        new_bytes = new_text.encode('utf-8')
        target_encoding = 'utf-8'

    new_marshal_long = encode_marshal_long(len(new_bytes))

    encoding_changed = target_encoding.lower().replace('-', '').replace('_', '') != \
                       byte_range.encoding.lower().replace('-', '').replace('_', '')

    if encoding_changed:
        # Replace blob + encoding suffix (from blob_start to attrs_end)
        new_suffix = _build_encoding_suffix(target_encoding)
        patch_bytes = new_marshal_long + new_bytes + new_suffix
        return PatchEntry(
            start=byte_range.blob_start,
            end=byte_range.attrs_end,
            new_bytes=patch_bytes,
        )
    else:
        # Replace only the blob (marshal_long + raw bytes)
        patch_bytes = new_marshal_long + new_bytes
        return PatchEntry(
            start=byte_range.blob_start,
            end=byte_range.blob_end,
            new_bytes=patch_bytes,
        )


# ---------------------------------------------------------------------------
# Main patcher: apply_binary_patch
# ---------------------------------------------------------------------------

def apply_binary_patch(
    raw_bytes: bytes,
    root: Any,
    string_ranges: dict[int, StringByteRange],
    translations: dict[str, str],
) -> bytes | None:
    """Apply translations to a Ruby Marshal byte stream via binary patching.
    
    Args:
        raw_bytes: Original file content (including \\x04\\x08 header).
        root: Deserialized object tree from OffsetTrackingReader.
        string_ranges: Mapping of id(obj) → StringByteRange from the reader.
        translations: Pre-unbundled path → translated text mapping.
    
    Returns:
        Patched bytes, or None if no patches were applied.
    """
    patches: list[PatchEntry] = []
    failed_paths: list[str] = []
    matched_count = 0

    for path, new_text in translations.items():
        if not new_text or not new_text.strip():
            continue

        # Resolve path to the target object in the deserialized tree
        target_obj = _resolve_path(root, path)
        if target_obj is None:
            failed_paths.append(path)
            continue

        # Look up byte range by object identity
        obj_id = id(target_obj)
        byte_range = string_ranges.get(obj_id)
        if byte_range is None:
            # Object might be a plain str (decoded from bytes by reader)
            # Try to find it via value matching as fallback
            failed_paths.append(path)
            continue

        patch = build_patch(byte_range, new_text, raw_bytes)
        if patch is not None:
            # Deduplicate: skip if the same byte range was already registered.
            # This happens when a single Marshal string is reachable via
            # multiple paths (TYPE_LINK object sharing). The first translation
            # encountered wins; subsequent duplicates are silently dropped.
            already_seen = any(p.start == patch.start and p.end == patch.end for p in patches)
            if not already_seen:
                patches.append(patch)
                matched_count += 1
            else:
                logger.debug(
                    "Binary patcher: duplicate range [%d:%d] for path %s — skipped",
                    patch.start, patch.end, path,
                )

    if not patches:
        if failed_paths:
            logger.warning("Binary patcher: %d paths could not be resolved", len(failed_paths))
        return None

    # Sort patches by start offset DESCENDING — apply from end to start
    # so earlier patches don't shift later offsets
    patches.sort(key=lambda p: p.start, reverse=True)

    # Check for overlapping patches
    for i in range(len(patches) - 1):
        if patches[i + 1].end > patches[i].start:
            logger.error(
                "Binary patcher: overlapping patches at [%d:%d] and [%d:%d]",
                patches[i + 1].start, patches[i + 1].end,
                patches[i].start, patches[i].end,
            )
            return None

    # Apply patches to a mutable copy
    data = bytearray(raw_bytes)
    for patch in patches:
        data[patch.start:patch.end] = patch.new_bytes

    if failed_paths:
        logger.warning(
            "Binary patcher: applied %d patches, %d paths unresolved",
            matched_count, len(failed_paths),
        )
    else:
        logger.info("Binary patcher: applied %d patches successfully", matched_count)

    return bytes(data)


# ---------------------------------------------------------------------------
# High-level API: patch_marshal_file
# ---------------------------------------------------------------------------

def patch_marshal_file(
    raw_bytes: bytes,
    translations: dict[str, str],
) -> bytes | None:
    """Convenience function: load, unbundle, resolve, and patch in one call.
    
    Args:
        raw_bytes: Original .rvdata2/.rxdata/.rvdata file content.
        translations: Translation dict (may contain bundled paths).
    
    Returns:
        Patched bytes ready for writing, or None on failure.
    """
    # Phase 1: Deserialize with offset tracking
    try:
        root, string_ranges = load_with_offsets(raw_bytes)
    except Exception as e:
        logger.error("Binary patcher: failed to deserialize: %s", e)
        return None

    # Phase 2: Unbundle translations
    unbundled = unbundle_translations(translations)

    # Phase 3: Apply patches
    result = apply_binary_patch(raw_bytes, root, string_ranges, unbundled)

    return result
