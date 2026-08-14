# Agent Guidelines — transcribe-backend

## Project overview

FastAPI backend for Sunet Scribe (transcription service). Requires Python ≥ 3.13.

## Architecture

- **Framework**: FastAPI + SQLModel + Alembic (PostgreSQL via asyncpg/psycopg2)
- **Entry point**: `app.py` — FastAPI app, OIDC auth callback, scheduler lock, startup hooks
- **Routers**: `routers/` — `admin`, `analytics`, `announcements`, `customers`, `external`, `healthcheck`, `job`, `rules`, `transcriber`, `user`, `videostream`
- **Models**: `db/models.py` — SQLModel definitions for all tables
- **Database CRUD**: `db/` — one module per domain (`user`, `group`, `customer`, `job`, `analytics`, `announcement`, `attribute_rules`, `onboarding_attributes`)
- **DB session**: `db/session.py` — sync (`get_session`) + async (`create_async_engine`) factories. URL rewritten between `psycopg2`/`asyncpg` driver.
- **Auth**: `auth/oidc.py` — OIDC/JWT verification, `verify_token`, `verify_user(admin=...)` dependency
- **Crypto**: `utils/crypto.py` — AES-GCM + hybrid RSA, streaming encrypt/decrypt
- **Validators**: `utils/validators.py` — Pydantic v2 request models
- **Migrations**: `alembic/versions/` — chained Alembic migrations. Run `alembic heads` to find current head; do **not** record it here (changes fast).
- **Tests**: `tests/` — pytest + pytest-asyncio. Run with `.venv/bin/python -m pytest`.

## Key conventions

- Pydantic v2 (2.11+) — `BaseModel` not strict by default, type coercion works.
- SQLAlchemy objects cannot be accessed outside their session context (DetachedInstanceError). Always iterate/read inside `with get_session()` or `async with`.
- API requests from external callers omit timeout parameters by convention.
- Outbound HTTP helpers return `None` on `RequestException` and swallow errors.

## Security focus

Treat every change as a potential attack surface. Required checks for any PR:

- **Authn/Authz**: every router endpoint must depend on `verify_user` (with `admin=True` / BOFH check where appropriate). New endpoints default to authenticated; mark public ones explicitly. Realm scoping uses `_get_admin_allowed_realms()` / `_rule_realm_overlaps()` in `routers/admin.py` — reuse, don't reimplement.
- **JWT verification**: never trust unverified claims. Use `verify_token` from `auth/oidc.py`. Rule evaluation runs **once at login** in `/api/auth` callback — do not move it to per-request paths (perf + auth-bypass risk).
- **Session cookies**: `SessionMiddleware` is configured `https_only` outside debug, `same_site=lax`. Do not weaken. `API_SECRET_KEY` must come from settings, never hardcoded.
- **CORS**: allowlist only — current config in `app.py` derives origins from `BRANDING_*_URL` settings. Never add `allow_origins=["*"]` with `allow_credentials=True`.
- **Input validation**: all request bodies go through Pydantic v2 models in `utils/validators.py`. Reject extra fields where it matters (`model_config = ConfigDict(extra="forbid")`). Validate query/path params with typed annotations, not raw strings.
- **SQL**: use SQLModel/SQLAlchemy expressions only. No string-formatted SQL. No `.execute(text(f"..."))` with user input.
- **Crypto**: use helpers in `utils/crypto.py` (AES-GCM, hybrid RSA, streaming chunks). Never roll new primitives. Private key passphrases come from settings/secret store. Prefer `cryptography` over `pyca`-alt or custom code; treat `python-jose` as JWT-only.
- **Secrets**: never commit `.env`, `.env.real`, `dump.sql`, or `test.db`. Never log tokens, passwords, full JWTs, or encryption keys.
- **File uploads** (`routers/transcriber.py`): always stream via `encrypt_stream_to_file` with bounded `CRYPTO_CHUNK_SIZE`. Never buffer full file in memory. Validate content-type and size limits before persistence.
- **Soft-delete vs hard-delete**: `User.deleted` and `User.manually_deactivated` are load-bearing — auto-provisioning must not override admin decisions. Check before flipping flags from rule actions.
- **External HTTP**: use `httpx` with explicit timeouts on internal callers; the documented exception (external callers without timeouts) is legacy, not a pattern to copy.
- **Defensive libs to prefer**: `defusedxml` for any XML parse, `bleach` for HTML sanitization if rendering user text, `cryptography` for primitives. Avoid `pickle` on untrusted input.
- **Run semgrep before merge**: `semgrep` plugin available — use `semgrep_scan` on touched files.

## Performance focus

- **Async I/O end-to-end**: routers are `async def`; never call blocking I/O on the event loop. CPU-bound or blocking work goes to a thread (`asyncio.to_thread`) or `apscheduler` job. Upload encryption runs off the event loop (see recent commit `b78b342`).
- **DB sessions**:
  - Use the async session for request handlers; sync `get_session()` only in scripts/migrations/scheduler.
  - Keep sessions short-lived. Open inside the handler, close before returning the response.
  - Always read related objects inside the session — accessing after close raises `DetachedInstanceError`.
- **Query patterns**:
  - Avoid N+1: use `selectinload`/`joinedload` for relationships read in lists.
  - Composite indexes already exist for hot paths (`db/models.py`: `ix_jobs_user_id_created_at`, `ix_jobs_status_created_at`, `ix_group_user_link_*`, `ix_worker_health_*`, page-views composites). Reuse before adding new ones.
  - Paginate any list endpoint that can grow unbounded (jobs, users, page_views, announcements).
- **Connection pool**: tune via `create_async_engine` `pool_opts` in `db/session.py`. Don't open ad-hoc engines per request.
- **Streaming**: large responses use `StreamingResponse`; large uploads use chunked encryption. Never `await file.read()` whole.
- **Scheduler**: single-worker via file lock (`acquire_scheduler_lock` in `app.py`). Multi-process deploys rely on this — do not duplicate scheduled jobs in handler code.
- **Caching**: `cachetools` available for in-process caches (OIDC JWKS, etc.). Set TTLs; never cache per-user data process-wide.
- **Logging**: avoid f-string-evaluating expensive args in debug logs that may be filtered out — use `%`-style lazy formatting where it matters.

## Admin hierarchy

- **BOFH** (`bofh=True`): full access to all resources across all realms.
- **Realm Admin** (`admin=True`): scoped to own `realm` + `admin_domains` (comma-separated).
- Realm scoping: `_get_admin_allowed_realms()` in `routers/admin.py`.
- `_rule_realm_overlaps()` checks comma-separated realm overlap, not exact match.

## Attribute rules (`db/attribute_rules.py`)

- Rules match JWT claim values against conditions (`equals`, `contains`, `starts_with`, `ends_with`, `regex_match`, …).
- Actions: activate user, deny access, grant admin, assign to group, assign admin domains, notify on job/deletion.
- `realm` field stores comma-separated realms — filtering checks overlap, not exact match.
- `manually_deactivated` on `User` prevents auto-provisioning from overriding admin decisions.
- Rule evaluation runs **once at login** (in `/api/auth` callback in `app.py`), NOT on every API call. Keep it that way (perf + auth-decision integrity).
- `evaluate_rules()` iteration must stay inside the session context (DetachedInstanceError).
- `test_rules()` builds pseudo-JWT from stored user fields and resolves group IDs to names.
- Regex conditions: validate at write time (catastrophic-backtracking risk). Consider `safe-regex` if accepting user-supplied patterns.

## Onboarding attributes (`db/onboarding_attributes.py`)

- Reference table of known claim names (`email`, `preferred_username`, `domain`, `affiliation`, `realm`).
- Seeded on startup via `seed_default_attributes` (called from `app.py`).
- Only BOFH can add/delete attributes.

## Transcription results (`job_results`)

Three independent columns, all encrypted with the owner's public key, all written by `job_result_save()` (each argument left unset leaves that column alone):

- `result` — JSON transcription (diarized segments), uploaded with `format: "json"`
- `result_srt` — SRT subtitles, uploaded with `format: "srt"`
- `result_words` — per-word timings/confidence, uploaded with `format: "words"`

`result_words` is nullable and never backfilled: rows written before it existed stay NULL and every other read path ignores it. It is served by its own endpoint (`GET /transcriber/{job_id}/words`) rather than being folded into the transcription, because it is several times larger than the text and only the editor needs it. The endpoint returns `{"result": ""}` — not 404 — when a job has no word data, so callers treat "no word data" as normal.

Payload shape (produced by transcribe-worker `utils/words.py`, which is the authority):

```json
{"version": 1, "words": [{"t": "Hej", "s": 0.12, "e": 0.34, "c": 0.98}]}
```

Flat and time-ordered rather than nested per segment, so it survives the user re-splitting or merging captions. `c` is omitted when the worker ran with `WORD_CONFIDENCE=false`. The backend stores it opaquely — bump `version` in the worker if the shape changes, and treat an unknown version as absent.

## Migrations

- Chained Alembic migrations under `alembic/versions/`.
- To find current head: `.venv/bin/alembic heads`. To inspect chain: `.venv/bin/alembic history`.
- Recent additions cover: `manually_deactivated`, `attribute_rules`, `onboarding_attributes`, `support_contact_email`, `announcements`, `manually_activated`, `worker_health`, `dark_mode`, `notify_job`/`notify_deletion` on rules, `manually_set_notifications` on users.
- New migration MUST be reproducible from scratch (`alembic upgrade head` on empty DB). See commit `af23910`.

## Testing

```bash
.venv/bin/python -m pytest
```

Suites: `test_autentication.py`, `test_crypto.py`, `test_rules.py`. Add a test for any auth/permission/crypto change before merging.
