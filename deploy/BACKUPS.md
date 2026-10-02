# Automated backups and offline recovery

Absensa's dedicated `backup` service polls a durable PostgreSQL job queue every
10 seconds. HTTP requests only enqueue work. PostgreSQL advisory locks and a
unique active-job index serialize manual and scheduled work across processes.
Keep one worker enabled. Backups run locally and require no internet connection.

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
| `BACKUP_KEEP_DAILY` | 14 newest successful archives |
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
choose appropriate backup times. A missing photo volume or symlink fails creation.
The worker must read all tables and own these application tables (the existing
application database role satisfies this). Temporary work directories are private;
only complete, fsynced encrypted archives are atomically published. Failed or
interrupted creations never become downloadable successes.

Times use the school timezone. On restart, the latest due slot **today** is caught
up; older days and earlier missed slots are not replayed. A unique slot prevents
retry storms even if that attempt failed. A manual job can retry a failure at any
time. A stopped worker leaves jobs queued until it restarts. A restart marks
abandoned jobs failed, preserving already completed local copies.

Retention runs only after a new local success. It keeps the **union** of the newest
14 archives, the newest archive in each of 8 distinct weeks, and the newest archive
in each of 3 distinct months. These are independent sets, not three copies of every
archive; gaps in school operation do not invent recovery points. Weekly/monthly
points survive daily rotation. Only existing local successes count toward rotation,
and the newest usable copy is always kept. Failures never initiate deletion.
Expired records remain in the audit inventory. A failed deletion keeps the file
and reports an error for the next successful rotation. Physical copies downloaded
to another device are independent of automatic rotation. Staff must check that the
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
   docker compose ... exec -T db pg_restore -U absensa -d absensa --no-owner --no-privileges --exit-on-error /tmp/database.dump
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

Ordinary service tests mock `pg_dump` and run against a disposable PostgreSQL
instance using the existing fixtures. They exercise encryption/tampering, snapshot
arguments, archives/files, schedules, queue locks, retention, failures and protected
downloads. An operational recovery drill with a real `pg_dump`/`pg_restore` is still
required for each site's actual disks. See PostgreSQL's
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
key. Missing/expired archives cannot be downloaded. Errors provide suggested checks
without exposing raw database exceptions. Restoration remains offline.
