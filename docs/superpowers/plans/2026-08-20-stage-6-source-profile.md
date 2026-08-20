# Stage 6 Source Configuration and Enterprise Profile Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let applicant owners safely recognize and explicitly enable public policy sources, and version-edit the shared enterprise profile and business entities with auditable changes, while keeping all mobile profile/source views read-only.

**Architecture:** Extend the existing `sources` module instead of adding a generic crawler: a server-owned recognition registry combines a public-network guard, bounded metadata/feed inspection, and exact supported-host/listing rules. Persist only a safe recognition projection and use the existing collection task/scheduler boundary after explicit owner enablement. Extend the existing `profiles` and append-only `audit` modules with versioned writes and a safe recent-audit projection; Vue consumes the typed API contract and gates every mutation control by the current owner role and a reactive mobile breakpoint.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, APScheduler, pytest/respx, Vue 3, TypeScript, Vitest, Vue Test Utils, Element Plus.

**Spec:** `docs/superpowers/specs/2026-08-20-stage-6-source-profile-design.md`

## Global Constraints

- Owner source records contain name, entry URL, optional region/topic labels, recognition state, safe preview, enable/disable control, and collection history; adapter implementation keys remain server-owned.
- The only recognition statuses are `recognizing`, `ready_to_enable`, `enabled`, `pending_verification`, `rejected`, and `disabled`.
- Recognition supports only RSS/Atom, released supported public government sites, released supported public listing pages, and one-off policy links; it must not authenticate, bypass captcha, run selectors, or enqueue unknown sites.
- Unsafe, private, inaccessible, or unsupported URLs become `rejected`; inconclusive recognition becomes `pending_verification`; neither may be scheduled.
- A source is scheduled only after a safe preview and explicit applicant-owner enablement; disabling preserves source and collection history.
- No API, audit, or log response may expose internal adapter keys, raw page contents, headers, credentials, filesystem paths, raw crawl errors, or recognition implementation details.
- Shared profile and entity writes are applicant-owner only, require an optimistic version, validate structured fields, return a stable conflict response, and create exactly one safe audit event per successful write.
- Saving a profile must not create an evaluation batch, invoke AI, enqueue notifications, overwrite a manual conclusion, or automatically re-evaluate historical policy.
- Authenticated users may read profiles and safe profile audits; all non-owners receive server-side `403` for profile/source writes.
- Desktop offers source/profile writes only to applicant owners. Mobile preserves reading but hides every source/profile mutation control.
- Do not add arbitrary website scraping rules, CSS/XPath configuration, login/captcha bypass, Redis, Kafka, generic workflow engines, WeCom login, backups/recovery work, automatic re-evaluation, notifications, production migration work, or production deployment work.
- Do not persist host paths, secrets, or a fixed source count. Use container-local configuration and the existing scheduler/worker boundary.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `backend/alembic/versions/0008_stage6_source_profile.py` | Reversible schema change from revision `0007_reconcile_eval_constraint`: source lifecycle/preview/version columns, profile/entity versions, and safe audit lookup index. |
| `backend/app/modules/sources/models.py` | SQLAlchemy source recognition-state enum and persisted safe source configuration fields; retain historical channels/tasks. |
| `backend/app/modules/sources/schemas.py` | Strict source input/output contracts, page envelopes, and public recognition/enable responses with no adapter implementation key. |
| `backend/app/modules/sources/safety.py` | Pure URL canonicalization, DNS/IP public-address checks, safe redirect validation, and bounded safe error classification. |
| `backend/app/modules/sources/recognition.py` | Server-owned recognizer registry, bounded HTTP inspection, and safe `RecognitionResult` projection for supported kinds. |
| `backend/app/modules/sources/service.py` | Transactional create/retry/enable/disable/list lifecycle and collection eligibility. |
| `backend/app/modules/sources/router.py` | Owner-only source HTTP routes, stable error mapping, and paginated safe records. |
| `backend/workers/scheduler.py` | Select only explicitly enabled, recognized sources with a released server adapter. |
| `backend/workers/collector.py` | Dispatch recognized server-owned collector keys only; never execute an owner-provided selector/key. |
| `backend/app/modules/profiles/models.py` | Optimistic versions on shared profile and entity rows. |
| `backend/app/modules/profiles/schemas.py` | Explicit structured editable-field input, versioned responses, safe audit summaries, and stable error detail types. |
| `backend/app/modules/profiles/service.py` | Owner update/validation/locking, one-event audit recording, read queries, and audit summary projection. |
| `backend/app/modules/profiles/router.py` | Authenticated reads and owner-only versioned PATCH routes. |
| `backend/tests/unit/sources/test_safety.py` | Deterministic URL/redirect/DNS safety tests without real network calls. |
| `backend/tests/unit/sources/test_recognition.py` | Recognizer classification and safe-preview/redaction tests with mocked `httpx`. |
| `backend/tests/unit/sources/test_service.py` | Source lifecycle, transition, version, and no-pre-enable-collection tests. |
| `backend/tests/unit/collection/test_scheduler.py` | Scheduler filtering for only `enabled` server-recognized source rows. |
| `backend/tests/unit/profiles/test_service.py` | Structured validation, optimistic conflict, exactly-one-audit, and no-evaluation-side-effect tests. |
| `backend/tests/integration/sources/test_routes.py` | Source HTTP authorization, public payload redaction, pagination, lifecycle, and rejected/pending route tests. |
| `backend/tests/integration/profiles/test_routes.py` | Profile HTTP authorization, conflict detail, audit projection, and read-only route tests. |
| `backend/tests/integration/test_stage6_schema.py` | Upgrade/downgrade and preservation checks for the new columns/indexes. |
| `frontend/src/api/sources.ts` | Source union types and create/retry/enable/disable/list client functions. |
| `frontend/src/api/profiles.ts` | Versioned profile/entity/audit types and typed read/write client functions. |
| `frontend/src/api/errors.ts` | Reusable stable-error-detail narrowing for version-conflict feedback. |
| `frontend/src/components/sources/SourceDrawer.vue` | Minimal name/entry URL/optional-label intake; it never renders channel, selector, or adapter inputs. |
| `frontend/src/components/sources/SourceStatusCard.vue` | Business-language source preview/status/history/actions with no implementation details. |
| `frontend/src/components/profiles/ProfileEditor.vue` | Explicit, version-aware shared/entity editor with field allowlists and conflict reload behavior. |
| `frontend/src/components/profiles/ProfileAuditList.vue` | Safe audit actor/time/field/before/after summary rendering. |
| `frontend/src/views/PolicySourcesView.vue` | Desktop owner source page, pagination, lifecycle actions, and mobile read-only state. |
| `frontend/src/views/EnterpriseProfileView.vue` | Desktop owner profile/entity edit surface; authenticated readers and mobile remain read-only. |
| `frontend/tests/unit/PolicySourcesView.spec.ts` | Source status/action, redaction, error, pagination, and mobile read-only UI tests. |
| `frontend/tests/unit/EnterpriseProfileView.spec.ts` | Shared/entity edit, audit, conflict, role, and mobile read-only UI tests. |
| `frontend/tests/unit/SourceDrawer.spec.ts` | Source intake contract tests proving no advanced scraping fields can be submitted. |
| `frontend/tests/unit/ProfileEditor.spec.ts` | Explicit profile payload, validation/error, version conflict, and disabled-submit tests. |
| `frontend/tests/unit/SourceApiContract.spec.ts` | Exact source request/response and error-mapping API contract tests. |
| `frontend/tests/unit/ProfileApiContract.spec.ts` | Exact profile request/response and conflict-mapping API contract tests. |

Implementation note: the current repository has URL syntax validation in `sources/schemas.py` but no reusable public-network/SSRF guard. Task 2 introduces the narrowly scoped guard required by this approved spec; it is the common safety model for all Stage 6 recognition requests, not a general crawler facility.

## Shared Interfaces

All later tasks use these exact names and shapes. Do not add an owner-selectable `adapter_key`, raw response body, raw crawl error, selector, header, credential, or filesystem-path field to an input, output, audit, or log message.

```python
# backend/app/modules/sources/recognition.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RecognitionStatus = Literal[
    "recognizing", "ready_to_enable", "enabled", "pending_verification", "rejected", "disabled"
]
RecognitionKind = Literal[
    "rss_atom", "supported_government_site", "public_listing_page", "one_off_policy_link"
]

@dataclass(frozen=True)
class RecognitionResult:
    status: Literal["ready_to_enable", "pending_verification", "rejected"]
    kind: RecognitionKind | None
    summary: str
    previewed_at: datetime | None
    adapter_key: str | None  # server-only: never serialize or audit

class SourceRecognizer:
    def recognize(self, entry_url: str) -> RecognitionResult:
        raise NotImplementedError
```

```python
# backend/app/modules/sources/schemas.py
class SourceRecognitionRetryInput(BaseModel):
    representative_url: str | None = None

class SourceVersionInput(BaseModel):
    expected_version: int

class SourceCreate(BaseModel):
    name: str
    entry_url: str
    region_labels: list[str] = Field(default_factory=list)
    topic_labels: list[str] = Field(default_factory=list)

class SourceResponse(BaseModel):
    id: int
    name: str
    entry_url: str
    region_labels: list[str]
    topic_labels: list[str]
    recognition_status: RecognitionStatus
    recognition_kind: RecognitionKind | None
    recognition_summary: str
    previewed_at: datetime | None
    owner_confirmed_at: datetime | None
    enabled_at: datetime | None
    disabled_at: datetime | None
    version: int
    latest_collection_at: datetime | None
    latest_result: str | None

class SourcePage(BaseModel):
    items: list[SourceResponse]
    page: int
    page_size: int
    total: int
```

```python
# backend/app/modules/profiles/schemas.py
class ProfilePatchInput(BaseModel):
    expected_version: int
    display_name: str | None = None
    data: dict[str, object] | None = None
    verification_status: str | None = None

class BusinessEntityPatchInput(BaseModel):
    expected_version: int
    legal_name: str | None = None
    data: dict[str, object] | None = None
    verification_status: str | None = None

class ProfileAuditSummary(BaseModel):
    id: int
    action: Literal["enterprise_profile_updated", "business_entity_updated"]
    actor_id: int
    actor_display_name: str
    object_type: Literal["enterprise_profile", "business_entity"]
    object_id: int
    changed_fields: list[str]
    before_values: dict[str, object]
    after_values: dict[str, object]
    occurred_at: datetime

class VersionedProfileResponse(BaseModel):
    code: str
    display_name: str
    data: dict[str, object]
    verification_status: str
    version: int
    recent_audits: list[ProfileAuditSummary]

class VersionedBusinessEntityResponse(BaseModel):
    seed_code: str
    legal_name: str
    data: dict[str, object]
    verification_status: str
    version: int
    recent_audits: list[ProfileAuditSummary]

class ProfileVersionConflict(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"profile version conflict: {current_version}")
```

```typescript
// frontend/src/api/sources.ts
export type RecognitionStatus = "recognizing" | "ready_to_enable" | "enabled" | "pending_verification" | "rejected" | "disabled";
export type RecognitionKind = "rss_atom" | "supported_government_site" | "public_listing_page" | "one_off_policy_link";
export interface PolicySource {
  id: number;
  name: string;
  entry_url: string;
  region_labels: string[];
  topic_labels: string[];
  recognition_status: RecognitionStatus;
  recognition_kind: RecognitionKind | null;
  recognition_summary: string;
  previewed_at: string | null;
  owner_confirmed_at: string | null;
  enabled_at: string | null;
  disabled_at: string | null;
  version: number;
  latest_collection_at: string | null;
  latest_result: string | null;
}
export interface SourceCreateInput { name: string; entry_url: string; region_labels: string[]; topic_labels: string[]; }
export interface SourcePage { items: PolicySource[]; page: number; page_size: number; total: number; }
export function getSources(page?: number, pageSize?: 10 | 20 | 50): Promise<SourcePage>;
export function createSource(payload: SourceCreateInput): Promise<PolicySource>;
export function retrySourceRecognition(id: number, representativeUrl?: string): Promise<PolicySource>;
export function enableSource(id: number, expectedVersion: number): Promise<PolicySource>;
export function disableSource(id: number, expectedVersion: number): Promise<PolicySource>;
```

```typescript
// frontend/src/api/profiles.ts
export interface ProfileAuditSummary {
  id: number;
  action: "enterprise_profile_updated" | "business_entity_updated";
  actor_id: number;
  actor_display_name: string;
  object_type: "enterprise_profile" | "business_entity";
  object_id: number;
  changed_fields: string[];
  before_values: Record<string, unknown>;
  after_values: Record<string, unknown>;
  occurred_at: string;
}
export interface VersionedProfileResponse { code: string; display_name: string; data: Record<string, unknown>; verification_status: string; version: number; recent_audits: ProfileAuditSummary[]; }
export interface VersionedBusinessEntityResponse { seed_code: string; legal_name: string; data: Record<string, unknown>; verification_status: string; version: number; recent_audits: ProfileAuditSummary[]; }
export interface ProfilePatchInput { expected_version: number; display_name?: string; data?: Record<string, unknown>; verification_status?: string; }
export interface BusinessEntityPatchInput { expected_version: number; legal_name?: string; data?: Record<string, unknown>; verification_status?: string; }
export function updateSharedProfile(payload: ProfilePatchInput): Promise<VersionedProfileResponse>;
export function updateBusinessEntity(seedCode: string, payload: BusinessEntityPatchInput): Promise<VersionedBusinessEntityResponse>;
```

### Task 1: Add the reversible Stage 6 persistence contract

**Files:**
- Create: `backend/alembic/versions/0008_stage6_source_profile.py`
- Modify: `backend/app/modules/sources/models.py`
- Modify: `backend/app/modules/profiles/models.py`
- Create: `backend/tests/integration/test_stage6_schema.py`
- Modify: `backend/tests/unit/sources/test_service.py`
- Modify: `backend/tests/unit/profiles/test_seed.py`

**Interfaces:**
- Consumes: existing `PolicySource.home_url`, `adapter_key`, `adapter_status`, `is_enabled`, historical `SourceChannel` rows, profile seed rows, and Alembic revision `0007_reconcile_eval_constraint`.
- Produces: the model fields and persisted state described in **Shared Interfaces**. `policy_sources.home_url` is renamed to `entry_url`; legacy source channels/tasks remain unchanged. `adapter_key` remains nullable server-only storage. `version` defaults to `1` for source/profile/entity rows.

- [ ] **Step 1: Write the failing migration/model tests**

Add assertions that migrate a Stage 5-shaped database to head, retain its source, channel, collection task, shared profile, and three entities, and expose exact defaults. Test that source states accept only the six statuses; `recognition_kind` accepts only the four kinds or `NULL`; legacy `ready` maps to `enabled` and legacy `pending` maps to `pending_verification`; and downgrade restores the Stage 5 columns/data shape.

```python
assert migrated_source.entry_url == "https://gdii.gd.gov.cn"
assert migrated_source.recognition_status == "enabled"
assert migrated_source.version == 1
assert migrated_shared.version == 1
assert migrated_entity.version == 1
```

- [ ] **Step 2: Run the schema tests to verify they fail**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/integration/test_stage6_schema.py
```

Expected: FAIL because revision `0008_stage6_source_profile` and the new model columns do not exist.

- [ ] **Step 3: Implement the smallest reversible migration and matching models**

In `upgrade()`, rename `home_url` to `entry_url`; add JSON `region_labels`/`topic_labels` with non-null empty-array server defaults, `recognition_status`, nullable `recognition_kind`, non-null safe `recognition_summary` with empty default, nullable `previewed_at`, `owner_confirmed_at`, `enabled_at`, `disabled_at`, and non-null `version` defaulting to `1`. Backfill each historical `ready` record to `enabled`, retain `adapter_key`, set a short safe migration summary, and set timestamps consistently; backfill each historical `pending` record to `pending_verification` and clear its `adapter_key`/enabled flag. Add `version` to both profile tables and index audit lookups by `(object_type, object_id, occurred_at, id)`.

Keep the existing channel and collection tables intact. In `downgrade()`, restore `home_url`, map `enabled` to `ready` and every non-enabled Stage 6 state to `pending`, drop only Stage 6 columns/indexes, and do not delete historical source, channel, task, profile, entity, or audit rows.

```python
SOURCE_RECOGNITION_STATUSES = (
    "recognizing", "ready_to_enable", "enabled", "pending_verification", "rejected", "disabled"
)

class PolicySource(Base, TimestampMixin):
    entry_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    recognition_status: Mapped[str] = mapped_column(SOURCE_RECOGNITION_STATUS_TYPE, nullable=False)
    recognition_kind: Mapped[str | None] = mapped_column(RECOGNITION_KIND_TYPE, nullable=True)
    recognition_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

- [ ] **Step 4: Run migration and model regression tests**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/integration/test_stage6_schema.py tests/unit/sources/test_service.py tests/unit/profiles/test_seed.py
docker compose run --rm --no-deps api python -m ruff check app alembic tests
```

Expected: PASS; migration upgrade/downgrade preserves Stage 5 rows and source/profile model tests use `entry_url` and `version`.

- [ ] **Step 5: Commit the persistence contract**

```powershell
git add backend/alembic/versions/0008_stage6_source_profile.py backend/app/modules/sources/models.py backend/app/modules/profiles/models.py backend/tests/integration/test_stage6_schema.py backend/tests/unit/sources/test_service.py backend/tests/unit/profiles/test_seed.py
git commit -m "feat: add stage 6 source profile schema"
```

### Task 2: Build bounded public URL safety and recognition

**Files:**
- Create: `backend/app/modules/sources/safety.py`
- Create: `backend/app/modules/sources/recognition.py`
- Modify: `backend/app/modules/sources/schemas.py`
- Create: `backend/tests/unit/sources/test_safety.py`
- Create: `backend/tests/unit/sources/test_recognition.py`

**Interfaces:**
- Consumes: `httpx>=0.28,<1`, Pydantic URL parsing, and the source `RecognitionResult` shape in **Shared Interfaces**.
- Produces: `canonicalize_public_http_url(value: str) -> str`, `assert_public_destination(url: str, resolver: Callable[[str], list[str]]) -> None`, `safe_redirect_target(current_url: str, location: str, resolver: Callable[[str], list[str]]) -> str`, and `SourceRecognizer.recognize(entry_url: str) -> RecognitionResult`.

The safety module defines these supporting types used by this task and by the fixed collectors in Task 3:

```python
from collections.abc import Callable
from dataclasses import dataclass

Resolver = Callable[[str], list[str]]

class UnsafePublicUrl(ValueError):
    pass

@dataclass(frozen=True)
class SafeHttpResponse:
    final_url: str
    content_type: str
    body: bytes
```

- [ ] **Step 1: Write failing pure safety tests**

Cover trimmed absolute HTTP(S) URLs, no credentials/fragments, DNS answers containing loopback/private/link-local/multicast/reserved/unspecified IPv4 and IPv6, literal IP hosts, DNS rebinding (one unsafe answer rejects the host), redirect-to-private rejection, redirect credentials rejection, and a public HTTPS redirect acceptance. Assert callers receive only one of the fixed safe messages `"URL is not a public HTTP(S) address"` or `"URL destination is not publicly reachable"`.

```python
with pytest.raises(UnsafePublicUrl, match="not publicly reachable"):
    assert_public_destination("https://source.example", lambda _: ["93.184.216.34", "127.0.0.1"])

assert safe_redirect_target(
    "https://source.example/a", "/feed.xml", lambda _: ["93.184.216.34"]
) == "https://source.example/feed.xml"
```

- [ ] **Step 2: Run the safety tests to verify they fail**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/sources/test_safety.py
```

Expected: FAIL because `safety.py` does not exist.

- [ ] **Step 3: Implement the public-network guard**

Use `urllib.parse.urlsplit/urlunsplit`, `ipaddress.ip_address`, and `socket.getaddrinfo`. Canonicalization must lower-case the host, strip a default port, strip a fragment, reject credentials, preserve path/query, and cap length at 2048. Resolve every hostname before each outbound request; reject when any resolved address is not globally routable (`is_global` false). Use an `httpx.Client` configured with `follow_redirects=False`, `timeout=httpx.Timeout(5.0, connect=2.0)`, max response bytes `131072`, and at most one redirect after validating its target. Do not log the URL query, headers, DNS values, response body, or exception text; translate network failures to the fixed safe public outcome.

```python
def inspect_public_url(entry_url: str, client: httpx.Client, resolver: Resolver) -> SafeHttpResponse:
    first = canonicalize_public_http_url(entry_url)
    assert_public_destination(first, resolver)
    response = client.get(first, headers={"Accept": "application/atom+xml, application/rss+xml, text/html;q=0.9"})
    if response.is_redirect:
        target = safe_redirect_target(first, response.headers.get("location", ""), resolver)
        response = client.get(target, headers={"Accept": "application/atom+xml, application/rss+xml, text/html;q=0.9"})
    return SafeHttpResponse(final_url=str(response.url), content_type=response.headers.get("content-type", ""), body=response.content[:131072])
```

- [ ] **Step 4: Write failing recognition tests**

Mock the bounded HTTP client for all supported paths: RSS XML and Atom XML return `ready_to_enable`/`rss_atom`; an exact released `gdii.gd.gov.cn` listing URL returns `ready_to_enable`/`supported_government_site` with server key `gdii`; an exact allowlisted listing URL returns `ready_to_enable`/`public_listing_page`; a public HTML policy document with title/date metadata returns `ready_to_enable`/`one_off_policy_link`; unsupported but public HTML returns `pending_verification`; unsafe/inaccessible/unsupported-protocol input returns `rejected`. Assert summaries contain only title/domain/count/date-style safe text and never response body, header, exception, URL query, or adapter key.

```python
result = recognizer.recognize("https://example.gov/policy/42?token=redacted")
assert result.status == "ready_to_enable"
assert result.kind == "one_off_policy_link"
assert "token=" not in result.summary
assert result.adapter_key == "single_policy_link"
```

- [ ] **Step 5: Implement the server-owned recognition registry**

Define immutable `SupportedRecognizer` entries with an exact host plus path predicate and a fixed internal collector key. Include only released keys: `gdii` for the two existing GDI listing paths, `rss_atom` for valid RSS/Atom feeds, and `single_policy_link` for a bounded public document preview. Do not infer a new adapter from a hostname or accept one from the request. Parse XML with `xml.etree.ElementTree` after size limiting; HTML recognition may use only document-level `<title>`, `meta[name=description]`, `time[datetime]`, and canonical link metadata, not CSS/XPath configuration or DOM extraction rules supplied by a user. `RecognitionResult.summary` must be assembled from a maximum 160-character normalized title/description and an ISO date when present.

Use `pending_verification` for valid public URLs that do not match a registry result; save the original source row so a later owner retry may pass a representative policy link to this same recognizer. Use `rejected` only for a safety failure, inaccessible response, invalid feed/document, or non-public/unsupported URL. The result does not queue collection or write a policy.

- [ ] **Step 6: Run safety and recognition tests**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/sources/test_safety.py tests/unit/sources/test_recognition.py
docker compose run --rm --no-deps api python -m mypy app/modules/sources
```

Expected: PASS; tests make no real DNS or HTTP request and all public messages are bounded/redacted.

- [ ] **Step 7: Commit URL safety and recognition**

```powershell
git add backend/app/modules/sources/safety.py backend/app/modules/sources/recognition.py backend/app/modules/sources/schemas.py backend/tests/unit/sources/test_safety.py backend/tests/unit/sources/test_recognition.py
git commit -m "feat: recognize safe public policy sources"
```

### Task 3: Make source recognition owner-confirmed and scheduler-safe

**Files:**
- Modify: `backend/app/modules/sources/service.py`
- Modify: `backend/app/modules/sources/schemas.py`
- Modify: `backend/workers/scheduler.py`
- Modify: `backend/workers/collector.py`
- Modify: `backend/tests/unit/sources/test_service.py`
- Modify: `backend/tests/unit/collection/test_scheduler.py`
- Modify: `backend/tests/unit/collection/test_collector.py`

**Interfaces:**
- Consumes: `SourceRecognizer`, persisted `PolicySource` lifecycle columns, `CollectionTaskService.create(source_id, trigger_type, requested_by)`, and source page schema.
- Produces: `SourceService.create(payload: SourceCreate) -> PolicySource`, `retry_recognition(source_id: int, payload: SourceRecognitionRetryInput) -> PolicySource`, `enable(source_id: int, expected_version: int) -> PolicySource`, `disable(source_id: int, expected_version: int) -> PolicySource`, `assert_collectable(source_id: int) -> PolicySource`, and `list(page: int, page_size: int) -> tuple[list[PolicySource], int]`.

Add these service exceptions in `backend/app/modules/sources/service.py`; Task 4 maps only these known errors:

```python
class SourceServiceError(Exception):
    code: str

class SourceNotFound(SourceServiceError):
    code = "source_not_found"

class SourceStateConflict(SourceServiceError):
    code = "source_state_conflict"

class SourceVersionConflict(SourceServiceError):
    code = "source_version_conflict"

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(self.code)

class SourceNotCollectable(SourceServiceError):
    code = "source_not_collectable"
```

- [ ] **Step 1: Write failing source lifecycle and collection-gate tests**

Test create as `recognizing` followed by one recognition result; recognized rows finish `ready_to_enable` with `is_enabled=False`; uncertain rows finish `pending_verification` with no collector key; rejected rows finish `rejected`; only `ready_to_enable` with matching `expected_version` can enter `enabled`; disable moves only an enabled row to `disabled`; a disabled source keeps tasks/channels. Test stale enable/disable raises `SourceVersionConflict(current_version)`, double enable is a state error, retry replaces the preview without creating a source, and every non-enabled state raises `SourceNotCollectable`.

```python
source = service.create(SourceCreate(name="Feed", entry_url="https://public.example/feed.xml"))
assert source.recognition_status == "ready_to_enable"
assert source.is_enabled is False
enabled = service.enable(source.id, source.version)
assert enabled.recognition_status == "enabled"
assert enabled.owner_confirmed_at is not None
assert CollectionTaskService(db).create(enabled.id, "scheduled", None).source_id == enabled.id
```

- [ ] **Step 2: Run the lifecycle tests to verify they fail**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/sources/test_service.py tests/unit/collection/test_scheduler.py tests/unit/collection/test_collector.py
```

Expected: FAIL because the service still uses `ready`/`pending`, defaults sources enabled, and has only toggle semantics.

- [ ] **Step 3: Implement strict lifecycle transitions**

Create persists the owner labels and an initial `recognizing` state, invokes the injected/default `SourceRecognizer`, and persists exactly the safe result projection in the same source row. `retry_recognition` accepts only `pending_verification` or `rejected`, changes to `recognizing`, runs the same recognizer against `representative_url` when supplied (otherwise `entry_url`), clears all confirmation/enabled timestamps, and saves a new safe projection. It must never automatically enable a recognized retry.

`enable` locks the row and accepts only `ready_to_enable`, checks `expected_version`, sets `recognition_status="enabled"`, `is_enabled=True`, `owner_confirmed_at=now`, `enabled_at=now`, `disabled_at=None`, increments version once, and updates the owner ID. `disable` locks the row, accepts only `enabled`, sets `disabled`, `is_enabled=False`, `disabled_at=now`, increments version once, and preserves preview/collection history. Replace the old PATCH/toggle/channel mutation operation with these exact lifecycle actions; do not delete channel history or expose editable channels in Stage 6.

```python
def assert_collectable(self, source_id: int) -> PolicySource:
    source = self._get(source_id)
    if source.recognition_status != "enabled" or not source.is_enabled:
        raise SourceNotCollectable("source is not owner-enabled")
    if source.adapter_key not in {"gdii", "rss_atom", "single_policy_link"}:
        raise SourceNotCollectable("source has no released collector")
    return source
```

- [ ] **Step 4: Implement server-only scheduler and collector dispatch**

Change `enqueue_enabled_ready_sources` to filter `recognition_status == "enabled"`, `is_enabled is True`, and `adapter_key.in_(("gdii", "rss_atom", "single_policy_link"))`. Preserve the existing active-task guard. In `collector.py`, dispatch by that fixed allowlist: existing `gdii` channels continue through the existing spider; `rss_atom` and `single_policy_link` call dedicated fixed collector functions that use `inspect_public_url`, record safe task outcome/count only, and never evaluate, notify, or accept selectors. Any unknown persisted key fails the task with a generic safe message and creates no process command.

- [ ] **Step 5: Run source/collection tests and static checks**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/sources/test_service.py tests/unit/collection/test_scheduler.py tests/unit/collection/test_collector.py
docker compose run --rm --no-deps api python -m ruff check app/modules/sources workers tests/unit/sources tests/unit/collection
docker compose run --rm --no-deps api python -m mypy app/modules/sources workers
```

Expected: PASS; no source schedules before explicit enable and no unknown key reaches a worker process.

- [ ] **Step 6: Commit the owner-confirmed source loop**

```powershell
git add backend/app/modules/sources/service.py backend/app/modules/sources/schemas.py backend/workers/scheduler.py backend/workers/collector.py backend/tests/unit/sources/test_service.py backend/tests/unit/collection/test_scheduler.py backend/tests/unit/collection/test_collector.py
git commit -m "feat: require source owner confirmation"
```

### Task 4: Publish safe owner source APIs

**Files:**
- Modify: `backend/app/modules/sources/router.py`
- Modify: `backend/app/modules/sources/schemas.py`
- Modify: `backend/tests/integration/sources/test_routes.py`

**Interfaces:**
- Consumes: Task 3 `SourceService` lifecycle methods and `SourcePage`/`SourceResponse` types.
- Produces: `GET /api/sources?page=1&page_size=20`, `POST /api/sources`, `POST /api/sources/{source_id}/recognition-retries`, `POST /api/sources/{source_id}/enable`, and `POST /api/sources/{source_id}/disable`. All use `require_role("applicant_owner")`.

- [ ] **Step 1: Write failing source route tests**

Authenticate owner and reader separately. Assert reader/unauthed calls get `403`/`401` for every source route; owner creates a recognized source and gets only public fields; owner enables with `{"expected_version": 1}`; stale disable returns `409` with `{"code":"source_version_conflict","current_version":2}`; pending/rejected sources cannot enable; retry records no new source; list has stable name/id ordering and `items/page/page_size/total`. Send malicious request fields (`adapter_key`, `channels`, `selector`, `headers`, `raw_html`) and assert Pydantic rejects them. Assert serialized values and captured log records omit adapter key, raw body, `Authorization`, URL query tokens, and exception text.

```python
created = client.post("/api/sources", json={"name": "Feed", "entry_url": "https://public.example/feed.xml", "region_labels": ["广东"], "topic_labels": ["制造"]})
assert created.status_code == 201
assert set(created.json()).isdisjoint({"adapter_key", "raw_html", "headers", "channels"})
assert client.post(f"/api/sources/{created.json()['id']}/enable", json={"expected_version": 1}).status_code == 200
```

- [ ] **Step 2: Run the source route tests to verify they fail**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/integration/sources/test_routes.py
```

Expected: FAIL because the old routes return arrays, accept channels, and expose only toggle semantics.

- [ ] **Step 3: Implement page responses and stable HTTP errors**

Implement page query validation `page >= 1`, `page_size in {10,20,50}`. Use one `_response()` projection that explicitly selects only `SourceResponse` fields and collection history summary. Map `SourceNotFound` to `404 {"detail":{"code":"source_not_found"}}`, invalid lifecycle transition to `409 {"detail":{"code":"source_state_conflict"}}`, and source version conflict to `409 {"detail":{"code":"source_version_conflict","current_version":N}}`. Do not pass request bodies, recognizer exceptions, raw redirects, or database errors through `detail`.

```python
@router.post("/{source_id}/enable", response_model=SourceResponse)
def enable_source(source_id: int, payload: SourceVersionInput, user: Owner, db: Session = Depends(get_db)) -> SourceResponse:
    try:
        source = SourceService(db, user).enable(source_id, payload.expected_version)
        db.commit()
        return _response(source, db)
    except SourceServiceError as error:
        db.rollback()
        raise _source_error_response(error) from None
```

- [ ] **Step 4: Run source API tests and complete backend source checks**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/integration/sources/test_routes.py tests/unit/sources tests/unit/collection
docker compose run --rm --no-deps api python -m ruff check app/modules/sources tests/integration/sources
docker compose run --rm --no-deps api python -m mypy app/modules/sources
```

Expected: PASS; routes have no owner-selected implementation key or raw recognition output.

- [ ] **Step 5: Commit the safe source API contract**

```powershell
git add backend/app/modules/sources/router.py backend/app/modules/sources/schemas.py backend/tests/integration/sources/test_routes.py
git commit -m "feat: expose safe source lifecycle api"
```

### Task 5: Add versioned profile/entity updates and safe audits

**Files:**
- Modify: `backend/app/modules/profiles/schemas.py`
- Modify: `backend/app/modules/profiles/service.py`
- Modify: `backend/app/modules/profiles/router.py`
- Create: `backend/tests/unit/profiles/test_service.py`
- Create: `backend/tests/integration/profiles/test_routes.py`

**Interfaces:**
- Consumes: existing `EnterpriseProfile`, `BusinessEntity`, `AuditService.record`, authenticated user dependency, and versions added in Task 1.
- Produces: `ProfileService.update_shared(payload: ProfilePatchInput, actor: User) -> VersionedProfileResponse`, `update_entity(seed_code: str, payload: BusinessEntityPatchInput, actor: User) -> VersionedBusinessEntityResponse`, `get_shared_profile(actor: User) -> VersionedProfileResponse`, and `list_business_entities(actor: User) -> list[VersionedBusinessEntityResponse]`.

- [ ] **Step 1: Write failing profile service tests**

Test explicit field validation: display/legal names trim and are 1–255 chars; `data` is a JSON object no larger than 32 KiB after canonical JSON encoding; only scalar string/number/bool/null, lists of those, and one-level nested object values are accepted; top-level keys are nonblank <= 64 chars; `verification_status` is 1–64 `[a-z0-9_]+`. A successful shared/entity write locks one row, requires exact version, increments it once, and creates exactly one `AuditEvent` with action, actor, object, timestamp, sorted changed field names, and bounded before/after safe values. A stale write raises `ProfileVersionConflict`; invalid/stale writes create no success audit. Assert policy/evaluation/collection/notification tables have identical counts before and after every profile write.

```python
updated = service.update_shared(
    ProfilePatchInput(expected_version=1, display_name="  新名称 ", data={"contact_email": "owner@example.com"}),
    seeded_owner,
)
assert updated.version == 2
assert audit.changes == {
    "changed_fields": ["data.contact_email", "display_name"],
    "before": {"data.contact_email": "contacts@supreium.com", "display_name": "适创科技"},
    "after": {"data.contact_email": "owner@example.com", "display_name": "新名称"},
}
```

- [ ] **Step 2: Run profile service tests to verify they fail**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/profiles/test_service.py
```

Expected: FAIL because profiles are read-only and have no version/audit service methods.

- [ ] **Step 3: Implement validated locked writes and one-event audit behavior**

Lock the selected shared row with `select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED").with_for_update()` and the entity row with `select(BusinessEntity).where(BusinessEntity.seed_code == seed_code).with_for_update()`. Reject calls unless the active actor has `applicant_owner`; the router also enforces the role. Compare `payload.expected_version` before mutation. Build the update only from explicitly present fields (`model_fields_set`); do not merge arbitrary incoming objects. Recursively redact values for audit: use the changed-field allowlist, truncate strings to 256 characters, cap lists at 20 entries, replace values for keys matching `password|secret|token|authorization|credential|header|path` with `"[redacted]"`, and never record an entire unbounded `data` blob. Record one event after computing all changes, with `changes={"changed_fields": changed_fields, "before": before, "after": after}`, then flush and return a fresh versioned projection with the newest 20 safe audit events.

```python
def _assert_expected_version(current: int, expected: int) -> None:
    if expected != current:
        raise ProfileVersionConflict(current)

AuditService(self.db).record(
    action="enterprise_profile_updated",
    actor_id=actor.id,
    object_type="enterprise_profile",
    object_id=profile.id,
    changes={"changed_fields": changed_fields, "before": before, "after": after},
)
```

- [ ] **Step 4: Write failing profile route tests**

Cover: unauthenticated read gets `401`; owner and reader can GET shared/entities; only owner can PATCH `/api/profiles/shared` and `/api/profiles/entities/{seed_code}`; reader gets `403`; unknown entity gets `404`; invalid input gets stable `422 {"code":"profile_field_validation_failed"}`; stale version gets `409 {"code":"profile_version_conflict","current_version":2}`; a successful response contains version and safe recent audit summary. Assert response/audit does not include raw secret-like values, headers, path keys, or evaluation/AI effects.

```python
stale = client.patch("/api/profiles/shared", json={"expected_version": 1, "display_name": "stale"})
assert stale.status_code == 409
assert stale.json()["detail"] == {"code": "profile_version_conflict", "current_version": 2}
```

- [ ] **Step 5: Implement profile HTTP routes and public error mapping**

Keep `GET /api/profiles/shared` and `GET /api/profiles/entities` authenticated. Add `PATCH /api/profiles/shared` and `PATCH /api/profiles/entities/{seed_code}` using `require_role("applicant_owner")`. The read projection includes `version` and `recent_audits`; reads never expose database IDs other than audit IDs/actor IDs already in the defined public contract. Map not found to `404 {"detail":{"code":"profile_not_found"}}`, invalid fields to the defined 422 code, and conflicts to the defined 409 code. Roll back every failed write before responding.

- [ ] **Step 6: Run profile tests and static checks**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/unit/profiles/test_service.py tests/integration/profiles/test_routes.py
docker compose run --rm --no-deps api python -m ruff check app/modules/profiles tests/unit/profiles tests/integration/profiles
docker compose run --rm --no-deps api python -m mypy app/modules/profiles
```

Expected: PASS; successful writes create one safe audit and never create evaluation or notification work.

- [ ] **Step 7: Commit profile editing and audit APIs**

```powershell
git add backend/app/modules/profiles/schemas.py backend/app/modules/profiles/service.py backend/app/modules/profiles/router.py backend/tests/unit/profiles/test_service.py backend/tests/integration/profiles/test_routes.py
git commit -m "feat: edit versioned enterprise profiles"
```

### Task 6: Establish exact frontend source and profile contracts

**Files:**
- Modify: `frontend/src/api/sources.ts`
- Modify: `frontend/src/api/profiles.ts`
- Modify: `frontend/src/api/errors.ts`
- Create: `frontend/tests/unit/SourceApiContract.spec.ts`
- Create: `frontend/tests/unit/ProfileApiContract.spec.ts`

**Interfaces:**
- Consumes: Tasks 4–5 HTTP response/error shapes and existing Axios `http` client.
- Produces: the TypeScript source/profile API interfaces in **Shared Interfaces** plus `getBusinessErrorCode(error: unknown): { code: string; currentVersion?: number } | null`.

- [ ] **Step 1: Write failing frontend API contract tests**

Mock `http` and assert exact endpoint/method/payload mapping: source create carries only `name`, `entry_url`, label arrays; retry uses optional `{ representative_url }`; enable/disable send only `expected_version`; pagination sends `{ params: { page, page_size } }`; profile writes use exact PATCH paths and version field. Test 409 parsing for both `source_version_conflict` and `profile_version_conflict`; assert no API type/property permits `adapter_key`, selector, channels, raw body, headers, or credential fields.

```typescript
await enableSource(7, 3);
expect(http.post).toHaveBeenCalledWith("/sources/7/enable", { expected_version: 3 });
expect(getBusinessErrorCode({ response: { data: { detail: { code: "profile_version_conflict", current_version: 4 } } } })).toEqual({ code: "profile_version_conflict", currentVersion: 4 });
```

- [ ] **Step 2: Run the frontend API tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/SourceApiContract.spec.ts tests/unit/ProfileApiContract.spec.ts
```

Expected: FAIL because the current source API uses `home_url`, channels, and toggle, and the profile API has no writes/version/audits.

- [ ] **Step 3: Implement typed API clients and stable error narrowing**

Replace `AdapterStatus` and channel input types with the exact recognition unions/interfaces above. Keep all public response types structural and finite. Update profiles to return versions/recent audits. In `errors.ts`, narrow only the documented response shape; return `null` for unknown status/body instead of displaying server details. Do not include any endpoint for direct adapter selection or arbitrary source update.

```typescript
export async function retrySourceRecognition(id: number, representativeUrl?: string): Promise<PolicySource> {
  return (await http.post<PolicySource>(`/sources/${id}/recognition-retries`, representativeUrl ? { representative_url: representativeUrl } : {})).data;
}
```

- [ ] **Step 4: Run contracts and TypeScript validation**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/SourceApiContract.spec.ts tests/unit/ProfileApiContract.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
```

Expected: PASS; the client cannot send unsupported source implementation/configuration fields.

- [ ] **Step 5: Commit frontend contracts**

```powershell
git add frontend/src/api/sources.ts frontend/src/api/profiles.ts frontend/src/api/errors.ts frontend/tests/unit/SourceApiContract.spec.ts frontend/tests/unit/ProfileApiContract.spec.ts
git commit -m "feat: add source profile frontend contracts"
```

### Task 7: Build the owner source preview and enablement UI

**Files:**
- Modify: `frontend/src/components/sources/SourceDrawer.vue`
- Create: `frontend/src/components/sources/SourceStatusCard.vue`
- Modify: `frontend/src/views/PolicySourcesView.vue`
- Modify: `frontend/tests/unit/PolicySourcesView.spec.ts`
- Create: `frontend/tests/unit/SourceDrawer.spec.ts`

**Interfaces:**
- Consumes: Task 6 `PolicySource`, source client functions, `currentUser`, and `getBusinessErrorCode`.
- Produces: owner desktop source creation/retry/enable/disable controls, source status cards, page navigation, and source reading with no write controls at mobile width.

- [ ] **Step 1: Write failing source drawer and page tests**

Assert the drawer has name, public entry URL, optional comma-separated region/topic labels, and no channel, adapter, selector, XPath/CSS, header, credential, or raw-preview inputs. Assert labels normalize by trim, remove duplicates, and cap at 20. Test cards show business labels: `识别中`, `可启用`, `已启用`, `待人工确认`, `无法使用`, `已停用`; a ready source displays its safe preview and enable button; pending displays retry; rejected displays correction/retry; enabled displays disable; all other states have no collect control. Assert a 409 shows reload guidance without reapplying a stale action, list page navigation calls `getSources`, owner sees actions only above 720px, and mobile still shows status/preview/history but no add/retry/enable/disable control.

```typescript
function setViewportWidth(width: number): void {
  const query = "(max-width: 720px)";
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((value: string) => ({
      matches: value === query && width <= 720,
      media: value,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
}

expect(wrapper.text()).toContain("可启用");
expect(wrapper.get("button[aria-label='启用 Feed']").exists()).toBe(true);
await setViewportWidth(640);
expect(wrapper.find("button[aria-label='添加政策来源']").exists()).toBe(false);
expect(wrapper.text()).toContain("预览：广东省科技业务管理阳光政务平台");
```

- [ ] **Step 2: Run source UI tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/SourceDrawer.spec.ts tests/unit/PolicySourcesView.spec.ts
```

Expected: FAIL because the current UI edits channels and exposes only ready/pending plus toggle behavior.

- [ ] **Step 3: Implement minimal source intake and status cards**

`SourceDrawer` emits `SourceCreateInput` only. Build label arrays using the concrete `normalizeLabels` helper; do not add client recognition logic. `SourceStatusCard` receives a `PolicySource` and emits `retry`, `enable`, or `disable` carrying the source ID/version. Render `recognition_summary` as text only; do not create an external HTML preview or show raw URLs beyond the sanitized entry URL anchor. `PolicySourcesView` loads a 20-row page, replaces a source from mutation responses, reloads the page after create/retry, and uses a reactive `matchMedia("(max-width: 720px)")` listener to suppress all owner mutation controls on mobile.

```typescript
function normalizeLabels(value: string): string[] {
  return Array.from(new Set(
    value.split(",").map((label) => label.trim()).filter((label) => label.length > 0),
  )).slice(0, 20);
}
```

```typescript
const mobile = ref(window.matchMedia("(max-width: 720px)").matches);
const canWrite = computed(() => !mobile.value && currentUser.value?.roles.includes("applicant_owner") === true);
const canEnable = (source: PolicySource) => canWrite.value && source.recognition_status === "ready_to_enable";
```

- [ ] **Step 4: Run source UI tests and type-check**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/SourceDrawer.spec.ts tests/unit/PolicySourcesView.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
```

Expected: PASS; no desktop/mobile view lets a user choose an adapter or build a scraping rule.

- [ ] **Step 5: Commit the source preview UI**

```powershell
git add frontend/src/components/sources/SourceDrawer.vue frontend/src/components/sources/SourceStatusCard.vue frontend/src/views/PolicySourcesView.vue frontend/tests/unit/SourceDrawer.spec.ts frontend/tests/unit/PolicySourcesView.spec.ts
git commit -m "feat: preview and enable policy sources"
```

### Task 8: Build versioned profile/entity editing and audit UI

**Files:**
- Create: `frontend/src/components/profiles/ProfileEditor.vue`
- Create: `frontend/src/components/profiles/ProfileAuditList.vue`
- Modify: `frontend/src/views/EnterpriseProfileView.vue`
- Modify: `frontend/tests/unit/EnterpriseProfileView.spec.ts`
- Create: `frontend/tests/unit/ProfileEditor.spec.ts`

**Interfaces:**
- Consumes: Task 6 versioned profile/entity types and mutation APIs, current owner role, and `getBusinessErrorCode`.
- Produces: separate shared/entity owner editors with safe audit summaries; all authenticated non-owner and mobile users see the same data/audit reading without writes.

- [ ] **Step 1: Write failing profile editor/view tests**

Test the shared editor submits only changed `display_name`, `data`, and `verification_status` along with `expected_version`; entity editor submits only `legal_name`, `data`, and `verification_status`. Test inline required/length/data errors, disabled submit during request, returned response replacement, and conflict feedback: show `资料已被他人更新（当前版本 4）。重新加载后再编辑。`; invoking reload fetches fresh data and clears the stale draft without retrying a write. Test every response shows the recent audit actor/time/changed-field names/before/after, redacted values display `已隐藏`, reader has no edit buttons, and 640px width hides all edit controls while preserving shared/entity/audit content.

```typescript
expect(updateSharedProfile).toHaveBeenCalledWith({
  expected_version: 1,
  display_name: "适创科技（更新）",
});
expect(wrapper.text()).toContain("变更字段：display_name");
expect(wrapper.find("button[aria-label='编辑公司共享档案']").exists()).toBe(false);
```

- [ ] **Step 2: Run profile UI tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProfileEditor.spec.ts tests/unit/EnterpriseProfileView.spec.ts
```

Expected: FAIL because the existing profile view is read-only and has no version/audit data or editing components.

- [ ] **Step 3: Implement explicit profile forms and audit summaries**

`ProfileEditor` accepts a discriminated `target: "shared" | "entity"` and complete response object. Clone only `display_name`/`legal_name`, `verification_status`, and JSON `data` into local form state. Build the outgoing object from explicit fields and compare serialized normalized values to omit unchanged fields; retain `expected_version` always. Render data as a textarea containing pretty JSON, parse only on submit, enforce the same 32 KiB client guard, and show a local message without sending malformed JSON. Do not spread the full server object into the request. `ProfileAuditList` uses `textContent` interpolation for all before/after values and replaces `[redacted]` with `已隐藏`.

```typescript
function stableJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, Object.keys(value).sort());
}
```

```typescript
const payload: ProfilePatchInput = { expected_version: props.profile.version };
if (name.value.trim() !== props.profile.display_name) payload.display_name = name.value.trim();
if (stableJson(parsedData) !== stableJson(props.profile.data)) payload.data = parsedData;
if (status.value !== props.profile.verification_status) payload.verification_status = status.value;
```

`EnterpriseProfileView` passes owner capability only when `currentUser` includes `applicant_owner` and the reactive mobile flag is false. It retains current seed-order/missing-city display behavior. On successful write, replace only the returned shared profile or matching entity, preserving the existing ordered list; it does not navigate to evaluation or invoke an evaluation API.

- [ ] **Step 4: Run profile UI tests and complete frontend checks**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProfileEditor.spec.ts tests/unit/EnterpriseProfileView.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
pnpm --dir frontend build
```

Expected: PASS; mobile and readers retain readable profile/audit information but have no write affordance.

- [ ] **Step 5: Commit the profile editing UI**

```powershell
git add frontend/src/components/profiles/ProfileEditor.vue frontend/src/components/profiles/ProfileAuditList.vue frontend/src/views/EnterpriseProfileView.vue frontend/tests/unit/ProfileEditor.spec.ts frontend/tests/unit/EnterpriseProfileView.spec.ts
git commit -m "feat: edit audited enterprise profiles"
```

### Task 9: Verify the complete Stage 6 boundary without deployment changes

**Files:**
- Create: `backend/tests/integration/test_stage6_flow.py`
- Create: `docs/testing/2026-08-20-stage-6-source-profile-smoke-test.md`
- Modify: `memory/project-memory.md`

**Interfaces:**
- Consumes: all Tasks 1–8; existing Docker Compose test commands only as a local verification environment.
- Produces: automated vertical-flow evidence and a reproducible local desktop/mobile smoke checklist. It does not alter deployment configuration, backups, recovery, production secrets, worker topology, or WeCom login.

- [ ] **Step 1: Write the failing Stage 6 vertical-flow test**

With mocked recognition responses and real FastAPI authentication, execute this exact flow:

1. Owner creates a public recognized feed/source and receives `ready_to_enable`; no `CollectionTask` exists.
2. Owner enables it with current version; scheduler creates exactly one scheduled task.
3. Owner creates an uncertain public source; it remains `pending_verification`, retry is permitted, and scheduler creates no task.
4. Unsafe/private source becomes `rejected`; no task exists and the response/log/audit contain no raw unsafe URL detail.
5. Reader cannot call any source/profile write route but can read profiles/audits.
6. Owner updates shared profile then one entity; each update increments exactly once and creates exactly one safe audit; stale shared update returns the stable 409 payload.
7. Count evaluation batches, policy conclusions, and notification-like task rows before/after and assert no automatic reevaluation/AI/notification side effect.

```python
before_batches = db.scalar(select(func.count()).select_from(EvaluationBatch))
before_tasks = db.scalar(select(func.count()).select_from(CollectionTask))
response = client.patch("/api/profiles/shared", json={"expected_version": 1, "display_name": "Updated"})
assert response.status_code == 200
assert db.scalar(select(func.count()).select_from(EvaluationBatch)) == before_batches
assert db.scalar(select(func.count()).select_from(CollectionTask)) == before_tasks
```

- [ ] **Step 2: Run the vertical-flow test to verify it fails**

Run:

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider tests/integration/test_stage6_flow.py
```

Expected: FAIL because the complete Stage 6 endpoints/flows are not all implemented before Tasks 1–8.

- [ ] **Step 3: Implement only the integration test and local smoke record**

Do not add production code in this task. Write `docs/testing/2026-08-20-stage-6-source-profile-smoke-test.md` with these local checks and evidence fields: commit SHA, test command outputs/totals, recognized no-login URL used, uncertain no-login URL used, source states observed, source scheduling count before/after enable, profile/entity versions, audit IDs/actions, owner/reader results, desktop result, 640px mobile result, redaction checks, and explicit confirmation that Stage 5 Docker/backup/recovery/UAT gates remain independent. Do not include credentials, host paths, secrets, raw pages, request headers, or production URLs with query values. Append a dated Stage 6 delivered/deferred summary to `memory/project-memory.md` that explicitly records exclusion of selector scraping, automatic re-evaluation, backups, WeCom login, and production deployment.

- [ ] **Step 4: Run the complete automated verification set**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider
docker compose run --rm --no-deps --build api python -m ruff check .
docker compose run --rm --no-deps --build api python -m mypy app policy_crawler workers
pnpm --dir frontend test
pnpm --dir frontend exec vue-tsc -b --noEmit
pnpm --dir frontend build
```

Expected: every command exits `0`. This is verification only; do not run a production deployment, change Compose topology, or substitute Stage 6 results for Stage 5 operational gates.

- [ ] **Step 5: Perform the local desktop/mobile authorization smoke checks**

At the local app after the automated suite passes, record these results without storing credentials:

1. Owner sees source intake, safe preview/status, explicit enable only after `可启用`, retry for `待人工确认`, and disable for `已启用`.
2. Owner cannot select an adapter, channel selector, CSS/XPath selector, header, or credential; no raw page content is visible.
3. One public no-login source is enabled after preview and is eligible for the scheduler; one uncertain public no-login source stays pending and is not scheduled.
4. Owner edits shared profile and one entity, sees a fresh version and safe audit summary, and gets reload guidance for a stale browser tab.
5. Reader can read profile/entity/audits but is denied direct source/profile write API requests.
6. At a 640px viewport, sources/profiles/status/audits remain readable while add, retry, enable, disable, and edit controls are absent.
7. No source/profile action creates an evaluation, invokes AI, queues a notification, or alters a manual policy conclusion.

- [ ] **Step 6: Commit the Stage 6 verification evidence**

```powershell
git add backend/tests/integration/test_stage6_flow.py docs/testing/2026-08-20-stage-6-source-profile-smoke-test.md memory/project-memory.md
git commit -m "test: verify stage 6 source profile loop"
```

---

## Delivery Gates

1. **Persistence gate:** Task 1 proves reversible schema evolution and preserves existing source/channel/task/profile/entity records.
2. **Public-network gate:** Task 2 proves canonical URL handling, DNS/redirect safety, bounded previews, and safe redaction with no real external dependency in unit tests.
3. **Enablement gate:** Tasks 3–4 prove no collection can be queued before explicit owner enablement, and no public API can expose or choose a collector implementation.
4. **Profile gate:** Task 5 proves owner-only versioned writes, structured validation, one safe audit event per successful update, stable conflicts, and no evaluation side effects.
5. **Frontend gate:** Tasks 6–8 type-check the backend contract and prove desktop owner controls plus reader/mobile read-only behavior.
6. **Acceptance gate:** Task 9 passes full automated suites and records local source/profile/redaction/mobile evidence without a production deployment or changes to independent Stage 5 gates.

## Self-Review

1. **Spec coverage:** Source records, safe recognition outcomes/preview/retry, explicit enable/disable, scheduler eligibility, controlled kinds/no adapter picker, public-network safety, paged/redacted APIs, shared/entity profile validation/versioning/audits, owner versus non-owner authorization, no automatic re-evaluation/AI/notifications, desktop actions, and mobile read-only behavior are mapped to Tasks 1–9. The excluded scraping, selector, login/captcha, Redis/Kafka/workflow, backup/recovery, WeCom, migration rollout, and deployment work are constrained globally and reiterated in the relevant tasks. Stage 5 gates are explicitly kept independent in Task 9.
2. **Placeholder scan:** This plan contains no `TBD`, `TODO`, “implement later”, “fill in details”, or “similar to Task” instruction. Every implementation task includes exact files, interfaces, failing-test command, concrete implementation direction/code, passing-test command, and commit command.
3. **Type consistency:** `RecognitionStatus`, `RecognitionKind`, `RecognitionResult`, source response/page shapes, source lifecycle method names, `expected_version`, `ProfilePatchInput`, `BusinessEntityPatchInput`, `ProfileVersionConflict`, and frontend API signatures are defined in Shared Interfaces and used consistently in Tasks 1–9. Server-only `adapter_key` exists only in the Python recognizer/service/worker boundary and is expressly absent from every public schema/type.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-20-stage-6-source-profile.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
