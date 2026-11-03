"""Argparse entry point for the tv (Tomato-Vine) CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from . import config
from .config import AppConfig
from .irc.connection import IRCConnection
from .irc.parser import parse_line
from .tui.app import VineApp

log = logging.getLogger("tv")


def cmd_status(args: argparse.Namespace) -> int:
    """Show configuration and connection status."""
    if not config.CONFIG_FILE.exists():
        print("No config found. Run 'tv config init' to create one.")
        return 1

    cfg = config.AppConfig.model_validate_json(config.CONFIG_FILE.read_text())
    print(f"Config: {config.CONFIG_FILE}")
    print(f"Servers: {len(cfg.servers)}")
    for s in cfg.servers:
        print(f"  {s.host}:{s.port} (tls={s.tls}) nick={s.nickname}")
        if s.channels:
            print(f"    channels: {', '.join(s.channels)}")
    return 0


async def _repl_loop(conn: IRCConnection) -> None:
    """Simple read-eval-print loop for testing connections."""

    async def on_message(line: str) -> None:
        try:
            msg = parse_line(line)
            if msg.command == "PING":
                await conn.send_raw(f"PONG :{msg.trailing}")
                return
            print(f"  [{msg.command}] {msg.nick} {msg.trailing or ' '.join(msg.params)}")
        except ValueError:
            print(f"  [raw] {line}")

    conn.on_message(on_message)
    await conn.connect()


def cmd_connect(args: argparse.Namespace) -> int:
    """Connect to a server in simple REPL mode for testing."""
    if not config.CONFIG_FILE.exists():
        print("No config. Run 'tv config init' first.")
        return 1

    cfg = config.AppConfig.model_validate_json(config.CONFIG_FILE.read_text())
    server = None
    if args.server:
        for s in cfg.servers:
            if s.host == args.server:
                server = s
                break
        if not server:
            print(f"Server '{args.server}' not found in config.")
            return 1
    elif cfg.servers:
        server = cfg.servers[0]
    else:
        print("No servers configured.")
        return 1

    conn = IRCConnection(
        host=server.host,
        port=server.port,
        tls=server.tls,
        nickname=server.nickname,
        username=server.username,
        realname=server.realname,
        password=server.password,
        reconnect=cfg.reconnect,
        reconnect_delay=float(cfg.reconnect_delay),
        reconnect_max_attempts=cfg.reconnect_max_attempts,
    )

    print(f"Connecting to {server.host}:{server.port} as {server.nickname}...")
    print("Type /quit to exit.\n")

    try:
        asyncio.run(_repl_loop(conn))
    except KeyboardInterrupt:
        print("\nDisconnecting...")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Configuration management subcommands."""
    if args.config_command == "init":
        config.BASE_DIR.mkdir(parents=True, exist_ok=True)
        if config.CONFIG_FILE.exists():
            print(f"Config already exists at {config.CONFIG_FILE}")
            return 1
        default = config.AppConfig(
            servers=[
                config.ServerConfig(
                    host="irc.libera.chat",
                    port=6697,
                    tls=True,
                    nickname="vine-user",
                    channels=["#tomato-vine"],
                )
            ]
        )
        config.CONFIG_FILE.write_text(default.model_dump_json(indent=2))
        print(f"Created config at {config.CONFIG_FILE}")
        return 0

    if args.config_command == "show":
        if not config.CONFIG_FILE.exists():
            print("No config. Run 'tv config init' first.")
            return 1
        print(config.CONFIG_FILE.read_text())
        return 0

    return 1


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the interactive TUI."""
    if not config.CONFIG_FILE.exists():
        print("No config. Run 'tv config init' first.")
        return 1

    cfg = config.AppConfig.model_validate_json(config.CONFIG_FILE.read_text())
    if not cfg.servers:
        print("No servers configured.")
        return 1

    if args.server and args.server not in [s.host for s in cfg.servers]:
        print(f"Server '{args.server}' not found in config.")
        return 1

    app = VineApp(app_config=cfg)
    app.run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tv",
        description="Tomato-Vine — a modern IRC TUI client.",
    )
    parser.add_argument("--debug", action="store_true", help="enable debug logging to error log")
    parser.add_argument("--log-chat", action="store_true", help="log chat messages to chat.log")
    parser.add_argument("--log-errors", action="store_true", help="log connection events to error.log")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show configuration and server status")

    connect = sub.add_parser("connect", help="connect to a server (REPL mode)")
    connect.add_argument("--server", "-s", help="server hostname (default: first in config)")

    config_cmd = sub.add_parser("config", help="manage configuration")
    config_cmd.add_argument(
        "config_command",
        choices=["init", "show"],
        help="config subcommand",
    )

    tui = sub.add_parser("tui", help="launch the interactive TUI")
    tui.add_argument("--server", "-s", help="server hostname (default: first in config)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from .log import setup_logging
    setup_logging(
        debug=args.debug,
        log_chat=args.log_chat,
        log_errors=args.log_errors,
    )

    if args.command == "status":
        return cmd_status(args)
    if args.command == "connect":
        return cmd_connect(args)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "tui":
        return cmd_tui(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
