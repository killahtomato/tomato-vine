"""Tests for IRC link/image detection."""

from __future__ import annotations

import pytest

from tv.irc.links import (
    extract_urls,
    is_image_url,
    is_image_host_url,
    extract_domain,
    truncate_url,
)


class TestExtractUrls:
    def test_simple(self):
        assert extract_urls("check https://example.com") == ["https://example.com"]

    def test_multiple(self):
        urls = extract_urls("a https://a.com and http://b.com")
        assert len(urls) == 2

    def test_none(self):
        assert extract_urls("no urls here") == []

    def test_with_path(self):
        urls = extract_urls("see https://imgur.com/gallery/abc123")
        assert "https://imgur.com/gallery/abc123" in urls

    def test_trailing_punctuation(self):
        urls = extract_urls("check this https://example.com.")
        assert urls[0] == "https://example.com"


class TestIsImageUrl:
    def test_png(self):
        assert is_image_url("https://example.com/photo.png")

    def test_jpg(self):
        assert is_image_url("https://i.redd.it/abc.jpg")

    def test_gif(self):
        assert is_image_url("https://media.tenor.com/xyz.gif")

    def test_imgur(self):
        assert is_image_url("https://imgur.com/abc123")

    def test_catbox(self):
        assert is_image_url("https://files.catbox.moe/abc.png")

    def test_not_image(self):
        assert not is_image_url("https://google.com/search")

    def test_plain_page(self):
        assert not is_image_url("https://example.com/about")


class TestIsImageHostUrl:
    def test_imgur(self):
        assert is_image_host_url("https://imgur.com/gallery/abc")

    def test_not_host(self):
        assert not is_image_host_url("https://google.com")


class TestExtractDomain:
    def test_simple(self):
        assert extract_domain("https://imgur.com/abc") == "imgur.com"

    def test_www(self):
        assert extract_domain("https://www.imgur.com/abc") == "imgur.com"

    def test_subdomain(self):
        assert extract_domain("https://i.imgur.com/abc") == "i.imgur.com"


class TestTruncateUrl:
    def test_short(self):
        assert truncate_url("https://a.com") == "https://a.com"

    def test_long(self):
        long = "https://example.com/" + "a" * 100
        assert len(truncate_url(long)) <= 50
        assert truncate_url(long).endswith("...")
