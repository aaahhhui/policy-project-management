# Stage 6 Source Configuration and Enterprise Profile Editing Design

> Status: approved design direction; ready for written-spec review.

## Goal

Deliver a demonstrable Stage 6 loop in which an applicant owner can configure policy sources without understanding technical adapters, safely enable recognized public sources, and edit shared/company-entity profiles with auditable changes.

## Scope

Included:

- Owner-configured source records with name, entry URL, optional region/topic labels, recognition state, preview, enable/disable control, and collection history.
- URL safety validation and controlled recognition of RSS/Atom, supported public government sites, supported public listing pages, and one-off policy links.
- Safe `pending_verification` downgrade when recognition is uncertain; the source remains recorded but cannot be scheduled.
- Owner editing for the shared enterprise profile and each business entity, optimistic version protection, validation, and audit history.
- Source/profile API and desktop UI plus mobile read-only behavior.

Excluded:

- Arbitrary website scraping rules, CSS/XPath configuration, login/captcha bypass, or automatic activation of unrecognized URLs.
- Automatic historical policy re-evaluation, AI invocation, notifications, or changes to manual decisions after profile edits.
- Redis, Kafka, generic workflow engines, WeCom login, backup/recovery changes, and production migration work.

## Source Configuration Model

`PolicySource` gains only safe configuration/recognition fields: `recognition_status`, controlled `recognition_kind`, safe `recognition_summary`, preview timestamps, owner confirmation/enable timestamps, and optimistic `version`. The recognized implementation key remains server-owned and is never chosen directly by an end user.

States:

- `recognizing`: URL accepted and recognition queued/in progress.
- `ready_to_enable`: a supported public kind was recognized and a safe preview is available; owner confirmation is required.
- `enabled`: eligible for the existing daily collection scheduler.
- `pending_verification`: recognition is inconclusive; it is saved but never scheduled.
- `rejected`: URL is unsafe, private, inaccessible, or unsupported.
- `disabled`: owner stopped a formerly eligible source; history remains intact.

## Recognition and Collection Flow

```text
Owner enters name + public URL
  -> URL/SSRF safety validation
  -> recognize RSS/Atom, supported site, public list page, or one-off link
  -> store controlled result and preview summary
  -> owner explicitly enables only ready_to_enable source
  -> existing scheduler collects enabled source
```

Recognition must use the existing public-network safety model. It does not authenticate, execute arbitrary selectors, follow unsafe redirects, or add an unknown site to the queue. A `pending_verification` source may be retried after an owner supplies a representative policy link; a later system adapter can re-recognize it without requiring a new source record.

## Profile Editing

The applicant owner may edit the single shared enterprise profile and individual business entities. The service validates structured fields, rejects stale optimistic versions with a stable conflict response, and records one audit event containing actor, object, timestamp, changed field names, and before/after safe values. All other roles receive server-side `403`; mobile clients display profiles read-only.

Saving a profile never creates an evaluation batch, invokes AI, enqueues a notification, or overwrites a manual policy conclusion. The UI may link the owner to the existing explicit re-evaluation action.

## API and UI Boundary

Owner routes expose source creation, recognition retry, preview/status, explicit enable/disable, and paginated safe records. Profile routes expose read for authenticated users and versioned writes only for applicant owners. Responses never include internal adapter keys, raw page contents, headers, credentials, filesystem paths, raw crawl errors, or recognition implementation details.

The desktop Sources page provides business-language status labels and preview/enable controls. It never asks the owner to choose an adapter. The Profiles page has separate shared-profile and entity editors with inline version conflict feedback and recent audit summaries. Mobile hides all write controls.

## Cloud and Deployment Compatibility

No host paths, secrets, or fixed source count are persisted. Recognition/collection uses existing container-local configuration and existing scheduler/worker boundaries, so future cloud deployment changes mounts/secrets/network policy rather than source rows or APIs. New supported adapters are server releases; existing `pending_verification` records remain reusable.

## Acceptance and Tests

TDD coverage must prove URL safety; recognition state transitions; no scheduling before explicit enable; safe pending/rejected downgrade; owner versus non-owner authorization; profile validation/version conflicts/audits; no automatic re-evaluation/notifications; mobile read-only controls; and API/log/audit redaction.

Demo acceptance uses at least two public no-login URLs: one recognized source enabled after preview and one uncertain source safely retained as pending verification. It also covers shared-profile/entity editing by owner, conflict behavior, audit visibility, and reader/mobile read-only behavior.

Stage 5 Docker/backup/recovery/UAT gates remain independent and cannot be replaced by Stage 6 acceptance.
