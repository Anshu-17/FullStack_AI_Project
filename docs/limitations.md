# Known limitations and next steps

Honest list, from the decision log and the evidence. Most important first.

## Quality

| Limitation | Effect | Next step |
|---|---|---|
| No held-out labelled set; the 9 fixture sites were used to tune the prompt (p3) | the 54/54 fixture score is fit, not accuracy | label 30-50 real companies by hand, never use them for prompt changes, measure on them |
| Groq fallback model weaker than Gemini | both clear errors in the pilot (Grow West agronomy, Star Oilco gas station) came from it | now `gpt-oss-120b`; re-run the pilot to check |
| Strict verbatim-quote check | stitched / paraphrased quotes are dropped -> some true answers become `possible` / `not_found` | keep strict (it is the safety net); improve prompts; reviewers see these as `review_required` |
| Keyword relevance check is a heuristic | can be fooled or be too strict | per-category evidence rubric, or a second-pass check |
| 12-page crawl budget (one page per category group first, then by score) | sites with many sections still have unread evidence pages; e.g. Agfinity's `/energy/refined-fuels` was not fetched, so Energy rests on menu text | adaptive budget (more pages when groups are still uncovered), use page titles / content to rank |
| Page-selection words are hand-made from co-op sites | sites that name sections differently get less balanced crawls | learn words from labelled sites; use sitemap `<lastmod>` / page titles |
| Menu / navigation text can be quoted as evidence | verbatim but weak ("ENERGY Propane Refined Fuels Lubricants") | strip repeated navigation blocks before passage selection |
| Model confidence is self-reported | not a calibrated probability | don't use it for decisions; calibrate on the labelled set |

## Crawling

| Limitation | Effect | Next step |
|---|---|---|
| No JavaScript rendering | JS-only sites and pages (content loaded by scripts, e.g. store finders / maps) give little or no text (`NO_CONTENT` / weak evidence) | optional headless-browser lane with strict limits |
| Compressed sitemaps (`.xml.gz`) are skipped; max 3 sitemap files | large sites' later sitemaps are not read | read gzip with a size cap; pick child sitemaps by relevance |
| Sites that refuse crawlers (HTTP 403) | job fails `NO_CONTENT` (2 of 15 in the pilot) | manual research; never bypass |
| TLS chains Python cannot verify | shown as `robots_disallowed` (misleading) | record "robots.txt unreachable: <reason>"; use the OS trust store (`truststore`) |
| DNS rebinding window in the SSRF check | resolve-then-connect gap | pin the checked IP for the connection |
| `urllib.robotparser` | no `*` / `$` wildcards, first-match | an RFC 9309 parser |

## AI providers and cost

| Limitation | Effect | Next step |
|---|---|---|
| Free tiers (Gemini 20 requests/model/day; Groq per-minute limits) | batches stall (`AI_UNAVAILABLE`), as in the pilot | paid tier, or a scheduler that spreads calls over the day |
| Quota breaker and rate-limit counters are in memory per process | several processes don't share them | shared store (Redis / a Postgres table) |
| Cost is NULL unless prices are configured; one price pair for all providers | no real cost figures on the free tier | per-provider price table |
| An AI call in flight when a worker is killed is not recorded | slight under-count of usage | write a "started" usage row before the call |

## Platform

| Limitation | Effect | Next step |
|---|---|---|
| One worker process (threads); not run distributed | throughput bounded; distributed safety tested only with two claimers in one process | several worker processes / machines + shared rate limiter |
| Free Render: API + worker in one container, sleeps when idle | jobs only progress while the service is awake; ~1 min cold start | separate always-on worker service |
| `docker compose` never run (no Docker on the dev machine); images are built only by Render | local container setup unverified | build in CI |
| Single organisation, no user-management screens | users come from the seed | tenant id + Supabase row-level security; admin screens |
| Login token in a JavaScript-written cookie (not HttpOnly); no refresh tokens / server-side revocation | a script on the page could read the token; logout deletes the cookie but the JWT stays valid until it expires (8 h); disabling the user is the way to cut access | HttpOnly server-set session cookie, refresh tokens, server-side session list |
| Company list / export filter on final answers in Python | fine for thousands of companies, slow for millions | SQL view / materialised table of final answers |
| CRM integration | not built | see `docs/crm-mapping.md` |
| Retention | not automated | see `docs/privacy.md` |
| ~1 s per job of loop overhead in the synthetic load test is unexplained | throughput figure is a lower bound for the platform | profile the worker loop |
