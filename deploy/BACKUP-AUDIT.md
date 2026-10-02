# Backup strategy audit — 2026-10-02

Scope: production Compose volumes/images, worker scheduling and queue ownership,
database/photo consistency, encryption, retention, administrator downloads,
maintenance instructions and offline recovery. Checks used synthetic data on a
separate disposable PostgreSQL 18 server. School data and deployment secrets were
not used or changed.

## Findings and fixes

| Severity | Finding | Fix |
| --- | --- | --- |
| High | A successful job could omit a photo/logo referenced by its database snapshot if the file was already missing, or disappeared before directory enumeration. | Read the reference inventory while the photo-related tables are locked, reject missing/unsafe paths, and require every reference to appear in the tar. Reject a non-custom-format database dump. |
| High | Existing files counted as recovery points without authentication. A corrupt recent file could displace a healthy older one during rotation. | Authenticate the entire new archive before success, and every successful local archive before retention. Persist integrity failures, preserve suspect files, and exclude them from retention quotas and recovery/download choices. |
| Medium | “14 daily” counted 14 jobs, providing about seven days at two runs per day. | Keep the newest authenticated archive per distinct school-local date, in union with independent weekly/monthly representatives. Multiple same-day manual jobs no longer consume the daily history. |
| Medium | A crash after atomic file publication but before the success transaction hid a complete recovery point as failed. | Under the worker advisory lock, authenticate the published file and recover the inventory record as successful. Missing/incomplete files still fail. |
| Medium | One-shot worker failures exited zero, and maintenance required ad hoc plaintext database/photo copies. | Add `--once --manual` to run regardless of schedule. Busy, failed and configuration-error runs exit nonzero. Document encrypted maintenance copies and an authentication CLI with no plaintext output. |
| Medium | A running worker with repeated backup failures could leave an old recovery point without a freshness warning. | Show a warning for a recovery point older than 24 hours; show persistent integrity errors in the inventory/API. |
| Operational | The procedure did not define the loss window, physical-copy frequency or recurring recovery rehearsal. | Document the default 17-hour overnight snapshot gap, daily disconnected copies, separate key/configuration storage and quarterly/pre-upgrade drills. |

## Verified protections

- Manual/automatic work is durable in PostgreSQL; advisory locks and an active-job
  unique index prevent concurrent creation. Scheduled slots are deduplicated.
- `pg_dump -Fc` uses the exported snapshot, with photo-related table locks held
  through copying. A backup does not require an internet connection.
- AES-256-GCM authenticates both the versioned header and encrypted payload.
  Decryption publishes plaintext only after authentication and refuses overwrite.
- Temporary work is private and cleaned under the worker lock after interruption.
  Complete archive publication uses file and directory fsync plus atomic rename.
- Admin access and same-origin CSRF protect actions; the web archive mount is
  read-only. WhatsApp credentials and deployment secrets stay outside archives.
- Failed creations do not rotate healthy copies; retention deletion errors keep
  the file and are retried after later successful work.

## Validation

Final result: **665 tests passed**, including Chromium tests and the opted-in real
restore drill, in 150.53 seconds. PostgreSQL server 18.4 and client tools 18.6 were
used. Ruff lint/format checks on changed Python files and `git diff --check` passed.

Regression coverage includes encrypted round trips/tampering, damaged archives
versus healthy retention, date-based retention across timezone boundaries, missing
student photos/logos, crash recovery, manual maintenance jobs and nonzero CLI
failure status. Admin/API and Chromium tests cover protected downloads, persistent
integrity errors, freshness warnings and the existing queue/settings workflows.

The opt-in real recovery test uses PostgreSQL 18 `pg_dump` and `pg_restore`: create
an encrypted database/photo archive, authenticate and decrypt it, extract using
the safe data filter, restore into a new empty database in one transaction, and
compare schema revision, student/attendance records and photo/logo bytes. This
test is committed in `web/tests/test_backups.py` and requires
`ABSENSA_TEST_REAL_BACKUP=1` plus the existing disposable-test-database opt-in.
Schema creation and rollback exercise the new integrity-error migration.

PostgreSQL's [snapshot export documentation](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION),
[table lock documentation](https://www.postgresql.org/docs/18/explicit-locking.html)
and [pg_dump documentation](https://www.postgresql.org/docs/18/app-pgdump.html)
were checked against the implementation.

## Deployment and remaining limits

Rebuild the web/backup images and apply Alembic revision `a20f46bd729c` before
starting the updated web and worker. Existing encrypted archives remain compatible;
saved schedule/retention values remain in force, with daily counts now interpreted
as distinct dates. Existing archives are authenticated on the next successful
retention pass, or immediately with the new `app.jobs.verify_backup` command.

The default archive volume shares the host's failure domain with the database.
Disconnected copies are still a staff task; code cannot establish that a physical
disk was copied, disconnected or stored elsewhere. Keep deployment settings/key
and matching source separately. Loss of the key remains unrecoverable. Changing
the key requires keeping original keys; old-key files are preserved and need a
technician to copy/recover them from storage.

This is snapshot recovery without WAL/PITR or a guaranteed recovery time. Full
authentication reads retained archives and adds I/O. Suspect files are deliberately
preserved and can consume storage until investigated. Large dumps hold photo-table
locks and can delay edits. Rehearse on the school's actual disks, verify admin
login/counts/photo rendering, relink WhatsApp, and measure recovery time before
depending on this strategy. Follow [BACKUPS.md](BACKUPS.md) and the
[staff guide](PANDUAN-CADANGAN.md).
