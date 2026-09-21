# A build prompt for a daily heritage-guessing game

Hand the section below to a capable coding AI. It is written as a brief rather
than a description, and it front-loads the mistakes — the traps section is the
part worth keeping, because everything above it can be re-derived and the traps
cost days to find.

---

## The brief

Build a **daily geography-guessing game about world heritage**, in the shape of
Wordle: one puzzle a day, the same puzzle for everyone, a shareable result grid.

### Hard constraints

- **One HTML file.** No build step, no bundler, no framework, no npm. The whole
  game is a single `game.html` that opens by double-clicking it. Data lives in a
  separate `data/dataset.json` it fetches.
- **Static hosting only.** It must run on GitHub Pages. No backend, no database,
  no server-side state, no paid service, no API key in the client.
- **Trilingual from the first commit** (pick three; English, French and Spanish
  work well). Not a translation layer bolted on later — every string goes
  through the dictionary from the start, and no language is ever allowed to fall
  behind the others.
- **Never use the UNESCO name, the acronym or the emblem** in code, copy,
  branding or the domain. The emblem is protected under the Hague Convention and
  the name is restricted. Say "world heritage" descriptively; link to official
  pages where a factual link is useful, and nowhere else.
- **Offline-capable after first load** is a nice-to-have, not a requirement.

### The game

Four rounds a day:

1. Three rounds on **physical sites**, one from each fame tier — famous,
   middling, obscure — so the difficulty ramps.
2. One bonus round on **living traditions** (intangible heritage), worth half
   again as much.

Each round: show a photograph and a short description, hide the name, and ask
the player to place it on a world map. Four guesses. After each wrong guess,
report distance, compass bearing and a heat band (`correct` under 40 km, `hot`
under 1000, `close` under 3000, `mid` under 6500, `far` beyond).

Scoring per round, out of the round's points:

```
credit   = [1, 0.85, 0.72, 0.6][guess_number - 1]     // solved on guess n
geo      = exp(-km / 2000)                            // smooth decay
cultural = 0.55 if right region else 0.3 if right continent else 0
missed   = min(0.45, max(geo, cultural))              // ceiling below worst solve
```

A miss must always score below the worst solve. That single rule is what stops
"place it in the ocean four times" being a viable strategy.

### The map

- **Equirectangular projection** onto a 440 × 220 SVG. `project` and `unproject`
  are two-line functions; resist anything heavier.
- **Free placement**: the player clicks anywhere, not on a country. Countries are
  then resolved by point-in-polygon against a simplified world outline.
- **Snap microstates**: within ~10 px of a tiny country's centroid, snap to it,
  or Monaco and Singapore are unclickable on a phone.
- **Multi-country answers count for all of them.** Roughly 8% of heritage sites
  are shared between countries, some between 25. Every one of them is a correct
  answer, and the reveal should ring each.
- Pin captions need a halo that is **counter-scaled against zoom**, or at 8× the
  halo covers the pin it is labelling. Flip the text anchor near the map edges.

### Daily dealing

The same puzzle for everyone, forever, with no server:

```
dayIndex = floor((utcMidnightToday - EPOCH) / 86400000)
```

Then per round slot, deal from a **deterministic permutation** — seed
`mulberry32` with `(slot, cycle)` and Fisher–Yates the pool. A permutation, not
a sample: sampling repeats an entry in week two while hundreds are never dealt.
Walk the tiers across cycles so the obscure entries eventually get their day
rather than being permanently excluded by a tier-1-only rule.

Store progress in `localStorage` behind a **generation key** (`gen = '4'`), and
wipe stored state whenever the generation changes. Any change to the dataset or
the deal reshuffles history; without the generation key, returning players see a
board that does not match the puzzle.

### The dataset

Build it from **Wikidata SPARQL** plus **Wikimedia Commons** thumbnails, into a
single `dataset.json` of a few thousand entries. Each entry:

```json
{ "id": "...", "qid": "Q...", "type": "material|immaterial",
  "names": {"en": "...", "fr": "...", "es": "..."},
  "aliases": {...}, "desc": {...},
  "lat": 0.0, "lng": 0.0, "country": ["..."], "continent": "EU",
  "tier": 1, "year": 1979, "image": "...", "photos": [...] }
```

Derive `tier` from **sitelink count** — how many Wikipedias cover it — which is
the only fame signal available that is not a guess.

Write the builder as a script that can be re-run. It should be idempotent, log
what it changed, and refuse to write a dataset smaller than the last one without
an explicit flag.

### Tests

Write a **smoke suite** that drives a real browser (Playwright) and asserts on
the live page: every string in all three languages, the scoring boundaries, the
share grid, the storage generation, the map hit-testing, and **that no request
404s**. Aim for a four-figure number of assertions; it is the only thing making
a single 5,000-line HTML file safe to change.

Never write a test that reads the clock without controlling it.

---

## The traps

These cost real time. They are the reason this document exists.

**A filter that cannot pass is the same bug as a test that cannot fail.** A
licence filter was written against `license.slug`; the API returns
`license.label`. It rejected every candidate for all 25 searches and looked like
a thin field rather than a broken filter. *Always print a sample of the raw API
response before writing a filter against it.*

**And its mirror.** A name-matching filter was later written that could almost
never fire, because the stop list stripped every word from the names it was
meant to match. Both directions are silent.

**A guard that cannot check must fail closed.** A relevance guard returned
`True` when it had no keywords to test with, commented "nothing distinctive to
test against". A site named `M'zab` produced no keywords — both words under four
letters — so it was handed a 1.3 GB panorama of a Swiss mountain and counted it.
The correct reading of "cannot verify" is *refuse*.

**A single generic word is not a match.** `Museum Island` matched an air museum
playground; `Omo River` would match every river. Require whole tokens, never
substrings, and treat words that name a *kind* of place as stop words.

**Sample sizes lie about thin data.** A per-continent sample estimated ~6 usable
items in Africa. A census of all 151 found **1**. If a decision rests on a
category's count, count it — do not estimate it.

**APIs meter data volume, not rows.** Asking for six fields silently returned
fewer results than asking for two, making a coverage survey report a third of
the truth. Ask for the minimum and verify the count changes when you add fields.

**A diagnostic must not block the work it diagnoses.** A schema probe hardcoded
to one location failed when that location had no data, and killed the survey
behind it. Probes walk a list and always exit zero.

**Cross products in SPARQL.** An item with three aliases, two images and six
criteria returns *hundreds* of near-identical rows. `GROUP_CONCAT` the
multi-valued fields and `SAMPLE` the single-valued ones, or a 250-item page
times out.

**Sample coordinates as a pair.** `SAMPLE(?lat)` and `SAMPLE(?lon)` separately
can take latitude from one statement and longitude from another and drop the pin
in the sea. Concatenate before sampling.

**Aspect ratio is not a format.** A 2:1 image is *probably* a 360° panorama and
might be a cropped wide photo. Read the file's actual metadata.

**YAML block scalars and heredocs.** A heredoc nested inside a YAML `run:` block
with an indented terminator never terminates. Put scripts in real files.

**Check the licence before the quality.** Share-alike on an asset baked into
your shipped file binds your file. Non-commercial and no-derivatives forbid the
resizing pipeline outright. Filter on licence first, then look at the thing.

**Ask whether the person can act on it.** A shortlist was delivered twice that
nobody could use — once because the links were described rather than included,
once because it sat on an unmerged branch. Before calling anything done, ask
whether the reader can act on it as delivered.
