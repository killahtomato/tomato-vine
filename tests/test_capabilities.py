"""Tests for IRCv3 capability negotiation."""

from __future__ import annotations

import pytest

from tv.irc.capabilities import CapabilityNegotiator
from tv.irc.commands import (
    build_sasl_plain_blob,
    cap_end,
    cap_list,
    cap_req,
    authenticate,
    ctcp,
    action,
    who,
    names,
    whois,
    respond_ctcp_version,
    respond_ctcp_ping,
    respond_ctcp_time,
)
from tv.irc.parser import parse_line


class TestCapabilityNegotiator:
    def test_empty(self):
        nego = CapabilityNegotiator()
        assert not nego.has_requests()

    def test_with_requests(self):
        nego = CapabilityNegotiator(["multi-prefix", "account-notify"])
        assert nego.has_requests()
        assert nego.requested == ["multi-prefix", "account-notify"]

    def test_ack_enables(self):
        nego = CapabilityNegotiator(["multi-prefix"])
        nego.handle_cap_ack("multi-prefix")
        assert nego.is_enabled("multi-prefix")
        assert nego.supports_multi_prefix()

    def test_ack_with_value(self):
        nego = CapabilityNegotiator()
        nego.handle_cap_ack("accountname=foo")
        assert nego.is_enabled("accountname")

    def test_del_removes(self):
        nego = CapabilityNegotiator(["multi-prefix"])
        nego.handle_cap_ack("multi-prefix")
        nego.handle_cap_del("multi-prefix")
        assert not nego.is_enabled("multi-prefix")

    def test_multi_prefix_not_enabled_by_default(self):
        nego = CapabilityNegotiator()
        assert not nego.supports_multi_prefix()

    def test_account_notify(self):
        nego = CapabilityNegotiator()
        nego.handle_cap_ack("account-notify")
        assert nego.supports_account_notify()

    def test_extended_join(self):
        nego = CapabilityNegotiator()
        nego.handle_cap_ack("extended-join")
        assert nego.supports_extended_join()

    def test_away_notify(self):
        nego = CapabilityNegotiator()
        nego.handle_cap_ack("away-notify")
        assert nego.supports_away_notify()

    def test_message_tags(self):
        nego = CapabilityNegotiator()
        nego.handle_cap_ack("message-tags")
        assert nego.supports_message_tags()


class TestSASL:
    def test_plain_blob(self):
        blob = build_sasl_plain_blob("user", "pass")
        import base64
        decoded = base64.b64encode(b"user\x00user\x00pass").decode()
        assert blob == decoded

    def test_authenticate_command(self):
        assert authenticate("PLAIN") == "AUTHENTICATE PLAIN"
        assert authenticate("+") == "AUTHENTICATE +"

    def test_sasl_plain_blob_decode(self):
        import base64
        blob = build_sasl_plain_blob("alice", "secret")
        decoded = base64.b64decode(blob).decode()
        assert decoded == "alice\x00alice\x00secret"


class TestCAPCommands:
    def test_cap_list(self):
        assert cap_list() == "CAP LIST"

    def test_cap_req(self):
        assert cap_req("multi-prefix") == "CAP REQ :multi-prefix"

    def test_cap_req_multiple(self):
        assert cap_req("multi-prefix account-notify") == "CAP REQ :multi-prefix account-notify"

    def test_cap_end(self):
        assert cap_end() == "CAP END"


class TestCTCPResponders:
    def test_version(self):
        line = respond_ctcp_version("nick", "tv 1.0")
        assert "VERSION" in line
        assert "nick" in line

    def test_ping(self):
        line = respond_ctcp_ping("nick", "12345")
        assert "PING" in line

    def test_time(self):
        line = respond_ctcp_time("nick", "Mon Jan 1 00:00:00 2026")
        assert "TIME" in line


class TestCommandBuilders:
    def test_action(self):
        line = action("#chan", "waves")
        assert "\x01ACTION waves\x01" in line

    def test_ctcp(self):
        line = ctcp("nick", "VERSION")
        assert "\x01VERSION\x01" in line

    def test_who(self):
        assert who("#chan") == "WHO #chan"

    def test_names(self):
        assert names("#chan") == "NAMES #chan"

    def test_whois(self):
        assert whois("nick") == "WHOIS nick"

    def test_whois_with_server(self):
        assert whois("nick", "irc.server") == "WHOIS irc.server nick"


class TestNamesReplyParsing:
    def test_353(self):
        msg = parse_line(":server 353 vine = #chan :@alice +bob vine")
        assert msg.command == "353"
        assert msg.params[2] == "#chan"
        nicks = msg.trailing.split()
        assert "@alice" in nicks
        assert "+bob" in nicks
        assert "vine" in nicks

    def test_366(self):
        msg = parse_line(":server 366 vine #chan :End of /NAMES")
        assert msg.command == "366"
        assert msg.params[1] == "#chan"


class TestModeParsing:
    def test_channel_mode(self):
        msg = parse_line(":server MODE #chan +o alice")
        assert msg.command == "MODE"
        assert msg.target == "#chan"

    def test_user_mode(self):
        msg = parse_line(":nick MODE nick +i")
        assert msg.command == "MODE"


class TestQuitParsing:
    def test_quit(self):
        msg = parse_line(":alice QUIT :Gone to lunch")
        assert msg.command == "QUIT"
        assert msg.nick == "alice"
        assert msg.trailing == "Gone to lunch"


class TestKickParsing:
    def test_kick(self):
        msg = parse_line(":alice KICK #chan bob :Being silly")
        assert msg.command == "KICK"
        assert msg.params == ["#chan", "bob"]
        assert msg.trailing == "Being silly"


class TestTopicParsing:
    def test_topic_change(self):
        msg = parse_line(":alice TOPIC #chan :New topic here")
        assert msg.command == "TOPIC"
        assert msg.trailing == "New topic here"
