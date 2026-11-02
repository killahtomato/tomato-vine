"""Textual TUI widgets for tomato-vine."""

from __future__ import annotations

from textual.widgets import Static, Input, ListView, ListItem, Label, RichLog

from ...irc.colors import irc_to_rich, strip_irc_formatting
from ...irc.links import extract_urls, is_image_url, is_image_host_url, truncate_url
from .palette import CommandPalette, DEFAULT_ACTIONS
from .sidebar import ServerTree


class StatusBar(Static):
    """Top status bar — server, channel, nick, connection state."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="status-bar")

    def update_status(
        self,
        server: str = "",
        channel: str = "",
        nick: str = "",
        status: str = "disconnected",
    ) -> None:
        parts: list[str] = []
        if status:
            parts.append(f"● {status}")
        if server:
            parts.append(server)
        if channel:
            parts.append(channel)
        if nick:
            parts.append(f"nick: {nick}")
        self.update(" │ ".join(parts) if parts else "tomato-vine")


class ChatView(RichLog):
    """Scrollable message display area."""

    DEFAULT_CSS = """
    ChatView {
        height: 1fr;
        background: $surface;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="chat-view", markup=True, auto_scroll=True)
        self._buffer: list[str] = []
        self._url_buffer: list[str] = []
        self._nick_color: str | None = None
        self._my_nick: str | None = None

    def set_nick_highlight(self, nick: str, color: str | None) -> None:
        self._my_nick = nick
        self._nick_color = color

    def _highlight_nick(self, text: str) -> str:
        if not self._nick_color or not self._my_nick:
            return text
        import re
        pattern = re.compile(r'\b' + re.escape(self._my_nick) + r'\b')
        return pattern.sub(f'[{self._nick_color}]\\g<0>[/{self._nick_color}]', text)

    def _add_line(self, text: str) -> None:
        from ...irc.colors import strip_irc_formatting
        self._buffer.append(strip_irc_formatting(text))
        if len(self._buffer) > 500:
            self._buffer = self._buffer[-500:]

    def copy_visible(self) -> str:
        """Return the last 50 plain-text messages for copying."""
        lines = self._buffer[-50:]
        return "\n".join(lines)

    def _render_links(self, text: str) -> str:
        """Detect URLs and render them as clickable links."""
        urls = extract_urls(text)
        if not urls:
            return text

        result = text
        for url in urls:
            self._url_buffer.append(url)
            if is_image_url(url) or is_image_host_url(url):
                display = f"[link={url}][bold magenta]🖼 {truncate_url(url)}[/bold magenta][/link]"
            else:
                display = f"[link={url}]{url}[/link]"
            result = result.replace(url, display)
        return result

    def last_urls(self, count: int = 5) -> list[str]:
        """Return the last N image URLs seen."""
        return self._url_buffer[-count:]

    def add_message(self, nick: str, text: str, outgoing: bool = False) -> None:
        rendered = self._render_links(irc_to_rich(text))
        nick_display = self._highlight_nick(nick)
        if outgoing:
            self.write(f"[dim]> {nick_display}:[/dim] {rendered}")
            self._add_line(f"> {nick}: {strip_irc_formatting(text)}")
        else:
            self.write(f"[bold cyan]<{nick_display}>[/bold cyan] {rendered}")
            self._add_line(f"<{nick}> {strip_irc_formatting(text)}")

    def add_system(self, text: str) -> None:
        rendered = self._render_links(irc_to_rich(text))
        self.write(f"[dim italic]* {rendered}[/dim italic]")
        self._add_line(f"* {strip_irc_formatting(text)}")

    def add_join(self, nick: str, channel: str) -> None:
        self.write(f"[dim]→ {nick} joined {channel}[/dim]")
        self._add_line(f"→ {nick} joined {channel}")

    def add_part(self, nick: str, channel: str) -> None:
        self.write(f"[dim]← {nick} left {channel}[/dim]")
        self._add_line(f"← {nick} left {channel}")

    def add_action(self, nick: str, text: str) -> None:
        rendered = irc_to_rich(text)
        self.write(f"[italic magenta]* {nick} {rendered}[/italic magenta]")
        self._add_line(f"* {nick} {text}")


class NickList(ListView):
    """Channel user list displayed in sidebar."""

    DEFAULT_CSS = """
    NickList {
        height: 1fr;
        width: 22;
        background: $panel;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="nick-list")

    def update_nicks(self, nicks: list[str]) -> None:
        self.clear()
        for nick in sorted(nicks):
            self.append(ListItem(Label(nick)))


class VineInput(Input):
    """Message input box with history ring buffer."""

    DEFAULT_CSS = """
    VineInput {
        height: 3;
        background: $panel;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="vine-input", placeholder="type a message...")
        self._history: list[str] = []
        self._history_pos = 0

    def add_to_history(self, text: str) -> None:
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_pos = len(self._history)

    def history_up(self) -> None:
        if self._history and self._history_pos > 0:
            self._history_pos -= 1
            self.value = self._history[self._history_pos]

    def history_down(self) -> None:
        if self._history and self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self.value = self._history[self._history_pos]
        else:
            self._history_pos = len(self._history)
            self.value = ""
