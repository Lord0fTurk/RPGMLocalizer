"""
Endpoint Router and Health Monitor for Google Translation Families
===================================================================

Manages routing between Google endpoint families:
- PRIMARY: translate_a/single
- BATCHEXECUTE: Google Translate batchexecute RPC
- CLIENTS5: clients5.google.com/translate_a/t
- LINGVA: Lingva fallback mirrors
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.core.constants import (
    RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD,
    RATE_LIMIT_PRIMARY_PROBE_INTERVAL,
)

logger = logging.getLogger("EndpointRouter")


class _FamilyHealth:
    """Tracks success/failure health for an individual endpoint family."""

    __slots__ = ("success", "failure", "last_failure_at", "blocked_until")

    def __init__(self) -> None:
        self.success: int = 0
        self.failure: int = 0
        self.last_failure_at: float = 0.0
        self.blocked_until: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success + self.failure
        return self.success / total if total > 0 else 1.0

    def record_success(self) -> None:
        self.success += 1

    def record_failure(self, block_for: float = 0.0) -> None:
        self.failure += 1
        self.last_failure_at = time.time()
        if block_for > 0:
            self.blocked_until = time.time() + block_for

    def is_blocked(self) -> bool:
        return time.time() < self.blocked_until

    def reset_block(self) -> None:
        self.blocked_until = 0.0


class EndpointRouter:
    """Session-scoped router between Google endpoint families."""

    FAMILY_PRIMARY = "primary"
    FAMILY_BATCHEXECUTE = "batchexecute"
    FAMILY_CLIENTS5 = "clients5"
    FAMILY_LINGVA = "lingva"

    PRIORITY_BATCH = [FAMILY_PRIMARY, FAMILY_BATCHEXECUTE, FAMILY_CLIENTS5, FAMILY_LINGVA]
    PRIORITY_SINGLE = [FAMILY_PRIMARY, FAMILY_CLIENTS5, FAMILY_BATCHEXECUTE, FAMILY_LINGVA]

    def __init__(self) -> None:
        self._health: Dict[str, _FamilyHealth] = {
            f: _FamilyHealth() for f in self.PRIORITY_BATCH
        }
        self._consecutive_primary_429: int = 0
        self._probe_task: Optional[asyncio.Task] = None
        self._do_probe: Optional[Any] = None
        self.logger = logger

    @property
    def primary_blocked(self) -> bool:
        """True while the circuit breaker for primary endpoints is active."""
        return self._consecutive_primary_429 >= RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD

    def best_family_for_batch(self) -> str:
        """Return highest-priority available family for batch requests."""
        for fam in self.PRIORITY_BATCH:
            if fam == self.FAMILY_PRIMARY and self.primary_blocked:
                continue
            if not self._health[fam].is_blocked():
                return fam
        return self.FAMILY_LINGVA

    def best_family_for_single(self) -> str:
        """Return highest-priority available family for single requests."""
        for fam in self.PRIORITY_SINGLE:
            if fam == self.FAMILY_PRIMARY and self.primary_blocked:
                continue
            if not self._health[fam].is_blocked():
                return fam
        return self.FAMILY_LINGVA

    def record_primary_429(self) -> None:
        """Record 429 rate limit hit on primary endpoints."""
        self._consecutive_primary_429 += 1
        if self._consecutive_primary_429 == RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD:
            self.logger.warning(
                "EndpointRouter: PRIMARY blocked — switching to BATCHEXECUTE/CLIENTS5. "
                "Background probe scheduled every %ds.", RATE_LIMIT_PRIMARY_PROBE_INTERVAL
            )
            self._schedule_probe()

    def record_primary_success(self) -> None:
        """Record successful call on primary endpoints."""
        self._health[self.FAMILY_PRIMARY].record_success()
        if self._consecutive_primary_429 > 0:
            self._consecutive_primary_429 = max(0, self._consecutive_primary_429 - 1)

    def record_family_success(self, family: str) -> None:
        """Record successful call on an alternate family."""
        h = self._health.get(family)
        if h:
            h.record_success()

    def record_family_failure(self, family: str, block_for: float = 120.0) -> None:
        """Record failure for an alternate family and apply cooldown."""
        h = self._health.get(family)
        if h:
            h.record_failure(block_for)
            if h.failure >= 2 and block_for > 0:
                self.logger.warning(
                    "EndpointRouter: %s blocked for %.0fs after repeated failures.",
                    family, block_for,
                )

    def _schedule_probe(self) -> None:
        """Start background health probe task if not already active."""
        if self._probe_task is None or self._probe_task.done():
            try:
                self._probe_task = asyncio.get_event_loop().create_task(
                    self._probe_loop(), name="EndpointRouter-probe"
                )
            except RuntimeError:
                pass

    async def _probe_loop(self) -> None:
        """Probe primary family until healthy, then auto-restore."""
        while self.primary_blocked:
            await asyncio.sleep(RATE_LIMIT_PRIMARY_PROBE_INTERVAL)
            if not self.primary_blocked:
                return
            if self._do_probe is None:
                continue
            try:
                ok = await self._do_probe()
                if ok:
                    self._consecutive_primary_429 = 0
                    self._health[self.FAMILY_PRIMARY].reset_block()
                    self.logger.warning(
                        "EndpointRouter: PRIMARY probe succeeded — restoring primary endpoints."
                    )
                    return
                self.logger.debug("EndpointRouter: probe attempt failed, staying on alternate.")
            except Exception as exc:
                self.logger.debug("EndpointRouter: probe raised %s", exc)
