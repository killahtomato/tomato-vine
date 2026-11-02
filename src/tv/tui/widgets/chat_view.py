"""Chat message display using per-message Static widgets with clickable links."""

from __future__ import annotations

import re

from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from ...irc.colors import irc_to_rich, strip_irc_formatting
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
    MessageRow .bubble {
        width: auto;
        max-width: 100%;
        height: auto;
        padding: 0 1;
        link-color: $accent;
        link-style: underline;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__(id=None)
        self._content = content

    def compose(self) -> None:
        yield Static(self._content, classes="bubble")


class MessagePane(VerticalScroll):
    """Scrollable chat area with clickable link support."""

    DEFAULT_CSS = """
    MessagePane {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="chat-view")
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

    def _add_message(self, content: str, plain_text: str) -> None:
        self._add_line(plain_text)
        self._track_urls(plain_text)
        row = MessageRow(content)
        self.mount(row)
        self.scroll_end(animate=False)

    def add_message(self, nick: str, text: str, outgoing: bool = False) -> None:
        rendered = _render_links(irc_to_rich(text))
        nick_display = self._highlight_nick(nick)
        if outgoing:
            content = f"[dim]> {nick_display}:[/dim] {rendered}"
            plain = f"> {nick}: {text}"
        else:
            content = f"[bold cyan]<{nick_display}>[/bold cyan] {rendered}"
            plain = f"<{nick}> {text}"
        self._add_message(content, plain)

    def add_system(self, text: str) -> None:
        rendered = _render_links(irc_to_rich(text))
        content = f"[dim italic]* {rendered}[/dim italic]"
        plain = text
        self._add_message(content, plain)

    def add_join(self, nick: str, channel: str) -> None:
        content = f"[dim]→ {nick} joined {channel}[/dim]"
        self._add_message(content, f"→ {nick} joined {channel}")

    def add_part(self, nick: str, channel: str) -> None:
        content = f"[dim]← {nick} left {channel}[/dim]"
        self._add_message(content, f"← {nick} left {channel}")

    def add_action(self, nick: str, text: str) -> None:
        rendered = _render_links(irc_to_rich(text))
        content = f"[italic magenta]* {nick} {rendered}[/italic magenta]"
        self._add_message(content, f"* {nick} {text}")

    def copy_visible(self) -> str:
        lines = self._buffer[-50:]
        return "\n".join(lines)

    def last_urls(self, count: int = 5) -> list[str]:
        return self._url_buffer[-count:]

    def set_url_click_handler(self, fn) -> None:
        pass
