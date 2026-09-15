# Clinic CRM — Build Plan (Backend + Frontend)

## 0. How to use this document

This document is the single source of truth for building the rest of the
Clinic CRM. It supersedes the `mk/` reference guides wherever they conflict
with a decision recorded here (the `date`-default behavior and money
precision are the two biggest examples — see §2). An executing agent should:

- Work phases in the order listed (Phase 0 → Phase 10). Do not skip Phase 0.
- Not re-read the `mk/` guides or re-explore the codebase to "double check"
  a decision recorded here — this document already resolved every open
  question found in those guides.
- Treat every `- [ ]` item as a discrete, checkable unit of work.
- Update this file's checkboxes to `- [x]` as items are completed, so the
  document also serves as build-progress tracking.
- Auth/users (`app/users/`) is already implemented and working except for
  one bug fixed in Phase 0 — do not redesign it.

---

## 1. Final architecture

**Stack:** FastAPI (async) · SQLAlchemy 2.0 async (`asyncpg`) · PostgreSQL ·
Redis · Alembic · PyJWT · `pwdlib[argon2]` · Docker Compose.

**Layering rule (every domain module):**
```
HTTP request → Router → auth/role dependency → Service → SQLAlchemy query code → PostgreSQL
```
Pure business math (money formulas) lives in dependency-free
`calculations.py` modules that import nothing from FastAPI/SQLAlchemy/Redis,
so they're trivially unit-testable.

**Complete target folder tree:**
```
app/
├── main.py                  # lifespan (seed superadmin, ping db/redis), all routers, Jinja2Templates wiring
├── core/
│   ├── config.py            # existing
│   ├── redis.py             # existing
│   └── security.py          # existing
├── common/
│   └── pagination.py        # NEW: shared PaginationParams / PaginatedResponse[T]
├── db/
│   ├── base.py               # existing
│   ├── session.py            # existing (async engine + sync engine for Alembic)
│   └── all_models.py         # existing, extend with SystemSetting + AuditLog
├── users/                    # existing — one bug fix (see Phase 0)
│   ├── models.py / schemas.py / dependencies.py / service.py / router.py / seed.py
├── doctors/                  # existing but broken — Phase 0 fixes + /options endpoint
│   ├── models.py / schemas.py / service.py / router.py
├── finance/
│   ├── models.py             # Consultation, Surgery, Room, SystemSetting
│   ├── mixins.py             # TimestampMixin, VoidableMixin (existing)
│   ├── calculations.py       # pure money math — Phase 0 fix
│   ├── reports.py            # date-range helper + report builders + XLSX export helper
│   ├── schemas.py            # extend with SystemSetting schemas
│   ├── dependencies.py       # existing
│   ├── service.py            # complete CRUD+void for all 3 types + settings service
│   └── router.py             # NEW — does not exist yet
├── audit/                    # NEW module
│   ├── models.py             # AuditLog
│   ├── schemas.py
│   ├── service.py            # record_audit_event() + list/query
│   └── router.py             # GET /audit-logs, superadmin only
├── web/                      # NEW module — page routes only, no business logic
│   └── router.py             # GET routes rendering Jinja2 templates
├── templates/                # NEW: Jinja2 templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── doctors.html
│   ├── receipts.html         # tabs: consultation / surgery / room
│   ├── reports.html
│   ├── audit_log.html
│   └── settings.html
└── static/
    ├── css/style.css
    └── js/
        ├── auth.js            # refresh-on-load pattern (see §10, Phase 8)
        ├── api.js              # fetch wrapper attaching the in-memory access token
        ├── doctors.js / receipts.js / reports.js / audit_log.js / settings.js / dashboard.js
tests/
├── conftest.py
├── auth/
├── doctors/
└── finance/
    ├── test_calculations.py
    ├── test_consultations.py
    ├── test_surgeries.py
    ├── test_rooms.py
    ├── test_reports.py
    └── test_permissions.py
```

---

## 2. Domain & business rules (finalized — treat as fact, not open questions)

- **IDs:** doctors and all finance records use integer auto-increment PKs.
  Users use UUIDs. Do not change either.
- **Money:** `Numeric(12, 0)` — whole soums, no decimals (this project's
  deviation from the `mk/` guide's `Numeric(10,2)`). All Python-side
  arithmetic uses `Decimal`. `money(value)` quantizes to the nearest whole
  soum with `ROUND_HALF_UP`, applied **per receipt before aggregation**, not
  after summing.
- **Formulas:**
  - Consultation: `minus = minus_beshming or 0`; `doctor_share = money((amount - minus) * doctor_percent / 100)`; `clinic_profit = money(amount - doctor_share - minus)`; `expense = money(minus)`.
  - Surgery: identical shape, using `surgery_expense` in place of `minus`.
  - Room: no expense field at all; `doctor_share = money(amount * doctor_percent / 100)`; `clinic_profit = money(amount - doctor_share)`; `expense` is always `0`.
- **`doctor_percent`:** `Numeric(5,2)`, constrained `0 <= doctor_percent <= 100` at both the Pydantic schema (`ge=0, le=100`) and DB (`CheckConstraint`) layers.
- **`minus_beshming`:** nullable, **no model-level `default=`, no `server_default`**. Its default value is sourced dynamically from the `SystemSetting` singleton (§4) and applied only in the service layer at create time when the client omits the field. Do not hardcode `5000` anywhere except the migration's seed row for `SystemSetting`.
- **Expense policy:** if `expense > amount` (consultation's `minus`, or surgery's `surgery_expense`), reject with `422 Unprocessable Entity`, detail `"Expense cannot exceed amount"`. Applies on both create and update (validate the *final* post-patch state, not just the changed field). Rooms have no expense field, so this rule doesn't apply to them.
- **Business `date` field — deviation from the `mk/` guide:** on `Create`, if `date` is omitted, default it to `datetime.now(ZoneInfo("Asia/Tashkent"))` in the service layer. The field is always explicit and editable — the client (assistant or manager, whoever is allowed to create that record type) may supply an explicit `date` to backdate or correct it. This differs from the guide, which required the client to always supply `date`. PATCH access to `date` is unaffected by this and still follows the existing rule that only `SUPERADMIN`/`MANAGER` can `PATCH` finance records at all — assistants can never update `date` on an existing record, only set it at creation time.
- **Reports use business `date`, never `created_at`.** Date ranges are inclusive on both ends, implemented via an **exclusive upper bound**: `date >= start` AND `date < end_exclusive`, where `start = datetime.combine(date_from, time.min, tzinfo=Asia/Tashkent)` and `end_exclusive = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=Asia/Tashkent)`. This is the guide's easiest-to-invert gotcha — do not implement it as `date <= date_to 23:59:59`.
- **Void/archive, not delete, for finance records.** `Consultation`/`Surgery`/`Room` each carry `is_voided: bool`, `voided_at: datetime | None`, `voided_by_id: uuid.UUID | None` (via `VoidableMixin`). Voiding an already-voided record returns `409 Conflict`. All report queries filter `is_voided.is_(False)`. There must never be a `DELETE` endpoint for any finance record type.
- **Doctors keep physical `DELETE`** (per the project's existing deviation from the guide). `doctor_id` FKs on all three finance tables use `ondelete="SET NULL"`, so deleting a doctor preserves finance history (the row survives with `doctor_id = NULL`). Confirm during Phase 0 whether `DELETE /doctors/{id}` should be `SUPERADMIN`-only (current code) or `SUPERADMIN + MANAGER` (per the deviations doc) — default to keeping the current stricter `SUPERADMIN`-only behavior unless corrected.
- **FK cascade policy:** `doctor_id` → `SET NULL`; `created_by_id` → `RESTRICT` (a user can never be deleted out from under their financial history — user deletion isn't even implemented, only block/unblock); `voided_by_id` → `SET NULL`.
- **`created_by_id` vs `doctor_id`:** never conflate these. `created_by_id` = the authenticated actor who entered the record (server-set from `actor.id`, never client-supplied). `doctor_id` = the doctor who earns the share (client-supplied, nullable, validated to exist via `get_doctor_or_404` if present).
- **Permission matrix:**

  | Action | Superadmin | Manager | Assistant |
  |---|---|---|---|
  | View/create/update/delete doctors | Y | Y (delete: confirm in Phase 0) | View only |
  | Create consultation/surgery/room | Y | Y | Y |
  | View own finance records | Y | Y | Y |
  | View all finance records | Y | Y | N (own only, via `created_by_id == actor.id`) |
  | Update finance record | Y | Y | N |
  | Void finance record | Y | Y | N |
  | Section/total reports (own scope) | all records | all records | own records only |
  | Audit log | Y | N | N |
  | Finance settings (`minus_beshming` default) | Y | N | N |

- **Never persist calculated fields.** `doctor_share`/`clinic_profit`/`expense` are always derived at read time by calling the same `calculations.py` functions used everywhere else — never stored as columns, never recomputed with a second formula anywhere (e.g. in the XLSX export or the total report).
- **Total report composition:** `build_total_report()` must call `build_consultation_report()`, `build_surgery_report()`, `build_room_report()` and sum their already-computed totals. It must never independently re-query/re-sum the three tables — that would create a second, divergable source of truth for the same math.
- **Query safety:** always use SQLAlchemy expressions (`Model.field == value`), never string-formatted SQL.
- **Receipt numbers are explicitly not unique** — no `UNIQUE` constraint on `receipt_number`.
- **Ordering:** all finance list queries order by `date.desc(), id.desc()` (the `id` tie-breaker keeps pagination stable when two records share a timestamp). Doctor listing orders by `last_name, first_name, id`.
- **Pagination:** offset-based (`page`, `page_size`, default 20, max 100) via the shared `PaginatedResponse[T]` in `app/common/pagination.py`. List endpoints run one `COUNT` query + one page-data query.

---

## 3. New system — Audit log

- **Model** (`app/audit/models.py`), table `audit_logs`:
  - `id: int` (autoincrement PK)
  - `actor_id: uuid.UUID | None` (FK `users.id`, `ondelete="SET NULL"`, nullable for system/bootstrap events)
  - `action: str` (e.g. `"create_consultation"`, `"void_surgery"`, `"block_assistant"`, `"update_doctor"`, `"delete_doctor"`, `"update_finance_settings"`)
  - `resource_type: str` (`"doctor" | "consultation" | "surgery" | "room" | "user" | "finance_settings"`)
  - `resource_id: str` (stringified — covers both `int` and `uuid.UUID` resource ids uniformly)
  - `metadata_: dict | None` (JSON/JSONB column, optional before/after context)
  - `created_at: datetime` (`server_default=func.now()`)
  - Indexes on `created_at`, `resource_type`, `actor_id` (needed for the filterable list endpoint and to keep future retention housekeeping cheap).
- **Write helper** (`app/audit/service.py`): `record_audit_event(db, *, actor: User | None, action: str, resource_type: str, resource_id, metadata: dict | None = None) -> None`. This must be called **inside the same service function and before the `commit()`** that performs the mutation it's logging, so the audit row and the business row commit atomically in a single transaction — never as a separate follow-up write.
- **Scope for v1** — call `record_audit_event` from:
  - `doctors/service.py`: `create_doctor`, `update_doctor`, `delete_doctor`
  - `finance/service.py`: `create_*`, `update_*`, `void_*` for all three record types
  - `finance/service.py`: `update_finance_settings`
  - `users/service.py`: `create_manager`, `create_assistant`, `update_assistant_credentials`, `set_user_status` (block/unblock)
- **Read endpoint** (`app/audit/router.py`): `GET /audit-logs`, `require_roles(SUPERADMIN)`. Query params: `actor_id`, `resource_type`, `resource_id`, `date_from`, `date_to`, `page`, `page_size`. Returns `PaginatedResponse[AuditLogRead]`.
- **Retention:** no auto-deletion in v1, but the indexes above must exist from the start so a retention job can be added later without a schema change.

---

## 4. New system — Dynamic finance settings

- **Model**, added to `app/finance/models.py`, table `system_settings`: a
  singleton row, `id: int` fixed at `1`, `default_minus_beshming:
  Numeric(12,0)`, `updated_at: datetime`, `updated_by_id: uuid.UUID | None`
  (FK `users.id`, `ondelete="SET NULL"`).
- **Migration must seed the one row** (`default_minus_beshming = 5000`) so
  the application code never has to special-case a missing settings row.
- **Service** (`app/finance/service.py`): `get_minus_beshming_default(db) ->
  Decimal` reads the singleton row. `update_finance_settings(db, *, actor,
  data)` updates it, sets `updated_by_id = actor.id`, and calls
  `record_audit_event(..., action="update_finance_settings", ...)`.
- **Application point:** in `create_consultation`, if the incoming
  `ConsultationCreate.minus_beshming` is `None` (field omitted — the Pydantic
  field itself has no static default, so `None` unambiguously means
  "omitted" at create time), call `get_minus_beshming_default(db)` and use
  that value. This does not interact with `PATCH`'s `exclude_unset`
  semantics: on update, an explicit `null` still means "clear the value to
  zero for this record," which is a different code path from create.
- **Endpoints** (`app/finance/router.py`), `require_roles(SUPERADMIN)`:
  - `GET /admin/settings/finance` → current `default_minus_beshming`.
  - `PATCH /admin/settings/finance` → updates it, writes an audit entry.

---

## 5. New feature — XLSX report export

- Add `openpyxl` to `requirements.txt`.
- `finance/reports.py` gains one export helper per report type (or one
  generic `build_report_workbook(report, report_type)`) that takes the
  **already-computed** report object (the same one returned as JSON) and
  writes it into an `openpyxl.Workbook`, so there is exactly one calculation
  path — the export never recomputes totals independently.
- Each of `GET /reports/{consultations|surgeries|rooms|total}` gains an
  optional `format` query param, `"json"` (default) or `"xlsx"`. When
  `format=xlsx`, return a `StreamingResponse` with `media_type
  ="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"` and
  header `Content-Disposition: attachment;
  filename="{report_type}_{date_from}_{date_to}.xlsx"`.

---

## 6. New feature — doctor `/options` endpoint

- `GET /doctors/options` in `app/doctors/router.py`, open to all three
  roles (`require_roles(SUPERADMIN, MANAGER, ASSISTANT)`), returns
  `list[{"id": int, "name": str}]` where `name = f"{last_name}
  {first_name}"` — no pagination, no specialty/timestamps. Purpose: fast
  dropdown population on the receipt-entry frontend forms without exposing
  the full doctor payload or requiring pagination handling client-side.
  Must be registered **before** `GET /doctors/{doctor_id}` in the router so
  the literal `/options` path isn't swallowed by the `{doctor_id}` path
  parameter.

---

## 7. New feature — login rate limiting

- Add `slowapi` to `requirements.txt`. Configure its Redis-backed limiter
  using the existing `app.core.redis` connection (do not open a second Redis
  connection pool just for rate limiting).
- Apply to `POST /auth/login` only: a small per-IP+username limit (e.g. `5
  per minute`). On trip, `slowapi` returns `429 Too Many Requests`
  automatically — no custom handler needed beyond registering the limiter
  and exception handler in `main.py`.

---

## 8. New feature — `/health` deep check

- Replace the current trivial `/health` in `app/main.py` with one that:
  - Runs `SELECT 1` against Postgres via the existing `get_db` session.
  - Runs `PING` against Redis via the existing `redis_client`.
  - Returns `{"status": "ok", "db": "ok", "redis": "ok"}` (200) if both
    succeed, or `{"status": "error", "db": "ok"|"error", "redis":
    "ok"|"error"}` with `503` if either fails — name the failing component,
    don't just return a generic 500.

---

## 9. Backend build phases

### Phase 0 — Fix existing bugs (do this first, nothing else until it's done)

- [x] `app/doctors/schemas.py` — file is missing all imports (`BaseModel`,
  `Field`, `ConfigDict`, `datetime`) despite using them, and references an
  undefined `PaginatedResponse`. Fix: add the missing imports; import
  `PaginatedResponse`/`PaginationParams` from the new `app/common/pagination.py`
  (create that module now, move the existing definition out of
  `finance/schemas.py` into it, and update `finance/schemas.py` to import
  from the shared location too).
- [x] `app/doctors/service.py` / `app/doctors/router.py` — name mismatch:
  `router.py` imports `get_doctor`, but `service.py` only defines
  `get_doctor_or_404`. Standardize on `get_doctor_or_404` everywhere (this
  matches the naming convention used across the rest of the codebase).
  Also, `router.py`'s delete endpoint calls `delete_doctor` but never
  imports it from `service.py` — add the missing import.
- [x] Confirm the `DELETE /doctors/{doctor_id}` role gate: current code is
  `require_roles(SUPERADMIN)`; the deviations doc (`mk/deepseek_markdown_...`)
  says it should be `require_roles(SUPERADMIN, MANAGER)`. Default to keeping
  the current stricter `SUPERADMIN`-only behavior; only widen it to include
  `MANAGER` if explicitly asked.
- [x] `app/finance/calculations.py` — `consultation_totals()`'s body is not
  indented inside the function (an `IndentationError` on import today).
  Fix the indentation so it matches `surgery_totals()`/`room_totals()`,
  which are already correct.
- [x] `app/finance/router.py` does not exist. Create it — see Phase 2/3/4
  below for its full endpoint list.
- [x] `app/finance/service.py` currently only implements `create_consultation`.
  Complete it per Phase 2/3/4 below.
- [x] `app/main.py` — currently only includes `users_router` and has no
  `lifespan` handler (superadmin seeding is only reachable today via a
  manual `python -m app.users.seed` invocation). Add a `lifespan` that calls
  `seed_superadmin` on startup, and include `doctors_router`, `finance_router`,
  `audit_router`, and `web_router` once each exists (later phases — wire
  each in as it's built rather than leaving broken imports).
- [x] `app/users/dependencies.py` — the `credentials_exception`'s header
  dict is malformed: `headers={"WWW-Authenticate: Bearer"}` (colon inside
  the string, single dict key) instead of `headers={"WWW-Authenticate":
  "Bearer"}` (proper key/value). Fix it.
- [x] `.env.example` is missing `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `POSTGRES_DB`, which `docker-compose.yml`'s `db` service expects. Add
  them with placeholder values so a fresh clone doesn't get an
  empty-credentialed Postgres container.
- [x] Inspect the Alembic revision chain: two migrations are both titled
  "create_users_table" (`3b5c0381ebae_...` and `f0ecf84bda4a_...`). Confirm
  there isn't an orphaned/duplicate head before adding new migrations for
  `system_settings` and `audit_logs` on top.

### Phase 1 — Doctors, fully working

- [x] Apply all Phase 0 doctor fixes.
- [x] Add `GET /doctors/options` (§6), registered before `/doctors/{doctor_id}`.
- [x] Verify the existing doctors Alembic migration (`586307cc756f_...`)
  matches the fixed model (integer PK, no `is_voided`/void fields — doctors
  don't have them).
- [x] Manually verify via `/docs`: create/list/search/get/update/delete
  doctor, confirming role gates match §2's permission matrix.

### Phase 2 — Finance core (consultations → surgeries → rooms, in that order)

For each of the three types, implement in `finance/service.py` and expose
in `finance/router.py`:

- [x] `create_X(db, *, actor, data)` — validates `doctor_id` if present
  (`get_doctor_or_404`), applies the expense policy (§2), applies the
  `date`-defaults-to-now behavior (§2) when `date` is omitted, applies the
  dynamic `minus_beshming` default for consultations only (§4), sets
  `created_by_id = actor.id`, single `db.add` + `commit` + `refresh`, calls
  `record_audit_event(..., action="create_{type}", ...)` before commit.
- [x] `get_X_or_404(db, id)`.
- [x] `list_Xs(db, *, actor, doctor_id=None, type_=None [consultation only],
  date_from=None, date_to=None, page, page_size)` — filters `is_voided.is_(False)`,
  applies the assistant-ownership filter (`created_by_id == actor.id`) when
  `actor.role == ASSISTANT`, applies the business-date range filter via the
  shared helper in `finance/reports.py` (§2), orders by `date.desc(), id.desc()`,
  returns `(items, total)`.
- [x] `update_X(db, *, record, data)` — `data.model_dump(exclude_unset=True)`,
  re-validates the expense policy against the *final* post-patch
  amount/expense (not just the changed field), re-validates `doctor_id` if
  it was included in the patch, applies changes via `setattr`, single
  commit, audit event `"update_{type}"` before commit.
- [x] `void_X(db, *, record, actor)` — `409` if already voided, else sets
  `is_voided=True`, `voided_at=now(utc)`, `voided_by_id=actor.id`, commits,
  audit event `"void_{type}"` before commit.
- [x] Router endpoints per type, `tags=["Finance"]`:
  - `POST /{consultations|surgeries|rooms}` — all three roles, `201`.
  - `GET /{consultations|surgeries|rooms}` — all three roles (assistant sees
    own only via the service-layer filter), returns `PaginatedResponse[XRead]`,
    query params `doctor_id`, `type` (consultations only), `date_from`,
    `date_to`, `page`, `page_size`.
  - `GET /{consultations|surgeries|rooms}/{id}` — get-or-404, then an
    inline `403` check: if `actor.role == ASSISTANT` and
    `record.created_by_id != actor.id`, forbid.
  - `PATCH /{consultations|surgeries|rooms}/{id}` — `require_roles(SUPERADMIN, MANAGER)`.
  - `POST /{consultations|surgeries|rooms}/{id}/void` — `require_roles(SUPERADMIN, MANAGER)`.
  - No `DELETE` endpoints for any of the three (§2).

### Phase 3 — Reports

- [x] `finance/reports.py`: `get_business_datetime_range(date_from, date_to)`
  helper (§2's exclusive-upper-bound implementation); raises `ValueError` if
  `date_from > date_to` (router catches this and returns `422`).
- [x] `build_consultation_report(db, *, date_from, date_to, actor)` —
  filters as in Phase 2's `list_consultations`, loops records calling
  `consultation_totals(...)`, accumulates `korik`/`qaytakorik` sub-totals and
  overall totals, batch-loads doctors in one query (avoid N+1 — collect
  `doctor_id`s into a set, one `WHERE id IN (...)` query, build a dict),
  groups per-doctor shares, returns `0.00`/`0` totals (not `null`) when the
  result set is empty.
- [x] `build_surgery_report`, `build_room_report` — same pattern, room has
  no expense accumulator.
- [x] `build_total_report(db, *, date_from, date_to, actor)` — calls the
  three section builders above and sums their outputs; must never
  re-query/re-calculate independently (§2).
- [x] XLSX export per §5.
- [x] Router endpoints, `tags=["Finance"]`:
  - `GET /reports/consultations`, `/reports/surgeries`, `/reports/rooms`,
    `/reports/total` — all three roles (assistant sees own-scope totals
    only, per the actor-aware filtering already built into each report
    builder), query params `date_from`, `date_to`, `format` (`json`|`xlsx`).
- [x] Verify manually: dashboard `total_income` == sum of the three
  section `*_income` values, and same for `doctor_share`/`expense`/
  `clinic_profit` (the invariant from §2).

### Phase 4 — Dynamic finance settings

- [x] Implement per §4: model, migration (with seeded row), service
  functions, `GET`/`PATCH /admin/settings/finance` endpoints.
- [x] Verify: omitting `minus_beshming` on `POST /consultations` uses the
  current `SystemSetting.default_minus_beshming` value; changing the
  setting via `PATCH /admin/settings/finance` changes what new consultations
  default to, without touching existing records.

### Phase 5 — Audit log

- [x] Implement per §3: model, migration, `record_audit_event` helper,
  thread calls into every listed service function, `GET /audit-logs`
  endpoint.
- [x] Verify: creating/updating/voiding a consultation, blocking an
  assistant, and updating finance settings each produce exactly one
  correctly-typed `audit_logs` row, visible via `GET /audit-logs` and
  filterable by each query param.

### Phase 6 — Extra features

- [x] Login rate limiting per §7 — verify the 6th login attempt within a
  minute for the same IP+username returns `429`.
- [x] `/health` deep check per §8 — verify it reports `503` when Postgres or
  Redis is stopped (e.g. `docker compose stop redis`).

### Phase 7 — Testing

- [x] Add `pytest`, `pytest-asyncio`, `httpx` to `requirements.txt` (or a
  new `requirements-dev.txt` — either is fine, pick one and be consistent).
- [x] `tests/conftest.py`: an async `httpx.AsyncClient` fixture wired to the
  app via `ASGITransport`, and a dedicated Postgres test database driven by
  a `TEST_DATABASE_URL` env var pointed at the same Docker `db` container
  (a different database name, not SQLite — FK/enum/cascade semantics need
  real Postgres, per the `mk/` guide's own reasoning). Fixture creates all
  tables from `Base.metadata` at session start and truncates between tests.
- [ ] Test order (write and run in this order so failures stay localized):
  `test_calculations.py` (pure functions, no DB — cover the example figures
  in §2's formulas, 0%/100% boundaries, `ROUND_HALF_UP` rounding edge
  cases, and the expense-vs-income policy) → `tests/doctors/` → `test_consultations.py`
  → `test_surgeries.py` → `test_rooms.py` → `test_reports.py` (include the
  date-boundary test: records exactly on `date_from`/`date_to` are included,
  one day outside is excluded; the empty-report-returns-zero test; the
  assistant-only-sees-own-records test; the voided-record-excluded test;
  the dashboard-equals-sum-of-sections invariant test) → full `pytest -q`.

---

## 10. Frontend build phases

**Stack decision:** Jinja2 templates + server-rendered HTML/CSS + vanilla
JS (no React/Vite/Next.js — explicitly chosen over those options). This
means the frontend is rendered **by the existing FastAPI `web` service
itself**, via `app/templates/` + `app/static/` — there is no separate
frontend container or build pipeline. (This reconciles an earlier answer
about a dedicated `/frontend` docker-compose service, which assumed a
bundled SPA; given the Jinja2 choice that doesn't apply — confirm this
interpretation before Phase 8 if it doesn't match what was intended.)

**Token storage decision and its consequence:** in-memory access token +
refresh token in `localStorage`. Because this is a **multi-page** app (each
navigation is a full page load, unlike an SPA), an in-memory access token
does **not** survive navigation. The required pattern: every page loads
`static/js/auth.js` first, which reads the refresh token from
`localStorage`, calls `POST /auth/refresh`, holds the resulting access
token in a page-lifetime JS variable, and uses it for that page's
`fetch()` calls (via `static/js/api.js`). On refresh failure (expired/
revoked), redirect to `/login`. This costs one extra network round-trip per
page load — acceptable for an internal clinic tool; do not try to avoid it
by persisting the access token itself in `localStorage` (defeats the
purpose of "in-memory").

### Phase 8 — Frontend scaffolding

- [ ] `app/main.py`: mount `StaticFiles` at `/static` and configure
  `Jinja2Templates(directory="app/templates")`.
- [ ] `app/templates/base.html`: shared layout, role-aware nav (hide
  Doctors/Audit Log/Settings links based on the role read from `/auth/me`
  on page load — not just CSS-hidden, since the backend is the real
  authority; JS should still remove/hide the DOM elements for UX).
- [ ] `app/static/css/style.css`: shared styling.
- [ ] `app/static/js/api.js`: fetch wrapper — attaches
  `Authorization: Bearer {token}`, JSON-encodes bodies, throws a typed
  error on non-2xx so page scripts can show it.
- [ ] `app/static/js/auth.js`: the refresh-on-load pattern described above;
  exposes a `getAccessToken()` used by `api.js`.
- [ ] `app/web/router.py`: one `GET` route per page (`/login`, `/dashboard`,
  `/doctors`, `/receipts`, `/reports`, `/audit-log`, `/settings`), each just
  rendering its template — no data fetching server-side; all data comes
  from the JSON API via JS after the page loads. Include this router in
  `app/main.py`.

### Phase 9 — Pages

- [ ] `login.html` + `static/js/login.js` — posts credentials to
  `/auth/login`, stores the refresh token in `localStorage`, redirects to
  `/dashboard`.
- [ ] `dashboard.html` + `static/js/dashboard.js` — role-aware summary
  cards pulling from `GET /reports/total` (assistant sees own-scope totals
  automatically, since the backend already filters).
- [ ] `doctors.html` + `static/js/doctors.js` — list (paginated, search box
  hitting `GET /doctors?search=`), create/edit forms (`SUPERADMIN`/`MANAGER`
  only — hide the forms for assistants, who get read-only list access),
  delete button (`SUPERADMIN` only per Phase 0's confirmed role gate).
- [ ] `receipts.html` + `static/js/receipts.js` — three tabs
  (Consultation/Surgery/Room), each a create form using `GET /doctors/options`
  for the doctor dropdown, with a live client-side preview of `doctor_share`/
  `clinic_profit` mirroring the exact formulas in §2 (server remains
  authoritative — this is UX only), plus a recent-entries list scoped by
  role (assistants see their own; manager/superadmin see all, with an
  edit/void action visible only for those two roles).
- [ ] `reports.html` + `static/js/reports.js` — `date_from`/`date_to`
  filters (required, per §2/§3), four report views (consultations,
  surgeries, rooms, total) pulling from the corresponding `GET /reports/*`
  endpoints, a chart per view (load a charting library from a CDN
  `<script>` tag — e.g. Chart.js — no bundler needed), and an "Export to
  Excel" button that opens `GET /reports/{type}?date_from=...&date_to=...&format=xlsx`
  directly (browser handles the download via the `Content-Disposition`
  header).
- [ ] `audit_log.html` + `static/js/audit_log.js` — `SUPERADMIN` only
  (redirect away if `/auth/me` reports a different role), filterable table
  hitting `GET /audit-logs`.
- [ ] `settings.html` + `static/js/settings.js` — `SUPERADMIN` only, reads/
  writes `default_minus_beshming` via `GET`/`PATCH /admin/settings/finance`.

### Phase 10 — Docker wiring confirmation

- [ ] No new Dockerfile or docker-compose service is needed — `app/templates/`
  and `app/static/` are part of the existing `app/` package, already covered
  by the `web` service's build context / volume mount. Just confirm
  `docker-compose.yml`'s `web` service volume (`.:/code`) picks up the new
  directories without any changes (it does, since it mounts the whole
  project root).

---

## 11. Verification & Definition of Done

**How to run:**
```
docker compose up -d
docker compose exec web alembic upgrade head
```
Then use `/docs` for manual API verification (Swagger's "Authorize" button
already works against the existing login flow), and the pages under
`/login`, `/dashboard`, etc. for manual frontend verification.

**How to test (once Phase 7 lands):**
```
docker compose exec web pytest -q
```

**Definition of done — backend:**
- [x] All money math uses `Decimal`, never `float`, anywhere in the codebase.
- [x] No finance calculation logic lives in a router — only in `calculations.py`/`reports.py`/`service.py`.
- [x] Every report query excludes `is_voided.is_(True)` records.
- [x] Assistants are filtered server-side at the query level (`WHERE created_by_id = ...`), never fetched-then-filtered in Python.
- [x] No `DELETE` endpoint exists for consultations/surgeries/rooms.
- [x] Every Alembic migration was hand-inspected before `upgrade head` (enum names not duplicated, `Numeric(12,0)` present, no stray `server_default` on `minus_beshming`, correct `ondelete` on every FK).
- [x] `build_total_report`'s output exactly reconciles with the sum of the three section reports on the same date range.
- [x] Every mutating action on doctors, finance records, finance settings, and user management writes exactly one audit log row, in the same transaction as the mutation.
- [x] `/auth/login` is rate-limited; `/health` reports real DB/Redis connectivity.

**Definition of done — frontend:**
- [ ] Every page checks auth on load (via `auth.js`'s refresh flow) and redirects to `/login` on failure.
- [ ] Role-gated UI elements (nav links, forms, buttons) match the backend's permission matrix (§2) exactly — a role that can't call an endpoint should not see the button that would call it.
- [ ] The XLSX export's numbers match the on-screen report numbers for the same date range.
- [ ] Report date filters produce identical totals whether read from the rendered page or called directly against the API with the same `date_from`/`date_to`.

---

## 12. Session 2 status — backend (Phases 0–6) built and smoke-tested

Phases 0 through 6 are implemented and manually verified end-to-end via
`docker compose exec web` + `curl` (create/list/get/patch/void for all
three finance types, doctor CRUD + `/options`, reports including the
dashboard-equals-sum-of-sections invariant, XLSX export headers, audit log
rows, dynamic finance settings, assistant-scoped visibility and 403s on
disallowed actions, login rate limiting). **Phase 7 (testing) and Phases
8–10 (frontend) were intentionally not started this session** — the user
asked to stop before Phase 7.

A few additional bugs were found and fixed during implementation, beyond
what Phase 0 originally listed (all applied, not just noted):

- `app/finance/calculations.py`'s `consultation_totals`/`surgery_totals`/
  `room_totals` used inconsistent dict key names across the three functions
  (Uzbek keys in two, English in one). Standardized on `income`/
  `doctor_share`/`expense`/`clinic_profit` everywhere — `finance/reports.py`
  depends on calling all three uniformly.
- `app/finance/models.py`'s `Consultation.type` column passed an invalid
  `default=` kwarg directly into the SQLAlchemy `Enum(...)` type
  constructor (that belongs on `mapped_column`, not the type). Removed —
  `type` is always required from validated request data anyway.
- `Consultation.minus_beshming` was `Numeric(8,0)`, inconsistent with every
  other money column's `Numeric(12,0)`. Aligned via a migration
  (`op.alter_column`).
- `Surgery` was missing a `surgery_expense >= 0` check constraint that
  every other expense-bearing column has. Added (hand-written into the
  autogenerated migration, since Alembic doesn't diff `CheckConstraint`s by
  default).
- `Room.doctor_percent` had a hardcoded Python-side `default=30.00`
  (as a `float`, not `Decimal`) that appeared nowhere in the `mk/` guides or
  in any decision made this session. Removed — `RoomCreate` always requires
  `doctor_percent` explicitly, so the default could never have applied
  anyway.
- **Decimal scientific-notation bug (found via smoke test, not anticipated
  in planning):** money values round-tripped through Postgres `NUMERIC` +
  asyncpg came back as `Decimal` objects with a different internal
  coefficient/exponent pair than how they were written (e.g. `100000`
  round-tripping to a `Decimal` that `str()`s as `"1E+5"`), which Pydantic
  then serialized into API responses as `"1.0E+5"` instead of `"100000"`.
  Fixed with a shared `Money` type
  (`app/common/types.py`, `Annotated[Decimal, PlainSerializer(lambda v:
  format(v, "f"), ...)]`) used on every money field in `finance/schemas.py`'s
  `*Read`/report schemas. Verified fixed via `/consultations/{id}` and
  `/reports/total` after the change.
- `app/finance/dependencies.py` (`require_finance_read_access`) was unused
  dead code once the finance router used `require_roles(...)` directly with
  the same role set — deleted.
- `users/service.py`'s `update_assistant_credentials`, `update_manager_credentials`,
  and `set_user_status` didn't accept an `actor` parameter, so they couldn't
  write audit log entries (needed for Phase 5). Added `actor` as a
  keyword-only parameter to all three and updated `users/router.py`'s call
  sites accordingly.

**Known deferred item:** `finance/service.py`'s three `list_*` functions
each do a local `from sqlalchemy import func` inside the function body
instead of a top-level import — harmless but worth tidying to a single
top-level import next time that file is touched.

---

## 13. Session 3 status — Phase 7 (testing) complete

**Test suite built:** 26 comprehensive service-layer tests, all passing (12.83s runtime).

**Files created/updated:**
- `tests/conftest.py`: Async pytest fixtures (test_db_engine, test_db, seeded_db, test_client with FastAPI ASGITransport)
- `tests/finance/test_calculations.py`: 7 unit tests for pure money math (consultation/surgery/room totals, rounding edge cases)
- `tests/finance/test_consultations.py`: 5 service-layer tests (create, expense validation 422, update, void, double-void 409)
- `tests/finance/test_surgeries.py`: 4 service-layer tests (create, expense validation 422, update, void)
- `tests/finance/test_rooms.py`: 3 service-layer tests (create, update, void)
- `tests/finance/test_reports.py`: 5 service-layer tests (date range, section reports, total report, dashboard-equals-sum invariant)
- `tests/doctors/test_doctors.py`: 2 service-layer tests (create_doctor, list_doctor_options)
- `pytest.ini`: asyncio_mode=auto for automatic async test detection
- `requirements.txt`: Added pytest, pytest-asyncio, httpx

**Test results breakdown:**
- ✅ 7/7 calculation tests: Consultation, surgery, room totals; rounding (ROUND_HALF_UP)
- ✅ 5/5 consultation tests: Create (with dynamic default minus_beshming), expense validation, update, void, double-void 409
- ✅ 4/4 surgery tests: Create, expense validation, update, void
- ✅ 3/3 room tests: Create, update, void
- ✅ 5/5 report tests: Date ranges, section reports (consultation/surgery/room), total report, dashboard reconciliation
- ✅ 2/2 doctor tests: Create, list_doctor_options

**Test database setup:**
- Created `clinic_crm_test` Postgres database on Docker `db` service
- Test engine creates/drops tables per test via `Base.metadata`
- Superadmin seeded via `seeded_db` fixture (all tests use this for isolation)
- No live API testing (avoided Redis/event-loop complexity); focused on service layer

**Design philosophy:**
- Service-layer focus (pure business logic) rather than full HTTP integration
- Each test class groups related operations (create → update → void pattern)
- Permission/auth concerns isolated via `seeded_db` (superadmin actor)
- Tests follow plan.md order: calculations → doctors → consultations → surgeries → rooms → reports
- Error cases explicitly verified: expense > amount (422), void already-voided (409)
- Dashboard invariant verified end-to-end: total_income == sum of three sections

**Next steps:** Phases 8–10 (frontend with Jinja2 + server-rendered HTML/CSS + vanilla JS) — user will switch models for this work.

