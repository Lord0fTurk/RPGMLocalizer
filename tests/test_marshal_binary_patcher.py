"""Tests for the Ruby Marshal binary patcher."""

import io
import struct
import unittest

import rubymarshal.reader
import rubymarshal.writer
from rubymarshal.classes import RubyObject, Symbol

from src.core.parsers.marshal_binary_patcher import (
    OffsetTrackingReader,
    StringByteRange,
    apply_binary_patch,
    build_patch,
    decode_marshal_long_from_bytes,
    encode_marshal_long,
    load_with_offsets,
    patch_marshal_file,
    unbundle_translations,
    _resolve_path,
)


def _serialize(obj) -> bytes:
    """Helper: serialize a Python object via rubymarshal.writer."""
    buf = io.BytesIO()
    rubymarshal.writer.write(buf, obj)
    return buf.getvalue()


class TestMarshalLongEncoding(unittest.TestCase):
    """Verify marshal_long encode/decode round-trip."""

    def test_zero(self):
        self.assertEqual(encode_marshal_long(0), b'\x00')

    def test_small_positive(self):
        for v in (1, 5, 50, 122):
            encoded = encode_marshal_long(v)
            decoded, consumed = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")
            self.assertEqual(consumed, len(encoded))

    def test_medium_positive(self):
        for v in (123, 200, 255):
            encoded = encode_marshal_long(v)
            decoded, consumed = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")

    def test_large_positive(self):
        for v in (256, 1000, 65535):
            encoded = encode_marshal_long(v)
            decoded, consumed = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")

    def test_small_negative(self):
        for v in (-1, -5, -100, -123):
            encoded = encode_marshal_long(v)
            decoded, consumed = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")

    def test_large_negative(self):
        for v in (-124, -200, -256, -1000):
            encoded = encode_marshal_long(v)
            decoded, consumed = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")


class TestOffsetTrackingReader(unittest.TestCase):
    """Verify that OffsetTrackingReader correctly records byte ranges."""

    def test_single_string(self):
        raw = _serialize("Hello")
        root, ranges = load_with_offsets(raw)
        self.assertEqual(root, "Hello")
        self.assertEqual(len(ranges), 1)
        r = next(iter(ranges.values()))
        self.assertEqual(r.encoding, "utf-8")
        # Blob should contain the marshal_long + "Hello" bytes
        blob_data = raw[r.blob_start:r.blob_end]
        self.assertIn(b"Hello", blob_data)

    def test_list_of_strings(self):
        raw = _serialize(["Alpha", "Beta", "Gamma"])
        root, ranges = load_with_offsets(raw)
        self.assertEqual(len(root), 3)
        self.assertEqual(len(ranges), 3)
        values = set()
        for obj_id in ranges:
            for item in root:
                if id(item) == obj_id:
                    values.add(item)
        self.assertEqual(values, {"Alpha", "Beta", "Gamma"})

    def test_dict_of_strings(self):
        raw = _serialize({"key1": "value1", "key2": "value2"})
        root, ranges = load_with_offsets(raw)
        self.assertIn("key1", root)
        self.assertEqual(root["key1"], "value1")
        # All 4 strings (2 keys + 2 values) should be tracked
        self.assertEqual(len(ranges), 4)

    def test_encoding_preserved(self):
        raw = _serialize("Hello")
        root, ranges = load_with_offsets(raw)
        r = next(iter(ranges.values()))
        self.assertEqual(r.encoding, "utf-8")

    def test_non_string_types_not_tracked(self):
        raw = _serialize([42, True, None, 3.14])
        root, ranges = load_with_offsets(raw)
        self.assertEqual(len(ranges), 0)

    def test_nested_structure(self):
        raw = _serialize({"outer": {"inner": "deep_value"}})
        root, ranges = load_with_offsets(raw)
        self.assertEqual(root["outer"]["inner"], "deep_value")
        self.assertGreater(len(ranges), 0)


class TestPathResolver(unittest.TestCase):
    """Verify path resolution through deserialized trees."""

    def test_dict_key(self):
        data = {"name": "Hero"}
        self.assertEqual(_resolve_path(data, "name"), "Hero")

    def test_list_index(self):
        data = ["a", "b", "c"]
        self.assertEqual(_resolve_path(data, "1"), "b")

    def test_nested_dict(self):
        data = {"outer": {"inner": "val"}}
        self.assertEqual(_resolve_path(data, "outer.inner"), "val")

    def test_list_in_dict(self):
        data = {"items": ["x", "y", "z"]}
        self.assertEqual(_resolve_path(data, "items.2"), "z")

    def test_missing_key_returns_none(self):
        data = {"a": 1}
        self.assertIsNone(_resolve_path(data, "b"))

    def test_ruby_object_attributes(self):
        obj = RubyObject("RPG::Actor", {"name": "Hero", "level": 1})
        self.assertEqual(_resolve_path(obj, "@name"), "Hero")


class TestUnbundleTranslations(unittest.TestCase):
    """Verify bundled key expansion."""

    def test_no_bundles(self):
        t = {"path.0.@parameters.0": "Hello"}
        result = unbundle_translations(t)
        self.assertEqual(result, t)

    def test_simple_bundle(self):
        t = {"list.2_bundled_4": "Line1\n\n\u27e6_I_\u27e7\n\nLine2\n\n\u27e6_I_\u27e7\n\nLine3"}
        result = unbundle_translations(t)
        self.assertIn("list.2.@parameters.0", result)
        self.assertIn("list.3.@parameters.0", result)
        self.assertIn("list.4.@parameters.0", result)
        self.assertEqual(result["list.2.@parameters.0"], "Line1")
        self.assertEqual(result["list.3.@parameters.0"], "Line2")
        self.assertEqual(result["list.4.@parameters.0"], "Line3")

    def test_empty_lines_skipped(self):
        t = {"list.5_bundled_6": "OnlyOne\n\n\u27e6_I_\u27e7\n\n"}
        result = unbundle_translations(t)
        self.assertIn("list.5.@parameters.0", result)
        # Second line is empty, should be skipped
        self.assertNotIn("list.6.@parameters.0", result)

    def test_mixed_bundle_and_normal(self):
        t = {
            "path.normal": "Normal text",
            "path.1_bundled_3": "A\n\n\u27e6_I_\u27e7\n\nB\n\n\u27e6_I_\u27e7\n\nC",
        }
        result = unbundle_translations(t)
        self.assertEqual(result["path.normal"], "Normal text")
        self.assertEqual(result["path.1.@parameters.0"], "A")
        self.assertEqual(result["path.3.@parameters.0"], "C")


class TestBinaryPatchRoundTrip(unittest.TestCase):
    """Full round-trip tests: serialize → patch → deserialize."""

    def test_patch_single_string_in_dict(self):
        raw = _serialize({"name": "Hero"})
        patched = patch_marshal_file(raw, {"name": "Kahraman"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["name"], "Kahraman")

    def test_patch_multiple_strings(self):
        raw = _serialize({"name": "Hero", "title": "Warrior"})
        patched = patch_marshal_file(raw, {"name": "Kahraman", "title": "Sava\u015f\u00e7\u0131"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["name"], "Kahraman")
        self.assertEqual(result["title"], "Sava\u015f\u00e7\u0131")

    def test_patch_string_in_list(self):
        raw = _serialize(["Hello", "World"])
        patched = patch_marshal_file(raw, {"0": "Merhaba", "1": "D\u00fcnya"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result[0], "Merhaba")
        self.assertEqual(result[1], "D\u00fcnya")

    def test_patch_nested_dict(self):
        raw = _serialize({"actor": {"name": "Hero", "class": "Knight"}})
        patched = patch_marshal_file(raw, {"actor.name": "Kahraman"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["actor"]["name"], "Kahraman")
        self.assertEqual(result["actor"]["class"], "Knight")  # Untouched

    def test_patch_preserves_non_string_data(self):
        raw = _serialize({"name": "Hero", "level": 10, "active": True})
        patched = patch_marshal_file(raw, {"name": "Kahraman"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["name"], "Kahraman")
        self.assertEqual(result["level"], 10)
        self.assertEqual(result["active"], True)

    def test_patch_longer_string(self):
        """Patch with a significantly longer string — tests marshal_long size class change."""
        raw = _serialize({"msg": "Hi"})
        long_text = "Bu bir uzun test metnidir. " * 10  # ~270 chars
        patched = patch_marshal_file(raw, {"msg": long_text.strip()})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["msg"], long_text.strip())

    def test_patch_shorter_string(self):
        raw = _serialize({"msg": "A very long message that will become shorter"})
        patched = patch_marshal_file(raw, {"msg": "Short"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["msg"], "Short")

    def test_no_translations_returns_none(self):
        raw = _serialize({"name": "Hero"})
        patched = patch_marshal_file(raw, {})
        self.assertIsNone(patched)

    def test_empty_translation_skipped(self):
        raw = _serialize({"name": "Hero"})
        patched = patch_marshal_file(raw, {"name": ""})
        self.assertIsNone(patched)

    def test_nonexistent_path_ignored(self):
        raw = _serialize({"name": "Hero"})
        patched = patch_marshal_file(raw, {"nonexistent": "value"})
        self.assertIsNone(patched)

    def test_unicode_content(self):
        raw = _serialize({"greeting": "Hello"})
        patched = patch_marshal_file(raw, {"greeting": "\u3053\u3093\u306b\u3061\u306f"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["greeting"], "\u3053\u3093\u306b\u3061\u306f")

    def test_list_of_dicts(self):
        raw = _serialize([{"name": "Actor1"}, {"name": "Actor2"}])
        patched = patch_marshal_file(raw, {"0.name": "Oyuncu1", "1.name": "Oyuncu2"})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result[0]["name"], "Oyuncu1")
        self.assertEqual(result[1]["name"], "Oyuncu2")

    def test_marshal_header_preserved(self):
        raw = _serialize({"test": "value"})
        patched = patch_marshal_file(raw, {"test": "new_value"})
        self.assertIsNotNone(patched)
        self.assertEqual(patched[:2], b'\x04\x08')


class TestMarshalLongBoundary(unittest.TestCase):
    """Test marshal_long size class transitions during patching."""

    def test_cross_122_boundary_upward(self):
        """String growing from <122 bytes to >122 bytes."""
        short = "A" * 100
        long = "B" * 200
        raw = _serialize({"text": short})
        patched = patch_marshal_file(raw, {"text": long})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["text"], long)

    def test_cross_122_boundary_downward(self):
        """String shrinking from >122 bytes to <122 bytes."""
        long = "A" * 200
        short = "B" * 50
        raw = _serialize({"text": long})
        patched = patch_marshal_file(raw, {"text": short})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["text"], short)

    def test_cross_255_boundary(self):
        """String growing past 255 bytes (2-byte → 3-byte marshal_long)."""
        medium = "C" * 200
        large = "D" * 500
        raw = _serialize({"text": medium})
        patched = patch_marshal_file(raw, {"text": large})
        self.assertIsNotNone(patched)
        result = rubymarshal.reader.loads(patched)
        self.assertEqual(result["text"], large)


class TestEncodingMarshalLong(unittest.TestCase):
    """Verify encode_marshal_long produces correct byte sequences."""

    def test_round_trip_all_small(self):
        for v in range(0, 123):
            encoded = encode_marshal_long(v)
            decoded, _ = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v)

    def test_round_trip_boundary_values(self):
        for v in [122, 123, 254, 255, 256, 65534, 65535, 65536]:
            encoded = encode_marshal_long(v)
            decoded, _ = decode_marshal_long_from_bytes(encoded, 0)
            self.assertEqual(decoded, v, f"Failed for {v}")


if __name__ == "__main__":
    unittest.main()
