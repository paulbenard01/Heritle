# assets

Brand files live here. The game loads the header mark from this folder.

| File | What it is | Used by |
|---|---|---|
| `heritlelogogold.svg` | the light mark, for the navy page | **the header** — `heritle.html` loads this exact path |
| `heritlelogonavy.svg` | the dark mark, for light backgrounds | share cards, print, anything on cream |
| `Heritlelogogold.png` | raster copy of the light mark | social preview (`og:image`), Apple touch icon |
| `Heritlelogonavy.png` | raster copy of the dark mark | spare |

Note the mixed capitalisation: the SVGs are lowercase and the PNGs are not.
That is how they were uploaded, and the code points at the real names rather
than renaming anyone's files. Worth normalising one day.

A `viewBox` was added to both SVGs, and nothing else was touched. Without one,
Safari will not scale an SVG inside an `<img>` — it renders at its native 673px
and gets clipped to the box. Chromium copes; Safari has never had to, and most
players are on a phone.

## Two things that will bite

**Capitalisation is part of the filename.** GitHub Pages serves from Linux, so
`Heritlelogogold.svg` and `heritlelogogold.svg` are different files. The page
asks for the first spelling exactly as written above.

**A missing or misnamed file is not a broken image.** The header hides the
`<img>` if it fails to load, so the page falls back to the wordmark alone. If
you upload and still see no mark, the filename does not match.

The mark is referenced once, in the header of `heritle.html`:

```html
<button class="mark" id="mark" aria-label="Heritle">
  <img src="assets/heritlelogogold.svg" alt="" onerror="…">
</button>
```

Changing which file the header uses means changing that one line.

## vectorised-241b3301.svg — the gate mark

Uploaded as a vectorisation, and edited twice on arrival. Both changes are
the kind that are invisible until they are not:

- **A `viewBox` was added.** Without one an SVG will not scale inside an
  `<img>` in Safari — it draws at its intrinsic 3000px and blows the layout
  apart. Chromium tolerates the omission, which is how it goes unnoticed.
  `tests/test_pipeline.py` fails any SVG here that lacks one.
- **The opening background rectangle was removed** from the first path
  (`M0 0h3000v2813H0z`, filled `#FDFDF4`). It painted the whole canvas cream,
  so on the navy page the mark arrived as a cream card rather than a disc.
  The cream *inside* the disc is part of the artwork and is untouched.

Numeric precision was left alone: rounding the path coordinates to one decimal
saved 30KB and visibly deformed the mark, because the data is relative and the
error accumulates along each path.
