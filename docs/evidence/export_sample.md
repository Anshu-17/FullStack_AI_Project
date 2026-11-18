# Export sample (live, 2026-11-18)

Downloaded as `viewer@demo.local` from the running API right after the scenario E run. Exports contain the
FINAL answers: a reviewer's correction wins (`source = human`), the automated answer stays visible in JSON.

```
GET /api/exports?format=csv            (viewer) -> HTTP 200 content-type=text/csv; charset=utf-8
    disposition=attachment; filename="companies-2026-11-18.csv"   bytes=2923
GET /api/exports?format=json           (viewer) -> HTTP 200 content-type=application/json
    disposition=attachment; filename="companies-2026-11-18.json"  bytes=20071
GET /api/exports/overrides?format=csv  (viewer) -> HTTP 200 content-type=text/csv; charset=utf-8
    disposition=attachment; filename="corrections-2026-11-18.csv" bytes=263
```

Checks: 39 CSV columns (4 + 5 per category x 7), 2 data rows (one per company); JSON has 2 items with keys
`company_name, website, canonical_domain, last_scanned_at, answers, override_history`.

Note: timestamps in this sample carry the database server's local offset (`-06:00`). This was changed right
after: database sessions now use UTC, so exports and the API return `+00:00` times.

## companies.csv (header + both rows)

```csv
company_name,website,canonical_domain,last_scanned_at,accounting_status,accounting_source,accounting_evidence_url,accounting_quote,accounting_conflict,agronomy_status,agronomy_source,agronomy_evidence_url,agronomy_quote,agronomy_conflict,grain_status,grain_source,grain_evidence_url,grain_quote,grain_conflict,energy_status,energy_source,energy_evidence_url,energy_quote,energy_conflict,feed_status,feed_source,feed_evidence_url,feed_quote,feed_conflict,gas_station_status,gas_station_source,gas_station_evidence_url,gas_station_quote,gas_station_conflict,retail_store_status,retail_store_source,retail_store_evidence_url,retail_store_quote,retail_store_conflict
Agtegra Cooperative,https://www.agtegra.com/,agtegra.com,2026-11-18T02:26:36.071201-06:00,yes,rule,,,no,yes,site,https://www.agtegra.com/products-services/agronomy,"Our seed, fertilizer, crop protection and custom application services are specifically prescribed for fields in our cooperative area.",no,possible,human,,,yes,yes,site,https://www.agtegra.com/products-services/energy,"From fuel to propane, we are equipped to meet your residential, agricultural, and commercial energy needs.",no,yes,site,https://www.agtegra.com/products-services/feed,"distributes dry feeds, minerals and liquid supplements to wholesale networks and producers on a direct basis.",no,yes,site,https://www.agtegra.com/products-services/energy,"Aberdeen Fuel Station – Cardtrol 811 3rd Ave SE Aberdeen, SD 57401 Details Directions Bath Fuel Station – Cardtrol 105 392nd Avenue S Aberdeen, SD 57401",no,yes,site,https://www.agtegra.com/products-services/energy,"Ipswich Farm Store 20 5th Ave Ipswich, SD 57451 605-846-1231 Details Directions",no
Insight FS,https://www.insightfs.com/,insightfs.com,2026-11-18T01:55:09.821032-06:00,yes,rule,,,no,yes,site,https://fscooperatives.com/insightfs/agriculture/seed,"Having access to the best traits and genetics in the industry allows our Insight FS seed product managers to choose the right seed for your operation. Top Seed Brands, Agronomic Expertise, and Partnership in the field",no,yes,site,https://fscooperatives.com/insightfs/agriculture/grain-marketing/cash-bids-new,"Insight FS provides producers with access to world grain markets that enable you to plan your grain handling, storage and marketing activities to compliment your on-farm storage capabilities and achieve your profitability targets. Insight FS Grain Storage and Marketing Facilities",no,yes,site,https://fscooperatives.com/insightfs/residential/propane,"FS Propane powers your home with confidence. From setup to service, our certified local specialists handle everything—so you never have to second guess your supply.",no,yes,site,https://fscooperatives.com/insightfs,Feed and Nutrition,no,not_found,site,,,no,yes,site,https://fscooperatives.com/insightfs/our-locations,"Jefferson Main Office 222 E. Puerner Street Jefferson, WI 53549 (920) 674 7000",no
```

Note: Insight FS's Feed answer rests on the short quote "Feed and Nutrition" from the homepage - verified, but
weak evidence (likely a section heading). That job is `review_required`.

## corrections.csv (audit trail)

```csv
created_at,company_name,category,old_status,new_status,reason,reviewer_email,version
2026-11-18T02:26:02.355480-06:00,Agtegra Cooperative,grain,not_found,possible,Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.,reviewer@demo.local,1
```

## companies.json (Agtegra, Grain answer and history only)

```json
{
  "company_name": "Agtegra Cooperative",
  "website": "https://www.agtegra.com/",
  "canonical_domain": "agtegra.com",
  "last_scanned_at": "2026-11-18T02:26:36.071201-06:00",
  "answers[grain]": {
    "category": "grain",
    "status": "possible",
    "provenance": "human",
    "explanation": "Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.",
    "automated": {
      "classification_id": 58,
      "job_id": 9,
      "status": "yes",
      "provenance": "site",
      "explanation": "The company provides commercial grain services, including cash bids, futures, grain marketing, and operates storage and loadout facilities (elevators).",
      "confidence": 1.0,
      "model_provider": "google",
      "model_name": "gemini-2.5-flash",
      "prompt_version": "p2",
      "policy_version": "v1",
      "conflicts_with_override_at_scan": true,
      "created_at": "2026-11-18T02:26:36.071201-06:00",
      "evidence": [
        {
          "quote": "CASH BIDS AND FUTURES CASH BIDS FUTURES",
          "source_url": "https://www.agtegra.com/products-services/grain",
          "quote_verified": true,
          "page_id": 70,
          "fetched_at": "2026-11-18T02:26:16.014989-06:00"
        }
      ]
    },
    "override": {
      "status": "possible",
      "reason": "Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.",
      "reviewer_id": 1,
      "version": 1,
      "created_at": "2026-11-18T02:26:02.355480-06:00"
    },
    "version": 1,
    "conflict": true
  },
  "override_history": [
    {
      "id": 1, "company_id": 1, "category": "grain",
      "old_status": "not_found", "new_status": "possible",
      "reason": "Scenario E demo: reviewer marks Grain as Possible until confirmed by phone.",
      "reviewer_email": "reviewer@demo.local", "version": 1, "based_on_classification_id": 51,
      "created_at": "2026-11-18T02:26:02.355480-06:00", "company_name": "Agtegra Cooperative"
    }
  ]
}
```
