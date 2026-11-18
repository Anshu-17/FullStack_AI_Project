# Deployment smoke test (REAL - live Render + Supabase)

Live services (Render free plan, Ohio; Supabase Postgres via the session pooler, East US - Ohio):

- UI: https://bep-ui-1dt0.onrender.com
- API: https://bep-api.onrender.com (docs: https://bep-api.onrender.com/docs)

## 1. Author's manual smoke test - 2026-11-18

Done by the author in the browser (reported, not re-run here): `/health` and `/ready` OK, login as reviewer,
a real company run completing with evidence shown in the UI.

## 2. Automated check with curl - 2026-11-18 15:44:06 UTC

Run from the development machine (Windows 11, `curl.exe`), no credentials used. Output copied verbatim:

```
> curl.exe -s -w "\nHTTP %{http_code} in %{time_total}s\n" https://bep-api.onrender.com/health
{"status":"ok"}
HTTP 200 in 0.361383s

> curl.exe -s -w "\nHTTP %{http_code} in %{time_total}s\n" https://bep-api.onrender.com/ready
{"status":"ready","database":"ok","migration":"13822ee21a66"}
HTTP 200 in 0.150238s

> curl.exe -s -o NUL -w "HTTP %{http_code} in %{time_total}s\n" https://bep-ui-1dt0.onrender.com
HTTP 200 in 0.150599s

> curl.exe -s -w "\nHTTP %{http_code}\n" https://bep-ui-1dt0.onrender.com/_stcore/health
ok
HTTP 200

> curl.exe -s -w "\nHTTP %{http_code}\n" https://bep-api.onrender.com/api/companies   (no token)
{"error":{"code":"UNAUTHORIZED","message":"Please log in.","details":{}}}
HTTP 401

> curl.exe -s -o NUL -w "HTTP %{http_code}\n" https://bep-api.onrender.com/docs
HTTP 200
```

## What this shows

- The API process is up and the live database is reachable at the latest migration (`13822ee21a66`) - the
  migrations ran on startup (`start.sh`).
- The Streamlit UI is served (HTTP 200) and its health endpoint answers `ok`.
- Protected routes refuse requests without a login (401 with the standard error shape).
- The services were already awake (sub-second times); after ~15 minutes idle the first request takes ~1 minute.

## Not shown here

- The login and the real run were checked by the author manually; this file contains no credentials, so the
  authenticated flow is not reproduced by curl here.
- Worker behaviour on Render (crash recovery etc.) is shown locally in the scenario files, not on the live service.
