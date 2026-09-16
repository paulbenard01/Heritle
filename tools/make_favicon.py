"""Build one favicon that changes colour with the browser's theme.

Two <link rel="icon" media="..."> entries is the documented way to do this and
it is not reliable: browsers differ on which candidate they take when several
match, and some ignore the media attribute altogether -- which is how a black
mark ended up in a dark tab strip.

One file removes the choice. An SVG favicon is a document, so it can carry its
own stylesheet, and `prefers-color-scheme` inside it is resolved against the
viewer's preference at paint time. The inline fill has to go: a style attribute
beats a rule in the sheet, which is why this rewrites the path rather than just
prepending a <style> block.

Run: python3 tools/make_favicon.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "assets", "vectorised-White.svg")
OUT = os.path.join(HERE, "assets", "favicon.svg")

# Not pure black on a light strip: the mark is navy everywhere else in the
# game, and a tab is the one place it would look like a different logo.
LIGHT = "#131D34"
DARK = "#F3EEDF"

def main():
    svg = open(SRC, encoding="utf-8").read()
    # Strip the inline fill wherever it appears, so the sheet can decide.
    before = svg
    svg = re.sub(r'style="fill:#[0-9a-fA-F]{3,6};?(fill-opacity:[\d.]+;?)?"', '', svg)
    svg = re.sub(r'\sfill="#[0-9a-fA-F]{3,6}"', '', svg)
    if svg == before:
        print("nothing to strip -- has the export changed?", file=sys.stderr)
        return 1
    sheet = (
        "<style>"
        f"path{{fill:{LIGHT};}}"
        f"@media (prefers-color-scheme:dark){{path{{fill:{DARK};}}}}"
        "</style>"
    )
    # After the opening <svg ...>, so it applies to everything in the file.
    i = svg.index(">", svg.index("<svg")) + 1
    svg = svg[:i] + sheet + svg[i:]
    open(OUT, "w", encoding="utf-8").write(svg)
    print(f"wrote {os.path.relpath(OUT, HERE)}  {len(svg)} bytes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
