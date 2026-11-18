# Crawl coverage improvement: sitemap discovery, category-balanced selection, 12-page budget (REAL)

**Found on the live site (2026-11-18):** Agfinity (agfinityinc.com) came back Gas Station = Not found although the
company runs C-Stores with pumps and an Ace Hardware. Cause: the crawler's 8 page slots went to the homepage + 7
agronomy sub-pages (every agronomy link matched the old "high priority" words equally), so no store, fuel or
location page was ever fetched.

**Fix** (`backend/app/crawler/crawl.py`, `backend/app/crawler/sitemap.py`):
1. Page budget 8 -> **12** (`CRAWL_MAX_PAGES`); total bytes (5 MB, sitemaps included) and the 120 s per-site
   deadline unchanged.
2. **Sitemap discovery** after the homepage: robots.txt `Sitemap:` lines, else `/sitemap.xml`; one nested index
   level; max 3 files x 500 KB, 1,000 URLs; same SSRF-checked fetch, same-site only, robots.txt respected; regex
   parsing (no XML entity expansion).
3. **Weighted words per category group** in URL path + link text (whole words: "ace" matches `/ace-hardware`, not
   `/marketplace`).
4. **Category-balanced selection:** first one page per group (agronomy, grain, energy, feed, gas station, retail
   store, locations), then by score minus 3 per page already fetched from the same folder. Deterministic.

## Test environment

- Date 2026-11-18, Windows 11, local PostgreSQL 18, `python -m app.classifier.cli <url> --quiet`.
- AI: **`gemini-2.5-flash-lite`** (command-only override `GOOGLE_MODEL=gemini-2.5-flash-lite`; the live site uses
  `gemini-2.5-flash`), Groq fallback configured but never needed.
- One run per site per version (sample size 1): an LLM can answer differently on a re-run.

## Agfinity - before / after

| | BEFORE (job #155, old crawler) | AFTER (job #161, new crawler) |
|---|---|---|
| pages | 8 (homepage + 7 agronomy pages) | 12 (1 per group + 4 by score) |
| sitemap | not read | 3 files (`sitemap.xml` index -> `page-sitemap.xml`, `post-sitemap.xml`), 133 new candidates |
| crawl bytes / time | - | 2.1 MB, ~17 s |
| job status | review_required (a quote failed verification) | **completed**, no issues |

Pages fetched AFTER, and why: homepage; `/agronomy/seed-solution` (first for agronomy);
`/grain/grain-commodities-procurement` (grain); `/energy/fuel-vs-propane-faq` (energy, from sitemap);
`/bulk-livestock-feed-email-sign-up` (feed, from sitemap); `/mead-c-store` (gas station); `/retail/ace-hardware`
(retail store); `/connect/locations` (locations); then by score `/retail/ace-hardware-and-animal-feed-delivery`,
`/feed-grain/feed-products-3`, `/agronomy/crop-nutrition-2`, `/feed-grain/nutritional-services-2`.
BEFORE: homepage, `/agronomy`, `/agronomy/seed-solution`, `/agronomy/crop-nutrition-2`,
`/agronomy/crop-protection-3`, `/agronomy/turf-ornamental`, `/agronomy/ice-melt-services`, `/agronomy/cfa-financial`.

| Category | BEFORE | AFTER (first verified quote) |
|---|---|---|
| Agronomy | yes | yes - "Our crop nutrition services include Soil and Tissues Sampling Plant Nutrition Pro..." (`/agronomy/crop-nutrition-2`) |
| Grain | **not_found** (model said yes, its quote "FEED & GRAIN / Grain Commodities and Procurement" could not be verified) | **yes** - "The 2.5 million bushels of on-site grain storage has the ability to unload 30,000..." (`/grain/grain-commodities-procurement`) |
| Energy | yes - menu text "ENERGY Propane Refined Fuels Lubricants" (homepage) | yes - the same menu text, now on 2 pages (weak; see caveats) |
| Feed | yes - menu text "FEED & GRAIN Feed Products" | yes - "Our services include ration & supplement formulation, custom formulation & biddin..." (`/feed-grain/nutritional-services-2`) |
| Gas Station | **not_found** | **yes** - "24-hour pay-at-pump fueling" / "Pay-at-Pump Fueling: 24 hours" (`/connect/locations`) |
| Retail Store | yes - menu text "RETAIL C-Store Town & Country Ace Hardware" only | yes - "Our Brighton Ace Hardware is your local one-stop-shop for your home improvement, ..." (`/retail/ace-hardware`) + "Eaton C-Store ... Address 55 Oak Avenue Eaton, CO 80615" (`/connect/locations`) |
| Accounting | yes (rule) | yes (rule) |

## Agtegra (regression check) - before / after

| | BEFORE (job #156) | AFTER (job #162) |
|---|---|---|
| pages | 8: homepage, `/products-services` + agronomy, energy, feed, grain, innovation-center, `/locations` | 12: 1 per group (crop inputs, historical cash bids, propane, show livestock, **Aberdeen Fuel Station**, **Ipswich Farm Store**, harvest hours) + 2 cash-bid years, propane safety, agronomy |
| sitemap | not read | 1 file (`/googlesitemap`, named in robots.txt), 339 new candidates |
| crawl bytes / time | - | 1.1 MB, ~21 s |
| job status | review_required | review_required |

All six site categories were **yes in both runs** (no regression); Accounting = yes (rule). `review_required` in
both runs comes from the existing reviewer correction on Grain (scenario E: the human answer conflicts with the
scan), not from the crawl. AFTER evidence is more specific, e.g. Gas Station "Cardtrol - Accepts Visa, MasterCard,
Discover, WEX and Agtegra gas card" (`/locations/aberdeen-fuel-station-cardtrol`) instead of a station name on the
locations list; Retail "Agtegra's Ipswich Farm Store location handles feed, farm supply, livestock equipm..."
(`/locations/ipswich-farm-store-cardtrol-bulk-fu...`).

## Fixture sites (no AI)

All 14 fixture sites have at most 6 pages, below both the old (8) and new (12) budget, so every page is fetched
with either crawler and the AI input of `scripts/evaluate.py` is unchanged. Checked with a crawl-only run against
the fixture server (every site: all its pages fetched; `robots-blocked` correctly fetches nothing; no fixture has a
sitemap). The fixture AI evaluation was **not** re-run, to stay inside the free-tier AI budget.

## AI calls used (all `google / gemini-2.5-flash-lite`, all first-try `ok`)

| ai_usage id | site | crawler version | tokens in / out |
|---|---|---|---|
| 285 | Agfinity | before | 2481 / 806 |
| 286 | Agtegra | before | 4334 / 1084 |
| 287 | Agfinity | after v1 | 3674 / 1152 |
| 288 | Agtegra | after v1 | 3465 / 1099 |
| 289 | Agtegra | after v2 | 3366 / 1232 |
| 290 | Agfinity | after v2 | 3850 / 1067 |
| 291 | Agfinity | **final** | 3575 / 1046 |
| 292 | Agtegra | **final** | 3366 / 1232 |

8 calls in total. The intermediate versions found two problems that were fixed before the final runs:
v1 - a page hinting at two groups (`/feed-grain/...`) covered the wrong one, so "first page for feed" was chosen 4
times; fixed by "a page covers the group it was chosen for" + "most specific page wins". v1 also spent 4 of
Agtegra's 12 slots on `historical-cash-bids/<year>` pages; v2 strictly preferred untouched folders, which made
Agfinity fetch weak `about-us/...application` pages; final: score minus 3 per page already fetched from the folder.

## Caveats

- Sample size 1 per site and version, with the lite model; a re-run can differ. The live system uses
  `gemini-2.5-flash` - the author will re-scan Agfinity on the live site.
- Agfinity Energy is still supported only by the site's **navigation menu text** ("ENERGY Propane Refined Fuels
  Lubricants"): the chosen energy page was a propane FAQ, and `/energy/refined-fuels` was not fetched. A quote from
  a menu is verbatim but weak evidence.
- Word lists are hand-made from these co-op sites; other sites name sections differently.
- The 12-page budget still misses evidence on sites with many sections; JavaScript-only pages are still not read.
- Crawls take longer (up to ~20 s here, from 12 pages + sitemaps); the 120 s deadline is checked before every fetch.
