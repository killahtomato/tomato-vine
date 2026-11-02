"""Command palette widget for the sidebar."""

from __future__ import annotations

from dataclasses import dataclass

from textual.widgets import Static


@dataclass
class PaletteAction:
    label: str
    command: str


DEFAULT_ACTIONS = [
    PaletteAction("List", "/list"),
    PaletteAction("Join", "/join "),
    PaletteAction("Who", "/who"),
    PaletteAction("Copy", "/copy"),
    PaletteAction("Open", "/open"),
    PaletteAction("Part", "/part"),
    PaletteAction("Away", "/away"),
    PaletteAction("Theme", "/theme next"),
    PaletteAction("Quit", "/quit"),
]


class CommandPalette(Static):
    """Sidebar command palette — clickable action buttons."""

    DEFAULT_CSS = """
    CommandPalette {
        height: 1fr;
        background: $panel;
        padding: 0;
        overflow-y: auto;
    }
    """

    def __init__(self, actions: list[PaletteAction] | None = None) -> None:
        super().__init__(id="command-palette")
        self._actions = actions or DEFAULT_ACTIONS
        self._selected = 0
        self._on_action = None

    def render(self) -> str:
        lines: list[str] = []
        for i, action in enumerate(self._actions):
            if i == self._selected:
                lines.append(f"[bold reverse] {action.label} [/bold reverse]")
            else:
                lines.append(f"[dim] {action.label} [/dim]")
        return "\n".join(lines) if lines else "[dim]No actions[/dim]"

    def _refresh(self) -> None:
        self.refresh()

    def on_key(self, event) -> None:
        if event.key == "up":
            self._selected = max(0, self._selected - 1)
            self._refresh()
            event.stop()
        elif event.key == "down":
            self._selected = min(len(self._actions) - 1, self._selected + 1)
            self._refresh()
            event.stop()
        elif event.key == "enter":
            if self._on_action and self._selected < len(self._actions):
                import asyncio
                asyncio.create_task(self._on_action(self._actions[self._selected].command))
            event.stop()

    def set_callback(self, fn) -> None:
        self._on_action = fn

    def on_click(self, event) -> None:
        y_offset = event.offset.y - self.offset.y
        row = int(y_offset)
        if 0 <= row < len(self._actions):
            self._selected = row
            self._refresh()
            if self._on_action:
                import asyncio
                asyncio.create_task(self._on_action(self._actions[row].command))
