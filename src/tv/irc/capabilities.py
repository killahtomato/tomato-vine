"""IRCv3 capability negotiation."""

from __future__ import annotations


class CapabilityNegotiator:
    """Track IRCv3 capability negotiation state."""

    def __init__(self, requested: list[str] | None = None) -> None:
        self.requested: list[str] = list(requested or [])
        self.enabled: set[str] = set()
        self.available: dict[str, str] = {}
        self._in_progress = False

    def has_requests(self) -> bool:
        return bool(self.requested)

    def handle_cap_new(self, caps: str) -> None:
        """Handle CAP NEW — server advertising capabilities."""
        for cap in caps.split():
            key, _, value = cap.partition("=")
            self.available[key] = value

    def handle_cap_ack(self, caps: str) -> None:
        """Handle CAP ACK — server enabling capabilities."""
        for cap in caps.split():
            if cap.startswith("-"):
                self.enabled.add(cap[1:])
            elif cap.startswith("~"):
                self.enabled.add(cap[1:])
            elif cap.startswith("="):
                self.enabled.add(cap[1:])
            else:
                key, _, _ = cap.partition("=")
                self.enabled.add(key)

    def handle_cap_nak(self, caps: str) -> None:
        """Handle CAP NAK — server rejecting capabilities."""
        pass

    def handle_cap_del(self, caps: str) -> None:
        """Handle CAP DEL — server removing capabilities."""
        for cap in caps.split():
            self.enabled.discard(cap)

    def is_enabled(self, cap: str) -> bool:
        return cap in self.enabled

    def supports_multi_prefix(self) -> bool:
        return "multi-prefix" in self.enabled

    def supports_account_notify(self) -> bool:
        return "account-notify" in self.enabled

    def supports_extended_join(self) -> bool:
        return "extended-join" in self.enabled

    def supports_away_notify(self) -> bool:
        return "away-notify" in self.enabled

    def supports_message_tags(self) -> bool:
        return "message-tags" in self.enabled

    def supports_labeled_response(self) -> bool:
        return "labeled-response" in self.enabled

    def supports_echomessage(self) -> bool:
        return "echo-message" in self.enabled


DEFAULT_CAPS = [
    "multi-prefix",
    "account-notify",
    "away-notify",
    "extended-join",
    "message-tags",
    "labeled-response",
    "sasl",
]
