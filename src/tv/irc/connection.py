"""Async IRC connection — TCP/TLS with auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections import deque
from typing import Awaitable, Callable

from .commands import pass_, user
from .parser import parse_line

log = logging.getLogger(__name__)


class IRCConnection:
    """Async IRC connection with TLS, reconnection, and line buffering."""

    def __init__(
        self,
        host: str,
        port: int = 6697,
        tls: bool = True,
        nickname: str = "vine",
        username: str | None = None,
        realname: str | None = None,
        password: str | None = None,
        encoding: str = "utf-8",
        ssl_context: ssl.SSLContext | None = None,
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
        reconnect_max_attempts: int = 10,
    ):
        self.host = host
        self.port = port
        self.use_tls = tls
        self.nickname = nickname
        self.username = username or nickname
        self.realname = realname or nickname
        self.password = password
        self.encoding = encoding
        self.ssl_context = ssl_context

        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay
        self.reconnect_max_attempts = reconnect_max_attempts

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._closed = False
        self._buffer = ""
        self._send_queue: deque[str] = deque()
        self._write_task: asyncio.Task[None] | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._attempt = 0
        self._transport: asyncio.Transport | None = None

        self._on_connect: list[Callable[[], Awaitable[None]]] = []
        self._on_disconnect: list[Callable[[], Awaitable[None]]] = []
        self._on_message: list[Callable[[str], Awaitable[None]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def on_connect(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_connect.append(fn)

    def on_disconnect(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_disconnect.append(fn)

    def on_message(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._on_message.append(fn)

    async def connect(self) -> None:
        """Establish connection and start read/write loops."""
        self._closed = False
        self._attempt = 0
        while not self._closed:
            try:
                await self._do_connect()
                self._connected = True
                self._attempt = 0
                for fn in self._on_connect:
                    await fn()
                return
            except (OSError, asyncio.CancelledError, ConnectionError) as exc:
                self._connected = False
                self._attempt += 1
                log.warning(
                    "connection to %s:%d failed (attempt %d/%d): %s",
                    self.host, self.port, self._attempt, self.reconnect_max_attempts, exc,
                )
                if not self._closed and self.reconnect:
                    if self._attempt >= self.reconnect_max_attempts:
                        log.error("max reconnect attempts reached for %s:%d", self.host, self.port)
                        break
                    delay = min(self.reconnect_delay * (2 ** (self._attempt - 1)), 60)
                    await asyncio.sleep(delay)
                else:
                    break

    async def _do_connect(self) -> None:
        """Open a single TCP/TLS connection."""
        ssl_ctx = None
        if self.use_tls:
            if self.ssl_context:
                ssl_ctx = self.ssl_context
            else:
                ssl_ctx = ssl.create_default_context()

        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_ctx,
        )
        self._transport = self._writer.transport
        log.info("connected to %s:%d (tls=%s)", self.host, self.port, self.use_tls)

        if self.password:
            await self.send_raw(pass_(self.password))
        await self.send_raw(user(self.username, self.realname))

        self._read_task = asyncio.create_task(self._read_loop())
        self._write_task = asyncio.create_task(self._write_loop())

        try:
            await asyncio.gather(self._read_task, self._write_task)
        except asyncio.CancelledError:
            pass

    async def _read_loop(self) -> None:
        """Read incoming data, buffer it, and dispatch complete lines."""
        assert self._reader is not None
        try:
            while not self._closed:
                data = await self._reader.read(4096)
                if not data:
                    log.info("server closed connection")
                    break
                self._buffer += data.decode(self.encoding, errors="replace")
                while "\r\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\r\n", 1)
                    for fn in self._on_message:
                        await fn(line)
        except (OSError, asyncio.CancelledError) as exc:
            log.debug("read loop ended: %s", exc)
        finally:
            self._connected = False
            if not self._closed and self.reconnect:
                asyncio.create_task(self.connect())
            else:
                for fn in self._on_disconnect:
                    await fn()

    async def _write_loop(self) -> None:
        """Drain the send queue and write to the socket."""
        assert self._writer is not None
        try:
            while not self._closed:
                if self._send_queue:
                    line = self._send_queue.popleft()
                    self._writer.write((line + "\r\n").encode(self.encoding))
                    await self._writer.drain()
                else:
                    await asyncio.sleep(0.05)
        except (OSError, asyncio.CancelledError) as exc:
            log.debug("write loop ended: %s", exc)

    async def send_raw(self, line: str) -> None:
        """Queue a raw IRC line for sending."""
        if self._connected:
            self._send_queue.append(line)
        else:
            log.debug("dropped (not connected): %s", line[:80])

    async def close(self) -> None:
        """Gracefully close the connection."""
        self._closed = True
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
        if self._read_task:
            self._read_task.cancel()
        if self._write_task:
            self._write_task.cancel()
        for fn in self._on_disconnect:
            await fn()
