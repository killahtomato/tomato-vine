"""Async IRC connection — TCP/TLS with auto-reconnect, SASL, IRCv3 caps."""

from __future__ import annotations

import asyncio
import base64
import logging
import ssl
from collections import deque
from typing import Awaitable, Callable

from .capabilities import DEFAULT_CAPS
from .commands import (
    cap_end,
    cap_list,
    cap_req,
    nick,
    pass_,
    user,
)
from .parser import parse_line

log = logging.getLogger(__name__)

_DEFAULT_CAPS = " ".join(DEFAULT_CAPS)


class IRCConnection:
    """Async IRC connection with TLS, reconnection, SASL, and IRCv3 caps."""

    def __init__(
        self,
        host: str,
        port: int = 6697,
        tls: bool = True,
        nickname: str = "vine",
        username: str | None = None,
        realname: str | None = None,
        password: str | None = None,
        sasl_username: str | None = None,
        sasl_password: str | None = None,
        capabilities: list[str] | None = None,
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
        self.sasl_username = sasl_username
        self.sasl_password = sasl_password
        self.capabilities = capabilities if capabilities is not None else DEFAULT_CAPS
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
        self._registered = False

        self._on_connect: list[Callable[[], Awaitable[None]]] = []
        self._on_disconnect: list[Callable[[], Awaitable[None]]] = []
        self._on_message: list[Callable[[str], Awaitable[None]]] = []
        self._on_registered: list[Callable[[], Awaitable[None]]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def registered(self) -> bool:
        return self._registered

    def on_connect(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_connect.append(fn)

    def on_disconnect(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_disconnect.append(fn)

    def on_message(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._on_message.append(fn)

    def on_registered(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_registered.append(fn)

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
                self._registered = False
                self._attempt += 1
                log.warning(
                    "connection to %s:%d failed (attempt %d/%d): %s",
                    self.host, self.port, self._attempt, self.reconnect_max_attempts, exc,
                )
                if not self._closed and self.reconnect:
                    if self._attempt >= self.reconnect_max_attempts:
                        log.error(
                            "max reconnect attempts reached for %s:%d",
                            self.host, self.port,
                        )
                        break
                    delay = min(self.reconnect_delay * (2 ** (self._attempt - 1)), 60)
                    await asyncio.sleep(delay)
                else:
                    break

    async def _do_connect(self) -> None:
        """Open a single TCP/TLS connection and start the protocol flow."""
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

        self._registration_phase = "caps"

        if self.capabilities:
            await self.send_raw(cap_req(" ".join(self.capabilities)))

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
                    await self._handle_line(line)
        except (OSError, asyncio.CancelledError) as exc:
            log.debug("read loop ended: %s", exc)
        finally:
            self._connected = False
            self._registered = False
            if not self._closed and self.reconnect:
                asyncio.create_task(self.connect())
            else:
                for fn in self._on_disconnect:
                    await fn()

    async def _handle_line(self, line: str) -> None:
        """Route an IRC line through protocol handlers and user callbacks."""
        try:
            msg = parse_line(line)
        except ValueError:
            return

        # Protocol-level handling
        handled = await self._handle_protocol(msg)

        if not handled:
            for fn in self._on_message:
                await fn(line)

    async def _handle_protocol(self, msg) -> bool:
        """Handle protocol-level messages. Returns True if consumed."""
        cmd = msg.command

        if cmd == "PING":
            await self.send_raw(f"PONG :{msg.trailing}")
            return True

        if cmd == "CAP":
            sub = msg.params[1].upper() if len(msg.params) > 1 else ""
            caps = msg.trailing
            if sub == "ACK":
                log.debug("cap ack: %s", caps)
                if self._registration_phase == "caps":
                    await self._complete_registration()
            elif sub == "NAK":
                log.debug("cap nak: %s", caps)
                if self._registration_phase == "caps":
                    await self._complete_registration()
            elif sub == "NEW":
                log.debug("cap new: %s", caps)
            elif sub == "DEL":
                log.debug("cap del: %s", caps)
            elif sub == "LIST":
                log.debug("cap list: %s", caps)
            return True

        if cmd == "AUTHENTICATE":
            if msg.trailing == "+" and self.sasl_username and self.sasl_password:
                blob = base64.b64encode(
                    f"{self.sasl_username}\x00{self.sasl_username}\x00{self.sasl_password}".encode()
                ).decode()
                await self.send_raw(f"AUTHENTICATE {blob}")
            return True

        if cmd == "903":
            log.info("SASL authentication successful")
            if self._registration_phase == "sasl":
                await self._complete_registration()
            return True

        if cmd == "904" or cmd == "905":
            log.warning("SASL authentication failed: %s", msg.trailing)
            if self._registration_phase == "sasl":
                await self._complete_registration()
            return True

        if cmd == "908":
            log.info("SASL mechanisms: %s", msg.trailing)
            return True

        if cmd == "001":
            self._registered = True
            self._registration_phase = "done"
            for fn in self._on_registered:
                await fn()
            return False

        if cmd == "433" or cmd == "432":
            log.warning("nick error: %s", msg.trailing)
            return False

        return False

    async def _complete_registration(self) -> None:
        """Move to the next registration phase."""
        if self._registration_phase == "caps":
            if self.sasl_username and self.sasl_password:
                self._registration_phase = "sasl"
                await self.send_raw("AUTHENTICATE PLAIN")
                return
            # No SASL — jump straight to reg
            self._registration_phase = "reg"
            await self.send_raw(cap_end())
            if self.password:
                await self.send_raw(pass_(self.password))
            await self.send_raw(nick(self.nickname))
            await self.send_raw(user(self.username, self.realname))
            return

        if self._registration_phase == "sasl":
            self._registration_phase = "reg"
            await self.send_raw(cap_end())
            if self.password and not self.sasl_username:
                await self.send_raw(pass_(self.password))
            await self.send_raw(nick(self.nickname))
            await self.send_raw(user(self.username, self.realname))
            return

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
        self._registered = False
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
