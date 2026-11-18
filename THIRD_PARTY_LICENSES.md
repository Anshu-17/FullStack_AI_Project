# Third-party licenses

Every dependency pinned in `backend/requirements.lock.txt` and `frontend/requirements.lock.txt`, with the license
declared in its installed package metadata (generated from the local virtual environments on 2026-11-18; the
metadata is the package authors' own statement - check the package for the authoritative text).

**Notes**

- All dependencies are open source; none are paid or proprietary. Almost all are permissive (MIT, BSD, Apache-2.0,
  ISC, PSF).
- **psycopg / psycopg-binary (LGPL-3.0-only):** used unmodified as a library (dynamic import), which LGPL permits
  in software under any license. Modifying psycopg itself would require sharing those changes.
- **certifi (MPL-2.0)** and **orjson (MPL-2.0 AND (Apache-2.0 OR MIT))**: file-level copyleft only for their own
  files; used unmodified.
- External services (not dependencies): Google Gemini API, Groq API, Supabase, Render - used under their own terms
  of service with the author's free-tier accounts.
- This project's own code is licensed under the **MIT License** - see [LICENSE](LICENSE) (copyright 2026 Anshuman
  R Prasad). The dependency licenses above are all compatible with distributing it under MIT.

## Backend (`backend/requirements.lock.txt`)
| Package | Version | License (from package metadata) |
|---|---|---|
| aiohappyeyeballs | 2.7.1 | Python Software Foundation License |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT |
| aiosignal | 1.4.0 | Apache Software License |
| alembic | 1.20.1 | MIT |
| annotated-doc | 0.0.6 | MIT |
| annotated-types | 0.8.0 | MIT |
| anthropic | 2.10.0 | Apache Software License |
| anyio | 4.16.0 | MIT |
| attrs | 26.1.0 | MIT |
| bcrypt | 5.0.0 | Apache Software License |
| beautifulsoup4 | 4.15.0 | MIT License |
| certifi | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| deprecated | 3.0.1 | MIT |
| distro | 1.9.0 | Apache Software License |
| dnspython | 2.9.2 | ISC |
| docstring-parser | 0.18.0 | MIT License |
| email-validator | 2.4.0 | The Unlicense (Unlicense) |
| fastapi | 0.163.2 | MIT |
| filetype | 1.2.0 | MIT License |
| frozenlist | 1.8.0 | Apache-2.0 |
| google-auth | 2.62.2 | Apache Software License |
| google-genai | 3.5.0 | Apache-2.0 |
| h11 | 0.16.0 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.16.2 | BSD-3-Clause |
| httptools | 0.9.0 | MIT |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.16.2 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jiter | 0.19.0 | MIT |
| jsonpatch | 1.47 | BSD-3-Clause |
| jsonpointer | 3.12 | BSD-3-Clause |
| langchain-anthropic | 1.7.10 | MIT License |
| langchain-core | 1.8.2 | MIT License |
| langchain-google-genai | 4.5.0 | MIT |
| langchain-openai | 1.8.1 | MIT License |
| langchain-protocol | 0.0.21 | MIT License |
| langchain-xai | 1.4.0 | MIT License |
| langsmith | 0.15.0 | MIT |
| limits | 5.8.0 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| mako | 1.4.3 | MIT |
| markupsafe | 3.0.4 | BSD-3-Clause |
| multidict | 7.2.1 | Apache-2.0 |
| openai | 3.55.0 | Apache-2.0 |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| propcache | 0.5.4 | Apache-2.0 |
| psycopg | 3.3.9 | LGPL-3.0-only |
| psycopg-binary | 3.3.9 | LGPL-3.0-only |
| pyasn1 | 0.6.5 | BSD-2-Clause |
| pyasn1-modules | 0.4.2 | BSD License |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.3 | MIT |
| pydantic-core | 2.50.4 | MIT |
| pydantic-settings | 2.16.3 | MIT |
| pyjwt | 2.15.1 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| python-multipart | 0.0.34 | Apache-2.0 |
| pyyaml | 6.0.3 | MIT License |
| regex | 2026.11.18 | Apache-2.0 AND CNRI-Python |
| requests | 2.34.2 | Apache Software License |
| requests-toolbelt | 1.0.0 | Apache Software License |
| slowapi | 0.1.10 | MIT License |
| sniffio | 1.3.1 | MIT License, Apache Software License |
| soupsieve | 4.1.1 | MIT |
| sqlalchemy | 2.1.9 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| structlog | 26.1.0 | MIT OR Apache-2.0 |
| tenacity | 9.1.4 | Apache Software License |
| tiktoken | 0.14.0 | MIT License |
| truststore | 0.10.5 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |
| tzdata | 2026.6 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uuid-utils | 0.19.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchfiles | 1.3.0 | MIT License |
| websockets | 17.4 | BSD-3-Clause |
| wrapt | 2.5.2 | BSD-2-Clause |
| xxhash | 4.1.0 | BSD-2-Clause |
| yarl | 1.25.1 | Apache-2.0 |
| zstandard | 0.25.0 | BSD-3-Clause |

## Frontend (`frontend/requirements.lock.txt`)

| Package | Version | License (from package metadata) |
|---|---|---|
| altair | 6.3.0 | BSD License |
| anyio | 4.16.0 | MIT |
| attrs | 26.1.0 | MIT |
| certifi | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| extra-streamlit-components | 0.1.81 | MIT License (classifier; the `License` field says UNKNOWN) |
| h11 | 0.16.0 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD License |
| idna | 3.20 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD License |
| jinja2 | 3.1.6 | BSD License |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| markupsafe | 3.0.4 | BSD-3-Clause |
| narwhals | 2.29.0 | MIT |
| numpy | 2.5.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.1.1 | BSD-3-Clause |
| pillow | 13.0.0 | MIT-CMU |
| protobuf | 7.36.2 | 3-Clause BSD License |
| pyarrow | 26.0.1 | Apache-2.0 |
| pydeck | 0.9.3 | Apache License 2.0 |
| python-dateutil | 4.0.0 | BSD-3-Clause |
| python-multipart | 0.0.34 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache Software License |
| rpds-py | 2026.9.1 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| streamlit | 1.67.0 | Apache-2.0 |
| typing-extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.6 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchdog | 7.1.0 | Apache-2.0 |
| websockets | 17.4 | BSD-3-Clause |
