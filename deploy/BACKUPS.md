# Automated backups and offline recovery

For the release installer, use the Indonesian [backup and recovery guide](README.md#7-cadangan).
The commands below describe the legacy source deployment and application-only
`.absbackup` format. Release installations additionally support encrypted full
`.absfull` snapshots with WhatsApp, Caddy and deployment configuration.

Absensa's dedicated `backup` service polls a durable PostgreSQL job queue every
10 seconds. HTTP requests only enqueue work. PostgreSQL advisory locks and a
unique active-job index serialize manual and scheduled work across processes.
Keep one worker enabled. Backups run locally and require no internet connection.
See the [backup audit](BACKUP-AUDIT.md) for findings, fixes and validation limits.

## Recovery targets and responsibilities

With healthy backups at 10:00 and 17:00, a server failure can lose up to **17 hours**
of changes (the overnight gap), plus backup execution time. This is a snapshot
strategy without point-in-time/WAL recovery. Disk loss recovery depends on the
date of the latest external copy.

Assign a staff owner to check the latest successful backup each school day and
copy it to disconnected media after the last daily run. Rotate two external disks
and keep one in a separate secure location. A weekly copy permits up to a week
of data loss after disk failure; daily copies reduce that window. Keep the key,
private deployment configuration and matching release in a separate protected
recovery record. Archive encryption does not protect plaintext secrets stored
beside it.

The technical administrator should authenticate each external copy, rehearse
recovery before version changes and at least quarterly, and record archive ID,
backup date, recovered counts/photos, elapsed recovery time and result. There is
no guaranteed recovery time until the school has measured this drill.

## Deployment

Build and start using `compose.production.yml` alone. The `runtime` image is for
web/notifications; the `backup` target adds PostgreSQL **18** `pg_dump` and
`pg_restore`, copied from the matching Debian PostgreSQL image. Do not assume a
host or web-container PostgreSQL client is available. Apply Alembic migrations
before starting the worker. Guided configuration now generates an encryption key.

For an existing installation, add `BACKUP_ENCRYPTION_KEY` to the private
`deploy/production.env`. Generate a base64-encoded random 32-byte key once:

```bash
python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Save this value in a secure offline recovery record, separately from the backup
disk. **Losing the key makes archives unrecoverable.** Do not change it without
retaining the old key for existing archives. Never commit environment files.
Empty/invalid keys reject manual jobs and prevent scheduled creation; they do
not affect attendance. Protect the environment file with mode 0600 or equivalent
Windows permissions.

| Variable | Default / purpose |
| --- | --- |
| `BACKUPS_DIR` | `backups` locally; `/app/backups` in Compose |
| `BACKUP_ENCRYPTION_KEY` | Required base64 32-byte AES key |
| `TIMEZONE` | School timezone, default `Asia/Jakarta` |
| `BACKUP_TIMES` | `10:00,17:00`, one/two daily HH:MM times |
| `BACKUP_KEEP_DAILY` | Newest archive from each of 14 distinct school-local dates |
| `BACKUP_KEEP_WEEKLY` | 8 distinct ISO weeks |
| `BACKUP_KEEP_MONTHLY` | 3 distinct calendar months |
| `BACKUP_TIMEOUT_SECONDS` | 3600, maximum `pg_dump` execution time |

Environment schedule/retention values seed the singleton settings on first use.
Afterward the saved school settings are authoritative. All archives stay on school-controlled storage.

Compose persists archives in `absensa_backups`, independent of `absensa_pgdata`.
The worker mounts the archive volume read/write, the web mounts it read-only, and
photos are read-only in the worker. Directories are 0700 and archives are 0600,
owned by application UID/GID 10001. For a bind mount, create an empty directory
outside the source repository, restrict host access, and assign UID/GID 10001
before mounting it at `/app/backups` in **both** services. The host disk should be
encrypted; private temporary database dumps can remain after a power failure
until the next worker tick cleans them. Size storage for retained recovery points
plus one database dump and one new encrypted archive. A named volume on the same
physical disk protects against container replacement, not disk loss; copy encrypted
archives to a USB drive or external disk and disconnect it after copying.

## Archive contents, scheduling and retention

Each job has a UUID and UTC creation timestamp in PostgreSQL and in its encrypted
manifest. AES-256-GCM authenticates a versioned header and tar contents. Decrypted
tars contain `database.dump` (`pg_dump -Fc`), `photos/` (including student photos and
card logos), and `manifest.json`. Pending import photos already live in PostgreSQL.
WhatsApp linked-device credentials and deployment secrets are excluded; relink
WhatsApp on recovery.

The worker exports a consistent database snapshot and passes it to `pg_dump`.
SHARE locks on `students` and `student_card_settings` block photo-related writes
while dumping/copying, to align associated files with the snapshot. Reads and
attendance scans can continue. Large databases can delay student/card edits;
choose appropriate backup times. A missing photo volume, symlink, or missing
referenced student photo/logo fails creation. The manifest also records the schema
revision and PostgreSQL version.
The worker must read all tables and own these application tables (the existing
application database role satisfies this). Temporary work directories are private;
only complete, fsynced encrypted archives are atomically published. The worker
reads back and authenticates the entire archive before recording success. Failed or
interrupted creations never become downloadable successes.

Times use the school timezone. On restart, the latest due slot **today** is caught
up; older days and earlier missed slots are not replayed. A unique slot prevents
retry storms even if that attempt failed. A manual job can retry a failure at any
time. A stopped worker leaves jobs queued until it restarts. A restart recovers a
fully published, authenticated archive if the worker crashed before saving its
success record; other abandoned jobs are marked failed.

Retention runs only after a new local success. It keeps the **union** of the newest
archive in each of 14 distinct school-local dates, the newest archive in each of
8 distinct weeks, and the newest archive in each of 3 distinct months. These are
independent sets, not three copies of every
archive; gaps in school operation do not invent recovery points. Weekly/monthly
points survive daily rotation. Only existing local successes that authenticate
with the configured key count toward rotation, and the newest usable copy is
always kept. Failures never initiate deletion.
Expired records remain in the audit inventory. A failed deletion keeps the file
and reports an error for the next successful rotation. Unavailable, corrupt or
old-key archives are preserved, flagged and excluded from recovery/download choices;
they cannot displace healthy archives. Checks run again on the next successful
rotation. Old-key archives need their original key; a technician can copy those
files directly from storage for recovery. Integrity checks read retained files
and can take time on slow disks. Physical copies downloaded to another device are
independent of automatic rotation. Staff must check that the
copy finished, safely eject the drive, and store it away from the server.

There is no database restoration endpoint. Recovery remains an offline maintenance
procedure performed by the school's technical administrator. Read the short
[Indonesian staff guide](PANDUAN-CADANGAN.md) for routine physical copies.

## Manual recovery (isolated deployment first)

Rehearse recovery on an isolated host with the same source/application version,
PostgreSQL major version, saved deployment settings and encryption key. Do not
restore into a live database. In commands below, replace `...` with
`--env-file deploy/production.env -f compose.production.yml`.

1. Start **only** the fresh database: `docker compose ... up -d db`. Do not run
   migrations into the empty destination before restoring an archive that already
   contains the schema. Keep web, scheduler and backup stopped throughout recovery.
2. Put the downloaded encrypted archive in a protected recovery directory and
   decrypt with the backup image and saved key. For example, create a private host
   folder writable by UID/GID 10001 and bind-mount it:

   ```bash
   docker compose ... run --rm --no-deps -v /absolute/recovery:/recovery backup python -m app.jobs.decrypt_backup /recovery/archive.absbackup /recovery/archive.tar
   ```

   The helper authenticates the entire file before publishing plaintext and refuses
   to overwrite an existing destination. A wrong key/corrupt archive produces no
   usable plaintext. Preserve the original encrypted archive.
3. Extract the authenticated tar into the private recovery directory. On Python
   3.12+ use the safe extraction filter:

   ```bash
   python3 -c 'import tarfile; t=tarfile.open("/absolute/recovery/archive.tar"); t.extractall("/absolute/recovery/extracted", filter="data")'
   ```

4. Copy `database.dump` into the database container, then restore into its empty
   database using the PostgreSQL 18 client:

   ```text
   docker compose ... cp /absolute/recovery/extracted/database.dump db:/tmp/database.dump
   docker compose ... exec -T db pg_restore -U absensa -d absensa --no-owner --no-privileges --single-transaction --exit-on-error /tmp/database.dump
   ```

   Check the exit code. Do not continue after a partial restore; recreate an empty
   isolated destination and repeat. Restoring uses the destination's database role.
5. Restore `photos/` into the fresh `photos` volume, including logos. Use a one-off
   maintenance container with that volume mounted at `/app/photos`; copy the
   directory contents and set ownership to UID/GID 10001. For a fresh volume:

   ```text
   docker compose ... run --rm --no-deps --user root -v /absolute/recovery/extracted:/recovery:ro web sh -c 'cp -a /recovery/photos/. /app/photos/ && chown -R 10001:10001 /app/photos'
   ```

   If the archive contains no photos, leave the fresh empty volume intact. Do not
   mix an old populated volume with the restored database.
6. Review restored admin/device/operator sessions. When recovery follows a
   compromise, invalidate them offline before starting the app:

   ```text
   docker compose ... exec -T db psql -U absensa -d absensa -c 'DELETE FROM admin_sessions; DELETE FROM operator_sessions; DELETE FROM trusted_devices;'
   ```

7. Start the matching application and migration services. Verify health, admin
   login, student counts, attendance history and sample photos/logos. Relink
   WhatsApp. The backup worker will mark the captured in-progress backup record
   interrupted; retained archives may not be present in the new archive volume.
   Trigger and verify a fresh backup before returning the recovered site to use.
8. Remove the temporary database dump and plaintext recovery files securely
   according to the host's disk-encryption policy. Keep the original encrypted
   recovery point and key in their protected locations.

## Checks

In commands below, replace `...` with
`--env-file deploy/production.env -f compose.production.yml`.
Authenticate a downloaded/external copy without producing plaintext. Mount the
copy read-only; the directory must be readable by UID/GID 10001:

```text
docker compose ... run --rm --no-deps -v /absolute/external-copy:/recovery:ro backup python -m app.jobs.verify_backup /recovery/archive.absbackup
```

A nonzero exit means the archive/key cannot be verified. Successful authentication
proves file integrity; a database/photo restore drill proves recovery works.

Before maintenance, stop web, scheduler and backup, then run a fresh manual backup
even when automatic backups are disabled or today's slots have already run:

```text
docker compose ... stop web scheduler backup
docker compose ... run --rm --no-deps backup python -m app.jobs.backups --once --manual
```

Require exit code zero and the `Backup completed: <id>` log. A busy/failed worker or
configuration failure exits nonzero. Preserve `<id>.absbackup` from the archive
volume on external media and authenticate it before upgrading. Do not copy the
database volume itself while PostgreSQL is running.

For a named archive volume, create a private external directory writable by
UID/GID 10001, replace `<id>` with the completed ID and copy through the worker
mount (use a new filename):

```text
docker compose ... run --rm --no-deps -v /absolute/external-copy:/external backup python -c "import os,shutil; os.umask(0o077); shutil.copyfile('/app/backups/<id>.absbackup', '/external/<id>.absbackup')"
```

Then run the authentication command above against the external `<id>.absbackup`.
When only taking a backup, resume with `docker compose ... start web scheduler backup`.

Ordinary service tests mock `pg_dump` and run against a disposable PostgreSQL
instance using the existing fixtures. They exercise encryption/tampering, snapshot
arguments, archives/files, schedules, queue locks, retention, failures and protected
downloads. The opt-in `ABSENSA_TEST_REAL_BACKUP=1` test also runs real
`pg_dump`/`pg_restore`, decrypts and extracts an archive, restores it to a temporary
database, and checks schema revision, student/attendance data and photo/logo bytes.
It requires PostgreSQL 18 clients and database-creation privileges on the disposable
test server. Use the normal separate `TEST_DATABASE_URL` and
`ABSENSA_ALLOW_TEST_DATABASE_RESET=1`; never point the suite at school data.
An operational recovery drill is still required for each site's actual disks. See PostgreSQL's
[pg_dump documentation](https://www.postgresql.org/docs/18/app-pgdump.html),
[cryptography's GCM guidance](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/).

## Administrator interface

Open **Cadangan** in the admin navigation at `/admin/backups`. Only an authenticated,
active administrator can use its pages, settings/actions and downloads. All mutations
use Absensa's existing same-origin CSRF middleware.

The page shows the latest attempt, newest usable recovery point, automatic schedule
and paginated history. Dates use the school timezone and sizes use binary units.
Select **Buat cadangan**, confirm **Mulai cadangan**, and follow the execution status.
Closing the browser does not stop a job. HTMX polls every five seconds during work
and every thirty seconds while idle, without replacing unsaved schedule fields.
A stopped worker is reported; queued work resumes when the service starts.

Settings enable/disable automatic backups, choose one/two daily times, and set
separate daily/weekly/monthly counts. They apply to future work and the next
successful retention pass. Failed attempts never trigger deletion.

**Unduh** serves complete encrypted archives. Copy the downloaded file onto a USB
drive or external disk, check the copy finished, eject the device and store it safely.
The interface explains these steps in Indonesian and never displays the encryption
key. Missing/expired archives and those with a recorded integrity failure cannot
be downloaded. The page warns when the available recovery point is over 24 hours
old. Errors provide suggested checks without exposing raw database exceptions.
Restoration remains offline.
