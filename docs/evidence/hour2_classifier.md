# Evidence - Classifier (real runs on agtegra.com)

Generated from the `bep` database with a query script (rows are not retyped).
Command used for each run: `python -m app.classifier.cli https://www.agtegra.com --name "Agtegra Cooperative"`.

## 1. Result table - job #4 (run #4), Gemini primary

Job status: **review_required**, finished 2026-11-18 07:28:59 UTC.

| category | status | provenance | model | prompt / policy | verified quotes (source) |
|---|---|---|---|---|---|
| agronomy | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "Our seed, fertilizer, crop protection and custom application services are specifically prescribed for fields â€¦" (https://www.agtegra.com/products-services/agronomy, verified=True)<br>"Using prescription fertility products, Agtegra Agronomists can provide timely crop nutrient solutions for optâ€¦" (https://www.agtegra.com/products-services/agronomy, verified=True)<br>"AGRONOMY SERVICES CROP INPUTS & SERVICES" (https://www.agtegra.com/products-services/agronomy, verified=True) |
| grain | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "Corn Drying Schedule Soybean Drying Schedule Huron Drying Schedule Milo Drying Schedule Wheat Drying Schedule" (https://www.agtegra.com/products-services/grain, verified=True) |
| energy | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "From fuel to propane, we are equipped to meet your residential, agricultural, and commercial energy needs." (https://www.agtegra.com/products-services/energy, verified=True)<br>"The Agtegra energy business provides petroleum and energy products and services to keep Agtegra territory runâ€¦" (https://www.agtegra.com/, verified=True)<br>"Agtegra Fuel: (605) 725-8580 Agtegra Propane: (605) 225-6383" (https://www.agtegra.com/products-services/energy, verified=True) |
| feed | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "Agtegra offers a range of feed products and services to meet your livestock needs and create a clear path to â€¦" (https://www.agtegra.com/, verified=True)<br>"Agtegra is equipped to provide farmers with grain, agronomy, energy and feed and farm supply products and serâ€¦" (https://www.agtegra.com/products-services, verified=True) |
| gas_station | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "Aberdeen Fuel Station – Cardtrol 811 3rd Ave SE Aberdeen, SD 57401 Details Directions Bath Fuel Station – Carâ€¦" (https://www.agtegra.com/products-services/energy, verified=True)<br>"Bowdle Fuel Station – Cardtrol 32491 US HWY 12 Bowdle, SD 57428 605-846-1047 Details Directions Dupree - Cardâ€¦" (https://www.agtegra.com/products-services/energy, verified=True)<br>"Milbank C-Store 313 West 4th Ave Milbank, South Dakota 57252 605-432-5561" (https://www.agtegra.com/products-services/energy, verified=True) |
| retail_store | **yes** | site | google/gemini-2.5-flash | p2 / v1 | "Ipswich Farm Store 20 5th Ave Ipswich, SD 57451 605-846-1231 Details Directions" (https://www.agtegra.com/products-services/energy, verified=True)<br>"Farm Supply" (https://www.agtegra.com/locations, verified=True)<br>"Feed and Farm Supply >" (https://www.agtegra.com/, verified=True) |
| accounting | **yes** | rule | - (business rule) | - / v1 | Default assessment policy v1: Accounting = Yes by explicit business rule. |

AI calls for this job:

| ai_usage id | provider | model | outcome | error_code | tokens in / out | latency ms | created (UTC) |
|---|---|---|---|---|---|---|---|
| 7 | google | gemini-2.5-flash | ok | - | 4427 / 3156 | 13385 | 2026-11-18 07:28:39 |

## 2. Forced fallback - job #5

The primary model was made to fail for ONE command only (environment override, `.env` untouched):
`$env:GOOGLE_MODEL='does-not-exist'; python -m app.classifier.cli https://www.agtegra.com ...`

Expected: Google returns 404 (unknown model) -> classified `AI_ERROR`, not retried (retrying cannot help) -> Groq is used.

| ai_usage id | provider | model | outcome | error_code | tokens in / out | latency ms | created (UTC) |
|---|---|---|---|---|---|---|---|
| 8 | google | does-not-exist | error | AI_ERROR | None / None | 288 | 2026-11-18 07:29:32 |
| 9 | groq | openai/gpt-oss-20b | ok | - | 4209 / 1549 | 2287 | 2026-11-18 07:29:43 |

Observed: one failed Google call, then Groq `ok`; job status **review_required** with 7 classifications (7 rows).

## 3. Accidental (real-world) fallback - job #3

Not staged. Gemini's answer failed the output schema three times (one quote was ~370 characters and the schema then had a hard 300-character limit), so the pipeline retried with backoff and then fell back to Groq.

| ai_usage id | provider | model | outcome | error_code | tokens in / out | latency ms | created (UTC) |
|---|---|---|---|---|---|---|---|
| 3 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3419 | 14868 | 2026-11-18 07:24:23 |
| 4 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3814 | 15290 | 2026-11-18 07:24:58 |
| 5 | google | gemini-2.5-flash | invalid_output | AI_INVALID_OUTPUT | 4271 / 3419 | 14639 | 2026-11-18 07:25:15 |
| 6 | groq | openai/gpt-oss-20b | ok | - | 4212 / 1681 | 3048 | 2026-11-18 07:25:23 |

Observed: 3 x `invalid_output` on Google, then Groq `ok`; job status **review_required**. Follow-up fix: size limits are now enforced per quote in validation, so one long quote no longer rejects the whole answer (see decision log, Hour 2).
