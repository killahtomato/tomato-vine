"""Tests for IRC color code rendering."""

from __future__ import annotations

import pytest

from tv.irc.colors import irc_to_rich, strip_irc_formatting


class TestIrcToRich:
    def test_plain_text(self):
        assert irc_to_rich("hello world") == "hello world"

    def test_color_code(self):
        result = irc_to_rich("\x0304red text")
        assert "red text" in result
        assert "[bold" in result

    def test_color_with_bg(self):
        result = irc_to_rich("\x0304,00white on red")
        assert "white on red" in result
        assert "on" in result

    def test_bare_color_reset(self):
        result = irc_to_rich("\x0304red\x03 normal")
        assert "red" in result
        assert "normal" in result

    def test_bold(self):
        result = irc_to_rich("\x02bold text\x02")
        assert "bold text" in result
        assert "[bold]" in result

    def test_italic(self):
        result = irc_to_rich("\x1ditalic text\x1d")
        assert "italic text" in result
        assert "[italic]" in result

    def test_underline(self):
        result = irc_to_rich("\x1funderline text\x1f")
        assert "underline text" in result
        assert "[underline]" in result

    def test_strikethrough(self):
        result = irc_to_rich("\x1estrike text\x1e")
        assert "strike text" in result
        assert "[strike]" in result

    def test_reset(self):
        result = irc_to_rich("\x02bold\x0f normal")
        assert "bold" in result
        assert "normal" in result

    def test_bracket_escape(self):
        result = irc_to_rich("hello [world]")
        assert "\\[" in result

    def test_multiple_formats(self):
        result = irc_to_rich("\x02\x0304bold red\x02")
        assert "bold red" in result


class TestStripFormatting:
    def test_plain(self):
        assert strip_irc_formatting("hello") == "hello"

    def test_strip_colors(self):
        assert strip_irc_formatting("\x0304red\x03 normal") == "red normal"

    def test_strip_bold(self):
        assert strip_irc_formatting("\x02bold\x02") == "bold"

    def test_strip_italic(self):
        assert strip_irc_formatting("\x1ditalic\x1d") == "italic"

    def test_strip_underline(self):
        assert strip_irc_formatting("\x1funderline\x1f") == "underline"
