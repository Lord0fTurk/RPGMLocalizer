"""Low-level binary parser and serializer for WOLF RPG Editor (ウディタ) project files.

Provides byte-level parsing and reconstruction for:
  - Map files: Data/MapData/**/*.mps
  - Common events: Data/BasicData/CommonEvent.dat
  - Database schema & records: Data/BasicData/*.project + *.dat

Supports:
  - Classic CP932 (Shift-JIS) and modern UTF-8 string encoding.
  - Automatic UTF-8 format upgrade when translated text exceeds CP932 charset.
  - LZ4 block compression/decompression across modern editor versions (v2.2+, v3.5-v3.7+).
"""
from __future__ import annotations

import struct
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

import lz4.block

CP932 = "cp932"
UTF8 = "utf-8"

CP932_CHAR_MAP: dict[str, str] = {
    # Turkish special characters
    "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
    # German & ligatures
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    # Typographic punctuation & dashes
    "—": "--", "–": "-", "―": "-", "…": "...",
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "«": '"', "»": '"', "•": "*", "·": "*",
    "¡": "", "¿": "",
    "\u00a0": " ", "\u200b": "", "\u202f": " ",
}


def normalize_for_cp932(text: str) -> str:
    """Normalize text so it can safely be encoded into CP932 without losing Japanese or ASCII.

    - Fast path: returns original string if already CP932-encodable (e.g. Japanese or ASCII).
    - Replaces Turkish, European, and typographic characters with safe ASCII equivalents.
    - Strips leftover combining diacritics via NFKD decomposition.
    """
    try:
        text.encode(CP932)
        return text
    except UnicodeEncodeError:
        pass

    out: list[str] = []
    for ch in text:
        if ch in CP932_CHAR_MAP:
            out.append(CP932_CHAR_MAP[ch])
        else:
            decomposed = unicodedata.normalize("NFKD", ch)
            base = "".join(c for c in decomposed if not unicodedata.combining(c))
            out.append(base if base else ch)
    return "".join(out)


CID_MESSAGE = 101
CID_CHOICES = 102
CID_ERROR_MESSAGE = 106
CID_STRING_OP = 122
CID_PICTURE_TEXT = 150
CID_BATTLE_MESSAGE = 210
CID_DB_ACCESS = 250

_ROUTE_TERMINATOR = bytes([0x01, 0x00])

_MAP_MAGIC = bytes(10) + b"WOLFM" + bytes(5)
_MAP_UTF8_INDEX = 16
_MAP_LZ4_VERSION_THRESHOLD = 0x65
_MAP_V35_VERSION_THRESHOLD = 0x67
_MAP_DEFAULT_VERSION = 0x64
_MAP_DEFAULT_UNKNOWN2 = 0x65
_MAP_DEFAULT_LAYER_COUNT = 3

_EVENT_MAGIC1 = bytes([0x39, 0x30, 0x00, 0x00])
_EVENT_INDICATOR = 0x6F
_EVENT_FINISH_INDICATOR = 0x66
_PAGE_INDICATOR = 0x79
_PAGE_FINISH_INDICATOR = 0x70
_PAGE_TERMINATOR = 0x7A
_PAGE_DEFAULT_FEATURES = 3
_CONDITIONS_SIZE = 1 + 4 + 4 * 4 + 4 * 4
_MOVEMENT_SIZE = 4

_CE_MAGIC_CP932 = bytes([0x57, 0x00, 0x00, 0x4F, 0x4C, 0x00, 0x46, 0x43, 0x00])
_CE_UTF8_INDEX = 5
_CE_DEFAULT_VERSION = 0x8F
_CE_MIN_TERMINATOR = 0x89
_CE_V35_VERSIONS = frozenset({0x93, 0xCC})

_DAT_MAGIC_CP932 = bytes([0x57, 0x00, 0x00, 0x4F, 0x4C, 0x00, 0x46, 0x4D, 0x00])
_DAT_UTF8_INDEX = 5
_DAT_DEFAULT_VERSION = 0xC1
_DAT_V35_VERSION = 0xC4
_DAT_TYPE_SEPARATOR = bytes([0xFE, 0xFF, 0xFF, 0xFF])
_DAT_STRING_INDICATOR = 0x0001D4C0

_FIELD_STRING_START = 0x07D0
_FIELD_INT_START = 0x03E8


class WolfFormatError(Exception):
    """Raised when a WOLF file is malformed, encrypted, or unsupported."""


class _StringEncodeError(Exception):
    """Internal signal when text cannot be encoded in the writer's current encoding."""


class ByteReader:
    """Sequential binary reader with encoding and LZ4 block decompression support."""

    def __init__(self, data: bytes, encoding: str = CP932) -> None:
        self._data = data
        self._pos = 0
        self.encoding = encoding

    def eof(self) -> bool:
        return self._pos >= len(self._data)

    def tell(self) -> int:
        return self._pos

    def seek(self, pos: int) -> None:
        self._pos = pos

    def read(self, size: int) -> bytes:
        end = self._pos + size
        if size < 0 or end > len(self._data):
            raise WolfFormatError(
                f"Unexpected end of data at offset {self._pos} (need {size} bytes, "
                f"have {len(self._data) - self._pos})"
            )
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_int(self) -> int:
        (value,) = struct.unpack_from("<i", self.read(4))
        return value

    def read_string(self) -> str:
        size = self.read_int()
        if size <= 0:
            raise WolfFormatError(f"String length must be positive, got {size} at offset {self._pos}")
        data = self.read(size - 1)
        terminator = self.read_byte()
        if terminator != 0:
            raise WolfFormatError(f"String not null-terminated at offset {self._pos}")
        try:
            return data.decode(self.encoding)
        except UnicodeDecodeError:
            # Fallback for modded / mixed-encoding games with stray or corrupted bytes
            alt_encoding = UTF8 if self.encoding == CP932 else CP932
            try:
                return data.decode(alt_encoding)
            except UnicodeDecodeError:
                return data.decode(self.encoding, errors="ignore")

    def verify(self, expected: bytes) -> None:
        got = self.read(len(expected))
        if got != expected:
            raise WolfFormatError(
                f"Magic mismatch at offset {self._pos - len(expected)}: expected {expected!r}, got {got!r}"
            )

    def verify_magic_utf8_aware(self, magic_cp932: bytes, utf8_index: int) -> bool:
        """Verify header magic bytes and dynamically detect whether file is UTF-8."""
        got = self.read(len(magic_cp932))
        if got == magic_cp932:
            self.encoding = CP932
            return False
        utf8_variant = bytearray(magic_cp932)
        utf8_variant[utf8_index] = 0x55
        if bytes(utf8_variant) == got:
            self.encoding = UTF8
            return True
        raise WolfFormatError(
            f"Unrecognized header (expected {magic_cp932!r} or UTF-8 variant, got {got!r}). "
            "File may be encrypted or WolfPro protected."
        )

    def unpack_lz4(self, start: int) -> None:
        """Decompress LZ4 block payload from `start` and replace underlying buffer."""
        self._pos = start
        dec_size = self.read_int()
        enc_size = self.read_int()
        compressed = self.read(enc_size)
        try:
            decompressed = lz4.block.decompress(compressed, uncompressed_size=dec_size)
        except Exception as exc:
            raise WolfFormatError(f"LZ4 decompression failed at offset {start}: {exc}") from exc
        self._data = self._data[:start] + decompressed
        self._pos = start


class ByteWriter:
    """Sequential binary writer with string encoding validation and CP932 transliteration."""

    def __init__(self, encoding: str = CP932, allow_transliterate: bool = False) -> None:
        self._buf = bytearray()
        self.encoding = encoding
        self.allow_transliterate = allow_transliterate

    def getvalue(self) -> bytes:
        return bytes(self._buf)

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    def write_byte(self, value: int) -> None:
        self._buf.append(value & 0xFF)

    def write_int(self, value: int) -> None:
        self._buf.extend(struct.pack("<i", value))

    def write_string(self, value: str) -> None:
        try:
            encoded = value.encode(self.encoding)
        except UnicodeEncodeError as exc:
            if self.allow_transliterate and self.encoding == CP932:
                normalized = normalize_for_cp932(value)
                encoded = normalized.encode(CP932, errors="replace")
            else:
                raise _StringEncodeError(f"Cannot encode as {self.encoding}: {value!r}: {exc}") from exc
        self.write_int(len(encoded) + 1)
        self.write(encoded)
        self.write_byte(0)


def lz4_pack(payload: bytes) -> bytes:
    """Pack payload as [uncompressed_len: i32][compressed_len: i32][lz4_data]."""
    compressed = lz4.block.compress(payload, mode="default", store_size=False)
    return struct.pack("<ii", len(payload), len(compressed)) + compressed


def _build_with_utf8_upgrade(is_utf8: bool, build_fn: Callable[[bool], bytes]) -> tuple[bytes, bool]:
    """Build binary data with automatic UTF-8 upgrade if non-CP932 characters occur."""
    try:
        return build_fn(is_utf8), is_utf8
    except _StringEncodeError:
        if is_utf8:
            raise WolfFormatError("Failed to encode text even under UTF-8.")
        return build_fn(True), True


def _check_not_encrypted(data: bytes, path_for_error: object, expected_first_byte: int | None = None) -> None:
    if not data:
        raise WolfFormatError(f"{path_for_error}: File is empty")
    if expected_first_byte is not None and data[0] != expected_first_byte:
        raise WolfFormatError(
            f"{path_for_error}: First byte is {data[0]:#x} (expected {expected_first_byte:#x}). "
            "This file appears to be encrypted (WolfPro AES or classic XOR)."
        )


@dataclass
class RouteCommand:
    command_id: int
    args: list[int]

    @classmethod
    def read(cls, r: ByteReader) -> RouteCommand:
        command_id = r.read_byte()
        count = r.read_byte()
        args = [r.read_int() for _ in range(count)]
        r.verify(_ROUTE_TERMINATOR)
        return cls(command_id, args)

    def write(self, w: ByteWriter) -> None:
        w.write_byte(self.command_id)
        w.write_byte(len(self.args))
        for arg in self.args:
            w.write_int(arg)
        w.write(_ROUTE_TERMINATOR)


@dataclass
class MoveExtra:
    unknown: list[int]
    flags: int
    route: list[RouteCommand]

    @classmethod
    def read(cls, r: ByteReader) -> MoveExtra:
        unknown = [r.read_byte() for _ in range(5)]
        flags = r.read_byte()
        route = [RouteCommand.read(r) for _ in range(r.read_int())]
        return cls(unknown, flags, route)

    def write(self, w: ByteWriter) -> None:
        for b in self.unknown:
            w.write_byte(b)
        w.write_byte(self.flags)
        w.write_int(len(self.route))
        for cmd in self.route:
            cmd.write(w)


@dataclass
class Command:
    cid: int
    args: list[int]
    indent: int
    string_args: list[str]
    move_extra: MoveExtra | None = None
    v35_unknown: bytes = b""

    @classmethod
    def read(cls, r: ByteReader, v35: bool = False) -> Command:
        size = r.read_byte()
        if size < 1:
            raise WolfFormatError(f"Command size byte must be >= 1, got {size}")
        cid = r.read_int()
        args = [r.read_int() for _ in range(size - 1)]
        indent = r.read_byte()
        string_args = [r.read_string() for _ in range(r.read_byte())]
        terminator = r.read_byte()
        move_extra = None
        if terminator == 1:
            move_extra = MoveExtra.read(r)
        elif terminator != 0:
            raise WolfFormatError(f"Unexpected command terminator {terminator:#x}")
        v35_unknown = b""
        if v35:
            v35_size = r.read_byte()
            if v35_size:
                v35_unknown = r.read(v35_size)
        return cls(cid, args, indent, string_args, move_extra, v35_unknown)

    def write(self, w: ByteWriter, v35: bool = False) -> None:
        w.write_byte(len(self.args) + 1)
        w.write_int(self.cid)
        for arg in self.args:
            w.write_int(arg)
        w.write_byte(self.indent)
        w.write_byte(len(self.string_args))
        for text in self.string_args:
            w.write_string(text)
        if self.move_extra is not None:
            w.write_byte(1)
            self.move_extra.write(w)
        else:
            w.write_byte(0)
        if v35:
            w.write_byte(len(self.v35_unknown))
            if self.v35_unknown:
                w.write(self.v35_unknown)


def command_text_slots(cmd: Command) -> list[int]:
    """Return indices into cmd.string_args that contain player-facing dialogue, choices, or UI text."""
    if cmd.cid == CID_MESSAGE:
        return [0] if cmd.string_args else []
    if cmd.cid == CID_CHOICES:
        return list(range(len(cmd.string_args)))
    if cmd.cid in (CID_ERROR_MESSAGE, CID_STRING_OP, CID_PICTURE_TEXT):
        return [0] if cmd.string_args else []
    if cmd.cid == CID_BATTLE_MESSAGE:
        return [i for i in range(1, len(cmd.string_args)) if cmd.string_args[i]]
    return []


def neutralize_data_name_checks(commands: list[Command]) -> int:
    """Neutralize runtime record-name validation in CID 250 (DB Access) commands.

    In WOLF RPG, bit 17 (0x20000) of args[3] forces the engine to validate that
    string_args[2] matches the record name in the database. When database record
    names are translated, this check fails and crashes the engine at runtime.
    If args[1] contains a valid non-variable record index (0 <= args[1] < 1_000_000),
    we clear bit 17 so the engine directly accesses the record by ID without crashing.
    """
    modified = 0
    for cmd in commands:
        if cmd.cid == CID_DB_ACCESS and len(cmd.args) > 3:
            if (cmd.args[3] & 0x20000) and (0 <= cmd.args[1] < 1_000_000):
                cmd.args[3] &= ~0x20000
                modified += 1
    return modified


@dataclass
class Page:
    unknown1: int
    graphic_name: str
    graphic_direction: int
    graphic_frame: int
    graphic_opacity: int
    graphic_render_mode: int
    conditions: bytes
    movement: bytes
    flags: int
    route_flags: int
    route: list[RouteCommand]
    commands: list[Command]
    shadow_graphic_num: int
    collision_width: int
    collision_height: int
    features: int = _PAGE_DEFAULT_FEATURES
    page_transfer: int = 0

    @classmethod
    def read(cls, r: ByteReader, v35: bool = False) -> Page:
        unknown1 = r.read_int()
        graphic_name = r.read_string()
        graphic_direction = r.read_byte()
        graphic_frame = r.read_byte()
        graphic_opacity = r.read_byte()
        graphic_render_mode = r.read_byte()
        conditions = r.read(_CONDITIONS_SIZE)
        movement = r.read(_MOVEMENT_SIZE)
        flags = r.read_byte()
        route_flags = r.read_byte()
        route = [RouteCommand.read(r) for _ in range(r.read_int())]
        commands = [Command.read(r, v35) for _ in range(r.read_int())]
        features = r.read_int()
        shadow_graphic_num = r.read_byte()
        collision_width = r.read_byte()
        collision_height = r.read_byte()
        page_transfer = r.read_byte() if features > 3 else 0
        terminator = r.read_byte()
        if terminator != _PAGE_TERMINATOR:
            raise WolfFormatError(f"Page terminator not {_PAGE_TERMINATOR:#x} (got {terminator:#x})")
        return cls(
            unknown1,
            graphic_name,
            graphic_direction,
            graphic_frame,
            graphic_opacity,
            graphic_render_mode,
            conditions,
            movement,
            flags,
            route_flags,
            route,
            commands,
            shadow_graphic_num,
            collision_width,
            collision_height,
            features,
            page_transfer,
        )

    def write(self, w: ByteWriter, v35: bool = False) -> None:
        w.write_int(self.unknown1)
        w.write_string(self.graphic_name)
        w.write_byte(self.graphic_direction)
        w.write_byte(self.graphic_frame)
        w.write_byte(self.graphic_opacity)
        w.write_byte(self.graphic_render_mode)
        w.write(self.conditions)
        w.write(self.movement)
        w.write_byte(self.flags)
        w.write_byte(self.route_flags)
        w.write_int(len(self.route))
        for rc in self.route:
            rc.write(w)
        w.write_int(len(self.commands))
        for c in self.commands:
            c.write(w, v35)
        w.write_int(self.features)
        w.write_byte(self.shadow_graphic_num)
        w.write_byte(self.collision_width)
        w.write_byte(self.collision_height)
        if self.features > 3:
            w.write_byte(self.page_transfer)
        w.write_byte(_PAGE_TERMINATOR)


@dataclass
class Event:
    event_id: int
    name: str
    x: int
    y: int
    pages: list[Page]
    unknown1: int = 0

    @classmethod
    def read(cls, r: ByteReader, v35: bool = False) -> Event:
        r.verify(_EVENT_MAGIC1)
        event_id = r.read_int()
        name = r.read_string()
        x = r.read_int()
        y = r.read_int()
        page_cnt = r.read_int()
        unknown1 = r.read_int()
        pages = []
        for _ in range(page_cnt):
            r.verify(bytes([_PAGE_INDICATOR]))
            pages.append(Page.read(r, v35))
        r.verify(bytes([_PAGE_FINISH_INDICATOR]))
        return cls(event_id, name, x, y, pages, unknown1)

    def write(self, w: ByteWriter, v35: bool = False) -> None:
        w.write(_EVENT_MAGIC1)
        w.write_int(self.event_id)
        w.write_string(self.name)
        w.write_int(self.x)
        w.write_int(self.y)
        w.write_int(len(self.pages))
        w.write_int(self.unknown1)
        for p in self.pages:
            w.write_byte(_PAGE_INDICATOR)
            p.write(w, v35)
        w.write_byte(_PAGE_FINISH_INDICATOR)


@dataclass
class WolfMap:
    header_stamp: str
    tileset_id: int
    width: int
    height: int
    events: list[Event]
    tiles: bytes = b""
    version: int = _MAP_DEFAULT_VERSION
    unknown2: int = _MAP_DEFAULT_UNKNOWN2
    unknown4: int = 0
    layer_cnt: int = _MAP_DEFAULT_LAYER_COUNT
    is_utf8: bool = False
    has_tiles: bool = True

    @property
    def v35(self) -> bool:
        return self.version >= _MAP_V35_VERSION_THRESHOLD

    @classmethod
    def from_bytes(cls, data: bytes, path_for_error: object = "memory") -> WolfMap:
        _check_not_encrypted(data, path_for_error)
        r = ByteReader(data)
        is_utf8 = r.verify_magic_utf8_aware(_MAP_MAGIC, _MAP_UTF8_INDEX)
        version = r.read_int()
        unknown2 = r.read_byte()
        if version >= _MAP_LZ4_VERSION_THRESHOLD:
            r.unpack_lz4(r.tell())
        header_stamp = r.read_string()
        tileset_id = r.read_int()
        width = r.read_int()
        height = r.read_int()
        event_cnt = r.read_int()
        unknown4 = 0
        layer_cnt = _MAP_DEFAULT_LAYER_COUNT
        v35 = version >= _MAP_V35_VERSION_THRESHOLD
        if v35:
            unknown4 = r.read_int()
            layer_cnt = r.read_int()
        tile_cnt = width * height * layer_cnt
        tiles = b""
        has_tiles = True
        if is_utf8:
            first_int = r.read_int()
            if first_int == -1:
                has_tiles = False
            else:
                tiles = struct.pack("<i", first_int) + r.read(tile_cnt * 4 - 4)
        else:
            tiles = r.read(tile_cnt * 4)
        events = []
        for _ in range(event_cnt):
            r.verify(bytes([_EVENT_INDICATOR]))
            events.append(Event.read(r, v35))
        r.verify(bytes([_EVENT_FINISH_INDICATOR]))
        if not r.eof():
            raise WolfFormatError(f"{path_for_error}: Unexpected trailing data in map file")
        return cls(
            header_stamp,
            tileset_id,
            width,
            height,
            events,
            tiles,
            version,
            unknown2,
            unknown4,
            layer_cnt,
            is_utf8,
            has_tiles,
        )

    @classmethod
    def read(cls, path: Path | str) -> WolfMap:
        p = Path(path)
        data = p.read_bytes()
        return cls.from_bytes(data, path_for_error=p)

    def write(self, path: Path | str) -> None:
        p = Path(path)
        p.write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        for e in self.events:
            for p in e.pages:
                neutralize_data_name_checks(p.commands)

        def _build(is_utf8_flag: bool, allow_transliterate: bool = False) -> bytes:
            encoding = UTF8 if is_utf8_flag else CP932
            header = ByteWriter()
            magic = bytearray(_MAP_MAGIC)
            if is_utf8_flag:
                magic[_MAP_UTF8_INDEX] = 0x55
            header.write(bytes(magic))
            header.write_int(self.version)
            header.write_byte(self.unknown2)

            body = ByteWriter(encoding=encoding, allow_transliterate=allow_transliterate)
            body.write_string(self.header_stamp)
            body.write_int(self.tileset_id)
            body.write_int(self.width)
            body.write_int(self.height)
            body.write_int(len(self.events))
            if self.v35:
                body.write_int(self.unknown4)
                body.write_int(self.layer_cnt)
            if is_utf8_flag and not self.has_tiles:
                body.write_int(-1)
            else:
                body.write(self.tiles)
            for e in self.events:
                body.write_byte(_EVENT_INDICATOR)
                e.write(body, self.v35)
            body.write_byte(_EVENT_FINISH_INDICATOR)

            if self.version >= _MAP_LZ4_VERSION_THRESHOLD:
                header.write(lz4_pack(body.getvalue()))
            else:
                header.write(body.getvalue())
            return header.getvalue()

        # WOLF 2.x engines (version < v35) do NOT support UTF-8 containers.
        # Preserve native CP932 format and transliterate unencodable characters safely.
        if not self.v35:
            self.is_utf8 = False
            return _build(is_utf8_flag=False, allow_transliterate=True)

        data, upgraded = _build_with_utf8_upgrade(self.is_utf8, lambda flag: _build(flag, allow_transliterate=False))
        if upgraded:
            self.is_utf8 = True
        return data


@dataclass
class CommonEvent:
    event_id: int
    unknown1: int
    unknown2: bytes
    name: str
    commands: list[Command]
    unknown11: str
    description: str
    unknown3: list[str]
    unknown4: list[int]
    unknown5: list[list[str]]
    unknown6: list[list[int]]
    unknown7: bytes
    unknown8: list[str]
    unknown9: str
    unknown10: str | None = None
    unknown12: int | None = None

    @classmethod
    def read(cls, r: ByteReader, v35: bool = False) -> CommonEvent:
        indicator = r.read_byte()
        if indicator != 0x8E:
            raise WolfFormatError(f"CommonEvent header indicator not 0x8E (got {indicator:#x})")
        event_id = r.read_int()
        unknown1 = r.read_int()
        unknown2 = r.read(7)
        name = r.read_string()
        commands = [Command.read(r, v35) for _ in range(r.read_int())]
        unknown11 = r.read_string()
        description = r.read_string()
        indicator = r.read_byte()
        if indicator != 0x8F:
            raise WolfFormatError(f"CommonEvent data indicator not 0x8F (got {indicator:#x})")
        unknown3 = [r.read_string() for _ in range(r.read_int())]
        unknown4 = [r.read_byte() for _ in range(r.read_int())]
        unknown5 = [[r.read_string() for _ in range(r.read_int())] for _ in range(r.read_int())]
        unknown6 = [[r.read_int() for _ in range(r.read_int())] for _ in range(r.read_int())]
        unknown7 = r.read(0x1D)
        unknown8 = [r.read_string() for _ in range(100)]
        indicator = r.read_byte()
        if indicator != 0x91:
            raise WolfFormatError(f"CommonEvent indicator not 0x91 (got {indicator:#x})")
        unknown9 = r.read_string()
        unknown10 = None
        unknown12 = None
        indicator = r.read_byte()
        if indicator == 0x92:
            unknown10 = r.read_string()
            unknown12 = r.read_int()
            indicator = r.read_byte()
            if indicator != 0x92:
                raise WolfFormatError(f"CommonEvent trailing indicator not 0x92 (got {indicator:#x})")
        elif indicator != 0x91:
            raise WolfFormatError(f"CommonEvent trailing indicator not 0x91/0x92 (got {indicator:#x})")
        return cls(
            event_id,
            unknown1,
            unknown2,
            name,
            commands,
            unknown11,
            description,
            unknown3,
            unknown4,
            unknown5,
            unknown6,
            unknown7,
            unknown8,
            unknown9,
            unknown10,
            unknown12,
        )

    def write(self, w: ByteWriter, v35: bool = False) -> None:
        w.write_byte(0x8E)
        w.write_int(self.event_id)
        w.write_int(self.unknown1)
        w.write(self.unknown2)
        w.write_string(self.name)
        w.write_int(len(self.commands))
        for c in self.commands:
            c.write(w, v35)
        w.write_string(self.unknown11)
        w.write_string(self.description)
        w.write_byte(0x8F)
        w.write_int(len(self.unknown3))
        for s in self.unknown3:
            w.write_string(s)
        w.write_int(len(self.unknown4))
        for b in self.unknown4:
            w.write_byte(b)
        w.write_int(len(self.unknown5))
        for group in self.unknown5:
            w.write_int(len(group))
            for s in group:
                w.write_string(s)
        w.write_int(len(self.unknown6))
        for group in self.unknown6:
            w.write_int(len(group))
            for v in group:
                w.write_int(v)
        w.write(self.unknown7)
        for s in self.unknown8:
            w.write_string(s)
        w.write_byte(0x91)
        w.write_string(self.unknown9)
        if self.unknown10 is not None:
            w.write_byte(0x92)
            w.write_string(self.unknown10)
            w.write_int(self.unknown12 or 0)
            w.write_byte(0x92)
        else:
            w.write_byte(0x91)


@dataclass
class WolfCommonEvents:
    events: list[CommonEvent]
    version: int = _CE_DEFAULT_VERSION
    terminator: int = _CE_DEFAULT_VERSION
    is_utf8: bool = False

    @property
    def v35(self) -> bool:
        return self.version in _CE_V35_VERSIONS

    @classmethod
    def from_bytes(cls, data: bytes, path_for_error: object = "memory") -> WolfCommonEvents:
        _check_not_encrypted(data, path_for_error)
        r = ByteReader(data)
        r.read_byte()  # First byte 0x00 indicator
        is_utf8 = r.verify_magic_utf8_aware(_CE_MAGIC_CP932, _CE_UTF8_INDEX)
        version = r.read_byte()
        v35 = version in _CE_V35_VERSIONS
        if v35:
            r.unpack_lz4(r.tell())
        events = [CommonEvent.read(r, v35) for _ in range(r.read_int())]
        terminator = r.read_byte()
        if terminator < _CE_MIN_TERMINATOR:
            raise WolfFormatError(f"{path_for_error}: Terminator {terminator:#x} smaller than {_CE_MIN_TERMINATOR:#x}")
        if not r.eof():
            raise WolfFormatError(f"{path_for_error}: Unexpected trailing data")
        return cls(events, version, terminator, is_utf8)

    @classmethod
    def read(cls, path: Path | str) -> WolfCommonEvents:
        p = Path(path)
        data = p.read_bytes()
        return cls.from_bytes(data, path_for_error=p)

    def write(self, path: Path | str) -> None:
        p = Path(path)
        p.write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        for e in self.events:
            neutralize_data_name_checks(e.commands)

        def _build(is_utf8_flag: bool, allow_transliterate: bool = False) -> bytes:
            encoding = UTF8 if is_utf8_flag else CP932
            header = ByteWriter()
            header.write_byte(0)
            magic = bytearray(_CE_MAGIC_CP932)
            if is_utf8_flag:
                magic[_CE_UTF8_INDEX] = 0x55
            header.write(bytes(magic))
            header.write_byte(self.version)

            body = ByteWriter(encoding=encoding, allow_transliterate=allow_transliterate)
            body.write_int(len(self.events))
            for e in self.events:
                e.write(body, self.v35)
            body.write_byte(self.terminator)

            if self.v35:
                header.write(lz4_pack(body.getvalue()))
            else:
                header.write(body.getvalue())
            return header.getvalue()

        # WOLF 2.x engines do NOT support UTF-8 containers.
        if not self.v35:
            self.is_utf8 = False
            return _build(is_utf8_flag=False, allow_transliterate=True)

        data, upgraded = _build_with_utf8_upgrade(self.is_utf8, lambda flag: _build(flag, allow_transliterate=False))
        if upgraded:
            self.is_utf8 = True
        return data


@dataclass
class Field:
    name: str
    type: int = 0
    unknown1: str = ""
    string_args: list[str] = field(default_factory=list)
    args: list[int] = field(default_factory=list)
    default_value: int = 0
    index_info: int = 0

    def is_string(self) -> bool:
        return self.index_info >= _FIELD_STRING_START

    def value_index(self) -> int:
        return self.index_info - (_FIELD_STRING_START if self.is_string() else _FIELD_INT_START)


@dataclass
class DataRecord:
    name: str
    int_values: list[int] = field(default_factory=list)
    string_values: list[str] = field(default_factory=list)


@dataclass
class DbType:
    name: str
    fields: list[Field]
    data: list[DataRecord]
    description: str
    field_type_list_size: int
    unknown1: int = 0
    unknown2: str = ""

    @classmethod
    def read_project(cls, r: ByteReader) -> DbType:
        name = r.read_string()
        fields = [Field(name=r.read_string()) for _ in range(r.read_int())]
        data = [DataRecord(name=r.read_string()) for _ in range(r.read_int())]
        description = r.read_string()

        field_type_list_size = r.read_int()
        for f in fields[:field_type_list_size]:
            f.type = r.read_byte()
        if field_type_list_size > len(fields):
            r.read(field_type_list_size - len(fields))

        memo_cnt = r.read_int()
        for f in fields[:memo_cnt]:
            f.unknown1 = r.read_string()
        if memo_cnt > len(fields):
            for _ in range(memo_cnt - len(fields)):
                r.read_string()

        sargs_cnt = r.read_int()
        for f in fields[:sargs_cnt]:
            n = r.read_int()
            f.string_args = [r.read_string() for _ in range(n)]
        if sargs_cnt > len(fields):
            for _ in range(sargs_cnt - len(fields)):
                n = r.read_int()
                for _ in range(n):
                    r.read_string()

        args_cnt = r.read_int()
        for f in fields[:args_cnt]:
            n = r.read_int()
            f.args = [r.read_int() for _ in range(n)]
        if args_cnt > len(fields):
            for _ in range(args_cnt - len(fields)):
                n = r.read_int()
                for _ in range(n):
                    r.read_int()

        def_cnt = r.read_int()
        for f in fields[:def_cnt]:
            f.default_value = r.read_int()
        if def_cnt > len(fields):
            for _ in range(def_cnt - len(fields)):
                r.read_int()

        return cls(name, fields, data, description, field_type_list_size)

    def write_project(self, w: ByteWriter) -> None:
        w.write_string(self.name)
        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_string(f.name)
        w.write_int(len(self.data))
        for d in self.data:
            w.write_string(d.name)
        w.write_string(self.description)

        ft_size = max(self.field_type_list_size, len(self.fields))
        w.write_int(ft_size)
        for f in self.fields:
            w.write_byte(f.type)
        if ft_size > len(self.fields):
            w.write(bytes(ft_size - len(self.fields)))

        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_string(f.unknown1)

        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_int(len(f.string_args))
            for s in f.string_args:
                w.write_string(s)

        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_int(len(f.args))
            for a in f.args:
                w.write_int(a)

        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_int(f.default_value)

    def read_dat(self, r: ByteReader) -> None:
        self.unknown1 = r.read_int()
        if self.unknown1 == _DAT_STRING_INDICATOR:
            self.unknown2 = r.read_string()
        field_count = r.read_int()
        index_infos = [r.read_int() for _ in range(field_count)]
        for i, f in enumerate(self.fields[:field_count]):
            f.index_info = index_infos[i]

        int_indices = [idx - 1000 for idx in index_infos if 1000 <= idx < 2000]
        str_indices = [idx - 2000 for idx in index_infos if idx >= 2000]
        int_count = max(int_indices) + 1 if int_indices else 0
        str_count = max(str_indices) + 1 if str_indices else 0

        record_count = r.read_int()
        for ri in range(record_count):
            ints = [r.read_int() for _ in range(int_count)]
            strs = [r.read_string() for _ in range(str_count)]
            if ri < len(self.data):
                self.data[ri].int_values = ints
                self.data[ri].string_values = strs
            else:
                self.data.append(DataRecord(name="", int_values=ints, string_values=strs))

    def write_dat(self, w: ByteWriter) -> None:
        w.write_int(self.unknown1)
        if self.unknown1 == _DAT_STRING_INDICATOR:
            w.write_string(self.unknown2)
        w.write_int(len(self.fields))
        for f in self.fields:
            w.write_int(f.index_info)

        int_indices = [f.index_info - 1000 for f in self.fields if 1000 <= f.index_info < 2000]
        str_indices = [f.index_info - 2000 for f in self.fields if f.index_info >= 2000]
        int_count = max(int_indices) + 1 if int_indices else 0
        str_count = max(str_indices) + 1 if str_indices else 0

        w.write_int(len(self.data))
        for d in self.data:
            for i in range(int_count):
                w.write_int(d.int_values[i] if i < len(d.int_values) else 0)
            for i in range(str_count):
                w.write_string(d.string_values[i] if i < len(d.string_values) else "")


@dataclass
class WolfDatabase:
    types: list[DbType]
    version: int = _DAT_DEFAULT_VERSION
    is_utf8: bool = False

    @property
    def v35(self) -> bool:
        return self.version == _DAT_V35_VERSION

    @classmethod
    def from_bytes(
        cls,
        proj_data: bytes,
        dat_data: bytes,
        proj_path_for_error: object = "memory.project",
        dat_path_for_error: object = "memory.dat",
    ) -> WolfDatabase:
        _check_not_encrypted(proj_data, proj_path_for_error)
        r_proj = ByteReader(proj_data)
        types = [DbType.read_project(r_proj) for _ in range(r_proj.read_int())]

        _check_not_encrypted(dat_data, dat_path_for_error)
        r_dat = ByteReader(dat_data)
        r_dat.read_byte()  # 0x00 indicator
        is_utf8_dat = r_dat.verify_magic_utf8_aware(_DAT_MAGIC_CP932, _DAT_UTF8_INDEX)
        version = r_dat.read_byte()
        if version == _DAT_V35_VERSION:
            r_dat.unpack_lz4(r_dat.tell())
        _ = r_dat.read_int()  # type count in .dat
        r_dat.verify(_DAT_TYPE_SEPARATOR)

        for ti, db_type in enumerate(types):
            db_type.read_dat(r_dat)
            if ti < len(types) - 1:
                r_dat.verify(_DAT_TYPE_SEPARATOR)

        _ = r_dat.read_byte()  # terminator byte (matches version)
        return cls(types, version, is_utf8=is_utf8_dat)

    @classmethod
    def read(cls, project_path: Path | str, dat_path: Path | str) -> WolfDatabase:
        proj_p = Path(project_path)
        dat_p = Path(dat_path)
        return cls.from_bytes(
            proj_p.read_bytes(),
            dat_p.read_bytes(),
            proj_path_for_error=proj_p,
            dat_path_for_error=dat_p,
        )

    def write(self, project_path: Path | str, dat_path: Path | str) -> None:
        proj_p = Path(project_path)
        dat_p = Path(dat_path)
        proj_bytes, dat_bytes = self.to_project_and_dat_bytes()
        proj_p.write_bytes(proj_bytes)
        dat_p.write_bytes(dat_bytes)

    def to_project_and_dat_bytes(self) -> tuple[bytes, bytes]:
        def _build_proj(is_utf8_flag: bool, allow_transliterate: bool = False) -> bytes:
            encoding = UTF8 if is_utf8_flag else CP932
            w = ByteWriter(encoding=encoding, allow_transliterate=allow_transliterate)
            w.write_int(len(self.types))
            for t in self.types:
                t.write_project(w)
            return w.getvalue()

        def _build_dat(is_utf8_flag: bool, allow_transliterate: bool = False) -> bytes:
            encoding = UTF8 if is_utf8_flag else CP932
            header = ByteWriter()
            header.write_byte(0)
            magic = bytearray(_DAT_MAGIC_CP932)
            if is_utf8_flag:
                magic[_DAT_UTF8_INDEX] = 0x55
            header.write(bytes(magic))
            header.write_byte(self.version)

            body = ByteWriter(encoding=encoding, allow_transliterate=allow_transliterate)
            body.write_int(len(self.types))
            body.write(_DAT_TYPE_SEPARATOR)
            for ti, t in enumerate(self.types):
                t.write_dat(body)
                if ti < len(self.types) - 1:
                    body.write(_DAT_TYPE_SEPARATOR)
            body.write_byte(self.version)

            if self.v35:
                header.write(lz4_pack(body.getvalue()))
            else:
                header.write(body.getvalue())
            return header.getvalue()

        # WOLF 2.x engines do NOT support UTF-8 containers.
        if not self.v35:
            self.is_utf8 = False
            return _build_proj(False, allow_transliterate=True), _build_dat(False, allow_transliterate=True)

        def _build_both(is_utf8_flag: bool) -> bytes:
            _ = _build_proj(is_utf8_flag, allow_transliterate=False)
            _ = _build_dat(is_utf8_flag, allow_transliterate=False)
            return b""

        _, upgraded = _build_with_utf8_upgrade(self.is_utf8, _build_both)
        if upgraded:
            self.is_utf8 = True

        return _build_proj(self.is_utf8, allow_transliterate=False), _build_dat(self.is_utf8, allow_transliterate=False)


def translatable_fields(db_type: DbType) -> list[Field]:
    """Return translatable text fields (string-typed and type == 0)."""
    return [f for f in db_type.fields if f.is_string() and f.type == 0]


def locator_get(root: object, locator: str) -> object:
    cur = root
    for seg in locator.split("/"):
        cur = cur[int(seg)] if seg.lstrip("-").isdigit() else getattr(cur, seg)  # type: ignore[index]
    return cur


def locator_set(root: object, locator: str, value: object) -> None:
    segments = locator.split("/")
    cur = root
    for seg in segments[:-1]:
        cur = cur[int(seg)] if seg.lstrip("-").isdigit() else getattr(cur, seg)  # type: ignore[index]
    last = segments[-1]
    if last.lstrip("-").isdigit():
        cur[int(last)] = value  # type: ignore[index]
    else:
        setattr(cur, last, value)


def iter_command_texts(commands: list[Command], locator_prefix: str) -> Iterator[tuple[str, str]]:
    """Yield (locator, text) for translatable dialogue/choice slots in commands."""
    for ci, cmd in enumerate(commands):
        for slot in command_text_slots(cmd):
            yield f"{locator_prefix}/{ci}/string_args/{slot}", cmd.string_args[slot]
