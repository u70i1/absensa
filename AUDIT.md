# Absensa pre-launch audit

Audit date: 2026-10-02. Scope: the live FastAPI application, PostgreSQL models and
migrations, Jinja/HTMX interface, notification scheduler, WhatsApp worker, tests,
scripts and deployment configuration. Repository files and the implemented rules
were inspected before changes. The archived React prototype is not a deployed
entry point; it was reviewed for scope rather than revived or redesigned.

## Executive summary

Confirmed problems affected password-login protection, concurrent attendance,
bulk persistence, guardian-contact preservation, notification freshness, worker
error privacy and database recovery. These have focused fixes and regression
coverage. Existing administrator authorization, device/operator authentication,
same-origin CSRF enforcement, Argon2 storage, import ownership and export escaping
were retained. No production credentials or school data were changed, and no
guardian notifications were sent.

The application is demonstrably improved, but this report is not a blanket
production-readiness certification. HTTPS, backup/restore rehearsal, live
WhatsApp/Chromium validation, unresolved Node dependency advisories and one static
typing issue remain launch considerations.

## Architecture and rules verified

- `web/app/main.py` exposes FastAPI, public pages, database readiness and browser
  security middleware. `web/app/routes/` separates administrator pages/APIs from
  trusted-device enrollment and operator scanning. Authentication dependencies
  enforce access on the server, including HTMX and legacy data APIs.
- SQLAlchemy sessions live in `web/app/db/session.py`; services implement writes,
  validation and transaction boundaries. Models cover students, classes, scan
  snapshots, administrator sessions, device bindings, operator sessions, import
  drafts/photos, card settings and notification settings/logs. Alembic is the
  source of schema changes.
- Attendance records active students once per configured school-local day.
  History snapshots survive student deletion; the relationship becomes nullable.
  Present/absent calculations use scans and active enrollment, rather than a
  separate permanent absence record. Operator history is intentionally
  school-wide; no class-scoped teacher authorization is implemented.
- Imports review combined workbooks and optional photo archives before applying
  all selected rows atomically. Draft ownership, stale-preview rejection,
  temporary class references, duplicate identities, archive expansion/path
  limits, normalized photos and spreadsheet formula handling were examined.
  Exports and student cards are administrator operations.
- `web/app/jobs/whatsapp_notifications.py` is a separately supervised scheduler.
  PostgreSQL run/delivery claims govern retries. The Python gateway sends final
  messages to `services/whatsapp/src/server.js`, whose Express API uses a shared
  secret and a `whatsapp-web.js`/Chromium client. Attendance persistence does not
  depend on successful WhatsApp delivery.
- `compose.production.yml` starts database, migration, web, scheduler and worker
  services. The worker and database are not published as host ports. Python and
  Node containers run as non-root users, with persistent photos and WhatsApp auth.
  The development Compose configuration is separate.

## Significant confirmed issues

Severity reflects the application impact. “Fixed” means implemented and checked
by the final tests described below; dependency reachability is qualified separately.

| Severity | Component | Root cause and possible impact | Resolution |
| --- | --- | --- | --- |
| High | `admin_auth.py`, `access_auth.py`; password login | Administrator and device passwords had no shared attempt budget. Repeated attempts allowed brute force and repeated expensive Argon2 work. | Fixed: atomic PostgreSQL budgets before verification, account and source limits, expiry and `429`/`Retry-After`. Concurrent attempts and unknown accounts tested. Existing PIN lockout retained. |
| High | `scan_service.post_scan` | Concurrent requests could both pass the same-day existence check and insert duplicate attendance. | Fixed: lock the student row before checking/inserting; take the local date after lock acquisition. Two real concurrent sessions produce one scan and one conflict. |
| High | Student/class/scan bulk delete services | Successful deletes lacked a commit and were undone when a request session closed. | Fixed: commit successful mutations; verify from a separate session after closure. Dry runs still roll back. |
| High | `student_service.edit_student`, bulk updates | An omitted guardian phone defaulted to `None`, silently clearing existing contact data. | Fixed: distinguish omission from explicit null for single and bulk edits. Omission preserves contact; explicit null clears it. |
| High | Student/class bulk update services | Final-state validation included rejected rows, allowing another row to reuse an identity that was never freed. Deferred constraints were not checked before dry-run rollback. | Fixed: validate surviving candidates repeatedly, reject dependent conflicts and repeated IDs, force constraints before completion, and roll back concurrent conflicts. Valid swaps and independent valid rows remain supported. |
| High | `whatsapp_notification_service.run_daily` | Recipient/contact/enrollment snapshots became stale during send delays; settings could stay cached after another process disabled sending. | Fixed: refresh settings and recipient fields before dispatch; skip deleted/inactive/contactless students and use current names/contact. Independent-session and delayed-edit tests pass. |
| High | `tests/conftest.py` | The suite automatically upgraded and downgraded its configured database, including a mistakenly selected application database. | Fixed: require explicit destructive-test opt-in and a distinct database target before migrations. Credential/driver spelling differences do not evade the equality check. Operators must still avoid hostname aliases for the same database. |
| Medium | `scan_logs.class`, scan response | Scan snapshots allowed ten characters while class names allowed twenty; the scan API also omitted its declared `nisn` field. Valid classes could cause failed scans and consumers received incomplete data. | Fixed: widen snapshots through migration and return `nisn`, retaining the existing `student_nisn` alias. |
| Medium | Scan date schemas/service | Naive bounds used the host timezone and mixed aware/naive comparisons could fail. Nonzero microseconds and unstable ordering affected boundary/history results. | Fixed: localize naive bounds to the school timezone, validate comparisons/range limits and use complete day bounds plus deterministic ordering. |
| Medium | Student/class write validation | Legacy writes accepted invalid NISNs, oversized names, invalid class references, blank class names or out-of-range grades until database failure. | Fixed: consistent identity validation and per-row bulk errors. Omitted bulk `current` preserves an existing value or defaults true on creation. |
| Medium | Student/class CRUD commits | A competing write after a uniqueness precheck raised an unhandled database error and left a failed session. | Fixed: roll back and map confirmed uniqueness/FK violations to existing application errors. Real concurrent creates tested. Other unexpected database errors still propagate. |
| Medium | Notification reservation/clock | A delayed manual reservation could start a different day's batch; long batches could continue yesterday's absence notifications after midnight. | Fixed: verify reserved run/day and stop a batch at school-local midnight. |
| Medium | Python WhatsApp gateway | Malformed state values could raise `TypeError`; redirects or missing/false send acknowledgements could be treated as success. | Fixed: validate state types, require a 2xx response and explicit `sent: true`; uncertain sends remain errors. |
| Medium | Worker gateway/app | Recipient lookup could resume through a replaced client; library error fragments could expose student names despite whole-message redaction. Raw secrets without a Bearer scheme were accepted and oversized JSON became a generic error. | Fixed: capture/recheck client identity, log stable codes, require Bearer authentication and return `413` for oversized bodies. |
| Medium | Browser middleware, `base.html` | Missing framing/content/referrer protections and HTMX history caching increased exposure on shared school browsers. | Fixed: security headers and `hx-history="false"`; escaping and no-store behavior regression-tested. CSP restricts framing/base/form destinations; it is not a complete script policy. |
| Medium | Database engine | Idle connections broken by a database interruption were handed to requests. SQLAlchemy exceptions also rendered bound parameter values into tracebacks. | Fixed: pool pre-ping and hidden SQL parameters. Tests terminate only an audit-owned connection and check error rendering. Driver-originated error details still require private log access. |
| Low | Models, routes, installer and tests | Unresolved forward type references, incorrect optional relationships, mutable form defaults, unused migration imports, lint failures and stale workbook/row-ID/photo fixtures obscured useful diagnostics. | Fixed: imports/types/defaults, reviewed lint corrections and fixtures aligned to the actual workbook schema and deduplication behavior. No checks were disabled. |

Authorization, SQL parameterization, CSRF, escaping, import ownership and archive
handling were reviewed and exercised by the existing and new tests. This audit
did not demonstrate an additional SQL injection, administrator authorization
bypass, import IDOR or executable spreadsheet-injection path in those workflows.
That conclusion applies to inspected paths and tests, not to every possible attack.

## Dependencies

The initial Python scan reported twelve findings across five packages, including
one duplicate CairoSVG advisory. Pins are now `httpcore2==2.12.0`,
`httpx2==2.12.0`, `CairoSVG==2.9.0`, `fonttools[woff]==4.60.2` and
`urllib3==2.8.0`. HTTPX2 requires the matching HTTPCore2 version. Patch selection
covered HTTP framing/TLS/decompression, SVG recursion and font processing
advisories; see the [HTTPX2 advisory](https://github.com/advisories/GHSA-8xx6-hgc6-gc2m),
[CairoSVG advisory](https://github.com/Kozea/CairoSVG/security/advisories/GHSA-f38f-5xpm-9r7c),
[fonttools advisory](https://github.com/fonttools/fonttools/security/advisories/GHSA-768j-98cg-p3fv)
and [urllib3 advisory](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw).

**High dependency risk, unresolved:** npm reports nine affected packages in the
WhatsApp dependency tree, propagated from `basic-ftp` and `extract-zip` advisories.
`basic-ftp` has a [directory-listing denial-of-service advisory](https://github.com/advisories/GHSA-c475-qrg2-pj4r);
`extract-zip` has [symlink archive write advisories](https://github.com/advisories/GHSA-7pqw-9j4j-h8q3).
The production image disables Puppeteer browser downloads, uses system Chromium
and does not feed school import archives to these Node libraries. A remotely
exploitable Absensa path was not demonstrated. npm's suggested fix downgrades
`whatsapp-web.js`; a forced downgrade or incompatible transitive override was not
applied without live compatibility validation. A compatible upstream dependency
update and worker rehearsal remain necessary.

## Verification

Tests ran against a newly created PostgreSQL 18.4 container on a distinct audit
port, with tmpfs storage, explicit test-reset authorization and an unused
application database name. User databases and containers were left alone. Network
delivery used mocked clients/transports only.

| Check | Before | Final result |
| --- | --- | --- |
| Python suite | 514 passed, 46 failed | 608 passed, zero failures/skips, 117.21 seconds |
| New regression reproductions | First seventeen cases failed before fixes | Covered by the final suite; 48 Python regression cases added overall |
| WhatsApp worker | 10 passed | 13 passed; three new mocked regressions |
| Deployment unit tests | 6 passed | 6 passed |
| Repository Ruff lint | 58 diagnostics | Pass |
| Repository Ruff formatting | Existing formatting failures | Pass |
| Supplemental Mypy, ordinary configuration | 55 errors in 16 files | 9 errors in 3 files; eight are Pydantic constructor inference |
| Supplemental Mypy with Pydantic plugin | Not used for baseline | One remaining schema inheritance diagnostic in 69 application files |
| Python advisory scan | 12 findings across 5 packages | Zero known findings in updated declared pins and all 84 packages in the temporary test environment |
| npm advisory scan | 9 high affected packages | Unchanged; unresolved as described above |
| Temporary runtime requirements | Original pins | Patched packages installed; `pip check` passes |
| Migration consistency/data preservation | — | Existing synthetic student/contact/scan preserved; Alembic detects no pending ORM/schema changes; narrowing rollback refuses to truncate twenty-character snapshots and leaves the schema intact |
| Whitespace validation | — | `git diff --check` passes |

Pylance diagnostics were not exposed through a callable editor interface, and
Pyright was not already installed/configured. Pylance was not treated as a CLI.
Installed Mypy was used as supplemental analysis with and without its Pydantic
plugin. `StudentImportRow.class_id` intentionally accepts temporary strings such
as `N1`, widening its parent write schema's integer type. That existing static
inheritance inconsistency remains **Low**, although runtime imports are tested.
A shared generic schema or independent import schema needs a separately reviewed
typing change; no diagnostic suppression was added.

Final suite output is available in `/tmp/absensa-audit-final-tests.txt`; baseline
output is in `/tmp/absensa-audit-baseline-tests.txt`. Supplementary tool outputs
use the `/tmp/absensa-audit-*` prefix. Ruff's installer target version preserves
parseability on older hosts so the existing Python 3.10 runtime requirement can
be reported; it does not disable the version check.

The patched runtime was isolated under `/tmp`; the user's existing Python
environment was not upgraded. Native Cairo/libarchive rendering, workbook/archive
workflows and browser tests ran as part of the suite. A fresh production image
build, target-host/container scanning and actual WhatsApp pairing/delivery were
not performed. Advisory scans describe known findings on the audit date, not a
guarantee that dependencies have no vulnerabilities.

## Deployment and remaining decisions

1. Install the updated requirements or rebuild images, back up database/photos,
   and apply `web/alembic/versions/e61c89a1d702_harden_login_and_scan_storage.py`
   before starting this version. Upgrade preserves records; ordinary index
   creation can block writes, so schedule it while attendance is idle. Downgrade
   refuses to truncate class snapshots longer than ten characters. Test rollback
   procedures on a copy; no production migration was run during the audit.
2. **High deployment risk:** the default distribution exposes LAN HTTP with
   non-Secure cookies. Configure HTTPS and `COOKIE_SECURE=true` for real student
   information, preserve the public Host, and explicitly trust forwarded headers
   only from the TLS proxy. The image currently uses `--no-proxy-headers`.
   Verify login/CSRF through that proxy. Password throttling uses the ASGI client
   address, so an unconfigured proxy can group every school browser into one
   source budget. Configure TLS according to the
   [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
3. **Medium deployment risk:** the bridge has `SYS_ADMIN` for Chromium's sandbox.
   That is a broad capability even with its non-root user. Validate a narrower
   working sandbox configuration on the target host before removing it; do not
   replace it with disabled sandboxing merely to silence the concern. Keep bridge
   endpoints private and auth/session files restricted.
4. Rehearse backup and restore, service restarts, database interruption, paired
   worker reconnect and graceful shutdown on the school's actual host. Confirm
   scheduler supervision, exactly one intended scheduler, log access controls,
   clock synchronization and working disk/volume persistence. Live worker checks
   should use an explicitly approved staff test number, never guardians.
5. Delivery claims preserve the existing at-most-once attempt policy: uncertain
   sends are skipped on retry and require staff review. A process crash between
   claiming and sending can leave a message unsent. Student attendance/contact can
   also change in the short interval between the last database check and external
   sending. Removing those limits would require a delivery protocol/business
   decision; these fixes do not claim exactly-once WhatsApp delivery.
6. No holiday/weekend calendar, teacher-to-class restriction, lateness threshold
   or separate finalized absence state was invented. Confirm those operational
   expectations before rollout. Review historical duplicate scans separately;
   this patch prevents new duplicates through the application scan path and does
   not delete or rewrite old records. Changing the school timezone also needs an
   explicit decision about historical attendance interpretation.

Developer test commands and the destructive-test opt-in are documented in
[RUNNING.md](RUNNING.md) and [README.md](README.md).
