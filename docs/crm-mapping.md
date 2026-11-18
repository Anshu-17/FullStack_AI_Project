# CRM mapping (proposal - NOT built)

How the export (`GET /api/exports?format=csv|json`) would map onto a typical CRM (Salesforce, HubSpot, Dynamics).
**No CRM integration exists in the code**; this is the proposed design.

## Account (company) fields

| Our field | CRM field (typical) | Notes |
|---|---|---|
| `company_name` | Account Name | |
| `website` | Website | normalised start URL |
| `canonical_domain` | Domain (unique external id) | **match key** for upserts (e.g. HubSpot "Company domain name", Salesforce custom External ID) |
| `last_scanned_at` | `BEP Last Verified` (date/time) | when the latest finished scan ended (UTC) |
| `source` | not synced | test data (`fixture` / `synthetic`) is excluded from sync |

## Per-category custom fields (7 categories x 5 fields)

For each category (`accounting`, `agronomy`, `grain`, `energy`, `feed`, `gas_station`, `retail_store`):

| Our field | CRM custom field | Type |
|---|---|---|
| `<cat>_status` | `BEP <Category>` | picklist: Yes / Possible / Not found / Not scanned |
| `<cat>_source` | `BEP <Category> Source` | picklist: Website / Rule / Human |
| `<cat>_evidence_url` | `BEP <Category> Evidence URL` | URL |
| `<cat>_quote` | `BEP <Category> Evidence` | long text (first verified quote, max 300 chars) |
| `<cat>_conflict` | `BEP <Category> Needs Review` | checkbox (human correction disagrees with the latest scan) |

Optional: one "BEP Evidence" child object (or notes) per verified quote from the JSON export, with
`category, quote, source_url, fetched_at, model, prompt_version, policy_version`.

## Sync approach (proposed)

1. Read the JSON export (or the API) for companies with `source = user`.
2. **Upsert by canonical domain**: find the CRM account with that domain; update if found, create if not
   (never match on name - names vary, domains are unique in our database).
3. Only write fields whose values changed (compare with the last synced values) to avoid noisy CRM history.
4. Never overwrite a field a CRM user edited by hand without a rule: either CRM edits win (one-way sync) or they
   come back as corrections (two-way - would need a webhook into `POST /api/companies/{id}/overrides`).
5. Schedule: after each completed run, or nightly.
6. Log each sync (accounts created / updated / skipped / failed) like our `ai_usage` table.

## Not built

- CRM API client, credentials, field creation, the sync job and its scheduling
- two-way sync (CRM edits back into corrections)
- mapping of CRM picklist values per vendor
- conflict policy between CRM edits and new scans
