"""Small standard-library terminal menu and private multiline header input."""

import curses
import sys
import termios
import textwrap

TITLE = "neurwerk automated tests - LibreChat"


def choose(
    title: str,
    options: list[str],
    overview: list[str] | None = None,
    descriptions: list[str] | None = None,
    initial: int = 0,
) -> int:
    """Choose with arrows/Enter, with numbered input for non-terminal use."""
    overview = overview or []
    descriptions = descriptions or [""] * len(options)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("\n" + title)
        print("\n".join(overview))
        for index, option in enumerate(options, 1):
            print(option if option.startswith(f"{index}. ") else f"{index}. {option}")
            if descriptions[index - 1]:
                print("   " + descriptions[index - 1])
        while True:
            answer = input("Number, then Enter: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1

    def screen(window):
        selected = initial
        curses.curs_set(0)
        window.keypad(True)
        accent = curses.A_BOLD
        selected_style = curses.A_REVERSE | curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
            accent |= curses.color_pair(1)
            selected_style = curses.color_pair(2) | curses.A_BOLD
        while True:
            window.erase()
            height, width = window.getmaxyx()
            left = 3 if width >= 40 else 0
            span = max(1, width - left * 2 - 1)

            def write(y, text, style=0):
                if 0 <= y < height - 1:
                    window.addnstr(y, left, text, span, style)

            write(1, TITLE, accent)
            if title != TITLE:
                write(3, title, curses.A_BOLD)
            visible_overview = overview[: max(0, height - 15)]
            for line, text in enumerate(visible_overview, 5):
                write(line, text, curses.A_DIM)
            heading_height = 4 if title == TITLE else 6
            top = min(heading_height + len(visible_overview), max(0, height - 7))
            write(top - 1, "─" * span, curses.A_DIM)
            capacity = max(1, height - top - 6)
            start = max(0, selected - capacity + 1)
            for offset, option in enumerate(options[start : start + capacity]):
                index = start + offset
                write(
                    top + offset,
                    ((" › " if index == selected else "   ") + option).ljust(span),
                    selected_style if index == selected else curses.A_NORMAL,
                )
            write(height - 6, "─" * span, curses.A_DIM)
            detail = descriptions[selected] or options[selected]
            for offset, line in enumerate(textwrap.wrap(detail, span)[:2]):
                write(height - 5 + offset, line, accent)
            write(
                height - 2,
                f"↑ ↓ Navigate   Enter Select   q Back     {selected + 1}/{len(options)}",
                curses.A_DIM,
            )
            window.refresh()
            key = window.getch()
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                return selected
            elif key in (27, ord("q")):
                return len(options) - 1

    return curses.wrapper(screen)


def select_many(title: str, options: list[str]) -> list[int]:
    selected = set()
    initial = 0
    while True:
        index = choose(
            title,
            [f"[{'x' if i in selected else ' '}] {option}" for i, option in enumerate(options)]
            + [f"Run selected ({len(selected)})", "Cancel"],
            ["Enter toggles a test. Choose Run selected when ready."],
            initial=initial,
        )
        if index == len(options) + 1:
            return []
        if index == len(options):
            if selected:
                return sorted(selected)
        elif index in selected:
            selected.remove(index)
        else:
            selected.add(index)
        initial = index


def paste_headers() -> str:
    print("\nConnect LibreChat once; keep automatic session renewal enabled in Settings.")
    print("1. Sign in to LibreChat in your browser.")
    print("2. Open Developer Tools → Network, then reload LibreChat.")
    print("3. Select a successful /api/user request on the LibreChat host.")
    print("4. Use Copy request headers (not response headers or Copy as cURL).")
    print("   Include the FULL Cookie and User-Agent headers, plus Authorization if present.")
    print("   If /api/user has no Cookie header, copy /api/auth/refresh request headers.")
    print("   Copy complete values, not shortened previews containing an ellipsis.")
    print("\nAccepted format (browser name/value pairs on separate lines also work):")
    print("Authorization: Bearer <full access token>")
    print("Cookie: <full browser Cookie request header>")
    print("User-Agent: <browser user-agent>")
    print("\nThe Cookie header enables renewal; a bearer token alone is not enough.")
    print("The runner saves renewed tokens and cookies in your private local settings.")
    print("A logged-out, revoked or expired login session still requires signing in again.\n")
    original = None
    if sys.stdin.isatty():
        original = termios.tcgetattr(sys.stdin)
        hidden = termios.tcgetattr(sys.stdin)
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, hidden)
    try:
        print("Paste copied request headers (Authorization, Cookie, User-Agent).")
        print(
            "Input is hidden. Finish with a blank line. Saved in private local settings.",
            flush=True,
        )
        lines = []
        size = 0
        while True:
            line = input()
            if not line.strip():
                return "\n".join(lines)
            size += len(line) + 1
            if size > 32768:
                raise ValueError("Headers exceed size limit")
            lines.append(line)
    finally:
        if original is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original)
        print()
