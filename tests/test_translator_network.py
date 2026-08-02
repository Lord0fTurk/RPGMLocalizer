"""
Unit tests for GoogleTranslator's network resilience layer:
- Mirror endpoint health/ban tracking (`_get_next_endpoint`)
- Thread/coroutine-safe session initialization (`_get_session` double-checked locking)

No real HTTP requests are made; only pure state-machine and concurrency behavior
is exercised.
"""
import asyncio
import unittest
from unittest.mock import patch

from src.core.translator import GoogleTranslator


class TestEndpointHealthTracking(unittest.TestCase):
    """`_get_next_endpoint` / `_register_failure` / `_register_success` state machine."""

    def setUp(self):
        self.translator = GoogleTranslator(mirror_max_failures=3, mirror_ban_time=60)

    def test_failing_endpoint_gets_banned_after_max_failures(self):
        endpoint = self.translator.google_endpoints[0]

        for _ in range(self.translator.mirror_max_failures):
            self.translator._register_failure(endpoint)

        health = self.translator._endpoint_health[endpoint]
        self.assertGreater(health["banned_until"], 0.0)
        self.assertGreater(health["banned_until"], __import__("time").time())

    def test_banned_endpoint_excluded_from_selection(self):
        banned = self.translator.google_endpoints[0]
        for _ in range(self.translator.mirror_max_failures):
            self.translator._register_failure(banned)

        # Sample many times: the banned endpoint must never be selected while healthy ones exist.
        for _ in range(50):
            self.assertNotEqual(self.translator._get_next_endpoint(), banned)

    def test_all_endpoints_banned_triggers_reset(self):
        for ep in self.translator.google_endpoints:
            for _ in range(self.translator.mirror_max_failures):
                self.translator._register_failure(ep)

        # All endpoints are banned -> _get_next_endpoint must reset health and still return one.
        selected = self.translator._get_next_endpoint()
        self.assertIn(selected, self.translator.google_endpoints)
        for ep in self.translator.google_endpoints:
            self.assertEqual(self.translator._endpoint_health[ep]["banned_until"], 0.0)

    def test_register_success_clears_failure_count(self):
        endpoint = self.translator.google_endpoints[0]
        self.translator._register_failure(endpoint)
        self.translator._register_failure(endpoint)
        self.assertEqual(self.translator._endpoint_health[endpoint]["fails"], 2)

        self.translator._register_success(endpoint)
        self.assertEqual(self.translator._endpoint_health[endpoint]["fails"], 0)


class TestSessionDoubleCheckedLocking(unittest.TestCase):
    """`BaseTranslator._get_session` must create exactly one aiohttp.ClientSession
    even under concurrent access."""

    @staticmethod
    def _fake_aiohttp_classes():
        """Lightweight stand-ins for aiohttp.ClientSession/TCPConnector.

        Avoids subclassing real aiohttp classes (discouraged/deprecated) while still
        letting us count instantiations and simulate close()/closed state.
        """
        created = []

        class FakeConnector:
            def __init__(self, *args, **kwargs):
                pass

        class FakeSession:
            def __init__(self, *args, **kwargs):
                self.closed = False
                created.append(self)

            async def close(self):
                self.closed = True

        return created, FakeSession, FakeConnector

    def test_concurrent_get_session_creates_single_session(self):
        translator = GoogleTranslator()
        created, fake_session_cls, fake_connector_cls = self._fake_aiohttp_classes()

        async def run():
            with patch("aiohttp.ClientSession", fake_session_cls), \
                 patch("aiohttp.TCPConnector", fake_connector_cls):
                return await asyncio.gather(*(translator._get_session() for _ in range(20)))

        sessions = asyncio.run(run())

        self.assertEqual(len(created), 1, "Only one aiohttp.ClientSession should be created")
        self.assertTrue(all(s is sessions[0] for s in sessions), "All callers must receive the same session")

    def test_get_session_recreates_after_close(self):
        translator = GoogleTranslator()
        created, fake_session_cls, fake_connector_cls = self._fake_aiohttp_classes()

        async def run():
            with patch("aiohttp.ClientSession", fake_session_cls), \
                 patch("aiohttp.TCPConnector", fake_connector_cls):
                s1 = await translator._get_session()
                await translator.close()
                s2 = await translator._get_session()
                await translator.close()
            return s1, s2

        s1, s2 = asyncio.run(run())
        self.assertIsNot(s1, s2)
        self.assertTrue(s1.closed)


if __name__ == "__main__":
    unittest.main()
