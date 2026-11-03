"""Chat message display using per-message Static widgets with clickable links."""

from __future__ import annotations

import re

from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from ...irc.colors import strip_irc_formatting
from ...irc.links import extract_urls, is_image_url, is_image_host_url, truncate_url


_URL_RE = re.compile(r"(https?://[^\s)]+|www\.[^\s)]+)")


def _render_links(text: str) -> str:
    """Convert URLs in text to Textual [@click] action markup."""
    parts: list[str] = []
    last = 0
    for match in _URL_RE.finditer(text):
        if match.start() > last:
            parts.append(_escape(text[last:match.start()]))
        url = match.group(0)
        target = url if not url.startswith("www.") else "https://" + url
        display = truncate_url(url, 50)
        parts.append(f"[@click=app.open_url('{target}')]{display}[/]")
        last = match.end()
    if last < len(text):
        parts.append(_escape(text[last:]))
    return "".join(parts) if parts else _escape(text)


def _escape(text: str) -> str:
    """Escape Textual markup characters."""
    return text.replace("[", "\\[")


class MessageRow(Horizontal):
    """A single message row with clickable links."""

    DEFAULT_CSS = """
    MessageRow {
        height: auto;
        width: 100%;
    }
    MessageRow Static {
        width: auto;
        height: auto;
        padding: 0 1;
    }
    MessageRow .message {
        width: 100%;
        link-color: $accent;
        link-style: underline;
    }
    """

    def __init__(self, nick_style: str, nick: str, message: str, outgoing: bool = False) -> None:
        super().__init__(id=None)
        self._nick_style = nick_style
        self._nick = nick
        self._message = message
        self._outgoing = outgoing

    def compose(self) -> None:
        if self._outgoing:
            yield Static(f"[dim]> {self._nick}:[/dim]", classes="nick")
        else:
            yield Static(f"[{self._nick_style}]<{self._nick}>[/{self._nick_style}]", classes="nick")
        yield Static(f" {self._message}", classes="message")


class MessagePane(VerticalScroll):
    """Scrollable chat area with clickable link support."""

    DEFAULT_CSS = """
    MessagePane {
        height: 1fr;
        padding: 0 1;
        &:focus {
            background: $surface;
        }
    }
    """

    def __init__(self) -> None:
        super().__init__(id="chat-view")
        self._buffer: list[str] = []
        self._url_buffer: list[str] = []
        self._pending_mounts: list[MessageRow] = []
        self._msg_count: int = 0
        self._nick_color: str | None = None
        self._my_nick: str | None = None

    def _trim_old_widgets(self, max_widgets: int = 100) -> None:
        while len(self.children) > max_widgets:
            self.children[0].remove()

    def on_mount(self) -> None:
        pass

    def set_nick_highlight(self, nick: str, color: str | None) -> None:
        self._my_nick = nick
        self._nick_color = color

    def _highlight_nick(self, text: str) -> str:
        if not self._nick_color or not self._my_nick:
            return text
        pattern = re.compile(r"\b" + re.escape(self._my_nick) + r"\b")
        return pattern.sub(f"[{self._nick_color}]\\g<0>[/{self._nick_color}]", text)

    def _add_line(self, text: str) -> None:
        plain = strip_irc_formatting(text)
        self._buffer.append(plain)
        if len(self._buffer) > 500:
            self._buffer = self._buffer[-500:]
        try:
            from ...log import chat_log
            chat_log().info(plain)
        except Exception:
            pass

    def _track_urls(self, text: str) -> None:
        for url in extract_urls(text):
            self._url_buffer.append(url)

    def _add_message(self, plain_text: str, row: MessageRow) -> None:
        self._add_line(plain_text)
        self._track_urls(plain_text)
        self.mount(row)
        self._msg_count += 1
        if self._msg_count % 500 == 0:
            self._trim_old_widgets()

    def add_message(self, nick: str, text: str, outgoing: bool = False) -> None:
        clean = strip_irc_formatting(text)
        rendered = _render_links(clean)
        nick_display = self._highlight_nick(nick)
        if outgoing:
            plain = f"> {nick}: {clean}"
            row = MessageRow("dim", f"> {nick_display}:", rendered)
        else:
            plain = f"<{nick}> {clean}"
            nick_style = f"bold {self._nick_color or 'cyan'}"
            row = MessageRow(nick_style, f"<{nick_display}>", rendered)
        self._add_message(plain, row)

    def add_system(self, text: str) -> None:
        clean = strip_irc_formatting(text)
        rendered = _render_links(clean)
        row = MessageRow("dim italic", "*", rendered)
        self._add_message(clean, row)

    def add_join(self, nick: str, channel: str) -> None:
        row = MessageRow("dim", "→", f"{nick} joined {channel}")
        self._add_message(f"→ {nick} joined {channel}", row)

    def add_part(self, nick: str, channel: str) -> None:
        row = MessageRow("dim", "←", f"{nick} left {channel}")
        self._add_message(f"← {nick} left {channel}", row)

    def add_action(self, nick: str, text: str) -> None:
        clean = strip_irc_formatting(text)
        rendered = _render_links(clean)
        row = MessageRow("italic magenta", f"* {nick}", rendered)
        self._add_message(f"* {nick} {clean}", row)

    def copy_visible(self) -> str:
        lines = self._buffer[-50:]
        return "\n".join(lines)

    def last_urls(self, count: int = 5) -> list[str]:
        return self._url_buffer[-count:]


