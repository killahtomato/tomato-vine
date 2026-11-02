"""Theme system for tomato-vine — Textual Theme integration + importers."""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

from textual.theme import Theme

log = logging.getLogger(__name__)

THEME_DIR = Path(os.environ.get("TV_THEME_DIR", Path.home() / ".config" / "tomato-vine" / "themes"))


def omarchy_to_theme(
    name: str, mode: str, colors: dict[str, str]
) -> Theme:
    """Convert an Omarchy colors.toml dict to a Textual Theme."""
    return Theme(
        name=name,
        background=colors.get("background", "#1e1e1e"),
        foreground=colors.get("foreground", "#e0e0e0"),
        surface=colors.get("background", "#1e1e1e"),
        panel=colors.get("lighter_background", colors.get("selection", "#2a2a2a")),
        primary=colors.get("accent", "#4fc3f7"),
        accent=colors.get("accent", "#4fc3f7"),
        warning=colors.get("yellow", "#f9e2af"),
        error=colors.get("red", "#f38ba8"),
        success=colors.get("green", "#a6e3a1"),
        dark=(mode == "dark"),
    )


def _load_themes_from_dir(theme_dir: Path, prefix: str) -> list[Theme]:
    """Load themes from a directory of colors.toml files."""
    themes: list[Theme] = []
    if not theme_dir.is_dir():
        return themes

    for entry in sorted(theme_dir.iterdir()):
        if not entry.is_dir():
            continue
        colors_file = entry / "colors.toml"
        if not colors_file.exists():
            continue
        try:
            with open(colors_file, "rb") as f:
                data = tomllib.load(f)

            mode = data.get("mode", "dark")
            colors = {k: v for k, v in data.items() if k != "mode" and isinstance(v, str)}

            slug = entry.name.lower().replace(" ", "-")
            theme = omarchy_to_theme(f"{prefix}-{slug}", mode, colors)
            themes.append(theme)
        except Exception as exc:
            log.debug("Failed to load theme %s: %s", entry.name, exc)

    return themes


def load_omarchy_themes() -> list[Theme]:
    """Load all installed Omarchy themes as Textual Themes."""
    dirs = [
        Path("/usr/share/omarchy/themes"),
        Path.home() / ".config" / "omarchy" / "themes",
    ]
    themes: list[Theme] = []
    for d in dirs:
        themes.extend(_load_themes_from_dir(d, "omarchy"))
    return themes


def load_custom_themes() -> list[Theme]:
    """Load user-installed custom themes."""
    return _load_themes_from_dir(THEME_DIR, "custom")


def install_theme_from_git(repo_url: str) -> str | None:
    """Install a theme from a git repo. Returns theme name or None."""
    import subprocess

    name = repo_url.rstrip("/").split("/")[-1].replace(".git", "").lower()
    target = THEME_DIR / name
    target.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(target)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return name
    except Exception as exc:
        log.error("Failed to clone theme repo: %s", exc)
        return None


def register_all_themes(app) -> list[str]:
    """Register all available themes. Returns list of registered theme names."""
    names: list[str] = []

    for theme in list(BUILTIN_THEMES.values()) + load_omarchy_themes() + load_custom_themes():
        try:
            app.register_theme(theme)
            names.append(theme.name)
        except Exception as exc:
            log.debug("Failed to register theme %s: %s", theme.name, exc)

    return names


BUILTIN_THEMES = {
    "dark": Theme(
        name="dark",
        primary="#4fc3f7",
        background="#1e1e1e",
        foreground="#e0e0e0",
        surface="#1e1e1e",
        panel="#242f38",
        accent="#4fc3f7",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
    ),
    "light": Theme(
        name="light",
        primary="#1565c0",
        background="#ffffff",
        foreground="#1a1a1a",
        surface="#ffffff",
        panel="#f0f0f0",
        accent="#1565c0",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
    ),
    "blue": Theme(
        name="blue",
        primary="#64b5f6",
        background="#0d1b2a",
        foreground="#c0d0e0",
        surface="#0d1b2a",
        panel="#1b2838",
        accent="#64b5f6",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
    ),
    "green": Theme(
        name="green",
        primary="#66bb6a",
        background="#0a1f0a",
        foreground="#c0e0c0",
        surface="#0a1f0a",
        panel="#1b2e1b",
        accent="#66bb6a",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
    ),
    "amber": Theme(
        name="amber",
        primary="#ffb300",
        background="#1a1408",
        foreground="#e0d0a0",
        surface="#1a1408",
        panel="#2a2210",
        accent="#ffb300",
        warning="#f9e2af",
        error="#f38ba8",
        success="#a6e3a1",
    ),
}
