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
  | Create/edit/block/unblock managers | Y | N (edit: self only, via `PATCH /users/managers/{own id}`) | N |
  | Create/edit/block/unblock assistants | Y | Y | N |
  | Rotate own login credentials | Y (`PATCH /users/superadmin`) | Y (`PATCH /users/managers/{own id}`) | N (no self-service endpoint exists for assistants) |

  (Last two rows added in §16 — they were previously governed only by
  `require_roles(...)` in `users/router.py` with no table row describing
  them, which is why the frontend gap went unnoticed for two sessions.)

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

- [x] `app/main.py`: mount `StaticFiles` at `/static` and configure
  `Jinja2Templates(directory="app/templates")`.
- [x] `app/templates/base.html`: shared layout, role-aware nav (hide
  Doctors/Audit Log/Settings links based on the role read from `/auth/me`
  on page load — not just CSS-hidden, since the backend is the real
  authority; JS should still remove/hide the DOM elements for UX).
- [x] `app/static/css/style.css`: shared styling.
- [x] `app/static/js/api.js`: fetch wrapper — attaches
  `Authorization: Bearer {token}`, JSON-encodes bodies, throws a typed
  error on non-2xx so page scripts can show it.
- [x] `app/static/js/auth.js`: the refresh-on-load pattern described above;
  exposes a `getAccessToken()` used by `api.js`.
- [x] `app/web/router.py`: one `GET` route per page (`/login`, `/dashboard`,
  `/doctors-page`, `/receipts`, `/reports`, `/audit-log`, `/settings`), each
  just rendering its template — no data fetching server-side; all data
  comes from the JSON API via JS after the page loads. Included in
  `app/main.py`.
  **Deviation from this section's original path list:** the doctors page
  had to move from `/doctors` to `/doctors-page` — `GET /doctors` is
  already the finance API's paginated doctor list (`app/doctors/router.py`),
  and registering a page route at the identical path+method shadows
  whichever router loads second (discovered by curling the page and
  getting a `401` JSON body instead of HTML). No other page path collided
  with an existing API path. `app/static/js/nav.js` links to `/doctors-page`
  accordingly; `app/static/js/doctors.js`'s API calls are unaffected since
  they correctly still target `/doctors`.

### Phase 9 — Pages

- [x] `login.html` + `static/js/login.js` — posts credentials to
  `/auth/login`, stores the refresh token in `localStorage`, redirects to
  `/dashboard`.
- [x] `dashboard.html` + `static/js/dashboard.js` — role-aware summary
  cards pulling from `GET /reports/total` (assistant sees own-scope totals
  automatically, since the backend already filters).
- [x] `doctors.html` + `static/js/doctors.js` — list (paginated, search box
  hitting `GET /doctors?search=`), create/edit forms (`SUPERADMIN`/`MANAGER`
  only — hide the forms for assistants, who get read-only list access),
  delete button (`SUPERADMIN` only per Phase 0's confirmed role gate).
  Served at `/doctors-page` — see Phase 8's deviation note.
- [x] `receipts.html` + `static/js/receipts.js` — three tabs
  (Consultation/Surgery/Room), each a create form using `GET /doctors/options`
  for the doctor dropdown, with a live client-side preview of `doctor_share`/
  `clinic_profit` mirroring the exact formulas in §2 (server remains
  authoritative — this is UX only), plus a recent-entries list scoped by
  role (assistants see their own; manager/superadmin see all, with a void
  action visible only for those two roles — there is no finance-record
  edit form in the UI yet, only create + void; `PATCH` is exercised via
  `/docs` today).
- [x] `reports.html` + `static/js/reports.js` — `date_from`/`date_to`
  filters (required, per §2/§3), four report views (consultations,
  surgeries, rooms, total) pulling from the corresponding `GET /reports/*`
  endpoints, a Chart.js bar chart per view (loaded from the cdnjs CDN), and
  an "Export to Excel" button that downloads
  `GET /reports/{type}?date_from=...&date_to=...&format=xlsx` via a
  Blob/object-URL (needed because the download must carry the bearer
  token — a plain `<a href>` can't attach an Authorization header).
- [x] `audit_log.html` + `static/js/audit_log.js` — `SUPERADMIN` only
  (redirect away if `/auth/me` reports a different role), filterable table
  hitting `GET /audit-logs`.
- [x] `settings.html` + `static/js/settings.js` — `SUPERADMIN` only, reads/
  writes `default_minus_beshming` via `GET`/`PATCH /admin/settings/finance`.

### Phase 10 — Docker wiring confirmation

- [x] No new Dockerfile or docker-compose service was needed —
  `app/templates/` and `app/static/` are part of the existing `app/`
  package, covered by the `web` service's build context / volume mount.
  Confirmed live via `docker compose up -d --build` +
  `docker compose exec web alembic upgrade head`: `/login`, `/dashboard`,
  `/doctors-page`, `/receipts`, `/reports`, `/audit-log`, `/settings` all
  return `200`, `/static/css/style.css` and `/static/js/api.js` are served,
  and a real login → `/auth/me` → `/doctors/options` →
  `/admin/settings/finance` → `/reports/total` round trip succeeds.
  **One dependency gap found and fixed:** `jinja2` was never in
  `requirements.txt` (only pulled in transitively before, or not at all) —
  `app/web/router.py`'s `Jinja2Templates` import crashed the app on
  startup with `ImportError: jinja2 must be installed`. Added `jinja2` to
  `requirements.txt`.

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
- [x] Every page checks auth on load (via `auth.js`'s refresh flow) and redirects to `/login` on failure. Verified in a real browser for both superadmin and a test assistant account: direct navigation to `/audit-log` and `/settings` as the assistant redirects to `/dashboard`.
- [x] Role-gated UI elements (nav links, forms, buttons) match the backend's permission matrix (§2) exactly — a role that can't call an endpoint should not see the button that would call it. Verified in-browser for both superadmin (full nav, doctor add/edit/delete, void buttons) and assistant (nav hides Doctors-management/Audit Log/Settings actions, doctors list is read-only with no action buttons, receipts list has no Void action, "Recent entries" is correctly scoped to the assistant's own records only).
- [x] The XLSX export's numbers match the on-screen report numbers for the same date range. Verified the export request itself succeeds (`GET /reports/consultations?...&format=xlsx` → `200`) with the exact date range shown on screen; the response is a Blob downloaded client-side, so byte-level spreadsheet content wasn't opened, but the backend export path (same code, no separate calculation) was already unit/manually verified in Session 2.
- [x] Report date filters produce identical totals whether read from the rendered page or called directly against the API with the same `date_from`/`date_to`. Verified: the total report's numbers in the browser (2,750,000 / 643,000 / 305,000 / 1,802,000) reconcile exactly against the three section reports' own on-screen numbers for the same range, matching the dashboard-equals-sum-of-sections invariant.

## 15. Session 5 — manual in-browser click-through (Claude in Chrome)

Used the `claude-in-chrome` skill to actually click through every page as a
real browser DOM, not just curl. Found and fixed three real bugs that the
Session 4 curl-based verification could not have caught:

- **Chart.js CDN version was wrong** (`reports.html` pinned
  `Chart.js/4.4.4/chart.umd.min.js`, which 404s — cdnjs never published a
  4.4.4 build). Every report page loaded with `Uncaught ReferenceError:
  Chart is not defined` in the console and the "Total"/section report tabs
  rendered a red "Chart is not defined" error box instead of the bar chart.
  Fixed by pinning to the actual latest cdnjs version, `4.5.1`
  (`chart.umd.min.js`), confirmed both a 200 from `curl` and a rendering
  chart in the browser afterward.
- **Success messages vanished instantly after every create/update/delete/void**
  on the Doctors and Receipts pages. `doctors.js`/`receipts.js` called
  `showSuccess(...)` and then immediately called the list-reload function
  (`loadDoctors()`/`loadRecent()`), and that reload function's own
  `clearMessages()` wiped the success box before it ever painted — so
  "Doctor created", "Consultation created", "Record voided", etc. never
  appeared, even though the mutation itself succeeded. Fixed by reordering
  every such handler to `await` the reload first and call `showSuccess(...)`
  after it, in `app/static/js/doctors.js` (create/update, delete) and
  `app/static/js/receipts.js` (all three create handlers, void). The list
  reload's own `clearMessages()` is unchanged and still correctly clears a
  *stale* success message when the user takes an unrelated action (switches
  tabs, paginates, searches).
- **Minor UX inaccuracy, not a bug per se:** the consultation receipt
  preview showed `expense: 0` when "Minus beshming" was left blank, but the
  server actually substitutes the clinic's dynamic default (5,000 at the
  time of testing) — so the previewed doctor share/clinic profit undercounted
  the real expense by that amount. Confirmed by creating a real consultation
  with amount 200,000 / 40%: preview said "expense: 0, doctor share: 80,000"
  but the created record (and the reports built from it) correctly showed
  expense 5,000, doctor share 78,000. Fixed `updateConsultationPreview()` in
  `receipts.js` to append a note when the field is blank, rather than
  silently implying zero.

**Also verified working correctly, no changes needed:** login/logout,
refresh-token flow surviving page navigation, doctor create/edit/list/search/
pagination, all three receipt-entry tabs (consultation/surgery/room) with
live client-side preview math matching the server's actual computed values
(once the default-expense note above is accounted for), the recent-entries
list per tab (correct headers per type, correct status/void-button
visibility), the reports page's four tabs and their doctor-share
breakdown tables, the audit log's resource-type filter, and the finance
settings read/write round trip. The `GET /doctors` vs. `/doctors-page`
routing fix from Session 4 was confirmed correct in the browser too (nav
link goes to the right place, no 401 JSON flash).

One coordinator-side gotcha, not a product bug: the `computer` tool's
simulated coordinate clicks intermittently failed to register on this page
(most clicks by ref/coordinate on tab buttons and edit buttons had no
effect, confirmed via `read_page`/`javascript_tool` that the DOM's own
`.click()` and `requestSubmit()` worked immediately). Worked around by
driving state changes through `javascript_tool` (`element.click()` /
`form.requestSubmit()`) and using screenshots purely to verify the
resulting state, not to aim clicks.

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

**Next steps (at the time):** Phases 8–10 (frontend with Jinja2 +
server-rendered HTML/CSS + vanilla JS) — user was going to switch models
for this work.

---

## 14. Session 4 status — Phases 8–10 (frontend) complete

All pages built and verified end-to-end against the real Docker stack
(Postgres + Redis + FastAPI, `docker compose up -d --build` +
`alembic upgrade head`): `/login`, `/dashboard`, `/doctors-page`,
`/receipts`, `/reports`, `/audit-log`, `/settings` all render; login →
`/auth/me` → `/doctors/options` → `/admin/settings/finance` →
`/reports/total` all round-trip correctly through the same fetch wrapper
the pages use. `pytest -q` still 26/26 passing after the frontend changes.

**Files added:** `app/web/__init__.py`, `app/web/router.py`,
`app/templates/{base,login,dashboard,doctors,receipts,reports,audit_log,settings}.html`,
`app/static/css/style.css`,
`app/static/js/{api,auth,nav,login,dashboard,doctors,receipts,reports,audit_log,settings}.js`.
`nav.js` (shared role-aware nav + `initPage()`/`requireAuth()` bootstrap) was
not in the original file list but was added because every other page script
needed the same auth-check-and-render-nav boilerplate.

**Deviations/bugs found and fixed this session (beyond the two logged in
Phase 8/10 above):**
- `.env` / `.env.example` were missing `TEST_DATABASE_URL`, so
  `tests/conftest.py` fell back to its `localhost` default, which doesn't
  resolve from inside the `web` container (needs the `db` service
  hostname) — every DB-backed test failed with a connection `OSError`
  until this was set to
  `postgresql+asyncpg://postgres:...@db:5432/clinic_crm_test`. This was
  presumably run with an ad-hoc env var outside of `.env` in Session 3;
  now it's committed so `pytest -q` works out of the box after
  `docker compose up`.
- The doctors page/API path collision (`GET /doctors` page vs.
  `GET /doctors` list API) — see Phase 8's deviation note above.

**Known gaps / not yet done:**
- No in-browser (real browser, not curl) click-through was performed —
  verification was via `curl`/API calls that reproduce exactly what the
  page JS calls, plus code review, not a rendered DOM. The two unchecked
  Definition-of-Done items above (XLSX-matches-on-screen, manager/assistant
  role-gating) should be clicked through in an actual browser before
  calling the frontend fully done.
- `receipts.html` has no edit form for existing finance records (only
  create + void) — `PATCH /{consultations|surgeries|rooms}/{id}` exists
  and works but isn't wired to any UI yet. Not explicitly required by
  Phase 9's checklist wording, but worth flagging as a likely next ask.
- `doctors.html`'s edit button re-populates the form from the already-
  fetched page of results (no extra `GET /doctors/{id}` call) — fine
  since `list_doctors` returns full `DoctorRead` objects, just noting the
  assumption in case that response shape ever gets trimmed.

---

## 16. Session 6 — full API ↔ frontend parity audit (planning only, no code changed this session)

Requested: check every backend endpoint against the frontend to confirm
nothing is orphaned, and check that business logic (role gates in
particular) is actually reachable through the UI. This section is the
audit result and the plan for closing the gaps — **no implementation
happens until this plan is reviewed**, per instruction.

### 16.1 Endpoint-by-endpoint usage matrix

**`app/users/router.py`** (Auth/users — pre-existing module, working, not
part of this project's build phases per §0):

| Endpoint | Used in frontend? |
|---|---|
| `POST /auth/login` | Yes — `login.js` |
| `POST /auth/refresh` | Yes — `auth.js` |
| `POST /auth/logout` | Yes — `auth.js` (`nav.js`'s logout button) |
| `GET /auth/me` | Yes — `auth.js` (`requireAuth()`), drives all role-gating |
| `POST /users/managers` (create) | **No** |
| `PATCH /users/managers/{id}` (update) | **No** |
| `POST /users/managers/{id}/block` | **No** |
| `POST /users/managers/{id}/unblock` | **No** |
| `POST /users/assistants` (create) | **No** |
| `PATCH /users/assistants/{id}` (update) | **No** |
| `POST /users/assistants/{id}/block` | **No** |
| `POST /users/assistants/{id}/unblock` | **No** |
| `PATCH /users/superadmin` (self credentials) | **No** |

This matches what you flagged: 9 of 13 `users` endpoints have zero UI path.
There is also a **backend gap underneath the frontend gap**: there is no
`GET` endpoint to list managers or assistants at all (confirmed — no
`list_users`/`list_managers`/`list_assistants` function exists in
`app/users/service.py`, and `app/users/router.py` has exactly one `GET`,
`/auth/me`). A user-management page can't show *which* managers/assistants
exist to edit/block/unblock without one — this has to be added to the
backend first, it isn't just a missing page.

**`app/doctors/router.py`:**

| Endpoint | Used in frontend? |
|---|---|
| `POST /doctors` (create) | Yes — `doctors.js` |
| `GET /doctors/options` | Yes — `receipts.js` (dropdowns) |
| `GET /doctors/{id}` (single) | No — `doctors.js`'s edit form reuses the already-fetched list row instead (see the note directly above this section) |
| `PATCH /doctors/{id}` | Yes — `doctors.js` |
| `GET /doctors` (list) | Yes — `doctors.js` |
| `DELETE /doctors/{id}` | Yes — `doctors.js` |

Doctors is fully wired except the single-record `GET`, which is
intentionally redundant given the list already returns full objects — not
a gap.

**`app/finance/router.py`:**

| Endpoint | Used in frontend? |
|---|---|
| `POST /consultations` / `/surgeries` / `/rooms` (create) | Yes — `receipts.js` |
| `GET /consultations` / `/surgeries` / `/rooms` (list) | Yes — `receipts.js` (recent entries) |
| `GET /consultations/{id}` / `/surgeries/{id}` / `/rooms/{id}` (single) | No |
| `PATCH /consultations/{id}` / `/surgeries/{id}` / `/rooms/{id}` (update) | **No** |
| `POST .../{id}/void` (all three) | Yes — `receipts.js` |
| `GET /reports/{consultations|surgeries|rooms|total}` | Yes — `reports.js`, `dashboard.js` |
| `GET /reports/{type}?format=xlsx` | Yes — `reports.js` (Export to Excel) |
| `GET /admin/settings/finance` | Yes — `settings.js` |
| `PATCH /admin/settings/finance` | Yes — `settings.js` |

The three `PATCH .../{id}` endpoints (edit an existing consultation,
surgery, or room) are unused — this was already flagged as a known gap in
§14/Session 4 ("`receipts.html` has no edit form for existing finance
records"). This audit confirms it's still open and adds it to the formal
plan below. The single-record `GET`s are the same story as doctors': not a
gap by themselves, only needed if the edit UI needs a fresh fetch rather
than reusing the already-loaded list row (it won't — same pattern as
`doctors.js` works fine here too).

**`app/audit/router.py`:** `GET /audit-logs` — Yes, fully used by
`audit_log.js`.

**`/health`, `/docs`, `/openapi.json`:** infrastructure/tooling endpoints,
not applicable to frontend wiring.

### 16.2 Business-logic-reachability check (beyond raw endpoint coverage)

Re-reading §2's permission matrix against what's actually clickable:

- Every row of §2's matrix **except user lifecycle management** has a UI
  path today: doctor CRUD, finance record create/view/update(void-only)/
  void, section/total reports scoped by role, audit log, finance settings.
  "Update finance record" (full field edit, not just void) is technically
  in the matrix as Superadmin/Manager-only but has no UI trigger — same gap
  as 16.1's `PATCH` finding, just restating it from the permissions angle.
- User lifecycle (create/update/block/unblock manager or assistant) was
  never in §2's matrix at all — it's governed by `require_roles(...)`
  directly in `users/router.py`, not by anything this plan's permission
  table described. That's why it was easy to miss: there was no table row
  to notice was unimplemented.
- Superadmin's own credential rotation (`PATCH /users/superadmin`) has no
  matrix row either, for the same reason.

### 16.3 Proposed next steps (not yet implemented — awaiting go-ahead)

**Phase 11 — Backend: list endpoints for user management** ✅ done (Session 7)
- [x] `app/users/service.py`: added `list_users_by_role(db, *, role, page,
  page_size)` — one parameterized function (not separate
  `list_managers`/`list_assistants`) since the two queries were identical
  but for the role filter. Orders by `full_name, username`. Follows the
  same `(items, total)` + `PaginatedResponse` pattern as every other list
  function in the codebase.
- [x] `app/users/router.py`: `GET /users/managers` — `SUPERADMIN` only.
  `GET /users/assistants` — `SUPERADMIN` + `MANAGER`. Both match their
  respective create/block/unblock gates exactly.
- [x] Confirmed via manual test: a blocked user (the Session 5 test
  assistant) still appears in `GET /users/assistants` with
  `"status": "blocked"` — no status filter was added, so there's always a
  UI path to unblock someone. `pytest -q` (26/26) unaffected.

**Phase 12 — Frontend: user management page** ✅ done (Session 7)
- [x] New page at `/users-page` (not `/users` — same reasoning as the
  Phase 8 doctors collision: keeps the convention consistent and leaves
  room for a future bare `GET /users` endpoint without a rename).
  `app/web/router.py`, `app/templates/users.html`,
  `app/static/js/users.js` all added; `nav.js` gained a "Users" link
  visible to `superadmin` and `manager` (not `assistant`).
- [x] Three sections, gated exactly per the role table above:
  **Managers** (superadmin only: list/create/edit/block/unblock),
  **Assistants** (superadmin + manager: same four actions),
  **My account** (superadmin uses `PATCH /users/superadmin`, optional
  fields, blank = unchanged; manager uses `PATCH /users/managers/{own id}`,
  all three fields required including password, matching
  `ManagerCredentialsUpdate`'s schema — confirmed in
  `update_manager_credentials`/`update_superadmin_credentials` before
  building the form, per the original plan's instruction to check this).
- [x] Followed the Session 5 success-message-ordering fix (`await` the
  list reload, then `showSuccess(...)`) and the `doctors.js` edit-button
  pattern (no redundant `GET /{id}`, reuses the already-fetched list row).
- [x] Manually click-tested end-to-end via Claude-in-Chrome as superadmin:
  created a manager, edited an assistant's full name (required entering a
  new password too, as the backend demands), unblocked the Session 5 test
  assistant, and updated the superadmin's own credentials (confirmed this
  correctly invalidates the current refresh token — got redirected to
  `/login` immediately after, re-logged in successfully with the same
  password since it was left unchanged).

**Phase 13 — Frontend: finance record edit forms** ✅ done (Session 7)
- [x] Added an "Edit" action next to "Void" in `receipts.html`'s
  recent-entries table (`superadmin`/`manager` only, hidden for voided
  records). Each of the three tab forms now doubles as its own edit form
  (hidden `_id` field + a "Cancel edit" button), mirroring `doctors.js`'s
  dual-purpose-form pattern — no new `GET /{id}` calls, the row data
  already fetched by `loadRecent()` is reused directly.
- [x] Handled the §4 null-semantics reminder concretely: on the
  consultation edit form, an explicitly blanked "Minus beshming" field
  sends `"0"` (not `null`) so it can never be misread as "reapply the
  create-time dynamic default" — that only applies to `POST`. Verified by
  editing consultation #1001 (originally created with the then-default
  5,000 expense) and confirming the live preview and the server's
  response both showed the real stored value, not a naive re-zeroed one.
- [x] Verified `date`/`doctor_id`/all money fields round-trip correctly
  for all three record types — edited a consultation's amount (200,000 →
  250,000), a surgery's expense (300,000 → 350,000), and cancelled a room
  edit to confirm "Cancel edit" correctly reverts the form to create mode
  without submitting anything.

**Phase 14 — Re-verify** ✅ done (Session 7)
- [x] `pytest -q`: 26/26 passing after all Phase 11–13 changes.
- [x] Claude-in-Chrome click-through covered: Users page (all three
  sections, both roles' visibility rules), Receipts page's new Edit
  actions on all three record types.
- [x] §2's permission matrix updated in place (see above) with the three
  rows this audit found missing, instead of leaving them only in this
  section.

**Not done / explicitly out of scope this session:**
- No self-service credential-change endpoint exists for assistants at
  all (`PATCH /users/assistants/{id}` requires `SUPERADMIN`/`MANAGER` as
  actor, with no self-only carve-out like managers get) — an assistant's
  own password can only be changed by a manager or superadmin. This is
  existing, already-working `app/users/` behavior per §0's "do not
  redesign it" instruction, not something this session changed; flagging
  it here since it surfaced during the same audit, in case it's ever
  worth a deliberate product decision.
- `GET /doctors/{id}`, `GET /consultations|surgeries|rooms/{id}` remain
  intentionally unused (§16.1) — no change needed, list views already
  return full objects.

---

## 17. Session 8 — assistant preview hidden + full Uzbek localization

Two requests: (1) assistants must not see the clinic-economics preview
(doctor share / clinic profit / expense) when creating a receipt, and
(2) the entire frontend must be in Uzbek.

**Preview hidden from assistants:**
- [x] `app/static/js/receipts.js`: added `const showPreview = user.role
  !== "assistant";`. When false, the three preview `<div>`s
  (`c_preview`/`s_preview`/`r_preview`) get `classList.add("hidden")` at
  page load, the `input` listeners that drive `updateConsultation/Surgery/
  RoomPreview()` are never attached, and each of those three functions
  also early-returns on `!showPreview` as a second guard (so calling them
  from `enterEditMode()` during an edit can't leak the numbers either).
  Verified via Claude-in-Chrome as the `asst1` test account: typed a
  200,000 amount and 40% doctor share into the consultation form and
  confirmed via `javascript_tool` that `c_preview`'s `textContent` stayed
  `""` and it kept the `hidden` class — no doctor-share/clinic-profit
  numbers were ever computed or rendered for that role. Superadmin/manager
  are unaffected; their preview behaves exactly as before (Session 5/7).
  This is a UI-only change — the underlying `POST`/`PATCH` endpoints an
  assistant can call already never expose `doctor_share`/`clinic_profit`
  in any response body (those are always computed at report/read time
  from `calculations.py`, not returned on create), so there was no
  matching backend change needed.

**Full Uzbek localization:**
- [x] Translated every template (`base.html` through `users.html`) and
  every static JS file's user-facing string: page titles, `<h1>`/`<h2>`
  headings, form labels and placeholders, table headers, button text,
  nav links, the logged-in user's role suffix (`nav.js`'s new
  `ROLE_LABELS` map: `superadmin` → "bosh administrator", `manager` →
  "menejer", `assistant` → "yordamchi"), success/error toast messages,
  `confirm()` dialog text, status words ("Active"/"Voided" →
  "Faol"/"Bekor qilingan", "approved"/"blocked" → "faol"/"bloklangan"),
  and the consultation type dropdown's *display* text ("Korik"/
  "Qaytakorik" → "Ko'rik"/"Qayta ko'rik" — the underlying `<option
  value="korik">`/`value="qaytakorik">` were left untouched since those
  are the `ConsultationType` enum wire values the backend expects, not
  UI copy).
- [x] `<html lang="en">` → `<html lang="uz"` on both `base.html` and the
  standalone `login.html`; `<title>` tags and the brand name ("Clinic
  CRM" → "Klinika CRM") translated too.
- [x] Added a shared `paginationLabel(data)` helper to `nav.js`
  (`"${page}-sahifa, ${pages} tadan (jami ${total})"`) and used it from
  `doctors.js`, `receipts.js`, `audit_log.js`, and both list sections in
  `users.js`, replacing five separate copies of the same English "Page X
  of Y (Z total)" string — the kind of duplication that would have made
  a future English string easy to miss during this exact audit.
- [x] `users.js`'s old `capitalize(prefix)` helper (fine for English
  "manager"/"assistant") was replaced with a `LABELS` map giving the
  correct Uzbek noun and accusative form per role
  (`{ manager: { noun: "Menejer", article: "bu menejerni" }, assistant:
  { noun: "Yordamchi", article: "bu yordamchini" } }`), since Uzbek
  grammar doesn't reduce to "capitalize the English word."
- [x] **Deliberately left untranslated:** data values entered by users
  (doctor names/specialties, usernames, full names) — those are content,
  not UI chrome, and translating them would corrupt real data. Also left
  alone: `app/users/router.py`'s existing Uzbek-language backend error
  string (`"Login yoki Parol xato, Adminga murojaat qiling!"`) and the
  `korik`/`qaytakorik`/`minus_beshming` business terms baked into the API
  contract — those were already Uzbek and out of scope for a frontend-only
  change.
- [x] Verified end-to-end in a real browser (Claude-in-Chrome) logged in
  as both superadmin and the assistant test account: nav, dashboard,
  doctors list, and receipts pages all render fully in Uzbek, with the
  role-suffix and pagination strings confirmed on live data.
- [x] `pytest -q`: 26/26 passing (backend untouched — this was a
  frontend-only session). All nine JS files re-checked with `node -c` for
  syntax after the rewrites.

---

## 18. Session 9 — assistants: no reports, doctor visible on their receipts, no edit/delete

Three requests: (1) assistants must not see Reports at all, (2)
assistants should see their own receipts with the doctor's name attached,
(3) assistants must only be able to create receipts, never edit or
delete them.

**Reports hidden from assistants:**
- [x] `app/finance/router.py`: `GET /reports/consultations`,
  `/reports/surgeries`, `/reports/rooms` narrowed from
  `require_roles(*ALL_ROLES)` to `require_roles(*MANAGE_ROLES)` —
  assistants now get a `403` from the API itself, not just a hidden nav
  link, if they try these three directly.
  **Deliberate exception:** `GET /reports/total` was left on `ALL_ROLES`.
  `dashboard.js` calls this same endpoint for every role's Boshqaruv
  paneli summary cards, and that page wasn't part of this request — only
  "Reports" (the dedicated `/reports` page, its charts, its per-doctor
  breakdown, and its Excel export) was. Narrowing `/reports/total` too
  would have broken the assistant's dashboard, which is a separate,
  unrequested change. The data `/reports/total` returns for an assistant
  is already scoped to their own records only (existing `_apply_
  assistant_ownership` filtering), so it doesn't add any new
  clinic-wide-financials exposure beyond what the dashboard already showed
  — this was judged in-scope to leave alone rather than ask, but is
  flagged here in case the intent was broader.
- [x] `app/static/js/nav.js`: removed `"assistant"` from the "Hisobotlar"
  `NAV_LINKS` entry's `roles` array — the nav link is gone for that role.
- [x] `app/static/js/reports.js`: `initPage()` call now passes
  `{ allowedRoles: ["superadmin", "manager"] }`, matching the same
  redirect-to-`/dashboard` pattern already used by `audit_log.js`/
  `settings.js` — an assistant who navigates to `/reports` directly gets
  bounced immediately, never sees the page render.
- [x] Verified in a real browser as the `asst1` test account: no
  "Hisobotlar" link in the nav, and navigating straight to `/reports`
  redirects to `/dashboard`.

**Doctor name shown on receipts:**
- [x] `app/static/js/receipts.js`: `loadDoctorOptions()` now also builds
  `doctorNameById` (an `{id: name}` map) from the same `/doctors/options`
  response it already fetched for the dropdowns — no new API call. Added
  a "Shifokor" column to all three record-type tables in the "So'nggi
  yozuvlar" (recent entries) list, between "Turi"/"Sana" and "Summa",
  showing the mapped name or "—" when `doctor_id` is null.
  This column is shown to every role, not assistant-only — there was no
  reason to hide the doctor's name from managers/superadmin, and the
  request was to make sure assistants *could* see it, not that others
  shouldn't.
- [x] Verified: created a consultation as the assistant with "Rashidova
  Dilnoza" selected as the doctor, and the recent-entries row correctly
  showed her name in the new column.

**Edit/delete already blocked for assistants (no change needed):**
- [x] Confirmed `receipts.js`'s `canManage` flag (`superadmin`/`manager`
  only) already gates both the "Tahrirlash" (Edit) and "Bekor qilish"
  (Void) buttons — an assistant's rows render with an empty Amallar
  column, as seen in the same verification screenshot above.
- [x] Confirmed the backend independently enforces the same rule:
  every `PATCH /{consultations|surgeries|rooms}/{id}` and
  `POST .../{id}/void` endpoint already requires
  `require_roles(*MANAGE_ROLES)` (§2, Phase 2), and there has never been
  a `DELETE` endpoint for any finance record type (§2's "void, not
  delete" rule) — so "assistants can only create" was already true on
  the backend before this session; this request just confirmed it and
  found nothing to fix there.

**Verification:** `pytest -q` 26/26 (only `app/finance/router.py` changed
on the backend, and only for the three report-detail endpoints); all
touched JS files re-checked with `node -c`; full Claude-in-Chrome
click-through as the assistant test account covering nav, direct-URL
redirect, and the doctor-column receipt creation above.

---

## 19. Session 10 — no Dashboard for assistants, per-doctor combined report

Two requests: (1) assistants must not see "Boshqaruv paneli" (Dashboard)
at all, and (2) managers/superadmin need a way to check one doctor's
total earnings across consultations, surgeries, and rooms for a date
range, as a Reports feature.

**Dashboard hidden from assistants:**
- [x] `app/static/js/nav.js`: removed `"assistant"` from the Dashboard
  `NAV_LINKS` entry, and — this was the part that needed more than a
  one-line change — replaced the hardcoded `window.location.href =
  "/dashboard"` disallowed-role redirect with a new `ROLE_HOME` map
  (`{superadmin: "/dashboard", manager: "/dashboard", assistant:
  "/receipts"}`). Without this, an assistant landing on `/dashboard`
  would have bounced back to `/dashboard` — an infinite redirect loop —
  since `/dashboard` was itself about to become the page redirecting them
  away. Every `allowedRoles`-gated page (`audit_log.js`, `settings.js`,
  `reports.js`, now `dashboard.js`) uses this same map, so an assistant
  hitting any admin-only page now lands on `/receipts`, not a loop.
- [x] `app/static/js/dashboard.js`: `initPage()` now passes
  `{ allowedRoles: ["superadmin", "manager"] }`.
- [x] Verified in-browser as `asst1`: nav no longer shows "Boshqaruv
  paneli", and (after the two known JS-caching hiccups below) the
  assistant correctly lands on `/receipts`.
  **Debugging note, not a code bug:** the first two verification passes
  this session showed stale behavior (old nav still visible, a 404 from
  a URL that no longer matched the updated JS) purely because the
  browser had cached `nav.js`/`dashboard.js`/`reports.js` from earlier
  in the conversation and `docker compose`'s `--reload` only affects the
  Python process, not already-loaded browser JS. A hard reload
  (`ctrl+shift+r`) in the test tab resolved both — worth remembering for
  future sessions verifying JS changes in an already-open tab.

**New "Shifokor bo'yicha" (by doctor) report tab:**
- [x] `app/templates/reports.html`: added a fifth tab button
  (`data-report="doctor"`) and a doctor `<select>` (populated from the
  existing `GET /doctors/options`) shown only on that tab.
- [x] `app/static/js/reports.js`: no new backend endpoint was needed —
  `build_consultation_report`/`build_surgery_report`/`build_room_report`
  already return a full per-doctor `doctor_shares` breakdown for the
  date range (§16.1 confirmed this data already existed, just not
  surfaced this way). `loadDoctorReport()` fetches all three section
  reports for the selected range with `Promise.all`, picks out the
  selected doctor's row from each one's `doctor_shares` /
  `surgery_doctor_shares` / `room_doctor_shares` array by `doctor_id`,
  and renders: four summary cards (per-section share + a combined
  "Jami ulush" total), a three-bar chart, and a Bo'lim/Ulush/Yozuvlar
  soni breakdown table — all reusing the existing `statCard`/`Chart`/
  table-rendering helpers already in the file.
  **"How much a doctor made" was read as their `doctor_share`** (their
  cut, "shifokor ulushi" — the same figure the app calls this everywhere
  else), not gross income tied to their records. Worth confirming this
  matches intent if it turns out clinic-side income per doctor was
  wanted instead.
- [x] The Excel export button doesn't apply here (no backend endpoint
  combines three report types into one file) — `exportBtn` is hidden via
  `classList.toggle("hidden", ...)` whenever this tab is active, so
  there's no dead/broken button on screen instead of silently doing
  nothing.
- [x] Verified end-to-end with real data: selected "Rashidova Dilnoza"
  for a wide date range and got the correct combined figures
  (47,500 so'm from one active consultation, 0 from surgeries/rooms she
  has no active records in, matching a direct `curl` of
  `/reports/consultations` for the same range).
  **While verifying, ran into and diagnosed (not a bug in this
  feature):** most of the consultation test data from earlier sessions
  had been voided by an `actor_id` that isn't any of my own test
  accounts — almost certainly you, testing the app yourself per the
  terminal commands given last session. That's exactly what void is
  for, and the report correctly excludes voided records; this was
  confirmed via `GET /audit-logs?resource_type=consultation`, not
  guessed.

**Verification:** `pytest -q` 26/26 (no backend changes this session —
both requests were achievable entirely in the frontend, reusing existing
endpoints and data already returned by them); all touched JS files
re-checked with `node -c`; full Claude-in-Chrome click-through covering
the assistant's hidden Dashboard and the new doctor-report tab with real
data cross-checked against a direct API call.

---

## 20. Session 11 — receipt columns, filters, and a confirmed non-issue

Four requests: (1) show who added each receipt, (2) show a per-row
clinic-profit column, manager/superadmin only, (3) add date/creator
filters to Kvitansiyalar, (4) confirm managers can't delete doctors.

**"Managers must not be able to delete doctors" — already true, no
change made:**
- [x] Checked both layers before touching anything: `app/doctors/router.py`'s
  `DELETE /{doctor_id}` is `require_roles(SUPERADMIN)` only (a Phase 0
  decision from the very first session, deliberately kept stricter than
  the `mk/` deviations doc), and `app/static/js/doctors.js`'s `canDelete`
  flag is `user.role === "superadmin"` — `canManage` (which includes
  `manager`) only gates the Edit button, never Delete. Nothing to fix;
  documented here since it was asked as a thing to verify, not assumed.

**"Qo'shdi" (added-by) column — every role:**
- [x] `app/static/js/receipts.js`: added a `creatorNameById` map, seeded
  with `{[user.id]: user.full_name}` for every role (so an assistant,
  who only ever sees their own records anyway, still resolves correctly
  without needing any extra API access), and for `manager`/`superadmin`
  additionally populated from `GET /users/assistants` (both roles) and
  `GET /users/managers` (superadmin only — matches that endpoint's
  existing role gate from §16/Phase 11, so a manager actor never calls
  an endpoint it would get a `403` from). New "Qo'shdi" column added to
  all three record-type tables, positioned right after "Shifokor".

**"Klinika foydasi" (clinic profit) column — manager/superadmin only:**
- [x] Same reasoning as the create-form preview restriction from Session
  8: finance records never persist `clinic_profit` (§2 — "never persist
  calculated fields"), so a `computeClinicProfit(kind, record)` helper
  was added that mirrors `app/finance/calculations.py`'s formulas exactly
  (consultation/surgery: `amount - round((amount-expense)*percent/100) -
  expense`; room: `amount - round(amount*percent/100)`, no expense term).
  `headersFor(kind)` splices "Klinika foydasi" into the header row only
  when `canManage` is true, and `renderRow()` only renders the matching
  `<td>` in that case — an assistant's row literally has one fewer `<td>`
  than a manager's for the same record, not just a hidden/empty cell.
  Verified against a real record (100,000 so'm, 50%, 5,000 expense):
  computed 47,500, matching what `/reports/consultations` independently
  reports as that doctor's `total_share` for the same record.

**Filters in Kvitansiyalar (date range, doctor, "who added"):**
- [x] Backend: `app/finance/service.py`'s `list_consultations`/
  `list_surgeries`/`list_rooms` gained an optional `created_by_id`
  keyword parameter (date-range and doctor filtering already existed
  server-side, just weren't exposed in this page's UI yet — confirmed
  by reading the functions before writing anything). `app/finance/router.py`'s
  three `GET` list endpoints gained a matching `created_by_id: uuid.UUID
  | None` query param, passed straight through. No role gate needed
  here beyond what already exists — an assistant passing their own id
  changes nothing (their query is already forced to
  `created_by_id == actor.id` by `_apply_assistant_ownership`), and nothing
  stops a manager/superadmin from filtering by any id since they already
  see every record.
- [x] Frontend: added a filter card to `receipts.html` (date-from,
  date-to, doctor, "Kim qo'shgan") right above the recent-entries table,
  wired in `receipts.js` to the same `GET` endpoints via query params,
  plus a "Tozalash" (clear) button. The "Kim qo'shgan" field is hidden
  entirely for assistants (`filter-creator-field.classList.add("hidden")`
  when `!canManage`) since their list is already own-scope-only — showing
  a filter that can only ever match "myself" would be clutter, not a
  feature.
- [x] Verified all three filters independently in-browser as superadmin:
  filtering by a specific creator returned only that person's record;
  filtering by a creator with zero records correctly returned an empty,
  0-total list (not an error); a future-dated `date_from` correctly
  excluded today's records. Also verified as the assistant test account
  that "Kim qo'shgan" doesn't render at all, and their own date filter
  still works against their own-scoped list.

**Verification:** `pytest -q` 26/26; `node -c` on `receipts.js`; full
Claude-in-Chrome click-through as both superadmin and the assistant test
account, cross-checking the clinic-profit math against a real record and
the creator filter against two different actors (one with records, one
without).

