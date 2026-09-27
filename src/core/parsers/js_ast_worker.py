"""Isolated JS AST reader for native-parser crash containment on Windows."""
from __future__ import annotations

import json
import sys

from .js_ast_extractor import JavaScriptAstAuditExtractor


def main() -> int:
    source = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    entries, _engine = JavaScriptAstAuditExtractor().extract_safe_sink_entries_from_source(source)
    sys.stdout.buffer.write(json.dumps(entries, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
