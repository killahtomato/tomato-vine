"""IRC command builders."""

from __future__ import annotations

from .parser import build_message


def nick(nickname: str) -> str:
    return build_message("NICK", params=[nickname])


def user(username: str, realname: str, mode: int = 0) -> str:
    return build_message("USER", params=[username, str(mode), "*"], trailing=realname)


def pass_(password: str) -> str:
    return build_message("PASS", params=[password])


def pong(token: str) -> str:
    return build_message("PONG", trailing=token)


def ping(token: str) -> str:
    return build_message("PING", trailing=token)


def join(channel: str, key: str | None = None) -> str:
    if key:
        return build_message("JOIN", params=[channel, key])
    return build_message("JOIN", params=[channel])


def part(channel: str, reason: str | None = None) -> str:
    if reason:
        return build_message("PART", params=[channel], trailing=reason)
    return build_message("PART", params=[channel])


def privmsg(target: str, text: str) -> str:
    return build_message("PRIVMSG", params=[target], trailing=text)


def notice(target: str, text: str) -> str:
    return build_message("NOTICE", params=[target], trailing=text)


def quit_(reason: str = "Leaving") -> str:
    return build_message("QUIT", trailing=reason)


def mode(target: str, modes: str, params: list[str] | None = None) -> str:
    if params:
        return build_message("MODE", params=[target, modes, *params])
    return build_message("MODE", params=[target, modes])


def topic(channel: str, text: str | None = None) -> str:
    if text is not None:
        return build_message("TOPIC", params=[channel], trailing=text)
    return build_message("TOPIC", params=[channel])


def invite(nick: str, channel: str) -> str:
    return build_message("INVITE", params=[nick, channel])


def kick(channel: str, nick: str, reason: str | None = None) -> str:
    if reason:
        return build_message("KICK", params=[channel, nick], trailing=reason)
    return build_message("KICK", params=[channel, nick])


def away(reason: str | None = None) -> str:
    if reason:
        return build_message("AWAY", trailing=reason)
    return build_message("AWAY")


def cap_list() -> str:
    return build_message("CAP", params=["LIST"])


def cap_req(capabilities: str) -> str:
    return build_message("CAP", params=["REQ"], trailing=capabilities)


def cap_end() -> str:
    return build_message("CAP", params=["END"])


def authenticate(data: str) -> str:
    return build_message("AUTHENTICATE", params=[data])


def whois(target: str) -> str:
    return build_message("WHOIS", params=[target])


def whowas(nick: str, count: int = 1) -> str:
    return build_message("WHOWAS", params=[nick, str(count)])


def action(target: str, text: str) -> str:
    return privmsg(target, f"\x01ACTION {text}\x01")


def ctcp(target: str, command: str, args: str | None = None) -> str:
    payload = command.upper()
    if args:
        payload = f"{payload} {args}"
    return privmsg(target, f"\x01{payload}\x01")
