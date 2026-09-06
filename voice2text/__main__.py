"""
Einstiegspunkt:

    python -m voice2text              → grafische Oberfläche
    python -m voice2text video.mp4    → Kommandozeile
"""

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main
        return cli_main()

    try:
        from .app import main as gui_main
    except SystemExit as exc:                 # customtkinter/tkinter fehlt
        print(exc, file=sys.stderr)
        return 1
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
