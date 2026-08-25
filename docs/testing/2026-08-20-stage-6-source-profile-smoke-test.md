# Stage 6 source/profile local smoke record

Date: 2026-08-24
Verification base commit: `f8325c1`
Scope: local verification only; no production deployment, production migration, backup, recovery, or WeCom-login action.

## Automated evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Stage 6 authenticated vertical flow | PASS | `1 passed`; real FastAPI cookie authentication with a mocked recognizer. |
| Reverse mutation | PASS | Temporarily made a recognized source enabled before owner confirmation; the test failed at the first scheduler call with expected `0`, actual `1`. The mutation was removed and the same test returned green. |
| Backend full suite | PASS | `519 passed, 2 skipped`; exit `0`. |
| Backend lint | PASS | Ruff: all checks passed; exit `0`. |
| Backend typing | PASS | mypy: no issues in `93` source files; exit `0`. |
| Frontend suite | PASS | `35` files, `161` tests; exit `0`. |
| Frontend typing | PASS | Vue TypeScript build check; exit `0`. |
| Frontend production build | PASS WITH WARNINGS | `1770` modules transformed; exit `0`. Existing third-party PURE-comment and large-chunk warnings remain. |
| SQLite Stage 6 schema suite | PASS | `17 passed`; exit `0`. |
| MySQL 8.4 fresh and round-trip | PASS | Fresh chain reached `0009`; downgrade reached `0008`; upgrade returned to `0009`; one fictional profile row remained present and returned with version `1`. |
| Docker Compose commands | DEFERRED | Compose explicitly loads a local `.env` and requires database/JWT test secrets. Per the safety gate, the file was not read and Compose was not started. Full tests instead ran in an isolated repository image without application secrets. |

## Public no-login URL probes

Only host/path and status are recorded; no response body, header, query value, or credential was retained.

| Intended scenario | Safe host/path | Direct network result | In-app result |
| --- | --- | --- | --- |
| Recognized feed | `github.blog/feed/` | HTTP `200`, no login | Full-stack live recognition deferred; mocked vertical flow and browser fixture observed `ready_to_enable`. |
| Uncertain public page | `example.com/` | HTTP `200`, no login | Full-stack live recognition deferred; mocked vertical retry remained `pending_verification`. |

## Source and scheduling evidence

The authenticated vertical test observed these source states: `ready_to_enable`, `enabled`, `pending_verification`, and `rejected`. Before explicit enablement, collection-task count was `0` and the scheduler created `0`. After owner enablement, one scheduler call created exactly `1` scheduled task. Retrying the uncertain source kept it pending and created no task. The rejected source created no task.

The rejection input contained a controlled unsafe query marker. The marker was absent from the HTTP response, captured logs, and all audit payloads. Public source responses exposed no adapter selector, channel selector, CSS/XPath selector, header, credential, raw page, raw error, or filesystem-path field.

## Profile, audit, and authorization evidence

| Evidence field | Observed result |
| --- | --- |
| Shared profile version | `1 -> 2` exactly once |
| Entity version | `1 -> 2` exactly once |
| Audit IDs/actions | Two distinct positive runtime IDs; `enterprise_profile_updated` and `business_entity_updated` |
| Stale shared update | Stable `409` with `profile_version_conflict` and current version `2` |
| Owner | Source create/preview/enable/retry and profile/entity writes allowed |
| Reader | Shared profile, entities, and safe audit summaries readable; all direct source/profile writes returned `403` |
| Side effects | EvaluationBatch, PolicyConclusionDecision, NotificationDelivery, NotificationAttempt, and CollectionTask counts were unchanged by profile writes |
| Manual decision | Existing `manual_override` policy projection and complete decision rows remained byte-for-byte equivalent at the ORM value boundary |

## Browser smoke

Native Python Playwright ran headless against the real local Vue application after reconnaissance and `networkidle`. API responses were controlled non-secret fixtures because the full Compose login environment was unavailable. Screenshots and the script remain ignored temporary evidence.

| View | Result | Evidence |
| --- | --- | --- |
| Desktop owner | PASS (frontend fixture fallback) | Source states, safe preview, add/enable/retry/disable controls, profile/entity edit controls, version `2`, safe audit, redacted value, and stale `409` reload guidance were visible. |
| Desktop reader | PASS (frontend fixture fallback) | Profile/entity/audit content remained readable; edit controls were absent; a direct write request returned `403`. |
| 640px owner | PASS (frontend fixture fallback) | Source/profile/status/audit content remained readable; add, retry, enable, disable, and shared/entity edit controls were absent. Screenshot review confirmed the responsive result. |
| Full-stack credentialed UAT | DEFERRED | No approved non-secret seed-login route was available. No local credential file was read and no credential was stored in scripts, screenshots, logs, or this record. |

## Security and dependency checks

- Tracked-diff scans found no private-key header, bearer value, provider-key shape, WeCom webhook value, or host filesystem path. The only URL query in the added test is the controlled redaction marker used to prove removal.
- No changed public source/profile schema or TypeScript contract added adapter, selector, raw body, header, credential, or filesystem-path fields.
- Python advisory audit reported findings only in image tooling/dev packages: `pip 25.0.1` and `pytest 8.4.2`; application runtime libraries had no reported finding in this run. The local project package itself is not published and was not auditable by the registry.
- Node production audit reported one high and one moderate advisory through the transitive build dependency `nanoid`; remediation is deferred to a separately reviewed dependency update.

## Independent gates and exclusions

Stage 5 Docker, backup, recovery, and UAT gates remain independent and were neither executed nor replaced by this Stage 6 evidence. Stage 6 explicitly excludes arbitrary selector scraping, owner-selected adapters, automatic historical re-evaluation, AI invocation from profile saves, notification creation from profile saves, Stage 5 backup/recovery work, WeCom login, production migration rollout, and production deployment.
