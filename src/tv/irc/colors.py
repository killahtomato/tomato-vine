"""IRC color code parsing — translate mIRC colors to Rich markup."""

from __future__ import annotations

import re

# mIRC color palette
MIRC_COLORS = {
    "0": "white",
    "1": "black",
    "2": "#00007f",
    "3": "#009300",
    "4": "#ff0000",
    "5": "#7f0000",
    "6": "#9c009c",
    "7": "#fc7f00",
    "8": "#ffff00",
    "9": "#00fc00",
    "10": "#009393",
    "11": "#00ffff",
    "12": "#0000fc",
    "13": "#ff00ff",
    "14": "#7f7f7f",
    "15": "#d2d2d2",
    "16": "#470000",
    "17": "#472100",
    "18": "#474700",
    "19": "#324700",
    "20": "#004700",
    "21": "#00472c",
    "22": "#004747",
    "23": "#002747",
    "24": "#000047",
    "25": "#2e0047",
    "26": "#47002a",
    "27": "#470000",
    "28": "#740000",
    "29": "#743a00",
    "30": "#747400",
    "31": "#517400",
    "32": "#007400",
    "33": "#007449",
    "34": "#007474",
    "35": "#004074",
    "36": "#000074",
    "37": "#550074",
    "38": "#74003f",
    "39": "#740000",
    "40": "#b50000",
    "41": "#b56300",
    "42": "#b5b500",
    "43": "#7db500",
    "44": "#00b500",
    "45": "#00b571",
    "46": "#00b5b5",
    "47": "#0063b5",
    "48": "#0000b5",
    "49": "#7d00b5",
    "50": "#b50059",
    "51": "#b50000",
    "52": "#ff0000",
    "53": "#ff6300",
    "54": "#ffff00",
    "55": "#7dff00",
    "56": "#00ff00",
    "57": "#00ff71",
    "58": "#00ffff",
    "59": "#007dff",
    "60": "#0000ff",
    "61": "#7d00ff",
    "62": "#ff0084",
    "63": "#ff0000",
    "64": "#ff6300",
    "65": "#ffff00",
    "66": "#7dff00",
    "67": "#00ff00",
    "68": "#00ff71",
    "69": "#00ffff",
    "70": "#007dff",
    "71": "#0000ff",
    "72": "#7d00ff",
    "73": "#ff00ff",
    "74": "#ff6363",
    "75": "#ffff63",
    "76": "#7dff63",
    "77": "#00ff63",
    "78": "#63ff63",
    "79": "#63ffff",
    "80": "#637dff",
    "81": "#6363ff",
    "82": "#ff63ff",
    "83": "#ff637d",
    "84": "#848484",
    "85": "#9c9c9c",
    "86": "#bfbfbf",
    "87": "#dfdfdf",
    "88": "#ffffff",
    "89": "#000000",
}

# Regex for IRC color codes: \x03 optionally followed by 1-2 digits, then optional ,1-2 digits
_COLOR_RE = re.compile(r"\x03(\d{1,2})?(?:,(\d{1,2}))?")
_COLOR_STRIP_RE = re.compile(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?")
# Regex for other formatting codes
_BOLD_RE = re.compile(r"\x02([^\x02]*?)\x02")
_ITALIC_RE = re.compile(r"\x1d([^\x1d]*?)\x1d")
_UNDERLINE_RE = re.compile(r"\x1f([^\x1f]*?)\x1f")
_STRIKE_RE = re.compile(r"\x1e([^\x1e]*?)\x1e")
_RESET_RE = re.compile(r"\x0f")


def irc_to_rich(text: str) -> str:
    """Convert IRC formatting codes to Rich markup.

    Handles:
    - Color codes (\x03FG,BG or \x03FG)
    - Bold (\x02)
    - Italic (\x1d)
    - Underline (\x1f)
    - Strikethrough (\x1e)
    - Reset (\x0f)

    Returns text with Rich markup tags. The output should be rendered
    via RichLog.write() with markup=True.
    """
    result = []
    i = 0
    fg: str | None = None
    bg: str | None = None
    bold = False
    italic = False
    underline = False
    strike = False

    while i < len(text):
        ch = text[i]

        if ch == "\x03":
            # Parse color code
            match = _COLOR_RE.match(text, i)
            if match and (match.group(1) or match.group(2)):
                fg_raw = match.group(1)
                bg_raw = match.group(2)
                fg = MIRC_COLORS.get(str(int(fg_raw))) if fg_raw else None
                bg = MIRC_COLORS.get(str(int(bg_raw))) if bg_raw else None
                i = match.end()
                # Open color tag
                if fg and bg:
                    result.append(f"[bold {fg} on {bg}]")
                elif fg:
                    result.append(f"[bold {fg}]")
                else:
                    result.append("[/]")
                    fg = None
                    bg = None
                continue
            else:
                # Bare \x03 or no digits — reset colors
                if fg or bg or bold or italic or underline or strike:
                    result.append("[/]")
                    fg = None
                    bg = None
                i += 1
                continue

        elif ch == "\x02":
            if bold:
                result.append("[/bold]")
                bold = False
            else:
                result.append("[bold]")
                bold = True
            i += 1
            continue

        elif ch == "\x1d":
            if italic:
                result.append("[/italic]")
                italic = False
            else:
                result.append("[italic]")
                italic = True
            i += 1
            continue

        elif ch == "\x1f":
            if underline:
                result.append("[/underline]")
                underline = False
            else:
                result.append("[underline]")
                underline = True
            i += 1
            continue

        elif ch == "\x1e":
            if strike:
                result.append("[/strike]")
                strike = False
            else:
                result.append("[strike]")
                strike = True
            i += 1
            continue

        elif ch == "\x0f":
            if bold:
                result.append("[/bold]")
                bold = False
            if italic:
                result.append("[/italic]")
                italic = False
            if underline:
                result.append("[/underline]")
                underline = False
            if strike:
                result.append("[/strike]")
                strike = False
            if fg or bg:
                result.append("[/]")
                fg = None
                bg = None
            i += 1
            continue

        elif ch == "[":
            result.append("\\[")
            i += 1
            continue

        elif ch == "\\":
            result.append("\\\\")
            i += 1
            continue

        else:
            result.append(ch)
            i += 1

    # Close any open tags
    if strike:
        result.append("[/strike]")
    if underline:
        result.append("[/underline]")
    if italic:
        result.append("[/italic]")
    if bold:
        result.append("[/bold]")
    if fg or bg:
        result.append("[/]")

    return "".join(result)


def strip_irc_formatting(text: str) -> str:
    """Strip all IRC formatting codes from text (no markup output)."""
    text = _COLOR_STRIP_RE.sub("", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _UNDERLINE_RE.sub(r"\1", text)
    text = _STRIKE_RE.sub(r"\1", text)
    text = _RESET_RE.sub("", text)
    return text
