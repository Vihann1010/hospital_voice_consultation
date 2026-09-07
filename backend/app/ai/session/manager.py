"""Session management for live voice consultations.

- One `ConversationMemory` per consultation, kept for SESSION_IDLE_TTL_S after
  the last activity so a dropped connection can resume with full context.
- Capacity guard (MAX_ACTIVE_SESSIONS) protects the node under load.
- A lazy background reaper evicts idle sessions.
"""
import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.ai.session.memory import ConversationMemory
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SessionCapacityError(Exception):
    pass


@dataclass
class SessionEntry:
    memory: ConversationMemory
    last_active: float = field(default_factory=time.monotonic)
    connected: bool = False


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[uuid.UUID, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._reaper: Optional[asyncio.Task] = None

    async def acquire(
        self,
        consultation_id: uuid.UUID,
        *,
        factory,
    ) -> ConversationMemory:
        """Return the existing memory (resume) or build a fresh one."""
        async with self._lock:
            self._ensure_reaper()
            entry = self._sessions.get(consultation_id)
            if entry is None:
                active = sum(1 for e in self._sessions.values() if e.connected)
                if active >= settings.MAX_ACTIVE_SESSIONS:
                    raise SessionCapacityError("Session capacity reached on this node")
                entry = SessionEntry(memory=factory())
                self._sessions[consultation_id] = entry
                logger.info("session_created", extra={"consultation_id": str(consultation_id)})
            else:
                logger.info("session_resumed", extra={"consultation_id": str(consultation_id)})
            entry.connected = True
            entry.last_active = time.monotonic()
            return entry.memory

    async def touch(self, consultation_id: uuid.UUID) -> None:
        entry = self._sessions.get(consultation_id)
        if entry is not None:
            entry.last_active = time.monotonic()

    async def release(self, consultation_id: uuid.UUID, *, discard: bool = False) -> None:
        """Mark disconnected; keep memory for TTL unless the visit is finished."""
        async with self._lock:
            entry = self._sessions.get(consultation_id)
            if entry is None:
                return
            entry.connected = False
            entry.last_active = time.monotonic()
            if discard:
                del self._sessions[consultation_id]
                logger.info("session_discarded", extra={"consultation_id": str(consultation_id)})

    def stats(self) -> dict:
        return {
            "sessions": len(self._sessions),
            "connected": sum(1 for e in self._sessions.values() if e.connected),
        }

    # -- reaper --------------------------------------------------------------
    def _ensure_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap_loop())

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.SESSION_REAPER_INTERVAL_S)
            cutoff = time.monotonic() - settings.SESSION_IDLE_TTL_S
            async with self._lock:
                stale = [
                    cid
                    for cid, entry in self._sessions.items()
                    if not entry.connected and entry.last_active < cutoff
                ]
                for cid in stale:
                    del self._sessions[cid]
            if stale:
                logger.info("sessions_reaped", extra={"count": len(stale)})

    async def shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        self._sessions.clear()


session_manager = SessionManager()
