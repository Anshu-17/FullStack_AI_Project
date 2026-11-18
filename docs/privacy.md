# Privacy and data handling

## What we store

| Data | Where | Why |
|---|---|---|
| Company name, website, canonical domain | `companies` | the list being researched (from uploads) |
| Cleaned visible text of up to 12 public pages per company per scan (max 50,000 characters each) + SHA-256 | `pages.text_content` | to verify quotes and let reviewers see the source |
| Short verbatim quotes (max 300 characters) + source URL | `evidence` | the evidence behind each answer |
| Answers, explanations, model / prompt / policy versions | `classifications` | results and their provenance |
| Reviewer corrections with reason, reviewer id, time | `overrides` | audit trail (append-only) |
| User accounts: email, bcrypt password hash, role | `users` | login for reviewers / viewers |
| AI call metadata: provider, model, tokens, latency, outcome | `ai_usage` | cost and reliability monitoring (no prompt text) |
| Upload file name, SHA-256, per-row input and result | `uploads`, `upload_rows` | intake audit |

## What we don't store

- **No raw HTML**, no images, no files (PDFs etc. are not downloaded).
- **No customer or private data**: only public websites are crawled; private / internal addresses are blocked.
- **No passwords in plain text**, no API keys or secrets in the database or the repository.
- **No AI prompts or AI responses in the database** beyond the validated answers and quotes (the prompt can be
  rebuilt from stored pages). Logs may contain up to 300 characters of a model's invalid output when a parse fails.
- **No visitor tracking.** Client IP addresses are kept in memory for rate limiting; our structured logs do not
  contain them, but the web server's (uvicorn) access log lines do include the client address - on Render these
  logs are kept by the host.

**Personal data note (honest):** public company pages sometimes list staff names, job titles, business email
addresses or phone numbers (seen during the real-site pilot, e.g. on a co-op's "meet the team" page). Such text can
end up in `pages.text_content` and, rarely, in a quote. We do not extract, index or use it, but it is stored as
part of the page text. A production system should either strip email addresses / phone numbers before storing, or
apply the retention below.

## Retention (proposal - not automated yet)

| Data | Proposed retention |
|---|---|
| Page text (`pages`) | keep only the pages of the latest 2 finished scans per company; delete older ones (quotes in `evidence` keep the source URL) |
| Evidence, classifications | keep while the company is in the system (they are the result) |
| Corrections (`overrides`) | keep (audit trail) |
| `ai_usage`, `attempts`, `job_events` | 12 months |
| Uploads / upload rows | 6 months |
| Deleted company | delete its pages, evidence, classifications and jobs (cascade) on request |

## AI providers

- Only **public website text** (the selected passages, at most ~12,000 characters per company) and the company
  name / domain are sent to the AI provider. No user data, no corrections, no credentials.
- **Gemini free tier:** Google's terms for the free tier allow Google to use requests and responses to improve its
  products. Acceptable here because only public website text is sent; a paid tier (or another provider) should be
  used if any non-public data were ever processed.
- **Groq** (fallback): the same passages are sent when Gemini is unavailable.
- Page text is treated as untrusted data (prompt-injection defences), see `docs/design.md`.

## Access

Reviewers and viewers need an account (JWT login); viewers can read and export, reviewers can also change data.
The database is reachable only by the API and the worker (Supabase credentials are secrets in the hosting
environment).
