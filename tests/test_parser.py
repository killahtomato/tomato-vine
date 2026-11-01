"""Tests for the IRC message parser."""

from __future__ import annotations

import pytest

from tv.irc.parser import (
    IRCMessage,
    build_message,
    parse_line,
    parse_lines,
    parse_tags,
    encode_tags,
)


class TestParseTags:
    def test_empty(self):
        assert parse_tags("") == {}

    def test_simple(self):
        assert parse_tags("a=b;c=d") == {"a": "b", "c": "d"}

    def test_no_value(self):
        assert parse_tags("a;b=c") == {"a": "", "b": "c"}

    def test_escaped_semicolon(self):
        assert parse_tags("a=hello\\:world") == {"a": "hello;world"}

    def test_escaped_space(self):
        assert parse_tags("a=hello\\sworld") == {"a": "hello world"}

    def test_escaped_backslash(self):
        assert parse_tags("a=hello\\\\world") == {"a": "hello\\world"}

    def test_escaped_cr_lf(self):
        assert parse_tags("a=hello\\r\\nworld") == {"a": "hello\r\nworld"}


class TestEncodeTags:
    def test_roundtrip(self):
        tags = {"a": "b", "c": "d;e", "f": ""}
        encoded = encode_tags(tags)
        assert parse_tags(encoded) == {"a": "b", "c": "d;e", "f": ""}


class TestParseLine:
    def test_privmsg(self):
        msg = parse_line(":nick!user@host PRIVMSG #channel :hello world")
        assert msg.command == "PRIVMSG"
        assert msg.nick == "nick"
        assert msg.userhost == "host"
        assert msg.params == ["#channel"]
        assert msg.trailing == "hello world"

    def test_join(self):
        msg = parse_line(":nick!user@host JOIN #channel")
        assert msg.command == "JOIN"
        assert msg.nick == "nick"
        assert msg.params == ["#channel"]
        assert msg.trailing == ""

    def test_numeric(self):
        msg = parse_line(":server 001 nick :Welcome to IRC")
        assert msg.command == "001"
        assert msg.is_numeric
        assert msg.trailing == "Welcome to IRC"

    def test_ping(self):
        msg = parse_line("PING :1234567890")
        assert msg.command == "PING"
        assert msg.prefix == ""
        assert msg.trailing == "1234567890"

    def test_tags(self):
        msg = parse_line("@time=2026-01-01T00:00:00.000Z :nick!u@h PRIVMSG #c :hi")
        assert msg.tags == {"time": "2026-01-01T00:00:00.000Z"}
        assert msg.command == "PRIVMSG"
        assert msg.trailing == "hi"

    def test_ctcp_action(self):
        msg = parse_line(":nick!u@h PRIVMSG #c :\x01ACTION waves\x01")
        assert msg.is_ctcp
        assert msg.ctcp_command == "ACTION"
        assert msg.ctcp_params == "waves"

    def test_empty_line_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_line("")

    def test_empty_only_whitespace(self):
        with pytest.raises(ValueError, match="empty"):
            parse_line("\r\n")


class TestParseLines:
    def test_multiple(self):
        lines = ":a JOIN #c\r\n:b PRIVMSG #c :hi\r\nPING :token"
        msgs = parse_lines(lines)
        assert len(msgs) == 3
        assert msgs[0].command == "JOIN"
        assert msgs[1].command == "PRIVMSG"
        assert msgs[2].command == "PING"


class TestBuildMessage:
    def test_simple(self):
        line = build_message("PRIVMSG", params=["#channel"], trailing="hello")
        assert line == "PRIVMSG #channel :hello"

    def test_with_tags(self):
        line = build_message(
            "PRIVMSG",
            params=["#c"],
            trailing="hi",
            tags={"time": "2026"},
        )
        assert line == "@time=2026 PRIVMSG #c :hi"

    def test_pong(self):
        assert build_message("PONG", trailing="token") == "PONG :token"

    def test_no_trailing(self):
        assert build_message("JOIN", params=["#c"]) == "JOIN #c"


class TestIRCMessage:
    def test_nick_from_prefix(self):
        msg = IRCMessage(command="PRIVMSG", prefix="nick!user@host")
        assert msg.nick == "nick"
        assert msg.userhost == "host"

    def test_nick_server_prefix(self):
        msg = IRCMessage(command="001", prefix="irc.server.net")
        assert msg.nick == "irc.server.net"

    def test_is_numeric_true(self):
        msg = IRCMessage(command="353")
        assert msg.is_numeric

    def test_is_numeric_false(self):
        msg = IRCMessage(command="PRIVMSG")
        assert not msg.is_numeric

    def test_format_roundtrip(self):
        original = ":nick!u@h PRIVMSG #chan :hello there"
        msg = parse_line(original)
        assert str(msg) == original
