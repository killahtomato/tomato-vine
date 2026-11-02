"""Textual TUI widgets for tomato-vine."""

from __future__ import annotations

from textual.widgets import Static, Input, ListView, ListItem, Label

from ...irc.colors import strip_irc_formatting
from .chat_view import MessagePane
from .palette import CommandPalette, DEFAULT_ACTIONS
from .sidebar import ServerTree

ChatView = MessagePane


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
