# Tomato-Vine (`tv`)

A modern IRC TUI client written in Python.

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
tv tui                          # launch the interactive TUI
```

## CLI Commands

| Command | Description |
|---|---|
| `tv config init` | Create a default configuration file |
| `tv config show` | Display current configuration as JSON |
| `tv status` | Show configured servers and connection info |
| `tv connect [-s host]` | Connect in simple REPL mode |
| `tv tui [-s host]` | Launch the interactive TUI |
| `tv --debug tui` | Launch TUI with debug logging |

## TUI Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `Tab` | Cycle focus (input ↔ chat ↔ sidebar) |
| `c` | Focus channel tree |
| `r` | Refresh display |
| `Enter` | Send message |
| `↑` / `↓` | Input history |
| `Esc` | Clear input / unfocus |

## TUI Commands

| Command | Action |
|---------|--------|
| `/join #channel` | Join a channel |
| `/part [#channel] [reason]` | Leave a channel |
| `/msg target text` | Send a private message |
| `/me text` | Send a CTCP action |
| `/topic [text]` | View or set channel topic |
| `/kick nick [reason]` | Kick a user |
| `/mode +x [params]` | Set channel mode |
| `/who [target]` | Query WHO |
| `/away [reason]` | Set/unset away |
| `/nick newnick` | Change nickname |
| `/raw command` | Send raw IRC line |
| `/quit [reason]` | Disconnect and quit |

## Features

- **SASL PLAIN authentication**
- **IRCv3 capabilities**: multi-prefix, account-notify, away-notify, extended-join, message-tags
- **Auto-reconnect** with exponential backoff
- **TreeView sidebar** with channel navigation and DM tracking
- **IRC color code rendering** (mIRC colors → Rich markup)
- **CTCP auto-replies**: VERSION, PING, TIME, FINGER
- **WHO/NAMES** — automatic nick list population
- **Channel modes**: +o, +v, +b, +k, +l tracking

## Architecture

```
src/tv/
├── config.py         # Pydantic config models (servers, SASL, reconnect)
├── cli.py            # Argparse entry point
├── irc/
│   ├── parser.py     # IRC message parser (RFC 1459 + IRCv3 tags)
│   ├── commands.py   # IRC command builders (PRIVMSG, JOIN, SASL, CTCP)
│   ├── connection.py # Async TCP/TLS + auto-reconnect + SASL + CAP
│   ├── capabilities.py # IRCv3 capability negotiation
│   └── colors.py     # IRC color code → Rich markup rendering
└── tui/
    ├── app.py        # Main Textual app — event handling, commands
    └── widgets/
        ├── __init__.py # StatusBar, ChatView, NickList, VineInput
        └── sidebar.py  # ServerTree — hierarchical channel navigation
```

## License

MIT
