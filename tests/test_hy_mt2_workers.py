"""Verify that Hy-MT2 sends bounded concurrent HTTP requests."""
from __future__ import annotations

import asyncio
import unittest

from aiohttp import web

from src.core.translators.manager import create_translator
from src.core.translators.services import HyMT2Translator


class HyMT2WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.active = 0
        self.peak = 0
        self.models: list[str] = []
        self.prompts: list[str] = []

        async def completion(request: web.Request) -> web.Response:
            payload = await request.json()
            self.models.append(payload["model"])
            self.prompts.append(payload["messages"][0]["content"])
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.25)
                return web.json_response({"choices": [{"message": {"content": "Çeviri"}}]})
            finally:
                self.active -= 1

        async def models(request: web.Request) -> web.Response:
            return web.json_response({
                "data": [{"id": "server-selected-model"}, {"id": "hy-mt2-test"}]
            })

        app = web.Application()
        app.router.add_post("/v1/chat/completions", completion)
        app.router.add_get("/v1/models", models)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.base_url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/v1"

    async def asyncTearDown(self) -> None:
        await self.runner.cleanup()

    async def test_eight_workers_send_eight_requests(self) -> None:
        translator = create_translator({
            "engine": "hy_mt2", "hy_mt2_url": self.base_url,
            "hy_mt2_model": "server-selected-model", "hy_mt2_workers": 8,
            "batch_size": 100,
        })
        try:
            progress: list[int] = []
            results = await translator.translate_batch([
                {"text": f"Text {index}", "source_lang": "en", "target_lang": "tr"}
                for index in range(16)
            ], progress_callback=progress.append)
            self.assertEqual(8, self.peak)
            self.assertEqual(16, len(results))
            self.assertTrue(all(result.success for result in results))
            self.assertEqual({"server-selected-model"}, set(self.models))
            self.assertEqual(16, sum(progress))
            self.assertEqual(16, len(progress))
        finally:
            await translator.close()

    async def test_batch_size_one_limits_window(self) -> None:
        translator = create_translator({
            "engine": "hy_mt2", "hy_mt2_url": self.base_url,
            "hy_mt2_model": "server-selected-model", "hy_mt2_workers": 8,
            "batch_size": 1,
        })
        try:
            await translator.translate_batch([
                {"text": f"Text {index}", "source_lang": "en", "target_lang": "tr"}
                for index in range(4)
            ])
            self.assertEqual(1, self.peak)
        finally:
            await translator.close()

    async def test_local_llm_saved_url_uses_hy_profile(self) -> None:
        translator = create_translator({
            "engine": "local_llm",
            "local_llm_url": self.base_url,
            "local_llm_model": "hy-mt2-test",
            "concurrent_requests": 20,
            "batch_size": 50,
        })
        self.assertIsInstance(translator, HyMT2Translator)
        self.assertEqual(self.base_url + "/chat/completions", translator.endpoint)
        self.assertEqual(8, translator.concurrency)
        try:
            await translator.verify_connection()
            results = await translator.translate_batch([
                {"text": "Hello", "source_lang": "en", "target_lang": "tr"}
            ])
            self.assertTrue(results[0].success)
        finally:
            await translator.close()

    async def test_missing_model_fails_before_batch(self) -> None:
        translator = create_translator({
            "engine": "hy_mt2", "hy_mt2_url": self.base_url,
            "hy_mt2_model": "missing-model",
        })
        try:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                await translator.verify_connection()
            self.assertEqual(0, self.peak)
        finally:
            await translator.close()

    async def test_style_is_sent_to_hy_mt2(self) -> None:
        translator = create_translator({
            "engine": "hy_mt2", "hy_mt2_url": self.base_url,
            "hy_mt2_model": "server-selected-model",
            "hy_mt2_style": "natural fantasy RPG dialogue",
        })
        try:
            await translator.translate_batch([{"text": "Hello", "target_lang": "tr"}])
            self.assertIn("natural fantasy RPG dialogue", self.prompts[0])
            self.assertIn("Turkish", self.prompts[0])
        finally:
            await translator.close()


if __name__ == "__main__":
    unittest.main()
