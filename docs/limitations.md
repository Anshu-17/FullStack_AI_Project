# Known limitations and next steps

Honest list, from the decision log and the evidence. Most important first.

## Quality

| Limitation | Effect | Next step |
|---|---|---|
| No held-out labelled set; the 9 fixture sites were used to tune the prompt (p3) | the 54/54 fixture score is fit, not accuracy | label 30-50 real companies by hand, never use them for prompt changes, measure on them |
| Groq fallback model weaker than Gemini | both clear errors in the pilot (Grow West agronomy, Star Oilco gas station) came from it | now `gpt-oss-120b`; re-run the pilot to check |
| Strict verbatim-quote check | stitched / paraphrased quotes are dropped -> some true answers become `possible` / `not_found` | keep strict (it is the safety net); improve prompts; reviewers see these as `review_required` |
| Keyword relevance check is a heuristic | can be fooled or be too strict | per-category evidence rubric, or a second-pass check |
| 8-page crawl budget | evidence on deeper pages is missed (e.g. co-ops' station / store pages) | smarter page selection (sitemaps), adaptive budget |
| Model confidence is self-reported | not a calibrated probability | don't use it for decisions; calibrate on the labelled set |

## Crawling

| Limitation | Effect | Next step |
|---|---|---|
| No JavaScript rendering | JS-only sites give little or no text (`NO_CONTENT` / weak evidence) | optional headless-browser lane with strict limits |
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
| Docker images and `start.sh` never built / run locally (no Docker on the dev machine) | first real build is on Render | build in CI |
| Not deployed yet | no live URLs | follow `docs/deployment.md` |
| Single organisation, no user-management screens | users come from the seed | tenant id + Supabase row-level security; admin screens |
| Token only in the Streamlit session; no refresh / revocation | closing the tab logs you out; disabling the user is the way to cut access | refresh tokens, server-side session list |
| Company list / export filter on final answers in Python | fine for thousands of companies, slow for millions | SQL view / materialised table of final answers |
| CRM integration | not built | see `docs/crm-mapping.md` |
| Retention | not automated | see `docs/privacy.md` |
| ~1 s per job of loop overhead in the synthetic load test is unexplained | throughput figure is a lower bound for the platform | profile the worker loop |
