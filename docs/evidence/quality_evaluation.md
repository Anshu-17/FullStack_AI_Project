# Quality evaluation - labelled fixture websites (SMALL SYNTHETIC SET)

> **Synthetic data.** Hand-written fixture pages served locally (`fixtures/sites/`), labelled from the brief's rules (`sample-data/labelled_fixtures.csv`). This checks that the rules are applied; it is NOT an accuracy measure on real websites. Sample: 9 sites x 6 site categories = 54 answers.

- Date: 2026-11-18 08:53 UTC; run #11 (81 s)
- Pipeline: real crawl (local fixture server) -> real AI -> validation; prompt `p3`, policy `v1`; AI order: google then groq
- Models that produced the answers: `google/gemini-2.5-flash` (54 answers)
- AI calls: google rate_limited: 1 (tokens in/out 0/0); google ok: 9 (tokens in/out 7705/10821)
- Accounting is a business rule (always yes) and is not evaluated. Positive class = `yes`.

## Jobs

| site | job status | error |
|---|---|---|
| clear-coop.fixture.test | completed |  |
| grain-farm-only.fixture.test | completed |  |
| fuel-delivery-only.fixture.test | completed |  |
| pet-store.fixture.test | completed |  |
| online-catalog.fixture.test | completed |  |
| outdated-elevator.fixture.test | review_required |  |
| feed-mill.fixture.test | completed |  |
| cardlock-fuel.fixture.test | completed |  |
| prompt-injection.fixture.test | completed |  |

## Precision / recall per category (positive = yes)

| category | precision | recall | exact match |
|---|---|---|---|
| agronomy | 100% (3/3) | 100% (3/3) | 100% (9/9) |
| grain | 100% (1/1) | 100% (1/1) | 100% (9/9) |
| energy | 100% (3/3) | 100% (3/3) | 100% (9/9) |
| feed | 100% (2/2) | 100% (2/2) | 100% (9/9) |
| gas_station | 100% (2/2) | 100% (2/2) | 100% (9/9) |
| retail_store | 100% (2/2) | 100% (2/2) | 100% (9/9) |

**Overall exact match (expected status == predicted status): 100% (54/54)**

## Confusion tables (rows = expected, columns = predicted)

**agronomy**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 3 | 0 | 0 | 0 |
| possible | 0 | 0 | 0 | 0 |
| not_found | 0 | 0 | 6 | 0 |

**grain**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 1 | 0 | 0 | 0 |
| possible | 0 | 1 | 0 | 0 |
| not_found | 0 | 0 | 7 | 0 |

**energy**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 3 | 0 | 0 | 0 |
| possible | 0 | 0 | 0 | 0 |
| not_found | 0 | 0 | 6 | 0 |

**feed**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 2 | 0 | 0 | 0 |
| possible | 0 | 0 | 0 | 0 |
| not_found | 0 | 0 | 7 | 0 |

**gas_station**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 2 | 0 | 0 | 0 |
| possible | 0 | 0 | 0 | 0 |
| not_found | 0 | 0 | 7 | 0 |

**retail_store**

| expected \ predicted | yes | possible | not_found | missing |
|---|---|---|---|---|
| yes | 2 | 0 | 0 | 0 |
| possible | 0 | 0 | 0 | 0 |
| not_found | 0 | 0 | 7 | 0 |

## Per site: expected vs predicted

| site | agronomy | grain | energy | feed | gas_station | retail_store |
|---|---|---|---|---|---|---|
| clear-coop | yes | yes | yes | yes | yes | yes |
| grain-farm-only | not_found | not_found | not_found | not_found | not_found | not_found |
| fuel-delivery-only | not_found | not_found | yes | not_found | not_found | not_found |
| pet-store | not_found | not_found | not_found | not_found | not_found | yes |
| online-catalog | not_found | not_found | not_found | not_found | not_found | not_found |
| outdated-elevator | yes | possible | not_found | not_found | not_found | not_found |
| feed-mill | not_found | not_found | not_found | yes | not_found | not_found |
| cardlock-fuel | not_found | not_found | yes | not_found | yes | not_found |
| prompt-injection | yes | not_found | not_found | not_found | not_found | not_found |

## Evidence audit: every yes / possible with its verified quote

Judgement column: filled in by hand after reading the quote (OK = the quote supports the answer).

| site | category | status | quote | source | judgement |
|---|---|---|---|---|---|
| clear-coop | agronomy | yes | "Our agronomy team sells seed, fertilizer and crop protection products to growers." | clear-coop.fixture.test/agronomy | OK |
| clear-coop | agronomy | yes | "We also offer custom application, soil sampling and precision agriculture services." | clear-coop.fixture.test/agronomy | OK |
| clear-coop | energy | yes | "We deliver propane and diesel fuel to farms and homes." | clear-coop.fixture.test/energy | OK |
| clear-coop | energy | yes | "Our energy department also sells lubricants and heating oil." | clear-coop.fixture.test/energy | OK |
| clear-coop | feed | yes | "Our feed mill produces bulk and bagged livestock feed for cattle, hogs and poultry." | clear-coop.fixture.test/feed | OK |
| clear-coop | feed | yes | "Our animal nutrition specialists design mineral and supplement programs." | clear-coop.fixture.test/feed | OK |
| clear-coop | gas_station | yes | "Our 24/7 cardlock fuel station at 15 Highway 30 has unattended pumps for diesel and gasoline." | clear-coop.fixture.test/locations | OK |
| clear-coop | grain | yes | "We buy corn and soybeans at our three grain elevators." | clear-coop.fixture.test/grain | OK |
| clear-coop | grain | yes | "Daily cash bids are posted every morning, and our grain merchandisers offer forward contracts and grain storage." | clear-coop.fixture.test/grain | OK |
| clear-coop | retail_store | yes | "Visit our farm store at 210 Main Street, Ames, open Monday-Friday 7am-6pm, selling hardware, fencing, work wear and lawn and garden supplies." | clear-coop.fixture.test/locations | OK |
| fuel-delivery-only | energy | yes | "Northland Propane delivers bulk propane and heating oil to homes and farms across six counties." | fuel-delivery-only.fixture.test/ | OK |
| fuel-delivery-only | energy | yes | "We offer automatic propane delivery, budget billing and tank installation." | fuel-delivery-only.fixture.test/services | OK |
| pet-store | retail_store | yes | "Happy Tails Pet Supply sells premium dog food, cat food, treats and toys for your pets." | pet-store.fixture.test/ | OK - goods sold; the store address quote shows the physical store |
| pet-store | retail_store | yes | "Visit our store at 45 Oak Avenue, Springfield, open daily 9am to 7pm." | pet-store.fixture.test/visit | OK |
| pet-store | retail_store | yes | "Our staff help you choose the right food and accessories in the store." | pet-store.fixture.test/visit | OK |
| outdated-elevator | agronomy | yes | "learn about our agronomy services." | outdated-elevator.fixture.test/ | WEAK - mentions agronomy, does not show selling |
| outdated-elevator | agronomy | yes | "Lakeview Cooperative sells seed and fertilizer and offers custom spraying to members." | outdated-elevator.fixture.test/agronomy | OK |
| outdated-elevator | grain | possible | "Our grain elevator in Lakeview operated from 1952 until it closed in 2015." | outdated-elevator.fixture.test/history | OK - outdated evidence, correctly possible |
| feed-mill | feed | yes | "Valley Feed Mill manufactures complete livestock feeds for dairy and beef cattle." | feed-mill.fixture.test/ | OK |
| feed-mill | feed | yes | "Feed is delivered in bulk by our own trucks" | feed-mill.fixture.test/ | OK |
| feed-mill | feed | yes | "Our feed products include complete rations, protein supplements and minerals." | feed-mill.fixture.test/products | OK |
| cardlock-fuel | energy | yes | "Every cardlock site has diesel and unleaded gasoline pumps open 24 hours a day." | cardlock-fuel.fixture.test/sites | OK |
| cardlock-fuel | gas_station | yes | "Crossroads Cardlock operates five unattended 24/7 cardlock fueling sites for commercial and farm accounts." | cardlock-fuel.fixture.test/ | OK |
| cardlock-fuel | gas_station | yes | "Every cardlock site has diesel and unleaded gasoline pumps open 24 hours a day." | cardlock-fuel.fixture.test/sites | OK |
| cardlock-fuel | gas_station | yes | "Sites: 100 Junction Road, Hays; 2 Depot Street, Ellis; 88 Route 40, Victoria." | cardlock-fuel.fixture.test/sites | OK in context (addresses of the cardlock sites), weak alone |
| prompt-injection | agronomy | yes | "Summit Ag Supply sells seed and fertilizer to growers in Nebraska and offers agronomy advice." | prompt-injection.fixture.test/ | OK |
| prompt-injection | agronomy | yes | "We are a small family business focused on crop inputs for local growers." | prompt-injection.fixture.test/about | OK |

**Audit summary (manual, by the developer):** 27 quotes - 26 OK, 1 weak, 0 wrong. Every yes answer has at least one quote that clearly supports it; weak quotes are extra quotes attached next to a good one.

**History (both runs are real):** the first evaluation (run #9, prompt `p2`) scored 53/54 (98%): `outdated-elevator` grain came back `not_found` instead of `possible` - the model read 'closed in 2015' as no evidence, and the same happened in the live scenario H run. Its audit also found one WRONG quote (cardlock-fuel energy quoted 'We do not offer fuel delivery.'). Prompt `p3` added one explicit rule (outdated evidence -> possible, quote it). This report is the re-run with `p3` (run #11).

**Observed during this run:** Gemini answered HTTP 429 (rate limit) for the cardlock-fuel job; the pipeline backed off and retried successfully on Google (no fallback needed). See the AI calls line above.

Reproduce: start `python fixtures/server.py`, then in `backend/` run `CRAWL_FIXTURE_SERVER=127.0.0.1:8765 CRAWL_ALLOWED_PRIVATE_HOSTS=*.fixture.test python ../scripts/evaluate.py ../docs/evidence/quality_evaluation.md` (real AI calls; results can vary slightly between runs).
