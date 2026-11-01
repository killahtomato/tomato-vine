"""Main Textual app for tomato-vine."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from .widgets import ChatView, NickList, StatusBar, VineInput
from ..config import ServerConfig
from ..irc.capabilities import DEFAULT_CAPS
from ..irc.connection import IRCConnection
from ..irc.commands import (
    action,
    join as join_cmd,
    kick as kick_cmd,
    mode as mode_cmd,
    nick as nick_cmd,
    part as part_cmd,
    privmsg,
    quit_,
    topic as topic_cmd,
    who,
)
from ..irc.parser import parse_line

log = logging.getLogger(__name__)

VERSION_STRING = "tomato-vine 0.1.0"


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
        self._channels: dict[str, dict] = {}
        self._current_channel: str = ""
        self._pending_names: dict[str, list[str]] = {}
        self._account: str | None = None

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
        nick = self.server_config.nickname
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(
            server=f"{self.server_config.host}:{self.server_config.port}",
            nick=nick,
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
            sasl_username=self.server_config.sasl.username if self.server_config.sasl else None,
            sasl_password=self.server_config.sasl.password if self.server_config.sasl else None,
            capabilities=DEFAULT_CAPS,
            reconnect=True,
            reconnect_delay=5.0,
            reconnect_max_attempts=10,
        )
        self._conn.on_message(self._handle_irc_line)
        self._conn.on_registered(self._on_registered)
        self._conn.on_disconnect(self._on_disconnected)

        asyncio.create_task(self._conn.connect())

    async def _handle_irc_line(self, line: str) -> None:
        try:
            msg = parse_line(line)
        except ValueError:
            return

        chat = self.query_one(ChatView)

        if msg.command == "PING":
            if self._conn:
                await self._conn.send_raw(pong_cmd(msg.trailing))
            return

        if msg.command == "001":
            nick = msg.params[0] if msg.params else self.server_config.nickname
            status_bar = self.query_one(StatusBar)
            status_bar.update_status(
                server=f"{self.server_config.host}:{self.server_config.port}",
                nick=nick,
                status="connected",
            )
            chat.add_system(msg.trailing or "Connected")
            for ch in self.server_config.channels:
                await self._join_channel(ch)
            return

        if msg.command == "004":
            chat.add_system(f"Server info: {' '.join(msg.params[1:])}")
            return

        if msg.command == "005":
            chat.add_system(f"Supported: {msg.trailing}")
            return

        if msg.command == "353":
            await self._handle_names_reply(msg)
            return

        if msg.command == "366":
            await self._handle_names_end(msg)
            return

        if msg.command == "332":
            channel = msg.params[1] if len(msg.params) > 1 else ""
            chat.add_system(f"Topic for {channel}: {msg.trailing}")
            return

        if msg.command == "333":
            channel = msg.params[1] if len(msg.params) > 1 else ""
            setter = msg.params[2] if len(msg.params) > 2 else "unknown"
            chat.add_system(f"Topic set by {setter} on {channel}")
            return

        if msg.command == "JOIN":
            channel = msg.trailing or (msg.params[0] if msg.params else "")
            if channel:
                is_self = msg.nick == self.server_config.nickname
                if is_self:
                    if channel not in self._channels:
                        self._channels[channel] = {"nicks": set(), "topic": ""}
                    self._current_channel = channel
                    chat.add_system(f"Joined {channel}")
                    if self._conn:
                        await self._conn.send_raw(who(channel))
                else:
                    if channel in self._channels:
                        self._channels[channel]["nicks"].add(msg.nick)
                    if channel == self._current_channel:
                        chat.add_join(msg.nick, channel)
                    self._update_nick_list()
            return

        if msg.command == "PART":
            channel = msg.params[0] if msg.params else self._current_channel
            if channel:
                is_self = msg.nick == self.server_config.nickname
                if is_self:
                    self._channels.pop(channel, None)
                    chat.add_system(f"Left {channel}")
                    if self._channels:
                        self._current_channel = next(iter(self._channels))
                else:
                    if channel in self._channels:
                        self._channels[channel]["nicks"].discard(msg.nick)
                    if channel == self._current_channel:
                        reason = msg.trailing or ""
                        chat.add_part(msg.nick, channel)
                        if reason:
                            chat.add_system(f"  reason: {reason}")
                    self._update_nick_list()
            return

        if msg.command == "KICK":
            channel = msg.params[0] if msg.params else ""
            target = msg.params[1] if len(msg.params) > 1 else ""
            is_self = target == self.server_config.nickname
            if is_self:
                self._channels.pop(channel, None)
                chat.add_system(f"You were kicked from {channel}: {msg.trailing}")
                if self._channels:
                    self._current_channel = next(iter(self._channels))
            else:
                if channel in self._channels:
                    self._channels[channel]["nicks"].discard(target)
                chat.add_system(f"{target} was kicked from {channel} by {msg.nick}: {msg.trailing}")
                self._update_nick_list()
            return

        if msg.command == "QUIT":
            reason = msg.trailing or ""
            removed_from = []
            for channel, data in self._channels.items():
                if msg.nick in data["nicks"]:
                    data["nicks"].discard(msg.nick)
                    removed_from.append(channel)
            if removed_from:
                chat.add_system(f"{msg.nick} quit ({reason})")
                self._update_nick_list()
            return

        if msg.command == "NICK":
            old_nick = msg.nick
            new_nick = msg.trailing or (msg.params[0] if msg.params else "")
            if old_nick == self.server_config.nickname:
                self.server_config.nickname = new_nick
                status_bar = self.query_one(StatusBar)
                status_bar.update_status(nick=new_nick)
                chat.add_system(f"You are now known as {new_nick}")
            else:
                for channel, data in self._channels.items():
                    if old_nick in data["nicks"]:
                        data["nicks"].discard(old_nick)
                        data["nicks"].add(new_nick)
                chat.add_system(f"{old_nick} is now known as {new_nick}")
                self._update_nick_list()
            return

        if msg.command == "MODE":
            target = msg.target
            mode_str = msg.params[1] if len(msg.params) > 1 else ""
            mode_params = msg.params[2:] if len(msg.params) > 2 else []
            if target.startswith("#"):
                chat.add_system(f"Mode {target} [{mode_str} {' '.join(mode_params)}] by {msg.nick}")
                self._apply_mode(target, mode_str, mode_params)
            else:
                chat.add_system(f"Your mode: {mode_str}")
            return

        if msg.command == "PRIVMSG":
            await self._handle_privmsg(msg)
            return

        if msg.command == "NOTICE":
            await self._handle_notice(msg)
            return

        if msg.command == "INVITE":
            inviter = msg.nick
            channel = msg.trailing or (msg.params[1] if len(msg.params) > 1 else "")
            chat.add_system(f"{inviter} has invited you to {channel}")
            return

        if msg.command == "TOPIC":
            channel = msg.params[0] if msg.params else self._current_channel
            if channel:
                chat.add_system(f"{msg.nick} changed topic on {channel}: {msg.trailing}")
                if channel in self._channels:
                    self._channels[channel]["topic"] = msg.trailing
            return

        if msg.is_numeric:
            chat.add_system(f"[{msg.command}] {msg.trailing}")

    async def _handle_privmsg(self, msg) -> None:
        chat = self.query_one(ChatView)
        target = msg.target

        if msg.is_ctcp:
            ctcp_cmd = msg.ctcp_command
            ctcp_args = msg.ctcp_params or ""

            if ctcp_cmd == "ACTION":
                if target.startswith("#"):
                    chat.add_action(msg.nick, ctcp_args)
                else:
                    chat.add_system(f"* {msg.nick} {ctcp_args}")
            elif ctcp_cmd == "VERSION":
                if self._conn:
                    from ..irc.commands import respond_ctcp_version
                    await self._conn.send_raw(respond_ctcp_version(msg.nick, VERSION_STRING))
            elif ctcp_cmd == "PING":
                if self._conn:
                    from ..irc.commands import respond_ctcp_ping
                    await self._conn.send_raw(respond_ctcp_ping(msg.nick, ctcp_args))
            elif ctcp_cmd == "TIME":
                if self._conn:
                    from ..irc.commands import respond_ctcp_time
                    await self._conn.send_raw(respond_ctcp_time(msg.nick, time.ctime()))
            elif ctcp_cmd == "FINGER":
                if self._conn:
                    from ..irc.commands import respond_ctcp_finger
                    await self._conn.send_raw(respond_ctcp_finger(msg.nick, self.server_config.realname or ""))
            else:
                chat.add_system(f"CTCP {ctcp_cmd} from {msg.nick}: {ctcp_args}")
            return

        if target.startswith("#"):
            outgoing = msg.nick == self.server_config.nickname
            chat.add_message(msg.nick, msg.trailing, outgoing=outgoing)
        else:
            chat.add_system(f"[DM from {msg.nick}] {msg.trailing}")

    async def _handle_notice(self, msg) -> None:
        chat = self.query_one(ChatView)

        if msg.trailing and msg.trailing.startswith("\x01") and msg.trailing.endswith("\x01"):
            inner = msg.trailing[1:-1]
            ctcp_cmd, _, ctcp_args = inner.partition(" ")
            chat.add_system(f"CTCP {ctcp_cmd} reply from {msg.nick}: {ctcp_args}")
            return

        chat.add_system(f"[Notice from {msg.nick}] {msg.trailing}")

    async def _handle_names_reply(self, msg) -> None:
        if len(msg.params) < 3:
            return
        channel = msg.params[2]
        nicks_raw = msg.trailing
        nicks = nicks_raw.split() if nicks_raw else []
        if channel not in self._pending_names:
            self._pending_names[channel] = []
        self._pending_names[channel].extend(nicks)

    async def _handle_names_end(self, msg) -> None:
        channel = msg.params[1] if len(msg.params) > 1 else ""
        if channel in self._pending_names:
            nicks = self._pending_names.pop(channel)
            if channel not in self._channels:
                self._channels[channel] = {"nicks": set(), "topic": ""}
            for nick in nicks:
                stripped = nick.lstrip("@+%&~")
                self._channels[channel]["nicks"].add(stripped)
            if channel == self._current_channel:
                self._update_nick_list()

    def _apply_mode(self, channel: str, mode_str: str, params: list[str]) -> None:
        """Apply mode changes to local nick list."""
        if channel not in self._channels:
            return
        idx = 0
        action = "+"
        for ch in mode_str:
            if ch == "+":
                action = "+"
            elif ch == "-":
                action = "-"
            elif ch in "ov":
                if idx < len(params):
                    target = params[idx]
                    idx += 1
                    if channel in self._channels:
                        self._channels[channel]["nicks"].add(target)
            elif ch == "b":
                idx += 1
            elif ch in "kl":
                idx += 1
            else:
                pass

    async def _join_channel(self, channel: str) -> None:
        if self._conn:
            await self._conn.send_raw(join_cmd(channel))
            await self._conn.send_raw(who(channel))

    def _update_nick_list(self) -> None:
        if self._current_channel and self._current_channel in self._channels:
            nicks = list(self._channels[self._current_channel]["nicks"])
        else:
            all_nicks: set[str] = set()
            for data in self._channels.values():
                all_nicks.update(data["nicks"])
            nicks = list(all_nicks)
        nick_list = self.query_one(NickList)
        nick_list.update_nicks(nicks)

    async def _on_registered(self) -> None:
        chat = self.query_one(ChatView)
        chat.add_system("Registration complete.")

    async def _on_disconnected(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(
            server=f"{self.server_config.host}:{self.server_config.port}",
            nick=self.server_config.nickname,
            status="disconnected",
        )
        chat = self.query_one(ChatView)
        chat.add_system("Disconnected. Reconnecting...")

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
        rest = parts[1] if len(parts) > 1 else ""

        if cmd == "/quit":
            if self._conn and rest:
                await self._conn.send_raw(quit_(rest))
            elif self._conn:
                await self._conn.send_raw(quit_())
            self.exit()

        elif cmd == "/join":
            channel = rest.strip() or ""
            if channel:
                await self._join_channel(channel)

        elif cmd == "/part":
            channel = rest.strip() or self._current_channel
            if channel and self._conn:
                reason = ""
                if " " in rest:
                    channel, _, reason = rest.partition(" ")
                await self._conn.send_raw(part_cmd(channel, reason or None))

        elif cmd == "/nick":
            new_nick = rest.strip()
            if new_nick and self._conn:
                await self._conn.send_raw(nick_cmd(new_nick))

        elif cmd == "/me":
            action_text = rest
            if action_text and self._current_channel and self._conn:
                await self._conn.send_raw(action(self._current_channel, action_text))
                chat.add_action(self.server_config.nickname, action_text)

        elif cmd == "/msg":
            target, _, message = rest.partition(" ")
            if target and message and self._conn:
                await self._conn.send_raw(privmsg(target, message))

        elif cmd == "/topic":
            if self._current_channel and self._conn:
                if rest:
                    await self._conn.send_raw(topic_cmd(self._current_channel, rest))
                else:
                    await self._conn.send_raw(topic_cmd(self._current_channel))

        elif cmd == "/kick":
            target, _, reason = rest.partition(" ")
            if self._current_channel and target and self._conn:
                await self._conn.send_raw(kick_cmd(self._current_channel, target, reason or None))

        elif cmd == "/mode":
            if self._current_channel and rest and self._conn:
                await self._conn.send_raw(mode_cmd(self._current_channel, rest))

        elif cmd == "/who":
            target = rest.strip() or self._current_channel
            if target and self._conn:
                await self._conn.send_raw(who(target))

        elif cmd == "/away":
            if self._conn:
                from ..irc.commands import away
                if rest:
                    await self._conn.send_raw(away(rest))
                else:
                    await self._conn.send_raw(away())

        elif cmd == "/raw":
            if rest and self._conn:
                await self._conn.send_raw(rest)

        else:
            chat.add_system(f"Unknown command: {cmd}")

    def action_cycle_focus(self) -> None:
        if self.query_one(VineInput).has_focus:
            self.query_one(ChatView).focus()
        else:
            self.query_one(VineInput).focus()

    def action_refresh(self) -> None:
        self.refresh()

    def action_cancel(self) -> None:
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
