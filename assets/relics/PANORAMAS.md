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

## Wikimedia Commons — thin, and easy to overcount

A 2:1 aspect ratio is how an equirectangular panorama is recognised, and it is
**necessary but not sufficient**: plenty of wide or cropped photographs land
near 2:1 by accident. Of six apparent hits across fourteen famous sites, only
the Colosseum's was unambiguously a 360 — a CC0 HDRI by Greg Zaal and Rico
Cilliers via Poly Haven. One was a church in **Cusco**, not Barcelona.

The definitive test is the GPano XMP tag (`ProjectionType=equirectangular`),
not the shape. That has not been implemented yet.

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

1. **Whether a Europe-heavy pool is the game you want**, or whether the pool
   shrinks to roughly ninety for the sake of spread. Measured above; the
   choice is not a technical one.
2. **Whether the Mapillary logo belongs on the reveal screen.** Required by
   the terms, so it is accept-or-abandon rather than a preference.
3. **Where the thin rows get filled from**, if neither pool size is
   acceptable. Commons and Poly Haven are the candidates and neither has been
   surveyed per continent.
4. **Per-image licence**, once images are actually fetched: CC-BY-SA is the
   default and not the guarantee.
