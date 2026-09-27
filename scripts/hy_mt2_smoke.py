"""Check a configured local Hy-MT2 server with an RPG Maker control code."""
from __future__ import annotations

import asyncio
import os

from src.core.translators.manager import create_translator
from src.core.translators.base import TranslationRequest


async def main() -> None:
    translator = create_translator({
        "engine": "hy_mt2",
        "hy_mt2_url": os.environ.get("HY_MT2_URL", "http://127.0.0.1:1234/v1"),
        "hy_mt2_model": os.environ.get("HY_MT2_MODEL", ""),
        "max_retries": 2,
    })
    try:
        results = await translator.translate_batch([
            TranslationRequest(text=r"Hello, \V[1]!", source_lang="en", target_lang="tr"),
        ])
        if len(results) != 1 or not results[0].success:
            raise RuntimeError("Hy-MT2 translation failed; check the local server and model selection")
        translated = results[0].translated_text
        if r"\V[1]" not in translated:
            raise RuntimeError(f"RPG Maker control code was lost: {translated!r}")
        print(translated)
    finally:
        await translator.close()


if __name__ == "__main__":
    asyncio.run(main())
