# 360 panoramas and 3D models: closed, 21 September 2026

**The whole visual-asset direction is abandoned.** Not because the
measurements were inconclusive — they were unusually clear — but because
what they showed was that the imagery for a world-spanning game does not
exist, and the workaround for that was more complexity than the project
wants to carry.

The numbers that closed it: Africa has **1** usable panorama across all 151
of its sites, Oceania **2** of 28, both counted rather than sampled. The 3D
models were shortlisted and, when opened, judged poor.

What survives is the daily game, which already spans 1,872 entries with real
spread and is constrained by nothing but the dataset. The Heritle 3D shell
remains unmerged on `claude/vigilant-ride-6p54ko`; the surveys and their
tooling remain in `tools/`, and the lessons are written up in
`docs/BUILD_PROMPT.md`.

Everything below is the record of how that was established.

---

# 360 panoramas: what the sources actually hold

Measured 19 September 2026, against the real dataset, by
`tools/survey_mapillary.py` and `tools/survey_panoramas.py`.

## Mapillary — 45 sites, spread across fame tiers

| | |
|---|---|
| At least one 360 within 150 m | **5 of 45 (11%)** |
| Any street-level imagery at all | 22 of 45 (49%) |
| Panoramas found in total | 34 |
| Extrapolated to the whole pool | ~208 of 1,872 entries |

## Spread: the answer to "more of the world, less of Europe"

Two draws, 14 and then 40 sites per continent, 312 sites in all. The second
was run because the first returned zero for three continents, and a zero out
of fourteen is as easily a fact about the shuffle as a fact about Mapillary.
It was worth running: **Asia went from 0/14 to 6/40**, so the first draw was
partly bad luck.

| Continent | Draw 1 | Draw 2 | Combined | Sites in pool | Reachable |
|---|---|---|---|---|---|
| Europe | 5/14 | 12/40 | **17/54 (31%)** | 515 | ~160 |
| Asia | 0/14 | 6/40 | **6/54 (11%)** | 332 | ~37 |
| North America | 0/14 | 3/40 | **3/54 (6%)** | 112 | ~7 |
| South America | 2/14 | 1/40 | **3/54 (6%)** | 79 | ~5 |
| Africa | 1/14 | 1/40 | **2/54 (4%)** | 151 | ~6 |
| Oceania | 0/14 | 0/28 | **0/42 (0%)** | 28 | 0 |
| | | | 31/312 (10%) | | **~215** |

Oceania is not a sample. The pool holds 28 material sites in Oceania and the
second draw took all 28. Zero of them have a 360 within 150 m. That row is a
census, and it is empty.

### So two hundred is reachable, and spread is not

Mapillary can supply roughly 215 places, which clears the two hundred. But
**three quarters of them are European**, and the constraint is not Europe's
abundance — it is that Africa, South America and Oceania together offer about
eleven sites. Cap any continent at a third of the pool and the whole thing
comes out around ninety.

Two hundred places and an even spread cannot both come from Mapillary. That is
the decision, and it is not a technical one.

## What the first draw got wrong

Draw 1's five hits were four historic towns and a cathedral, and this file
previously concluded from that that Mapillary coverage is *only* street-shaped.
Draw 2 says otherwise: **Tiwanaku (24), Itsukushima Shrine (6), Liberty Island
(7), Kew Gardens (5), Jelling (21), Kathmandu Valley (46)** are an archaeo-
logical site, a shrine, a monument, a botanical garden, a burial mound complex
and a valley. The bias towards inhabited places is real but it is a tilt, not
a rule — five hits was too few to tell the two apart.

What holds is the shape of the zeroes: remote, roadless and mountain sites get
nothing. Konark, Tsodilo, Mount Kumgang, Jiuzhaigou, the Philippine Cordilleras,
Lake Turkana, Djenné, the Mijikenda Kaya Forests — all empty. Someone has to
have carried a rig there, and for most of Africa and all of Oceania nobody has.

Only 10% have a 360 while about half have *some* imagery, which says most
Mapillary contributions are flat phone and dashcam frames rather than spherical
rigs.

## Wikimedia Commons — measured properly, and thin

25 sites per continent, 150 in all, every candidate's file opened and read.

| Continent | Hit | Reachable in the pool |
|---|---|---|
| South America | 2/25 (8%) | ~6 of 79 |
| Europe | 1/25 (4%) | ~20 of 515 |
| Asia | 1/25 (4%) | ~13 of 332 |
| Oceania | 1/25 (4%) | ~1 of 28 |
| Africa | **0/25** | 0 of 151 |
| North America | **0/25** | 0 of 112 |
| | 5/150 (3%) | **~40** |

The five: Verla, Hiraizumi, Cuenca, Humberstone, the Greater Blue Mountains.

So Commons is a supplement worth about forty places, not a rescue. It cannot
fill Africa, which was the row it was asked to fill.

### The projection test earned itself on the first run

A 2:1 aspect ratio is necessary and nowhere near sufficient, which this file
has said for days while the survey went on trusting it. It is now tested
properly: 128 KB of each candidate is fetched and searched for the GPano XMP
tag the stitcher writes, which is enough because XMP sits near the start of a
JPEG.

Eight sites came back "looked 2:1, none were spheres" — Malbork, Pienza,
Speyer, Mount Wutai, Thebes, Maloti-Drakensberg, Castillo de San Pedro, the
Sydney Opera House. Every one of those would have counted under the old test.
It would have reported 13 of 150 instead of 5, and nearly tripled the rate the
pool size rests on.

A file that cannot be read returns neither yes nor no, and those are counted
apart. Reading a network failure as "not a panorama" would turn an outage into
a finding.

### Poly Haven: candidates, never counts

Four filters were written for it and each failed differently. Substrings gave
`viale_giuseppe_GARIbaldi` for K'gari. Whole tokens still gave a museum of
history for National History Park. Requiring the lone word to be rare in the
catalogue passed that one anyway — "history" is rare in a library of render
lighting and generic everywhere else. Requiring two distinctive words to agree
could almost never fire, because heritage names collapse to one key once the
stop list has taken "temple", "park" and every word under four letters:
"Angkor Wat Temple" reduces to "angkor".

A test that cannot pass is the same bug as a test that cannot fail, and this
survey produced one of each. So Poly Haven now prints links for a person to
open and adds nothing to any total. It is a library for lighting 3D renders;
the honest expectation is that it holds no heritage spheres at all.

## What the two sources give together

| Continent | Mapillary | Commons | Together | Sites in pool |
|---|---|---|---|---|
| Europe | ~160 | ~20 | **~180** | 515 |
| Asia | ~37 | ~13 | **~50** | 332 |
| South America | ~5 | ~6 | **~11** | 79 |
| North America | ~7 | ~0 | **~7** | 112 |
| Africa | ~6 | 0 | **~6** | 151 |
| Oceania | 0 | ~1 | **~1** | 28 |
| | ~215 | ~40 | **~255** | 1,219 |

## The census: Africa and Oceania counted, not sampled

Every site in both continents, both sources, 179 sites. Run because the
sampled estimates for these rows were built on a handful of hits and the
pool's whole shape depended on them.

| | Africa (151 sites) | Oceania (28 sites) |
|---|---|---|
| Mapillary | **1** — Grand-Bassam | **1** — Sydney Opera House |
| Commons | **0** | **1** — Greater Blue Mountains |
| Total | **1 place** | **2 places** |

The sampled estimate for Africa was ~6. The true count is 1 — the estimate
was six times too high, which is what a census is for.

Two caveats on the counts themselves. Mapillary's Oceania census returned 0
on one run and 1 on the next, the same 28 sites both times, so even a census
carries the run-to-run instability recorded below. And Commons' Africa count
fell from 2 to 0 when the relevance guard was fixed: both African "hits" were
false, M'zab having been handed a 1.3 GB photograph of the Pfaffen and
another of the Bälmeten, which are Swiss.

The six-continent sample was re-run after that same fix and came back
unchanged at 5 of 150. The broken guard had inflated the census, not the
sample.

## What actually exists, after all of it

| Continent | Mapillary | Commons | Together | Sites in pool |
|---|---|---|---|---|
| Europe | ~160 | ~20 | **~180** | 515 |
| Asia | ~37 | ~13 | **~50** | 332 |
| South America | ~5 | ~6 | **~11** | 79 |
| North America | ~7 | ~0 | **~7** | 112 |
| Oceania | 1 | 1 | **2** (counted) | 28 |
| Africa | 1 | 0 | **1** (counted) | 151 |

## Spread is not available at any pool size

Ninety places chosen for spread was the decision. It cannot be built. Africa
has one usable panorama and Oceania has two, and those are counts of every
site rather than estimates, so no target and no amount of further searching
moves them.

A ninety-place pool would be Africa 1 and Oceania 2 — three places, three per
cent, for two continents holding an enormous share of the world's heritage.
Europe and Asia would carry about 77% of it. That is not a spread-focused
pool with a caveat; it is a Europe-and-Asia game with two other continents
represented by a token.

And a genuinely flat pool — every continent equal — is capped by Africa at
one, so it would hold about six places in total.

The constraint is not the target. It is that the imagery does not exist:
360 rigs are carried by people who own them, along roads they drive, and that
distribution is what the survey has been measuring all along.

## The options that are actually open

1. **Ninety places, honestly labelled.** Build it, and say plainly that it is
   where 360 imagery exists rather than where heritage is. Africa 1,
   Oceania 2.
2. **Two hundred places, Europe-heavy.** The original shape, ~215 available.
   Same imbalance, more game.
3. **Keep the daily game as the world-spanning one** and make 360 a bonus
   mode over the few dozen places that have coverage. The daily game already
   draws on 1,872 entries with real spread; nothing about it is constrained
   by where someone carried a panorama rig.
4. **Go back to 3D models.** Sketchfab coverage is not street-shaped, so its
   geography is different — but the models were judged poor when looked at,
   and that judgement has not changed.

Option 3 is the one worth recommending. The spread the project wants already
exists in the daily game, and 360 is a good bonus over a small set and a bad
foundation for a world-spanning one. It also costs nothing already built: the
Heritle 3D shell on `claude/vigilant-ride-6p54ko` is a separate mode by
design.

## Not usable

**Google Street View** — the terms forbid downloading and self-hosting. Worth
recording so nobody spends a week discovering it.

## Resolution: measured by opening the files

Not read off a field. Downloaded and measured with Pillow, because every field
in this survey has at some point been absent, differently named or differently
shaped from what was assumed.

| Site | Measured | File |
|---|---|---|
| Grand-Bassam | 11000 × 5500 | 5.8–6.0 MB |
| Speyer Cathedral | 7680 × 3840 | 3.1–3.6 MB |
| Rjukan–Notodden | 5760 × 2880 | 1.5–1.6 MB |
| Røros | 5760 × 2880 | 1.3–1.7 MB |

All exactly 2:1, all genuine equirectangular. These are proper 360 rigs rather
than dashcam frames — the quality worry was unfounded, and the resolutions are
*higher* than the game needs. At 4096 × 2048 WebP these land in the low
hundreds of kilobytes, so two hundred places is well under 100 MB.

## What varies between identical runs

Asking for fewer fields returns more rows: Mapillary meters the amount of data
in a response, so `id,is_pano` alone found 89 panoramas across the sample where
`id,is_pano,geometry,compass_angle,thumb_2048_url,creator` found 34.

But the per-site counts move a great deal between runs even so — Røros 5 then
41, Grand-Bassam 13 then 0. So a single query answers **"does this site have a
360"** reliably and **"how many"** not at all.

The site-level rate reproduced exactly: 5 of 45 on both runs. That is the
number to plan with.

## The terms, read in full

Read 19 September 2026 by `tools/read_pages.py` via the `Read the terms`
workflow, from mapillary.com/terms, effective 15 February 2024. The sandbox
cannot reach the page and a text browser was bounced to a Facebook "update
your browser" interstitial, so it was rendered with a real engine. The
quotations below are verbatim.

### Self-hosting is permitted, and named

Section 11 does not merely fail to forbid downloading and re-hosting — it
contemplates it directly:

> "If you are **downloading individual images and serving them from your own
> servers**, you must attribute the image(s) by visibly displaying the
> Mapillary logo and linking back to the Mapillary homepage or corresponding
> Mapillary image page."

So the blocker is lifted. It comes with three conditions.

**One: the Mapillary logo must be visibly displayed.** Not a text credit — the
logo. This is a design constraint on the reveal screen, and it is not
negotiable, so it decides the direction as much as any coverage number does.
Section 7 says the logo "may not be copied, imitated or used... without our
prior written permission"; Section 11 is that permission, for this use.

**Two: the application must be registered** for a `client_id`, and

> "must be designed to provide products or services that materially supplement
> those provided via the Mapillary Services (and not to merely redistribute
> Content or create applications that substantially replicate the
> functionality of Mapillary Services)."

A guessing game that hides the location and asks the player to find it is not
a street-level imagery browser. It supplements rather than replicates. Worth
recording that this is a reading, not a ruling.

**Three: the API must be used as published.** Section 5 forbids "data mining,
robots or similar data gathering or extraction methods not approved by
Mapillary" and requires access "through the currently available, published
interfaces". The Graph API with a token is exactly that. The published rate
limits are generous: 60,000 requests per minute to entity endpoints, 10,000
to search endpoints, 50,000 per day to tiles.

### The licence is not uniformly CC-BY-SA

Section 3 is more careful than the help centre article:

> "Your use of any User Content provided by other users is subject to the
> Creative Commons Share Alike (CC BY-SA) license, **unless we indicate
> otherwise**. For instance, we may provide access to certain User Content...
> under a separate set of license terms (such as the Creative Commons
> Attribution NonCommercial Share Alike (CC BY-NC-SA) license)."

So per-image licence has to be checked rather than assumed. NonCommercial is
refused everywhere else in this project and has to be refused here too.

### ShareAlike binds the panoramas, not the game

`tools/shortlist_models.py` refuses ShareAlike outright, on the reasoning that
"share-alike would bind the game". That reasoning does not carry over, and the
difference is worth stating because the two look identical from a distance.

Resizing a panorama to 4096 × 2048 and re-encoding it as WebP makes an
adaptation, so **the adapted panorama must itself be published under
CC-BY-SA**. That is a cost Heritle can pay: the files are derived from someone
else's work and passing the licence on with them is the deal. It does not
reach the surrounding page. A collection of separately-licensed works is not a
derivative of each of them.

A 3D model is different only in that it would arrive as a mesh baked into the
same file the game ships, which is why that tool draws the line where it does.
Neither position needs changing.

### What each panorama must carry

Both licences apply at once, so the reveal screen needs all of:

- the Mapillary logo, visibly displayed
- a link to the Mapillary homepage or that image's page
- the contributor's username, linked to their profile
- the licence name
- the adapted file published under CC-BY-SA in turn

Mapillary's own model: *"Madeira, Portugal by nunocaldeira, licensed under
CC-BY-SA."*

## Open questions before committing to this

1. **Which of the four options above.** Everything measurable has now been
   measured; this one is a decision about what the game is for.
2. **Per-image licence**, if images are fetched: CC-BY-SA is the default and
   not the guarantee, and NonCommercial is refused.

Settled: the Mapillary logo is accepted, so self-hosting is permitted. Commons
and Poly Haven are surveyed per continent. Africa and Oceania are counted
outright. And the ninety-place spread target, as specified, is not buildable —
not for want of a plan but for want of photographs.
