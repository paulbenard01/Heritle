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

## The finding that matters: coverage is street-shaped

The five hits were not scattered. They were **Rjukan–Notodden (12 panoramas),
Grand-Bassam (13), Røros (5), Pienza (3), Speyer Cathedral (1)** — and four of
the five are inhabited historic *towns*, not single monuments.

That is what street-level imagery is. Someone drives or walks a route with a
360 rig, so a historic town centre gets dozens and a temple on a hill gets
none. The zeroes are the tell: Konark Sun Temple, Tsodilo, Mount Kumgang,
Jiuzhaigou Valley, the Rice Terraces of the Philippine Cordilleras, Lake
Turkana, Djenné, the Sacred Mijikenda Kaya Forests — nothing at all.

So 200 places is reachable in principle, but the 200 you would reach are
biased towards **European historic town centres**. Four of the five hits here
were European. A game built on this pool would ask the player to place a
cobbled street in Norway rather more often than it asked about Angkor.

Only 11% have a 360 while 49% have *some* imagery, which says most Mapillary
contributions are flat phone and dashcam frames rather than spherical rigs.

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

## Open questions before committing to this

1. **Mapillary's API terms.** The imagery is CC-BY-SA, but Mapillary's own
   terms place conditions on bulk download and redistribution that a Creative
   Commons licence does not settle. To be read before the first image is
   cached.
2. **Whether a street-biased pool is the game you want.** This is the real
   question, the only one left, and it is not a technical one.
