"""IRC message parser — RFC 1459 + IRCv3 message tags."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# IRC message tags escaping per IRCv3 spec
TAG_ESCAPE = {
    "\\:": ";",
    "\\s": " ",
    "\\\\": "\\",
    "\\r": "\r",
    "\\n": "\n",
}
TAG_UNESCAPE = {v: k for k, v in TAG_ESCAPE.items()}

# Regex for a full IRC line: @tags :prefix COMMAND params :trailing
# Each part is optional except COMMAND.
_LINE_RE = re.compile(
    r"^(?P<tags>@[^ ]+ )?"
    r"(?P<prefix>:[^ ]+ )?"
    r"(?P<command>\S+)"
    r"(?P<params>( [^:]\S+)*)"
    r"(?P<trailing> :.+)?$"
)

_CTCP_RE = re.compile(r"\x01(.+?)\x01")


def _unescape_tag(value: str) -> str:
    """Unescape an IRCv3 tag value."""
    result: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            pair = value[i : i + 2]
            result.append(TAG_ESCAPE.get(pair, pair[1]))
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def _escape_tag(value: str) -> str:
    """Escape a value for IRCv3 message tags."""
    result: list[str] = []
    for ch in value:
        result.append(TAG_UNESCAPE.get(ch, ch))
    return "".join(result)


def parse_tags(tag_str: str) -> dict[str, str]:
    """Parse IRCv3 message tags (without leading @) into a dict.

    Tag values are unescaped. Tags without values map to "".
    """
    if not tag_str:
        return {}
    tags: dict[str, str] = {}
    for raw in tag_str.split(";"):
        if not raw:
            continue
        key, _, value = raw.partition("=")
        tags[key] = _unescape_tag(value) if value else ""
    return tags


def encode_tags(tags: dict[str, str]) -> str:
    """Encode a dict of IRCv3 message tags into the wire format (without @)."""
    parts: list[str] = []
    for key, value in tags.items():
        if value:
            parts.append(f"{key}={_escape_tag(value)}")
        else:
            parts.append(key)
    return ";".join(parts)


@dataclass(frozen=True)
class IRCMessage:
    """A parsed IRC protocol message."""

    command: str
    prefix: str = ""
    params: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    raw: str = ""
    trailing: str = ""

    @property
    def nick(self) -> str:
        """Extract nick from prefix (nick!user@host)."""
        if "!" in self.prefix:
            return self.prefix.split("!", 1)[0].lstrip(":")
        return self.prefix.lstrip(":")

    @property
    def userhost(self) -> str:
        """Extract user@host from prefix."""
        if "@" in self.prefix:
            return self.prefix.split("@", 1)[1]
        return ""

    @property
    def is_ctcp(self) -> bool:
        """Check if trailing content is a CTCP message."""
        return bool(_CTCP_RE.fullmatch(self.trailing)) if self.trailing else False

    @property
    def ctcp_command(self) -> str | None:
        """Extract CTCP command name if this is a CTCP message."""
        if not self.trailing:
            return None
        m = _CTCP_RE.fullmatch(self.trailing)
        if m:
            return m.group(1).split(" ", 1)[0].upper()
        return None

    @property
    def ctcp_params(self) -> str | None:
        """Extract CTCP parameters if this is a CTCP message."""
        if not self.trailing:
            return None
        m = _CTCP_RE.fullmatch(self.trailing)
        if m:
            return m.group(1).split(" ", 1)[1] if " " in m.group(1) else ""
        return None

    @property
    def is_numeric(self) -> bool:
        """Check if command is a numeric reply (3 digits)."""
        return len(self.command) == 3 and self.command.isdigit()

    @property
    def target(self) -> str:
        """First param is typically the target (channel or nick)."""
        return self.params[0] if self.params else ""

    def format(self) -> str:
        """Reconstruct the message for display/logging."""
        parts: list[str] = []
        if self.tags:
            parts.append(f"@{encode_tags(self.tags)}")
        if self.prefix:
            parts.append(f":{self.prefix}" if not self.prefix.startswith(":") else self.prefix)
        parts.append(self.command)
        if self.params:
            parts.extend(self.params)
        if self.trailing:
            parts.append(f":{self.trailing}")
        return " ".join(parts)

    def __str__(self) -> str:
        return self.format()


def parse_line(line: str) -> IRCMessage:
    """Parse a single IRC wire-format line into an IRCMessage.

    Handles:
    - IRCv3 message tags (@key=value;...)
    - Prefix (:nick!user@host)
    - Command (PRIVMSG, JOIN, 001, etc.)
    - Middle params and trailing param
    - CTCP (\x01ACTION ...\x01)

    Raises ValueError if the line is malformed.
    """
    line = line.rstrip("\r\n")
    if not line:
        raise ValueError("empty line")

    m = _LINE_RE.match(line)
    if not m:
        raise ValueError(f"malformed IRC line: {line!r}")

    tags_str = m.group("tags")
    prefix = m.group("prefix")
    command = m.group("command")
    params_str = m.group("params") or ""
    trailing = m.group("trailing") or ""

    tags = parse_tags(tags_str[1:].strip()) if tags_str else {}
    prefix = prefix[1:].strip() if prefix else ""

    params: list[str] = []
    if params_str:
        raw_params = params_str.strip().split(" ")
        params = raw_params

    if trailing:
        trailing = trailing[2:] if trailing.startswith(" :") else trailing[1:]

    return IRCMessage(
        command=command.upper() if not command.isdigit() else command,
        prefix=prefix,
        params=params,
        tags=tags,
        raw=line,
        trailing=trailing,
    )


def parse_lines(data: str) -> list[IRCMessage]:
    """Parse a buffer of potentially multiple IRC lines."""
    messages: list[IRCMessage] = []
    for line in data.split("\r\n"):
        line = line.strip()
        if line:
            try:
                messages.append(parse_line(line))
            except ValueError:
                continue
    return messages


def build_message(
    command: str,
    params: list[str] | None = None,
    trailing: str | None = None,
    tags: dict[str, str] | None = None,
    prefix: str | None = None,
) -> str:
    """Build an IRC wire-format message."""
    parts: list[str] = []

    if tags:
        parts.append(f"@{encode_tags(tags)}")

    if prefix:
        parts.append(f":{prefix}")

    parts.append(command)

    if params:
        for p in params:
            if " " in p and p != params[-1]:
                raise ValueError(f"middle param with space: {p!r}")
            parts.append(p)

    if trailing is not None:
        parts.append(f":{trailing}")
    elif params:
        last = params[-1]
        if " " in last or last.startswith(":"):
            parts[-1] = f":{last}"

    return " ".join(parts)
