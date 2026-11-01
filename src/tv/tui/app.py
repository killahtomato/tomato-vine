"""Main Textual app for tomato-vine."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from .widgets import ChatView, NickList, StatusBar, VineInput
from ..config import ServerConfig
from ..irc.connection import IRCConnection
from ..irc.parser import parse_line
from ..irc.commands import action, privmsg, join as join_cmd, pong as pong_cmd

log = logging.getLogger(__name__)


class VineApp(App):
    """Tomato-Vine IRC TUI."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-area {
        height: 1fr;
        layout: horizontal;
    }

    #chat-column {
        width: 1fr;
        layout: vertical;
    }

    #sidebar {
        width: 20;
        height: 1fr;
        layout: vertical;
    }

    #input-area {
        height: 3;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("tab", "cycle_focus", "Focus", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "history_up", "Hist ↑", show=False),
        Binding("down", "history_down", "Hist ↓", show=False),
    ]

    def __init__(
        self,
        server_config: ServerConfig,
        on_send: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.server_config = server_config
        self.on_send = on_send
        self._conn: IRCConnection | None = None
        self._channels: dict[str, set[str]] = {}
        self._current_channel: str = ""

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with Horizontal(id="main-area"):
            with Vertical(id="chat-column"):
                yield ChatView()
            with Vertical(id="sidebar"):
                yield NickList()
        with Horizontal(id="input-area"):
            yield VineInput()

    async def on_mount(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(
            server=f"{self.server_config.host}:{self.server_config.port}",
            nick=self.server_config.nickname,
            status="connecting...",
        )
        chat = self.query_one(ChatView)
        chat.add_system(f"Connecting to {self.server_config.host}...")

        self._conn = IRCConnection(
            host=self.server_config.host,
            port=self.server_config.port,
            tls=self.server_config.tls,
            nickname=self.server_config.nickname,
            username=self.server_config.username,
            realname=self.server_config.realname,
            password=self.server_config.password,
            reconnect=True,
            reconnect_delay=5.0,
            reconnect_max_attempts=10,
        )
        self._conn.on_message(self._handle_irc_line)
        self._conn.on_connect(self._on_connected)
        self._conn.on_disconnect(self._on_disconnected)

        asyncio.create_task(self._conn.connect())

    async def _handle_irc_line(self, line: str) -> None:
        try:
            msg = parse_line(line)
        except ValueError:
            return

        chat = self.query_one(ChatView)
        status_bar = self.query_one(StatusBar)

        if msg.command == "PING":
            if self._conn:
                await self._conn.send_raw(pong_cmd(msg.trailing))
            return

        if msg.command == "001":
            nick = msg.params[0] if msg.params else self.server_config.nickname
            status_bar.update_status(
                server=f"{self.server_config.host}:{self.server_config.port}",
                nick=nick,
                status="connected",
            )
            chat.add_system(msg.trailing or "Connected")
            for ch in self.server_config.channels:
                if self._conn:
                    await self._conn.send_raw(join_cmd(ch))
            return

        if msg.command == "JOIN":
            channel = msg.trailing or (msg.params[0] if msg.params else "")
            if channel:
                chat.add_join(msg.nick, channel)
                if channel not in self._channels:
                    self._channels[channel] = set()
                self._channels[channel].add(msg.nick)
                self._update_nick_list()
            return

        if msg.command == "PART":
            channel = msg.params[0] if msg.params else self._current_channel
            if channel:
                chat.add_part(msg.nick, channel)
                if channel in self._channels:
                    self._channels[channel].discard(msg.nick)
                self._update_nick_list()
            return

        if msg.command == "PRIVMSG":
            target = msg.target
            if msg.is_ctcp and msg.ctcp_command == "ACTION":
                chat.add_action(msg.nick, msg.ctcp_params or "")
            else:
                outgoing = msg.nick == self.server_config.nickname
                chat.add_message(msg.nick, msg.trailing, outgoing=outgoing)
            return

        if msg.command == "NOTICE":
            chat.add_system(f"[Notice] {msg.trailing}")
            return

        if msg.is_numeric:
            chat.add_system(f"[{msg.command}] {msg.trailing}")

    async def _on_connected(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(
            server=f"{self.server_config.host}:{self.server_config.port}",
            nick=self.server_config.nickname,
            status="connected",
        )

    async def _on_disconnected(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(
            server=f"{self.server_config.host}:{self.server_config.port}",
            nick=self.server_config.nickname,
            status="disconnected",
        )
        chat = self.query_one(ChatView)
        chat.add_system("Disconnected. Reconnecting...")

    def _update_nick_list(self) -> None:
        if self._current_channel and self._current_channel in self._channels:
            nicks = list(self._channels[self._current_channel])
        else:
            all_nicks: set[str] = set()
            for nicks_set in self._channels.values():
                all_nicks.update(nicks_set)
            nicks = list(all_nicks)
        nick_list = self.query_one(NickList)
        nick_list.update_nicks(nicks)

    @on(Input.Submitted, "#vine-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        input_widget = self.query_one(VineInput)
        input_widget.add_to_history(text)
        input_widget.value = ""

        if text.startswith("/"):
            await self._handle_command(text)
        elif self._current_channel:
            if self._conn:
                await self._conn.send_raw(privmsg(self._current_channel, text))
                chat = self.query_one(ChatView)
                chat.add_message(self.server_config.nickname, text, outgoing=True)

    async def _handle_command(self, text: str) -> None:
        chat = self.query_one(ChatView)
        parts = text.split(None, 1)
        cmd = parts[0].lower()

        if cmd == "/quit":
            self.exit()
        elif cmd == "/join":
            channel = parts[1] if len(parts) > 1 else ""
            if channel and self._conn:
                await self._conn.send_raw(join_cmd(channel))
        elif cmd == "/part":
            channel = parts[1] if len(parts) > 1 else self._current_channel
            if channel and self._conn:
                await self._conn.send_raw(join_cmd(channel))
        elif cmd == "/nick":
            chat.add_system(f"Current nick: {self.server_config.nickname}")
        elif cmd == "/me":
            action_text = parts[1] if len(parts) > 1 else ""
            if action_text and self._current_channel and self._conn:
                await self._conn.send_raw(action(self._current_channel, action_text))
                chat.add_action(self.server_config.nickname, action_text)
        else:
            chat.add_system(f"Unknown command: {cmd}")

    def action_cycle_focus(self) -> None:
        """Cycle focus between input and chat view."""
        if self.query_one(VineInput).has_focus:
            self.query_one(ChatView).focus()
        else:
            self.query_one(VineInput).focus()

    def action_refresh(self) -> None:
        """Force a refresh of the display."""
        self.refresh()

    def action_cancel(self) -> None:
        """Cancel current input / unfocus."""
        if self.query_one(VineInput).has_focus:
            self.query_one(VineInput).value = ""
        self.query_one(VineInput).focus()

    def action_history_up(self) -> None:
        if self.query_one(VineInput).has_focus:
            self.query_one(VineInput).history_up()

    def action_history_down(self) -> None:
        if self.query_one(VineInput).has_focus:
            self.query_one(VineInput).history_down()

    def action_quit(self) -> None:
        if self._conn:
            asyncio.create_task(self._conn.close())
        self.exit()
