"""TreeView sidebar for server/channel navigation."""

from __future__ import annotations

from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class ServerTree(Tree):
    """Hierarchical tree showing servers, channels, and DMs."""

    DEFAULT_CSS = """
    ServerTree {
        height: 1fr;
        width: 24;
        background: $panel;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("servers", id="server-tree")
        self._servers: dict[str, TreeNode] = {}
        self._channels: dict[str, TreeNode] = {}
        self._dms: dict[str, TreeNode] = {}

    def add_server(self, host: str, nickname: str = "") -> TreeNode:
        """Add or update a server node."""
        label = f"● {host}" if not nickname else f"● {nickname}@{host}"
        if host in self._servers:
            node = self._servers[host]
            node.label = label
            return node
        node = self.root.add(label, expand=True)
        self._servers[host] = node
        return node

    def set_server_status(self, host: str, status: str) -> None:
        """Update server connection status indicator."""
        if host not in self._servers:
            return
        node = self._servers[host]
        label = str(node.label)
        if status == "connected":
            node.label = label.replace("○ ", "● ").replace("◌ ", "● ")
        elif status == "disconnected":
            node.label = label.replace("● ", "○ ").replace("◌ ", "○ ")
        elif status == "connecting...":
            node.label = label.replace("● ", "◌ ").replace("○ ", "◌ ")
        self.refresh()

    def add_channel(self, host: str, channel: str) -> TreeNode:
        """Add a channel under a server."""
        if channel in self._channels:
            return self._channels[channel]
        server_node = self._servers.get(host)
        if not server_node:
            self.add_server(host)
            server_node = self._servers[host]
        node = server_node.add(f"  {channel}", expand=False)
        self._channels[channel] = node
        return node

    def remove_channel(self, host: str, channel: str) -> None:
        """Remove a channel from the tree."""
        if channel in self._channels:
            node = self._channels.pop(channel)
            node.remove()

    def add_dm(self, host: str, nick: str) -> TreeNode:
        """Add a DM conversation under a server."""
        key = f"dm:{nick}"
        if key in self._dms:
            return self._dms[key]
        server_node = self._servers.get(host)
        if not server_node:
            self.add_server(host)
            server_node = self._servers[host]
        node = server_node.add(f"  💬 {nick}", expand=False)
        self._dms[key] = node
        return node

    def remove_dm(self, nick: str) -> None:
        """Remove a DM node."""
        key = f"dm:{nick}"
        if key in self._dms:
            node = self._dms.pop(key)
            node.remove()

    def mark_active(self, channel: str | None) -> None:
        """Highlight the active channel."""
        for ch, node in self._channels.items():
            if ch == channel:
                node.label = f"▸ {ch}"
            elif not str(node.label).startswith("  💬"):
                node.label = f"  {ch}"
        self.refresh()

    def mark_unread(self, channel: str) -> None:
        """Mark a channel as having unread messages."""
        if channel in self._channels:
            node = self._channels[channel]
            label = str(node.label).rstrip(" *")
            if "*" not in str(node.label):
                node.label = f"{label} *"
            self.refresh()
