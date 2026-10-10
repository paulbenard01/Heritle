"""Build the home-screen icons: square PNGs with the mark's disc centred.

Without these, "Add to home screen" fell back to the tab favicon, and that
file was never meant for it. Its canvas is 4012 x 3762, not square, and the
disc does not sit in the middle of it -- its centre is about 80 units left of
and 130 above the canvas centre. Android fitted the whole canvas into a white
tile, so the mark came out small and visibly off-centre.

So the disc is measured here rather than trusted: the mark is rendered, the
painted pixels are boxed, and every icon is drawn around the centre of that
box. Re-run after the mark is re-exported.

    python3 tools/make_app_icons.py

Uses Playwright's Chromium to rasterise the SVG. Set CHROMIUM to an executable
path if the bundled browser is not the one installed.
"""
import base64
import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "assets", "vectorised-White.svg")
OUT = os.path.join(HERE, "assets", "icons")

NAVY = "#131D34"
WHITE = "#FFFFFF"

# name, size in px, disc diameter as a share of the side.
#  - apple-touch: iOS rounds the corners itself and keeps everything inside.
#  - any: what Chrome uses when it does not mask.
#  - maskable: Android crops to its own shape; only the central 80% circle is
#    guaranteed to survive, so the disc stays just inside it.
ICONS = [
    ("apple-touch-icon.png", 180, 0.84),
    ("icon-192.png", 192, 0.86),
    ("icon-512.png", 512, 0.86),
    ("maskable-192.png", 192, 0.78),
    ("maskable-512.png", 512, 0.78),
]

# Painted-pixel box of the mark, in its own SVG units.
MEASURE = """async (src) => {
  const img = new Image();
  img.src = 'data:image/svg+xml;base64,' + src;
  await img.decode();
  const W = img.naturalWidth, H = img.naturalHeight, N = 2000;
  const s = N / Math.max(W, H);
  const c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0, W * s, H * s);
  const d = g.getImageData(0, 0, N, N).data;
  let x0 = N, y0 = N, x1 = -1, y1 = -1;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    if (d[(y * N + x) * 4 + 3] > 20) {
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  }
  return { W, H, box: [x0 / s, y0 / s, (x1 + 1) / s, (y1 + 1) / s] };
}"""


def navy_mark():
    """The mark with its fill forced to navy, as base64 for a data: URL."""
    svg = open(SRC, encoding="utf-8").read()
    i = svg.index(">", svg.index("<svg")) + 1
    # !important beats the inline style="fill:..." the export carries.
    svg = svg[:i] + f"<style>path{{fill:{NAVY} !important;}}</style>" + svg[i:]
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


def main():
    os.makedirs(OUT, exist_ok=True)
    src = navy_mark()
    launch = {}
    if os.environ.get("CHROMIUM"):
        launch["executable_path"] = os.environ["CHROMIUM"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        page = browser.new_page()
        page.set_content("<body></body>")
        m = page.evaluate(MEASURE, src)
        x0, y0, x1, y1 = m["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        disc = max(x1 - x0, y1 - y0)
        print(f"disc {x1 - x0:.0f} x {y1 - y0:.0f} at ({cx:.0f}, {cy:.0f}) "
              f"in a {m['W']} x {m['H']} canvas")
        for name, size, share in ICONS:
            scale = size * share / disc
            left = size / 2 - cx * scale
            top = size / 2 - cy * scale
            page.set_viewport_size({"width": size, "height": size})
            page.set_content(
                f"<body style='margin:0'><div id=t style='position:relative;"
                f"width:{size}px;height:{size}px;overflow:hidden;background:{WHITE}'>"
                f"<img src='data:image/svg+xml;base64,{src}' style='position:absolute;"
                f"left:{left}px;top:{top}px;width:{m['W'] * scale}px;"
                f"height:{m['H'] * scale}px'></div></body>")
            page.wait_for_function("document.querySelector('img').complete")
            page.locator("#t").screenshot(path=os.path.join(OUT, name))
            print(f"wrote assets/icons/{name}")
        browser.close()


if __name__ == "__main__":
    main()
