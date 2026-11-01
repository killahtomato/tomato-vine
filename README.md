# Tomato-Vine (`tv`)

A modern IRC TUI client written in Python.

> Phase 1: protocol core — parser, connection, config, CLI skeleton.

## Requirements

- Python 3.11+

## Install

```bash
git clone https://github.com/killahtomato/tomato-vine.git
cd tomato-vine
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -sf "$PWD/tv" ~/.local/bin/tv
```

## Quick start

```bash
tv config init                  # create default config at ~/.config/tomato-vine/
tv config show                  # display current config
tv status                       # show configured servers
tv connect                      # connect to first server in REPL mode
tv tui                          # launch the interactive TUI (Phase 2)
```

## Commands

| Command | Description |
|---|---|
| `tv config init` | Create a default configuration file |
| `tv config show` | Display current configuration as JSON |
| `tv status` | Show configured servers and connection info |
| `tv connect` | Connect to a server in simple REPL mode |
| `tv tui` | Launch the interactive TUI (coming in Phase 2) |

## Architecture

```
src/tv/
├── config.py         # Pydantic config models (servers, SASL, reconnect)
├── cli.py            # Argparse entry point
├── irc/
│   ├── parser.py     # IRC message parser (RFC 1459 + IRCv3 tags)
│   ├── commands.py   # IRC command builders (PRIVMSG, JOIN, etc.)
│   ├── connection.py # Async TCP/TLS with auto-reconnect
│   └── capabilities.py # IRCv3 capability negotiation (Phase 2)
└── tui/              # Textual-based TUI (Phase 2)
```

## License

MIT
