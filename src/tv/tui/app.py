"""Main Textual app for tomato-vine — multi-server support."""

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

from .widgets import ChatView, CommandPalette, NickList, ServerTree, StatusBar, VineInput
from ..log import error_log, setup_logging
from ..config import AppConfig, ServerConfig
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

from .themes import register_all_themes


class VineApp(App):
    """Tomato-Vine IRC TUI — multi-server."""

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
        width: 44;
        height: 1fr;
        layout: vertical;
    }

    #nick-area {
        height: 1fr;
    }

    #sidebar-bottom {
        height: 1fr;
        layout: horizontal;
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
        Binding("c", "show_tree", "Channels", show=True),
        Binding("o", "open_last_url", "Open URL", show=True),
    ]

    def __init__(
        self,
        app_config: AppConfig,
        on_send: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.app_config = app_config
        self.on_send = on_send
        self._server_configs: dict[str, ServerConfig] = {}
        self._connections: dict[str, IRCConnection] = {}
        self._channels: dict[str, dict[str, dict]] = {}
        self._pending_names: dict[str, dict[str, list[str]]] = {}
        self._pending_list: dict[str, list[dict]] = {}
        self._list_loading: dict[str, bool] = {}
        self._active_server: str | None = None
        self._active_channel: str = ""
        self._current_theme: str = app_config.theme
        self._theme_names: list[str] = []
        self._connecting: set[str] = set()

        for sc in app_config.servers:
            self._server_configs[sc.host] = sc

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with Horizontal(id="main-area"):
            with Vertical(id="chat-column"):
                yield ChatView()
            with Vertical(id="sidebar"):
                yield ServerTree()
                with Horizontal(id="sidebar-bottom"):
                    yield NickList()
                    yield CommandPalette()
        with Horizontal(id="input-area"):
            yield VineInput()

    async def on_mount(self) -> None:
        status_bar = self.query_one(StatusBar)
        status_bar.update_status(nick="—", status="idle")

        tree = self.query_one(ServerTree)
        for host, sc in self._server_configs.items():
            tree.add_server(host, sc.nickname)

        palette = self.query_one(CommandPalette)
        palette.set_callback(self._on_palette_action)

        self.query_one(ChatView)

        self._theme_names = register_all_themes(self)

        for host, sc in self._server_configs.items():
            if sc.auto_connect:
                await self._connect_server(host)

    async def _connect_server(self, host: str) -> None:
        """Establish a connection to a server."""
        if host in self._connections:
            return
        sc = self._server_configs.get(host)
        if not sc:
            return

        error_log().info("Connecting to %s:%d as %s", host, sc.port, sc.nickname)

        conn = IRCConnection(
            host=sc.host,
            port=sc.port,
            tls=sc.tls,
            nickname=sc.nickname,
            username=sc.username,
            realname=sc.realname,
            password=sc.password,
            sasl_username=sc.sasl.username if sc.sasl else None,
            sasl_password=sc.sasl.password if sc.sasl else None,
            capabilities=DEFAULT_CAPS,
            reconnect=False,
        )

        conn.on_message(self._make_line_handler(host))
        conn.on_registered(self._make_registered_handler(host))
        conn.on_disconnect(self._make_disconnect_handler(host))

        self._connections[host] = conn
        self._channels[host] = {}
        self._pending_names[host] = {}

        tree = self.query_one(ServerTree)
        tree.set_server_status(host, "connecting...")

        status_bar = self.query_one(StatusBar)
        status_bar.update_status(server=host, nick=sc.nickname, status="connecting...")

        asyncio.create_task(conn.connect())

    def _make_line_handler(self, host: str) -> Callable[[str], Awaitable[None]]:
        async def handler(line: str) -> None:
            await self._handle_irc_line(host, line)
        return handler

    def _make_registered_handler(self, host: str) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await self._on_registered(host)
        return handler

    def _make_disconnect_handler(self, host: str) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await self._on_disconnected(host)
        return handler

    async def _handle_irc_line(self, host: str, line: str) -> None:
        try:
            msg = parse_line(line)
        except ValueError:
            return

        chat = self.query_one(ChatView)
        sc = self._server_configs[host]

        if msg.command == "PING":
            conn = self._connections.get(host)
            if conn:
                await conn.send_raw(f"PONG :{msg.trailing}")
            return

        if msg.command == "001":
            nick = msg.params[0] if msg.params else sc.nickname
            tree = self.query_one(ServerTree)
            tree.set_server_status(host, "connected")
            if host == self._active_server:
                status_bar = self.query_one(StatusBar)
                status_bar.update_status(server=host, nick=nick, status="connected")
            chat.add_system(f"[{host}] {msg.trailing or 'Connected'}")
            for ch in sc.channels:
                await self._join_channel(host, ch)
            return

        if msg.command == "004":
            chat.add_system(f"[{host}] Server info: {' '.join(msg.params[1:])}")
            return

        if msg.command == "005":
            chat.add_system(f"[{host}] Supported: {msg.trailing}")
            return

        if msg.command == "353":
            await self._handle_names_reply(host, msg)
            return

        if msg.command == "366":
            await self._handle_names_end(host, msg)
            return

        if msg.command == "332":
            channel = msg.params[1] if len(msg.params) > 1 else ""
            chat.add_system(f"[{host}] Topic for {channel}: {msg.trailing}")
            return

        if msg.command == "333":
            channel = msg.params[1] if len(msg.params) > 1 else ""
            setter = msg.params[2] if len(msg.params) > 2 else "unknown"
            chat.add_system(f"[{host}] Topic set by {setter} on {channel}")
            return

        if msg.command == "JOIN":
            await self._handle_join(host, msg)
            return

        if msg.command == "PART":
            await self._handle_part(host, msg)
            return

        if msg.command == "KICK":
            await self._handle_kick(host, msg)
            return

        if msg.command == "QUIT":
            reason = msg.trailing or ""
            removed_from = []
            for channel, data in self._channels[host].items():
                if msg.nick in data["nicks"]:
                    data["nicks"].discard(msg.nick)
                    removed_from.append(channel)
            if removed_from:
                chat.add_system(f"[{host}] {msg.nick} quit ({reason})")
                if host == self._active_server:
                    self._update_nick_list(host)
            return

        if msg.command == "NICK":
            await self._handle_nick_change(host, msg)
            return

        if msg.command == "MODE":
            await self._handle_mode(host, msg)
            return

        if msg.command == "PRIVMSG":
            await self._handle_privmsg(host, msg)
            return

        if msg.command == "NOTICE":
            await self._handle_notice(host, msg)
            return

        if msg.command == "INVITE":
            inviter = msg.nick
            channel = msg.trailing or (msg.params[1] if len(msg.params) > 1 else "")
            chat.add_system(f"[{host}] {inviter} has invited you to {channel}")
            return

        if msg.command == "TOPIC":
            channel = msg.params[0] if msg.params else self._active_channel
            if channel:
                chat.add_system(f"[{host}] {msg.nick} changed topic on {channel}: {msg.trailing}")
                if channel in self._channels.get(host, {}):
                    self._channels[host][channel]["topic"] = msg.trailing
            return

        if msg.command == "322":
            await self._handle_list_entry(host, msg)
            return

        if msg.command == "323":
            await self._handle_list_end(host)
            return

        if msg.is_numeric:
            chat.add_system(f"[{host}] [{msg.command}] {msg.trailing}")
            if msg.command in ("433", "432", "904", "905", "481", "482"):
                error_log().warning("[%s] %s %s", host, msg.command, msg.trailing)

    async def _handle_list_entry(self, host: str, msg) -> None:
        if len(msg.params) < 3:
            return
        channel = msg.params[1]
        try:
            users = int(msg.params[2])
        except ValueError:
            users = 0
        topic = msg.trailing if msg.trailing else ""
        self._pending_list.setdefault(host, []).append({
            "channel": channel,
            "users": users,
            "topic": topic,
        })

    async def _handle_list_end(self, host: str) -> None:
        chat = self.query_one(ChatView)
        channels = self._pending_list.pop(host, [])
        self._list_loading.pop(host, None)

        if not channels:
            chat.add_system(f"[{host}] No channels found")
            return

        channels.sort(key=lambda c: c["users"], reverse=True)
        max_name = max(len(c["channel"]) for c in channels)
        max_name = max(max_name, 20)

        header = f"{'Channel':<{max_name}}  {'Users':>5}  Topic"
        sep = "─" * (max_name + 30)
        chat.add_system(f"[{host}] Channel list ({len(channels)} channels):")
        chat.add_system(f"  {header}")
        chat.add_system(f"  {sep}")
        for ch in channels:
            topic = ch["topic"][:50]
            chat.add_system(f"  {ch['channel']:<{max_name}}  {ch['users']:>5}  {topic}")

    async def _handle_join(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        sc = self._server_configs[host]
        channel = msg.trailing or (msg.params[0] if msg.params else "")
        if not channel:
            return

        is_self = msg.nick == sc.nickname
        tree = self.query_one(ServerTree)

        if is_self:
            self._channels[host][channel] = {"nicks": set(), "topic": ""}
            tree.add_channel(host, channel)
            if self._active_server is None:
                self._active_server = host
                self._active_channel = channel
                tree.mark_active(channel)
                status_bar = self.query_one(StatusBar)
                status_bar.update_status(server=host, channel=channel, nick=sc.nickname, status="connected")
            chat.add_system(f"[{host}] Joined {channel}")
            conn = self._connections.get(host)
            if conn:
                await conn.send_raw(who(channel))
        else:
            self._channels[host].setdefault(channel, {"nicks": set(), "topic": ""})
            self._channels[host][channel]["nicks"].add(msg.nick)
            if host == self._active_server and channel == self._active_channel:
                chat.add_join(msg.nick, channel)
            if host == self._active_server:
                self._update_nick_list(host)

    async def _handle_part(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        sc = self._server_configs[host]
        channel = msg.params[0] if msg.params else self._active_channel
        if not channel:
            return

        is_self = msg.nick == sc.nickname
        tree = self.query_one(ServerTree)

        if is_self:
            self._channels[host].pop(channel, None)
            tree.remove_channel(host, channel)
            chat.add_system(f"[{host}] Left {channel}")
            if host == self._active_server:
                if self._channels[host]:
                    self._active_channel = next(iter(self._channels[host]))
                    tree.mark_active(self._active_channel)
                else:
                    self._active_channel = ""
                    tree.mark_active(None)
                self._update_nick_list(host)
        else:
            ch_data = self._channels[host].get(channel)
            if ch_data:
                ch_data["nicks"].discard(msg.nick)
            if host == self._active_server and channel == self._active_channel:
                reason = msg.trailing or ""
                chat.add_part(msg.nick, channel)
                if reason:
                    chat.add_system(f"  reason: {reason}")
            if host == self._active_server:
                self._update_nick_list(host)

    async def _handle_kick(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        sc = self._server_configs[host]
        channel = msg.params[0] if msg.params else ""
        target = msg.params[1] if len(msg.params) > 1 else ""
        is_self = target == sc.nickname
        tree = self.query_one(ServerTree)

        if is_self:
            self._channels[host].pop(channel, None)
            tree.remove_channel(host, channel)
            chat.add_system(f"[{host}] You were kicked from {channel}: {msg.trailing}")
            if host == self._active_server:
                if self._channels[host]:
                    self._active_channel = next(iter(self._channels[host]))
                    tree.mark_active(self._active_channel)
                else:
                    self._active_channel = ""
                    tree.mark_active(None)
                self._update_nick_list(host)
        else:
            ch_data = self._channels[host].get(channel)
            if ch_data:
                ch_data["nicks"].discard(target)
            chat.add_system(f"[{host}] {target} was kicked from {channel} by {msg.nick}: {msg.trailing}")
            if host == self._active_server:
                self._update_nick_list(host)

    async def _handle_nick_change(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        sc = self._server_configs[host]
        old_nick = msg.nick
        new_nick = msg.trailing or (msg.params[0] if msg.params else "")

        if old_nick == sc.nickname:
            sc.nickname = new_nick
            if host == self._active_server:
                status_bar = self.query_one(StatusBar)
                status_bar.update_status(server=host, nick=new_nick, status="connected")
            chat.add_system(f"[{host}] You are now known as {new_nick}")
        else:
            for channel, data in self._channels[host].items():
                if old_nick in data["nicks"]:
                    data["nicks"].discard(old_nick)
                    data["nicks"].add(new_nick)
            chat.add_system(f"[{host}] {old_nick} is now known as {new_nick}")
            if host == self._active_server:
                self._update_nick_list(host)

    async def _handle_mode(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        target = msg.target
        mode_str = msg.params[1] if len(msg.params) > 1 else ""
        mode_params = msg.params[2:] if len(msg.params) > 2 else []

        if target.startswith("#"):
            chat.add_system(f"[{host}] Mode {target} [{mode_str} {' '.join(mode_params)}] by {msg.nick}")
            self._apply_mode(host, target, mode_str, mode_params)
        else:
            chat.add_system(f"[{host}] Your mode: {mode_str}")

    async def _handle_privmsg(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)
        target = msg.target

        if msg.is_ctcp:
            ctcp_cmd = msg.ctcp_command
            ctcp_args = msg.ctcp_params or ""
            conn = self._connections.get(host)

            if ctcp_cmd == "ACTION":
                if target.startswith("#"):
                    chat.add_action(msg.nick, ctcp_args)
                else:
                    chat.add_system(f"[{host}] * {msg.nick} {ctcp_args}")
            elif ctcp_cmd == "VERSION" and conn:
                from ..irc.commands import respond_ctcp_version
                await conn.send_raw(respond_ctcp_version(msg.nick, VERSION_STRING))
            elif ctcp_cmd == "PING" and conn:
                from ..irc.commands import respond_ctcp_ping
                await conn.send_raw(respond_ctcp_ping(msg.nick, ctcp_args))
            elif ctcp_cmd == "TIME" and conn:
                from ..irc.commands import respond_ctcp_time
                await conn.send_raw(respond_ctcp_time(msg.nick, time.ctime()))
            elif ctcp_cmd == "FINGER" and conn:
                from ..irc.commands import respond_ctcp_finger
                await conn.send_raw(respond_ctcp_finger(msg.nick, self._server_configs[host].realname or ""))
            else:
                chat.add_system(f"[{host}] CTCP {ctcp_cmd} from {msg.nick}: {ctcp_args}")
            return

        if target.startswith("#"):
            outgoing = msg.nick == self._server_configs[host].nickname
            chat.add_message(msg.nick, msg.trailing, outgoing=outgoing)
        else:
            tree = self.query_one(ServerTree)
            tree.add_dm(host, msg.nick)
            if host != self._active_server or target != self._active_channel:
                tree.mark_unread(target)
            chat.add_system(f"[{host}] [DM from {msg.nick}] {msg.trailing}")

    async def _handle_notice(self, host: str, msg) -> None:
        chat = self.query_one(ChatView)

        if msg.trailing and msg.trailing.startswith("\x01") and msg.trailing.endswith("\x01"):
            inner = msg.trailing[1:-1]
            ctcp_cmd, _, ctcp_args = inner.partition(" ")
            chat.add_system(f"[{host}] CTCP {ctcp_cmd} reply from {msg.nick}: {ctcp_args}")
            return

        chat.add_system(f"[{host}] [Notice from {msg.nick}] {msg.trailing}")

    async def _handle_names_reply(self, host: str, msg) -> None:
        if len(msg.params) < 3:
            return
        channel = msg.params[2]
        nicks_raw = msg.trailing
        nicks = nicks_raw.split() if nicks_raw else []
        self._pending_names[host].setdefault(channel, []).extend(nicks)

    async def _handle_names_end(self, host: str, msg) -> None:
        channel = msg.params[1] if len(msg.params) > 1 else ""
        names = self._pending_names[host].pop(channel, [])
        self._channels[host].setdefault(channel, {"nicks": set(), "topic": ""})
        for nick in names:
            stripped = nick.lstrip("@+%&~")
            self._channels[host][channel]["nicks"].add(stripped)
        if host == self._active_server and channel == self._active_channel:
            self._update_nick_list(host)

    def _apply_mode(self, host: str, channel: str, mode_str: str, params: list[str]) -> None:
        """Apply mode changes to local nick list."""
        ch_data = self._channels.get(host, {}).get(channel)
        if not ch_data:
            return
        idx = 0
        for ch in mode_str:
            if ch == "+":
                pass
            elif ch == "-":
                pass
            elif ch in "ov":
                if idx < len(params):
                    target = params[idx]
                    idx += 1
                    ch_data["nicks"].add(target)
            elif ch == "b":
                idx += 1
            elif ch in "kl":
                idx += 1

    async def _join_channel(self, host: str, channel: str) -> None:
        conn = self._connections.get(host)
        if conn:
            await conn.send_raw(join_cmd(channel))
            await conn.send_raw(who(channel))

    def _update_nick_list(self, host: str) -> None:
        channels = self._channels.get(host, {})
        if self._active_channel and self._active_channel in channels:
            nicks = list(channels[self._active_channel]["nicks"])
        else:
            all_nicks: set[str] = set()
            for data in channels.values():
                all_nicks.update(data["nicks"])
            nicks = list(all_nicks)
        nick_list = self.query_one(NickList)
        nick_list.update_nicks(nicks)

    async def _on_registered(self, host: str) -> None:
        error_log().info("Connected to %s as %s", host, self._server_configs[host].nickname)
        tree = self.query_one(ServerTree)
        tree.set_server_status(host, "connected")
        status_bar = self.query_one(StatusBar)
        sc = self._server_configs[host]
        status_bar.update_status(server=host, nick=sc.nickname, status="connected")
        chat = self.query_one(ChatView)
        sc = self._server_configs[host]
        chat.set_nick_highlight(sc.nickname, sc.nick_color)
        chat.add_system(f"[{host}] Registration complete.")

    async def _on_disconnected(self, host: str) -> None:
        error_log().warning("Disconnected from %s", host)
        tree = self.query_one(ServerTree)
        tree.set_server_status(host, "disconnected")
        if host == self._active_server:
            status_bar = self.query_one(StatusBar)
            sc = self._server_configs[host]
            status_bar.update_status(server=host, nick=sc.nickname, status="disconnected")
        chat = self.query_one(ChatView)
        chat.add_system(f"[{host}] Disconnected. Reconnecting...")

    async def on_tree_node_selected(self, event: ServerTree.NodeSelected) -> None:
        """Handle channel/DM/server selection from the tree."""
        node = event.node
        label = str(node.label).strip()

        # Server node — connect if not connected, switch active server
        if label.startswith("●") or label.startswith("○") or label.startswith("◌"):
            host = label[2:].strip()
            if "@" in host:
                host = host.split("@")[-1]
            if host not in self._connections and host not in self._connecting:
                self._connecting.add(host)
                await self._connect_server(host)
            self._active_server = host
            sc = self._server_configs.get(host)
            nick = sc.nickname if sc else "?"
            first_ch = next(iter(self._channels.get(host, {})), "")
            self._active_channel = first_ch
            status_bar = self.query_one(StatusBar)
            status_bar.update_status(server=host, nick=nick, channel=first_ch, status="connecting...")
            chat = self.query_one(ChatView)
            chat.add_system(f"Switched to {host}")
            return

        # DM node
        if label.startswith("💬 "):
            nick = label[2:].strip()
            self._active_channel = nick
            tree = self.query_one(ServerTree)
            tree.mark_active(nick)
            chat = self.query_one(ChatView)
            chat.add_system(f"DM with {nick}")
            return

        # Channel node
        channel = label.lstrip("\u25b8 ").strip()
        for host, channels in self._channels.items():
            if channel in channels:
                self._active_server = host
                self._active_channel = channel
                tree = self.query_one(ServerTree)
                tree.mark_active(channel)
                sc = self._server_configs[host]
                status_bar = self.query_one(StatusBar)
                status_bar.update_status(server=host, channel=channel, nick=sc.nickname, status="connected")
                chat = self.query_one(ChatView)
                chat.add_system(f"Switched to {host}/{channel}")
                self._update_nick_list(host)
                return

    async def _on_palette_action(self, command: str) -> None:
        """Handle a command palette button press."""
        input_widget = self.query_one(VineInput)
        input_widget.value = command
        input_widget.focus()
        if command.endswith(" "):
            return
        await self._handle_command(command)
        input_widget.value = ""

    def apply_theme(self, name: str) -> None:
        """Apply a color theme to the TUI."""
        self._current_theme = name
        try:
            self.theme = name
        except Exception:
            pass

    def _cycle_theme(self, direction: int) -> None:
        """Cycle to next (1) or previous (-1) theme."""
        if not self._theme_names:
            return
        try:
            idx = self._theme_names.index(self._current_theme)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(self._theme_names)
        theme_name = self._theme_names[idx]
        self.apply_theme(theme_name)
        chat = self.query_one(ChatView)
        chat.add_system(f"Theme: {theme_name}")

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
        elif self._active_channel and self._active_server:
            conn = self._connections.get(self._active_server)
            if conn:
                await conn.send_raw(privmsg(self._active_channel, text))
                chat = self.query_one(ChatView)
                sc = self._server_configs[self._active_server]
                chat.add_message(sc.nickname, text, outgoing=True)

    async def _handle_command(self, text: str) -> None:
        chat = self.query_one(ChatView)
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        conn = self._connections.get(self._active_server) if self._active_server else None

        if cmd == "/quit":
            if conn:
                if rest:
                    await conn.send_raw(quit_(rest))
                else:
                    await conn.send_raw(quit_())
            self.exit()

        elif cmd == "/help":
            if rest.strip():
                topic = rest.strip().lower().lstrip("/")
                help_text = self._command_help(topic)
                if help_text:
                    chat.add_system(f"/{topic}: {help_text}")
                else:
                    chat.add_system(f"No help available for /{topic}")
            else:
                commands = [
                    "/join <#channel> — join a channel",
                    "/list [filter] — browse public channels",
                    "/part [#channel] [reason] — leave a channel",
                    "/msg <nick> <text> — private message",
                    "/me <text> — send action",
                    "/topic [text] — view or set topic",
                    "/kick <nick> [reason] — kick user",
                    "/mode <modes> [params] — set channel mode",
                    "/who [target] — query WHO",
                    "/away [reason] — set away",
                    "/nick <newnick> — change nickname",
                    "/server list — list servers",
                    "/server add host:port nick [#chans] — add server",
                    "/server remove host — remove server",
                    "/raw <command> — send raw IRC",
                    "/quit [reason] — disconnect and exit",
                    "/copy — copy last 50 lines to clipboard",
                    "/open — open links from recent messages",
            "/help [command] — show this help",
                ]
                chat.add_system("Available commands:")
                for line in commands:
                    chat.add_system(f"  {line}")

        elif cmd == "/join":
            channel = rest.strip()
            if channel and self._active_server:
                await self._join_channel(self._active_server, channel)

        elif cmd == "/list":
            if not self._active_server or not conn:
                chat.add_system("No active server")
                return
            self._pending_list[self._active_server] = []
            self._list_loading[self._active_server] = True
            if rest.strip():
                await conn.send_raw(f"LIST {rest.strip()}")
            else:
                await conn.send_raw("LIST")
            chat.add_system(f"[{self._active_server}] Loading channel list...")

        elif cmd == "/part":
            channel = rest.strip() or self._active_channel
            if channel and conn:
                reason = ""
                if " " in rest:
                    channel, _, reason = rest.partition(" ")
                await conn.send_raw(part_cmd(channel, reason or None))

        elif cmd == "/nick":
            new_nick = rest.strip()
            if new_nick and conn:
                await conn.send_raw(nick_cmd(new_nick))

        elif cmd == "/me":
            action_text = rest
            if action_text and self._active_channel and conn:
                await conn.send_raw(action(self._active_channel, action_text))
                chat.add_message(self._server_configs[self._active_server].nickname, f"* {action_text}")

        elif cmd == "/msg":
            target, _, message = rest.partition(" ")
            if target and message and conn:
                await conn.send_raw(privmsg(target, message))

        elif cmd == "/topic":
            if self._active_channel and conn:
                if rest:
                    await conn.send_raw(topic_cmd(self._active_channel, rest))
                else:
                    await conn.send_raw(topic_cmd(self._active_channel))

        elif cmd == "/kick":
            target, _, reason = rest.partition(" ")
            if self._active_channel and target and conn:
                await conn.send_raw(kick_cmd(self._active_channel, target, reason or None))

        elif cmd == "/mode":
            if self._active_channel and rest and conn:
                await conn.send_raw(mode_cmd(self._active_channel, rest))

        elif cmd == "/who":
            target = rest.strip() or self._active_channel
            if target and conn:
                await conn.send_raw(who(target))

        elif cmd == "/away":
            if conn:
                from ..irc.commands import away
                if rest:
                    await conn.send_raw(away(rest))
                else:
                    await conn.send_raw(away())

        elif cmd == "/raw":
            if rest and conn:
                await conn.send_raw(rest)

        elif cmd == "/copy":
            content = chat.copy_visible()
            try:
                import subprocess
                subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE).communicate(content.encode())
                chat.add_system("Copied last 50 lines to clipboard")
            except FileNotFoundError:
                try:
                    subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE).communicate(content.encode())
                    chat.add_system("Copied last 50 lines to clipboard")
                except FileNotFoundError:
                    chat.add_system("Clipboard tool not found — install wl-copy or xclip")

        elif cmd == "/open":
            import subprocess
            urls = chat.last_urls(5)
            if urls:
                for url in urls:
                    subprocess.Popen(["xdg-open", url])
                chat.add_system(f"Opened {len(urls)} link(s)")
            else:
                chat.add_system("No links found in recent messages")

        elif cmd == "/theme":
            if not rest.strip():
                themes = ", ".join(self._theme_names[:10])
                more = f" (+{len(self._theme_names) - 10} more)" if len(self._theme_names) > 10 else ""
                chat.add_system(f"Themes: {themes}{more}")
                chat.add_system(f"Current: {self._current_theme}")
            elif rest.strip() == "next":
                self._cycle_theme(1)
            elif rest.strip() == "prev":
                self._cycle_theme(-1)
            elif rest.strip().startswith("install "):
                url = rest.strip()[8:].strip()
                from .themes import install_theme_from_git
                name = install_theme_from_git(url)
                if name:
                    chat.add_system(f"Installed theme: {name}")
                    self._theme_names = register_all_themes(self)
                else:
                    chat.add_system("Failed to install theme")
            elif rest.strip() in self._theme_names:
                theme_name = rest.strip()
                self.apply_theme(theme_name)
                self.app_config.theme = theme_name
                chat.add_system(f"Theme: {theme_name}")
            else:
                chat.add_system(f"Unknown theme: {rest.strip()}")

        elif cmd == "/server":
            await self._handle_server_command(rest)

        else:
            chat.add_system(f"Unknown command: {cmd}")

    def _command_help(self, topic: str) -> str | None:
        """Return help text for a specific command."""
        help_topics = {
            "join": "Join a channel. Usage: /join #channel",
            "list": "Browse public channels. Usage: /list [filter]",
            "part": "Leave a channel. Usage: /part [#channel] [reason]",
            "msg": "Send a private message. Usage: /msg nick text",
            "me": "Send a CTCP action. Usage: /me waves hello",
            "topic": "View or set channel topic. Usage: /topic [new topic]",
            "kick": "Kick a user. Usage: /kick nick [reason]",
            "mode": "Set channel mode. Usage: /mode +o nick",
            "who": "Query WHO. Usage: /who [nick|channel]",
            "away": "Set or clear away. Usage: /away [reason]",
            "nick": "Change nickname. Usage: /nick newnick",
            "quit": "Disconnect and exit. Usage: /quit [reason]",
            "server": "Manage servers. Subcommands: list, add, remove",
            "server list": "List configured servers",
            "server add": "Add a server. Usage: /server add host:port nick [#chans]",
            "server remove": "Remove a server. Usage: /server remove host",
            "raw": "Send raw IRC. Usage: /raw PRIVMSG #chan :hello",
            "copy": "Copy last 50 lines to clipboard",
            "open": "Open URLs from recent messages in browser",
            "theme": "Switch theme. Usage: /theme [name|next|prev|install <url>]",
            "help": "Show this help or details for a command",
        }
        return help_topics.get(topic)

    async def _handle_server_command(self, rest: str) -> None:
        """Handle /server add/remove/list subcommands."""
        chat = self.query_one(ChatView)
        parts = rest.split(None, 2)
        sub = parts[0].lower() if parts else ""

        if sub == "list":
            for host, sc in self._server_configs.items():
                status = "connected" if host in self._connections else "not connected"
                chat.add_system(f"  {host} ({sc.nickname}) — {status}")

        elif sub == "add":
            # /server add host:port nick [channel1,channel2]
            args = parts[1:] if len(parts) > 1 else []
            if not args:
                chat.add_system("Usage: /server add host:port nick [#chan1,#chan2]")
                return
            host_port = args[0]
            nick = args[1] if len(args) > 1 else "vine-user"
            channels = []
            if len(args) > 2:
                channels = [c.strip() for c in args[2].split(",")]

            if ":" in host_port:
                host, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
            else:
                host = host_port
                port = 6697

            sc = ServerConfig(host=host, port=port, tls=True, nickname=nick, channels=channels, auto_connect=True)
            self._server_configs[host] = sc

            tree = self.query_one(ServerTree)
            tree.add_server(host, nick)

            await self._connect_server(host)
            chat.add_system(f"Added and connecting to {host}:{port}...")

        elif sub == "remove":
            host = parts[1] if len(parts) > 1 else ""
            if host in self._connections:
                await self._connections[host].close()
                del self._connections[host]
            self._server_configs.pop(host, None)
            self._channels.pop(host, None)
            chat.add_system(f"Removed {host}")

        else:
            chat.add_system("Usage: /server [list|add|remove]")

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

    def action_open_url(self, url: str) -> None:
        """Open a URL in the default browser. Called from [@click] links."""
        import subprocess
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            chat = self.query_one(ChatView)
            chat.add_system(f"Opened: {url[:80]}")
        except FileNotFoundError:
            chat = self.query_one(ChatView)
            chat.add_system("xdg-open not found")

    def action_open_last_url(self) -> None:
        """Open the most recent URL in chat."""
        chat = self.query_one(ChatView)
        urls = chat.last_urls(1)
        if urls:
            self.action_open_url(urls[0])
        else:
            chat.add_system("No URLs found")

    def action_show_tree(self) -> None:
        self.query_one(ServerTree).focus()

    def action_quit(self) -> None:
        for conn in self._connections.values():
            asyncio.create_task(conn.close())
        self.exit()
