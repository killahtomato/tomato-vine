"""Link and image URL detection for IRC messages."""

from __future__ import annotations

import re

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".ico", ".tiff", ".avif", ".heic", ".heif",
}

IMAGE_HOSTS = {
    "imgur.com", "i.imgur.com",
    "catbox.moe", "files.catbox.moe",
    "litterbox.catbox.moe",
    "gyazo.com",
    "prnt.sc", "prntscr.com",
    "i.redd.it", "preview.redd.it",
    "media.discordapp.net", "cdn.discordapp.com",
    "media.tenor.com", "tenor.com",
    "giphy.com", "media.giphy.com",
    "i.imgur.com",
}

URL_RE = re.compile(
    r'https?://[^\s<>"\')\]]+',
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    urls = URL_RE.findall(text)
    result = []
    for url in urls:
        url = url.rstrip(".,;:!?")
        result.append(url)
    return result


def is_image_url(url: str) -> bool:
    """Check if a URL likely points to an image."""
    lower = url.lower()

    # Check by file extension
    path = lower.split("?")[0].split("#")[0]
    for ext in IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return True

    # Check by known image hosting domain
    domain = extract_domain(url)
    if domain in IMAGE_HOSTS:
        return True

    return False


def is_image_host_url(url: str) -> bool:
    """Check if URL is from an image host but doesn't have an image extension."""
    domain = extract_domain(url)
    return domain in IMAGE_HOSTS


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    match = re.match(r'https?://([^/\s]+)', url)
    if not match:
        return ""
    domain = match.group(1).lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def truncate_url(url: str, max_len: int = 50) -> str:
    """Truncate URL for display."""
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."
