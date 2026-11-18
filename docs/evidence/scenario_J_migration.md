# Scenario J - schema change (migration) without breaking existing data

**Question:** we need a new column. Can the database be changed - and changed back - without losing data or
breaking code that doesn't know about the column yet?
**Answer shown here:** yes. Migration `13822ee21a66` adds `companies.source` (`user` / `fixture` /
`synthetic`, used to label test data). Upgrade, downgrade and upgrade again all run cleanly, existing rows
keep their data and get `source = 'user'`, and `alembic check` reports no drift.

Date: 2026-11-18. Database: `bep_test` (PostgreSQL 18). REAL run of the real migrations (no mocks).

## Compatibility strategy (expand first, never break old code)

1. **Additive change with a server default.** `ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'user'`: Postgres
   fills every existing row at once, and code that never mentions `source` (an older API or worker still
   running during a deploy) keeps inserting rows without errors - shown below.
2. **The database guards the values**: `CHECK (source IN ('user','fixture','synthetic'))` rejects anything else.
3. **Reversible**: the downgrade drops the constraint and the column; only the labels are lost.
4. Deploy order for a real system: run the migration first, then roll out the code that reads/writes the column.
   A destructive change (rename / drop) would be split into several releases (add new -> copy -> switch code ->
   drop old), never done in one step.

## Steps

Script: upgrade head -> downgrade -1 -> insert a row with the OLD schema -> upgrade -> insert a row the old way
(without `source`) -> try an invalid value -> downgrade -1 -> upgrade -> `alembic check`.

## Observed output

```
database: postgresql+psycopg://postgres:***@localhost:5432/bep_test

$ alembic upgrade head

$ alembic downgrade -1   (back to the schema WITHOUT companies.source)

[before upgrade: old schema, one existing row] alembic revision = 9633adfef360
  companies columns: ['id', 'name', 'website_url', 'canonical_domain', 'created_at', 'updated_at']
  check constraints: []
  rows: [(1, 'Old Row Co-op', 'old-row.example')]

$ alembic upgrade head   (adds companies.source with default 'user')

[after upgrade: column added, existing row kept its data and got source='user'] alembic revision = 13822ee21a66
  companies columns: ['id', 'name', 'website_url', 'canonical_domain', 'created_at', 'updated_at', 'source']
  check constraints: ['ck_companies_source']
  rows: [(1, 'Old Row Co-op', 'old-row.example', 'user')]

  UPDATE source='bogus' -> rejected by the database: IntegrityError (ck_companies_source)

[after an insert that does not mention source (old code path)] alembic revision = 13822ee21a66
  companies columns: ['id', 'name', 'website_url', 'canonical_domain', 'created_at', 'updated_at', 'source']
  check constraints: ['ck_companies_source']
  rows: [(1, 'Old Row Co-op', 'old-row.example', 'user'), (2, 'New Row Co-op', 'new-row.example', 'user')]

$ alembic downgrade -1   (drops the column again)

[after downgrade: column gone, rows still there] alembic revision = 9633adfef360
  companies columns: ['id', 'name', 'website_url', 'canonical_domain', 'created_at', 'updated_at']
  check constraints: []
  rows: [(1, 'Old Row Co-op', 'old-row.example'), (2, 'New Row Co-op', 'new-row.example')]

$ alembic upgrade head

[after upgrade again] alembic revision = 13822ee21a66
  companies columns: ['id', 'name', 'website_url', 'canonical_domain', 'created_at', 'updated_at', 'source']
  check constraints: ['ck_companies_source']
  rows: [(1, 'Old Row Co-op', 'old-row.example', 'user'), (2, 'New Row Co-op', 'new-row.example', 'user')]
No new upgrade operations detected.

$ alembic check
  No new upgrade operations detected.

(cleanup: the two demo rows were deleted from bep_test)
```

## Result: PASS

| Check | Result |
|---|---|
| Upgrade adds the column + CHECK constraint | yes |
| Existing row keeps its data, gets `source='user'` | yes (`Old Row Co-op`) |
| Old-style insert without `source` still works | yes (`New Row Co-op` -> `user`) |
| Invalid value rejected by the database | yes (`IntegrityError`, `ck_companies_source`) |
| Downgrade removes the column, rows stay | yes |
| Upgrade again + `alembic check` clean | yes |

The same migration was applied to the main `bep` database (`alembic upgrade head`; `alembic check`: no drift).
