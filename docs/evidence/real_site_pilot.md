# Real-site pilot - 15 real company websites (REAL data, REAL AI)

**REAL run.** Real websites crawled live from a home connection, real AI providers (Gemini primary, Groq fallback),
default settings (no test hooks). Run #15, 2026-11-18. Nothing here is synthetic; every number below comes from
the database (`scripts/real_pilot.py`). This report - especially the **manual evidence audit** - is the real-world
quality signal for the project; the fixture evaluation (`quality_evaluation.md`) only checks the rules on our own
synthetic pages.

## Company list and where each website came from

The 12 companies named in the brief plus 3 chosen for coverage (a cardlock/fuel distributor, a feed company, and a
clearly non-agricultural organisation). Websites were proposed from web searches and confirmed by the user before
the run; the user also checked: AGRILAND FS (company profiles list agrilandfs.com), Agfinity (SAM.gov lists
agfinityinc.com), ALCIVIA (CropLife Top 100 + its employer profile list alcivia.com; it sold its agronomy unit in
2025-26), Asmus (FMCSA registration + company profile list afschem.com). The full list with a source per company is
`sample-data/real_companies.csv` and is repeated below.

## What happened (in order)

1. `POST /api/uploads` (15 rows: 13 new, 2 already known - Agtegra and Insight FS from earlier tests), then ONE run
   (`POST /api/runs`, Idempotency-Key), processed by one worker process with **2 threads**, default settings.
2. **Gemini's free tier was already exhausted for the day.** Its quota is **20 requests per day per model**
   (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `limit: 20` in the 429 message) and earlier evaluation and
   scenario runs that day had used it. Only 3 Gemini calls succeeded; everything else fell back to Groq, which then
   hit ITS per-minute limit. The first pass ended with 4 jobs `AI_UNAVAILABLE` (crawl fine, both AIs refused) and
   3 jobs `NO_CONTENT` (site refused us):
   - Total time (run created -> finished): 327 s; jobs by status: {'review_required': 5, 'failed': 7, 'completed': 3}
   - AI calls: `groq/openai/gpt-oss-20b` ok: 5 (tokens in/out 14668/5656); `google/gemini-2.5-flash` rate_limited: 64 (tokens in/out 0/0); `groq/openai/gpt-oss-20b` error: 5 (tokens in/out 0/0); `google/gemini-2.5-flash` ok: 3 (tokens in/out 10386/9446); `groq/openai/gpt-oss-20b` rate_limited: 44 (tokens in/out 0/0)
3. **One** manual retry (`POST /api/jobs/{id}/retry`) of the 4 `AI_UNAVAILABLE` jobs only, with the worker
   restarted on **1 thread** to stay under Groq's per-minute limit. The 3 `NO_CONTENT` jobs were NOT retried
   (retrying cannot fix a 403 or a certificate problem). All 4 then succeeded on Groq:

```
[09:15:20Z] failed jobs: [('Top Ag Cooperative', 'NO_CONTENT'), ('Innovative Ag Services (IAS)', 'AI_UNAVAILABLE'), ('ALCIVIA Cooperative', 'AI_UNAVAILABLE'), ('Grow West', 'AI_UNAVAILABLE'), ('River Valley Cooperative (RVC)', 'AI_UNAVAILABLE'), ('Asmus Farm Supply Inc.', 'NO_CONTENT'), ('Kent Nutrition Group', 'NO_CONTENT')]
  POST /api/jobs/145/retry (Innovative Ag Services (IAS)) -> HTTP 200 status=queued max_attempts=6
  POST /api/jobs/148/retry (ALCIVIA Cooperative) -> HTTP 200 status=queued max_attempts=6
  POST /api/jobs/149/retry (Grow West) -> HTTP 200 status=queued max_attempts=6
  POST /api/jobs/150/retry (River Valley Cooperative (RVC)) -> HTTP 200 status=queued max_attempts=6
[09:15:20Z] Innovative Ag Services (IAS): queued (att 3); ALCIVIA Cooperative: queued (att 3); Grow West: queued (att 3); River Valley Cooperative (RVC): queued (att 3)
[09:15:37Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: running (att 4); Grow West: queued (att 3); River Valley Cooperative (RVC): queued (att 3)
[09:15:54Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: running (att 4); River Valley Cooperative (RVC): queued (att 3)
[09:16:11Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: running (att 4); River Valley Cooperative (RVC): queued (att 3)
[09:16:28Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: queued (att 4); River Valley Cooperative (RVC): queued (att 4)
[09:16:45Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: queued (att 4); River Valley Cooperative (RVC): queued (att 4)
[09:17:02Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: queued (att 4); River Valley Cooperative (RVC): queued (att 4)
[09:17:19Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: queued (att 4); River Valley Cooperative (RVC): queued (att 4)
[09:17:36Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: queued (att 4); River Valley Cooperative (RVC): queued (att 4)
[09:17:53Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: running (att 5); River Valley Cooperative (RVC): queued (att 4)
[09:18:10Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:18:27Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:18:44Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:19:01Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:19:19Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:19:36Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:19:53Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:20:10Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:20:27Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:20:44Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:21:01Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:21:18Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): queued (att 5)
[09:21:35Z] Innovative Ag Services (IAS): review_required (att 4); ALCIVIA Cooperative: review_required (att 4); Grow West: review_required (att 5); River Valley Cooperative (RVC): review_required (att 6)
run 15: completed_with_errors counts={'completed': 3, 'review_required': 9, 'failed': 3}
```

## Run data (generated from the database by `scripts/real_pilot.py`)

- Date: 2026-11-18 09:21 UTC; see the first report of this run; run #15
- Machine: Windows-11-10.0.26300-SP0, Python 3.13.5, PostgreSQL 18; one worker process (no test hooks; threads: see the run notes); prompt `p3`, policy `v1`; AI order: google then groq
- Total time (run created -> finished): 811 s; jobs by status: {'review_required': 9, 'failed': 3, 'completed': 3}
- AI calls: `groq/openai/gpt-oss-20b` ok: 9 (tokens in/out 27611/11529); `google/gemini-2.5-flash` rate_limited: 85 (tokens in/out 0/0); `groq/openai/gpt-oss-20b` error: 7 (tokens in/out 0/0); `google/gemini-2.5-flash` ok: 3 (tokens in/out 10386/9446); `groq/openai/gpt-oss-20b` rate_limited: 50 (tokens in/out 0/0)

Answers: Y = yes, P = possible, - = not_found, ? = no answer (job failed). Order: Acct Agro Grain Energy Feed Gas Retail (Accounting = business rule).

| company | domain | job | attempts | pages ok | other page outcomes | homepage redirected to | answers | error | AI |
|---|---|---|---|---|---|---|---|---|---|
| Agtegra Cooperative | agtegra.com | review_required | 1 | 8/8 |  |  | `Y Y Y Y Y Y Y` |  | google |
| AGRILAND FS Inc. | agrilandfs.com | review_required | 1 | 8/8 |  |  | `Y Y Y Y Y P Y` |  | google |
| Insight FS | insightfs.com | review_required | 2 | 8/8 |  | https://fscooperatives.com/insightfs | `Y Y Y Y Y - -` |  | google |
| Top Ag Cooperative | topag.net | failed | 3 | 0/1 | {'http_error': 1} |  | `? ? ? ? ? ? ?` | NO_CONTENT |  |
| Mid Kansas Cooperative (MKC) | mkcoop.com | completed | 2 | 8/8 |  |  | `Y Y Y Y Y - -` |  | groq |
| Innovative Ag Services (IAS) | innovativeag.com | review_required | 4 | 8/8 |  |  | `Y Y Y - Y - -` |  | groq |
| Valley Agronomics (Valley Ag) | valleyag.com | review_required | 1 | 8/8 |  |  | `Y Y - - - - Y` |  | groq |
| Agfinity Inc. | agfinityinc.com | review_required | 2 | 8/8 |  | https://agfinityinc.com/ | `Y Y Y Y P - Y` |  | groq |
| ALCIVIA Cooperative | alcivia.com | review_required | 4 | 7/8 | {'robots_disallowed': 1} |  | `Y - Y Y Y - -` |  | groq |
| Grow West | growwest.com | review_required | 5 | 8/8 |  |  | `Y - - - - - Y` |  | groq |
| River Valley Cooperative (RVC) | rivervalleycoop.com | review_required | 6 | 8/8 |  |  | `Y Y Y Y Y - -` |  | groq |
| Asmus Farm Supply Inc. | afschem.com | failed | 3 | 0/1 | {'http_error': 1} |  | `? ? ? ? ? ? ?` | NO_CONTENT |  |
| Star Oilco | staroilco.net | completed | 2 | 8/8 |  | https://staroilco.net/ | `Y - - Y - - -` |  | groq |
| Kent Nutrition Group | kentnutritiongroup.com | failed | 3 | 0/1 | {'robots_disallowed': 1} |  | `? ? ? ? ? ? ?` | NO_CONTENT |  |
| Mozilla | mozilla.org | completed | 1 | 7/8 | {'http_error': 1} |  | `Y - - - - - -` |  | groq |

### Website sources

| domain | where the website address came from |
|---|---|
| agtegra.com | ZoomInfo + issuu company profiles; crawled successfully in earlier runs |
| agrilandfs.com | LandCAN + company profiles list agrilandfs.com (may redirect to fscooperatives.com like Insight FS) |
| insightfs.com | NCFC member listing + AgriTech Tomorrow press article; redirects to fscooperatives.com/insightfs |
| topag.net | CropLife Top 100 company listing |
| mkcoop.com | issuu publisher page + NCFC member listing |
| innovativeag.com | company's own pages (innovativeag.com/about) |
| valleyag.com | company's own pages (valleyag.com/about) |
| agfinityinc.com | LandCAN + BizWest; SAM.gov lists agfinityinc.com |
| alcivia.com | CropLife Top 100 + employer profile list alcivia.com; agronomy unit sold 2025-26 |
| growwest.com | Rice Farming name-change article + ZoomInfo (private retailer - not a cooperative) |
| rivervalleycoop.com | Craft company profile + CoBank customer story |
| afschem.com | 2017 ARA award application + FMCSA registration + company profile list afschem.com |
| staroilco.net | company's own pages (staroilco.net/pacificpride) - extra: cardlock / fuel |
| kentnutritiongroup.com | company's own pages (kentnutritiongroup.com) - extra: feed-focused |
| mozilla.org | company's own pages (mozilla.org/about) - extra: clearly NOT agricultural |

### Evidence audit list (every site-derived yes / possible quote)

| domain | category | status | quote | source page | judgement |
|---|---|---|---|---|---|
| agtegra.com | agronomy | yes | "Our seed, fertilizer, crop protection and custom application services are specifically prescribed for fields in our cooperative area." | www.agtegra.com/products-services/agronomy | OK |
| agtegra.com | agronomy | yes | "Using prescription fertility products, Agtegra Agronomists can provide timely crop nutrient solutions for optimum crop nutrition, including starter fertilizers, nitrogen blends and foliar blends." | www.agtegra.com/products-services/agronomy | OK |
| agtegra.com | agronomy | yes | "AGRONOMY SERVICES CROP INPUTS & SERVICES" | www.agtegra.com/products-services/agronomy | WEAK - page heading; the other agronomy quotes carry it |
| agtegra.com | energy | yes | "From fuel to propane, we are equipped to meet your residential, agricultural, and commercial energy needs." | www.agtegra.com/products-services/energy | OK |
| agtegra.com | energy | yes | "Agtegra Fuel: (605) 725-8580 Agtegra Propane: (605) 225-6383" | www.agtegra.com/products-services/energy | WEAK - phone numbers; other quotes carry energy |
| agtegra.com | energy | yes | "The Agtegra energy business provides energy products and services to keep Agtegra territory running without interruption." | www.agtegra.com/products-services/energy | OK |
| agtegra.com | feed | yes | "distributes dry feeds, minerals and liquid supplements to wholesale networks and producers on a direct basis." | www.agtegra.com/products-services/feed | OK |
| agtegra.com | feed | yes | "Regardless of stage of production, we can help you find the right feed for your cattle." | www.agtegra.com/products-services/feed | OK |
| agtegra.com | feed | yes | "Our selection of feed products doesn’t end with our general livestock species. We also offer horse, poultry, wildlife, rabbit and pet food too." | www.agtegra.com/products-services/feed | OK |
| agtegra.com | gas_station | yes | "Aberdeen Fuel Station – Cardtrol 811 3rd Ave SE Aberdeen, SD 57401" | www.agtegra.com/products-services/energy | OK |
| agtegra.com | gas_station | yes | "Bowdle Fuel Station – Cardtrol 32491 US HWY 12 Bowdle, SD 57428" | www.agtegra.com/products-services/energy | OK |
| agtegra.com | gas_station | yes | "Milbank C-Store 313 West 4th Ave Milbank, South Dakota 57252" | www.agtegra.com/products-services/energy | OK |
| agtegra.com | grain | yes | "Grain Marketing \| Grain Sales \| Grain Elevators - Agtegra" | www.agtegra.com/products-services/grain | WEAK - page title; supported by other quotes |
| agtegra.com | grain | yes | "Agtegra Cooperative has vigilantly invested in efficient storage and loadout facilities to meet the needs of our customers." | www.agtegra.com/products-services/grain | OK |
| agtegra.com | grain | yes | "CASH BIDS AND FUTURES CASH BIDS FUTURES" | www.agtegra.com/products-services/grain | OK |
| agtegra.com | retail_store | yes | "Ipswich Farm Store 20 5th Ave Ipswich, SD 57451" | www.agtegra.com/products-services/energy | OK |
| agtegra.com | retail_store | yes | "FENCING MATERIAL ANIMAL HEALTH FARM SUPPLY LIVESTOCK HANDLING" | www.agtegra.com/products-services/feed | OK |
| agtegra.com | retail_store | yes | "AGTEGRA FEED AND FARM SUPPLY YOUR TRUSTED FEED/FARM SUPPLY SOURCE" | www.agtegra.com/products-services/feed | OK |
| agrilandfs.com | agronomy | yes | "From quality seed, crop nutrients, and crop protection to custom application, grid sampling, and personalized recommendations, get the best performance from your field before, during, and after the growing season with AG" | www.agrilandfs.com/agronomy_seed/ | OK |
| agrilandfs.com | agronomy | yes | "Talk to your local Agronomist and get a personalized plan that fits you and your operation. Soil testing, field mapping, custom application, crop protection, and nutrients – you can rely on AGRILAND FS to be your trusted" | www.agrilandfs.com/agronomy_seed/ | OK |
| agrilandfs.com | agronomy | yes | "AGRILAND FS offers a full line of crop protection products such as herbicides, pesticides, and insecticides to keep your crops healthy for harvest. Our local Agronomists work with you to offer crop protection solutions a" | www.agrilandfs.com/agronomy_seed/ | OK |
| agrilandfs.com | energy | yes | "AGRILAND FS delivers diesel, gas, propane, DEF, and lubricants to locations across the United States and works with you to create a solution specific to your needs." | www.agrilandfs.com/fuel/ | OK |
| agrilandfs.com | energy | yes | "From 500 and 1,000-gallon propane tanks to 18,000-gallon propane bullets, our experienced Propane Service Team is equipped to install, fix, and maintain your propane system, including regulators and vaporizers." | www.agrilandfs.com/propane/ | OK |
| agrilandfs.com | feed | yes | "When you need more than just a few bags of feed, you can count on AGRILAND FS to deliver the commercial livestock feed you need to ensure operational success and healthy animals. Beef Cattle Swine Dairy Cattle Poultry Cr" | www.agrilandfs.com/feed/ | OK |
| agrilandfs.com | feed | yes | "Our Feed Specialists are experts in the dietary needs and productivity of beef cattle, swine, dairy cows, sheep, poultry, and other animals. From custom-blended bulk feed to bagged feed options, we offer feed products th" | www.agrilandfs.com/ | OK |
| agrilandfs.com | feed | yes | "Burlington Junction’s grain processing facility offers competitive bids and feeds our on-site feed mill with full-service grind and mix capabilities." | www.agrilandfs.com/grain/ | OK |
| agrilandfs.com | gas_station | possible | "18 FAST STOP locations" | www.agrilandfs.com/ | OK as possible - FAST STOP is a convenience/fuel format, pumps not stated |
| agrilandfs.com | gas_station | possible | "Propane Bottle Fill Locations Fuel your grill, smoker, outdoor fire pit, and more with propane bottle fills from AGRILAND FS. Visit any of these locations to get your propane bottle filled." | www.agrilandfs.com/propane/ | OK as possible - bottle fills are not vehicle fueling |
| agrilandfs.com | grain | yes | "Looking for Cash Bids & Futures? Log in to your myFS Solution Center account to see our current Cash Bids and Futures at Hopkins and Clarinda." | www.agrilandfs.com/grain/ | OK |
| agrilandfs.com | grain | yes | "Our knowledgeable and experienced AGRILAND FS Grain Merchandisers provide competitive prices, transportation needs, and drying and storage services. We meet the demands of the producer and the consumer, supplying grain t" | www.agrilandfs.com/grain/ | OK |
| agrilandfs.com | retail_store | yes | "Our extensive network of retail supply locations and distribution hubs allows us to supply truckload and pallet quantities of products to large commercial accounts." | www.agrilandfs.com/turf/ | QUESTIONABLE - describes wholesale/commercial supply, not a store open to the public |
| agrilandfs.com | retail_store | yes | "AGRILAND FS is a leading supplier of bagged and bulk salt and ice melt products. We have more than 20 locations throughout the state for bagged ice melt and product distribution hubs" | www.agrilandfs.com/turf/ | QUESTIONABLE - product distribution points, weak store signal |
| insightfs.com | agronomy | yes | "Having access to the best traits and genetics in the industry allows our Insight FS seed product managers to choose the right seed for your operation." | fscooperatives.com/insightfs/agriculture/seed | OK |
| insightfs.com | agronomy | yes | "We offer a full line of herbicides, pesticides, and insecticides to keep your fields clean and your crops healthy. Between our lineup of products from industry leading manufacturers, to our proprietary portfolio, and our" | fscooperatives.com/insightfs/agriculture/crop-protection | OK |
| insightfs.com | agronomy | yes | "We provide feed, agronomy, propane, fuels, lubricants, agri-finance, seed, and turf products and services, as well as grain marketing, to our patrons." | fscooperatives.com/insightfs | OK |
| insightfs.com | energy | yes | "At Insight FS, we are an agricultural and energy business, serving customers from 23 locations. We provide feed, agronomy, propane, fuels, lubricants, agri-finance, seed, and turf products and services, as well as grain " | fscooperatives.com/insightfs | OK |
| insightfs.com | energy | yes | "Propane Reliable energy for farms, homes, and businesses Fuels Premium fuels to keep you running" | fscooperatives.com/insightfs | OK |
| insightfs.com | energy | yes | "We provide 24/7 emergency service, installation, leak checks, pressure checks, tank and equipment maintenance, scheduled deliveries, and more so you can count on safe," | fscooperatives.com/insightfs/residential/propane | OK |
| insightfs.com | feed | yes | "Feed and Nutrition" | fscooperatives.com/insightfs | WEAK - menu heading (kept, the 25-char rule needs another quote for yes - it has one) |
| insightfs.com | feed | yes | "Feed solutions and nutritionist consultations" | fscooperatives.com/insightfs | OK |
| insightfs.com | feed | yes | "We provide feed, agronomy, propane, fuels, lubricants, agri-finance, seed, and turf products and services, as well as grain marketing, to our patrons." | fscooperatives.com/insightfs | OK |
| insightfs.com | grain | yes | "Insight FS provides producers with access to world grain markets that enable you to plan your grain handling, storage and marketing activities to compliment your on-farm storage capabilities and achieve your profitabilit" | fscooperatives.com/insightfs/agriculture/grain-marketing/cash-bids-new | OK |
| insightfs.com | grain | yes | "Grain Marketing Competitive grain bids and pricing programs" | fscooperatives.com/insightfs | OK |
| mkcoop.com | agronomy | yes | "MKC - Agronomy \| Agronomy services delivered by professional applicators" | www.mkcoop.com/services/agronomy | OK |
| mkcoop.com | agronomy | yes | "Treat manure lagoons, compost, poultry litter, swine facilities and other organic wastes with Wasteaway" | www.mkcoop.com/services/agronomy | WEAK - a waste-treatment product, not crop inputs; the applicator quote carries agronomy |
| mkcoop.com | energy | yes | "MKC operates one of the top professional energy departments in the state of Kansas and is dedicated to the success of our customers, both commercial and agricultural." | www.mkcoop.com/ | OK |
| mkcoop.com | feed | yes | "We deliver top-notch nutrition programs, great customer service and the best quality products. Our team understands how important performance is to your livestock operation." | www.mkcoop.com/ | OK |
| mkcoop.com | grain | yes | "We make strategic investments in our grain business, and we’ve established partnerships to align cooperative- and farmer-owners in the Southern Plains with customers around the world. A quarter billion bushels pass throu" | www.mkcoop.com/services/grain | OK |
| mkcoop.com | grain | yes | "The MKC Grain Exchange Program provides an opportunity for farmers to transfer bushels of their current year wheat crop to MKC in exchange for certified seed wheat for the next growing season." | www.mkcoop.com/services/agronomy | OK |
| innovativeag.com | agronomy | yes | "Our Agronomy Team understands that every field is different and requires a unique solution to reach its full potential." | www.innovativeag.com/customer#market-commentary | WEAK - generic, but agronomy is plausibly right |
| innovativeag.com | feed | yes | "IAS also purchases dried distiller grains with solubles (DDGS) for use at our feed mills." | www.innovativeag.com/grain | OK |
| innovativeag.com | grain | yes | "IAS takes pride in being a leader in marketing alternatives for our grain producers." | www.innovativeag.com/grain | OK |
| valleyag.com | agronomy | yes | "Valley Ag operates as a full-service agricultural retail company, offering a comprehensive range of products and services including seed, crop nutrition, crop protection, and precision farming solutions." | www.valleyag.com/about/ | OK |
| valleyag.com | retail_store | yes | "Valley Ag operates as a full-service agricultural retail company, offering a comprehensive range of products and services including seed, crop nutrition, crop protection, and precision farming solutions." | www.valleyag.com/about/ | QUESTIONABLE - 'agricultural retail' of crop inputs; no store address/hours quoted -> possible |
| agfinityinc.com | agronomy | yes | "We offer the ability to work with local seed experts and a wide selection of top-performing seed brands including Dekalb, Croplan, and more." | agfinityinc.com/agronomy/seed-solution/ | OK |
| agfinityinc.com | agronomy | yes | "Our crop nutrition services include Soil and Tissues Sampling Plant Nutrition Products Custom Application" | agfinityinc.com/agronomy/crop-nutrition-2/ | OK |
| agfinityinc.com | energy | yes | "Propane Refined Fuels Lubricants Nevoo Monitors Consumer Propane Plan" | agfinityinc.com/ | WEAK - menu text, but specific products |
| agfinityinc.com | feed | possible | "Feed Products" | agfinityinc.com/ | OK as possible - menu heading only |
| agfinityinc.com | grain | yes | "Grain Commodities and Procurement" | agfinityinc.com/ | WEAK - menu heading only; yes is plausible but under-evidenced |
| agfinityinc.com | retail_store | yes | "C-Store Town & Country Ace Hardware" | agfinityinc.com/ | OK - names store formats (menu text) |
| alcivia.com | energy | yes | "Manage grain, fuel, propane, payments, contracts, and more in one easy-to-use platform." | www.alcivia.com/ | WEAK - customer-portal sentence; energy is plausibly right |
| alcivia.com | feed | yes | "We offer custom blended rations, bagged and bulk feed options, and flexible delivery or pickup." | www.alcivia.com/feed-2/ | OK |
| alcivia.com | feed | yes | "Feed Solutions Built Around Your Operation" | www.alcivia.com/feed-2/ | OK |
| alcivia.com | grain | yes | "ALCIVIA will only contract grain during open market hours (Mon-Fri 8:30 am-1:15 pm, excluding market holidays)." | www.alcivia.com/ | OK |
| alcivia.com | grain | yes | "ALCIVIA grain cash bids and futures prices below." | www.alcivia.com/ | OK |
| growwest.com | retail_store | yes | "Sonoma Retail 23199 Maffei Road, Sonoma, CA 95476 707-939-1820" | www.growwest.com/ | OK |
| growwest.com | retail_store | yes | "23 retail, farm supply and wholesale manufacturing locations throughout California." | www.growwest.com/about-us | OK |
| rivervalleycoop.com | agronomy | yes | "Provide custom applications by certified agronomy professionals." | www.rivervalleycoop.com/products-services/agronomy | OK |
| rivervalleycoop.com | agronomy | yes | "seed, fertilizer, crop protection products, and custom application services." | www.rivervalleycoop.com/ | OK |
| rivervalleycoop.com | energy | yes | "We’re a full-service provider of propane to homes, farms and businesses." | www.rivervalleycoop.com/products-services/energy | OK |
| rivervalleycoop.com | energy | yes | "Let the professionals at River Valley Cooperative shoulder the responsibility when it comes to your needs for propane, refined fuels and quality oils and lubricants." | www.rivervalleycoop.com/products-services/energy | OK |
| rivervalleycoop.com | feed | yes | "River Valley Cooperative supplies quality bulk feed for swine and poultry throughout eastern Iowa and Western Illinois." | www.rivervalleycoop.com/products-services/feed | OK |
| rivervalleycoop.com | grain | yes | "DAILY CLOSING GRAIN BIDS" | www.rivervalleycoop.com/products-services/grain | OK - heading, but specific to grain buying |
| rivervalleycoop.com | grain | yes | "Our full-time team of merchandisers and grain buyers is here to help you reach your grain marketing objectives." | www.rivervalleycoop.com/products-services/grain | OK |
| rivervalleycoop.com | grain | yes | "More than 40 million bushels of licensed storage space between our facilities in Iowa and Illinois." | www.rivervalleycoop.com/products-services/grain | OK |
| staroilco.net | energy | yes | "we make it our business to provide Portland, Vancouver and the Pacific Northwest with diesel, bio-diesel, off-road diesel (dyed diesel), and gasoline." | staroilco.net/ | OK |
| staroilco.net | energy | yes | "We are one of the largest distributors of Biodiesel in the Portland area and we are committed to sustainability by providing biofuels to both retail and commercial customers." | staroilco.net/ | OK |
| staroilco.net | energy | yes | "Bulk Fuel Deliveries: On-Road Diesel Off-Road Diesel Biodiesel Kerosene Gasoline Onsite Refueling Service: On Road Diesel Off Road Diesel Biodiesel Bulk Fueling - We Keep It Simple - We Keep It Full" | staroilco.net/bulk-fuel/ | OK |

## Why 3 sites failed (checked with our crawler afterwards)

```
https://www.topag.net
  robots.txt: outcome=http_error http=403 detail=HTTP 403 first lines=''
  homepage:   outcome=http_error http=403 detail=HTTP 403 final=https://www.topag.net/
https://www.afschem.com
  robots.txt: outcome=http_error http=403 detail=HTTP 403 first lines=''
  homepage:   outcome=http_error http=403 detail=HTTP 403 final=https://www.afschem.com/
https://www.kentnutritiongroup.com
  robots.txt: outcome=error http=None detail=ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1028) first lines=''
  homepage:   outcome=error http=None detail=ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1028) final=None
```

| Site | Real cause | Shown in the app as |
|---|---|---|
| topag.net | HTTP **403** on every page, even robots.txt - the site refuses our crawler (bot protection) | homepage `http_error` 403 -> job `failed` `NO_CONTENT` |
| afschem.com | HTTP **403**, same as above | same |
| kentnutritiongroup.com | **TLS certificate chain cannot be verified** by Python (`CERTIFICATE_VERIFY_FAILED`); robots.txt is therefore "unreachable", which by RFC 9309 means "disallow everything" | homepage `robots_disallowed` -> `NO_CONTENT` (**misleading label** - the real cause is TLS; see findings) |

All three correctly end as a failed job with NO answers ("not scanned"), never as seven "not_found".

## Manual evidence audit (by the developer)

Each site-derived yes / possible quote above was read and judged (judgement column): **78 quotes - 66 OK,
9 weak, 3 questionable**. "Weak" = the quote is a heading, phone number or generic sentence. For most weak
quotes another quote for the same answer is solid; **four answers rest on a weak quote alone**: Agfinity grain
(menu heading), Agfinity energy (menu text), ALCIVIA energy (customer-portal sentence) and IAS agronomy (generic
sentence) - plausible, but under-evidenced. "Questionable" = the quote does
not really show what the category requires.

Answers I judge WRONG or doubtful after reading the crawled pages (checked in the database):

```
growwest.com (job 149): 8 pages
  ok    https://www.growwest.com/                                                   chars=  4478 hits=['agronom']
  ok    https://www.growwest.com/about-us                                           chars=  8988 hits=['fertiliz']
  ok    https://www.growwest.com/home                                               chars=  4478 hits=['agronom']
  ok    https://www.growwest.com/services/wholesale                                 chars=  3045 hits=['crop protection', 'fertiliz']
  ok    https://www.growwest.com/services/organics                                  chars=  3182 hits=['crop protection', 'fertiliz', 'seed']
  ok    https://www.growwest.com/services/trucking                                  chars=  3549 hits=['fertiliz']
  ok    https://www.growwest.com/services/engineering                               chars=  3144 hits=['fertiliz', 'seed']
  ok    https://www.growwest.com/services/retail                                    chars=  1962 hits=['crop protection', 'fertiliz', 'pca', 'pest control advis']

staroilco.net (job 152): 8 pages
  ok    https://www.staroilco.net/                                                  chars=  6091 hits=['cardlock', 'pacific pride']
  ok    https://staroilco.net/cardlock                                              chars=  5146 hits=['cardlock', 'pacific pride']
  ok    https://staroilco.net/diesel-fuel-storage-tanks                             chars=  6274 hits=[]
  ok    https://staroilco.net/on-site-refueling                                     chars=  5357 hits=['cardlock']
  ok    https://staroilco.net/bulk-fuel                                             chars=  4167 hits=['cardlock']
  ok    https://staroilco.net/common-carrier-services                               chars=  4071 hits=[]
  ok    https://staroilco.net/pfm                                                   chars=  9958 hits=[]
  ok    https://staroilco.net/generator-fuel-testing-guide                          chars=  5901 hits=[]

mkcoop.com (job 144): 8 pages
  ok    https://www.mkcoop.com/                                                     chars=  2893 hits=['convenience']
  ok    https://www.mkcoop.com/about                                                chars= 23542 hits=[]
  ok    https://www.mkcoop.com/about/applications                                   chars= 23542 hits=[]
  ok    https://www.mkcoop.com/about/board-and-leadership                           chars= 23542 hits=[]
  ok    https://www.mkcoop.com/about/sustainability                                 chars=  1873 hits=[]
  ok    https://www.mkcoop.com/services                                             chars=  1641 hits=[]
  ok    https://www.mkcoop.com/services/grain                                       chars=  2098 hits=['convenience']
  ok    https://www.mkcoop.com/services/agronomy                                    chars=  7754 hits=[]

valleyag.com (job 146): 8 pages
  ok    https://www.valleyag.com/                                                   chars=  1522 hits=['store']
  ok    https://www.valleyag.com/about                                              chars=  4378 hits=['store']
  ok    https://www.valleyag.com/locations                                          chars=  1070 hits=[]
  ok    https://www.valleyag.com/agronomy                                           chars=  6588 hits=['store']
  ok    https://www.valleyag.com/other-services                                     chars=  1921 hits=['store']
  ok    https://www.valleyag.com/member-hub!                                        chars=  5721 hits=['store']
  ok    https://www.valleyag.com/agronomy/adjuvants-interlock                       chars=  2188 hits=['store']
  ok    https://www.valleyag.com/valley-ag-fertilizer-program                       chars=  5883 hits=['store']
```

| Company | Category | System said | My judgement | Why |
|---|---|---|---|---|
| Grow West | agronomy | not_found | **wrong - should be yes** | crawled pages mention crop protection, fertilizer and PCAs (pest control advisers) on `/services/retail`; the model (Groq) missed it |
| Star Oilco | gas_station | not_found | **wrong - should be yes** | `/cardlock` was crawled and describes Pacific Pride cardlock fueling; the model (Groq) missed it |
| Valley Ag | retail_store | yes | doubtful - possible | only "agricultural retail company" (crop inputs); no store address / hours quoted |
| AGRILAND FS | retail_store | yes | doubtful - possible | quotes describe wholesale supply and distribution points |
| Agfinity | grain, energy | yes | plausible but under-evidenced | only menu text ("Grain Commodities and Procurement"; "Propane Refined Fuels Lubricants ...") |
| ALCIVIA / IAS | energy / agronomy | yes | plausible but under-evidenced | one generic sentence each |
| MKC / IAS / RVC | gas_station, retail_store | not_found | cannot verify | the crawled pages (8-page budget) did not show stations or stores; these co-ops may have them on pages we did not reach |
| ALCIVIA | agronomy | not_found | consistent with the facts | the co-op sold its agronomy unit in 2025-26; the site no longer shows it |
| Mozilla | all six | not_found | correct | non-agricultural control: only the Accounting business rule says yes |

**Summary:** of 12 classified companies (72 site answers), 2 answers are clearly wrong (both false negatives from
the Groq fallback model), 2 `yes` answers are doubtful and should be `possible`, the rest are supported by verified
quotes. Every quote shown is verbatim from the crawled page (validation drops anything else). 9 of 12 jobs were
sent to review (`review_required`), so a reviewer sees most of these cases anyway.

## Findings and follow-ups (honest)

1. **Free-tier AI quota is the bottleneck.** Gemini's daily free quota (20 requests/model/day) was gone; with the
   fallback on a per-minute limit, 15 companies needed a retry. The system behaved correctly (backoff, fallback,
   `AI_UNAVAILABLE`, manual retry works), but a real batch needs a paid tier or a per-provider budget.
2. **No circuit breaker for a provider that is out for the day.** Every attempt still tried Gemini 3 times first
   (85 Gemini 429 rows in `ai_usage`). Follow-up: when a provider says its DAILY quota is exhausted, skip it until
   the next day.
3. **Groq fallback quality is lower.** Both clear errors came from `openai/gpt-oss-20b`; Groq also returned 3
   `LengthFinishReasonError` (answer cut off by the output-token limit) and 2 HTTP 400 responses, recorded as
   `AI_ERROR` (not retried, next provider).
4. **TLS chain problem shown as robots_disallowed.** Follow-up: record "robots.txt unreachable: <reason>" as the
   page detail, and consider the OS certificate store (`truststore`) so sites that browsers accept also work here.
5. **Duplicate pages waste the 8-page budget** (MKC `/about*` pages with identical text; Grow West `/` and `/home`).
   Follow-up: skip a page whose text hash equals one already crawled.
6. **Two sites block bots outright (403).** Respected as-is; such companies need manual research.

## Follow-up: fixes made after this pilot (2026-11-18)

| Finding above | Fix |
|---|---|
| 1-2. Gemini daily quota gone, still called 3x per attempt (85 wasted calls) | Quota breaker: a daily-quota 429 is not retried and the provider is skipped for 30 min by that worker (`skipped_quota` rows, no call) |
| 3. Groq 20b weaker; `LengthFinishReasonError` | Groq default is now `openai/gpt-oss-120b`; output limit raised to 8,192 tokens; a cut-off answer is treated as invalid output and retried |
| 5. Duplicate pages waste the page budget | Pages with text identical to an earlier page are marked `duplicate_of:<url>`, not counted, not sent to the AI |
| 4. TLS chain problem shown as `robots_disallowed` | Not fixed yet (still open) |

These fixes are covered by automated tests; the pilot itself was NOT re-run, so the numbers above are still the
numbers of run #15.
