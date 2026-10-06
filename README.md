# Absensa - School Attendance System

Version 1.0.0 is being prepared for its first stable release.

Untuk pemasangan di sekolah, baca [panduan instalasi lengkap berbahasa Indonesia](deploy/README.md).
Installer menyediakan rilis terverifikasi, HTTPS, cadangan, pemulihan, pembaruan,
dan perintah pemeliharaan. Mendukung deployment Linux amd64 dan menyediakan backend native Windows Server
2019/2022/2025 amd64. Lihat batas validasi Windows sebelum dipakai di sekolah.

Cara yang disarankan adalah mengunduh dan membaca installer terlebih dahulu:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh -o install.sh
less install.sh
bash install.sh
```

Cara cepat: `curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh | bash`.
### Windows Server

Buka **PowerShell sebagai Administrator** dan jalankan:

```powershell
irm https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1 | iex
```

Bootstrap memasang paket rilis stabil terverifikasi, runtime dan layanan Windows
native. Binary berada di `C:\Program Files\Absensa`, data di
`C:\ProgramData\Absensa`. Lihat [panduan Windows](deploy/windows/README.md)
dan [status pengujian](deploy/windows/VALIDATION.md). Perintah ini memerlukan
rilis Windows yang sudah diterbitkan; branch ini belum menerbitkan rilis.
**Maintainer note:** The installer requires a published stable release and public
image access. See the [release checklist](deploy/RELEASING.md) and
[validation results](deploy/INSTALLER-VALIDATION.md) before using these commands
for a school installation. Preparing v1.0.0 does not publish the release.

For local development, see [Run Absensa locally](RUNNING.md).

Contributions are welcomed! Please check out the to-do list below for current priorities.

## Student profile photos

After installing `web/requirements.txt`, run `.venv/bin/alembic upgrade head`
from `web/` to add the nullable `students.photo_path` column.

The student edit dialog uploads multipart field `photo` to
`POST /admin/students/{student_id}/photo`. Both this endpoint and
`GET /admin/students/{student_id}/photo` require an active admin session.
The upload returns `student_id`, `photo_path`, and `photo_url`.

JPEG, PNG, and WebP images are accepted up to 5 MiB and 20 megapixels. Images
are resized to fit 1024 × 1024, stripped of metadata, and saved as JPEG with
generated filenames under `PHOTOS_DIR` (default: `photos`, relative to the
web working directory). Keep this directory persistent and back it up
alongside the database. Replacing a photo removes the previous file after
the database update succeeds. Existing students keep their initials until
a photo is uploaded.

## Student cards

Open **Kartu Siswa** (`/admin/cards`) to preview, print, or download cards. The page
shares the student dashboard's search, class filters, pagination, and selection.
Choose the current page, selected rows, or every student (including inactive
students). Processing every student ignores filters and requires confirmation.
One card downloads as PNG; multiple cards download as a ZIP with NISN/name filenames.

All cards use a fixed landscape size of **85.6 × 53.98 mm**, matching Indonesian
KTP dimensions, with **3:4** center-cropped photos. The school header sits above
the photo and student details; names and NISNs appear beside the photo, with a
Code 128 barcode below and a **Kartu Presensi Absensa** label at the top right.

**Pengaturan cetak** saves only the cutting gap, school name, and uploaded logo.
The gap defaults to **3 mm** and accepts **0–200 mm**. Its slider and keyboard
input stay synchronized. Both school name and logo are required to display the
watermark; leave both empty to disable it. Logos use the same validated storage
and upload limits as student photos. Back up `PHOTOS_DIR` with the database.

The wider settings dialog shows a live card preview on the left using the bundled
placeholder photo. School name and logo changes appear before saving. On smaller
screens, the preview appears above the settings. Card dimensions and photo ratio
are fixed throughout preview, printing, and PNG/ZIP export. The migration removes
the retired size and ratio columns while preserving the saved gap and watermark.

Install the updated `web/requirements.txt` and run `.venv/bin/alembic upgrade head`
from `web/`. PNG export requires the native Cairo library (`libcairo2` on
Debian/Ubuntu, `cairo` on Arch); the Docker image includes it. The migration adds
the singleton `student_card_settings` table; subsequent migrations keep it in sync with the current settings.

The shared renderer in `app/services/student_card_service.py` produces a
self-contained SVG with bundled Inter outlines and local Code 128 barcodes.
Preview, browser printing, and PNG exports use this same design. PNGs have at least
300 DPI and physical-size metadata for 85.6 × 53.98 mm (rounded to whole pixels). Missing photos use `static/images/no-photo.png`.
Single-card services do not require admin context; future student routes must
authorize ownership before calling them. Existing card routes are admin-only.

Printing opens the browser's native dialog after images load. Use actual size / 100%
scale and paper large enough for the 85.6 × 53.98 mm card dimensions plus 10 mm page
margins. The document flows whole cards across pages and contains only cards.
Exports render one PNG at a time into an anonymous temporary ZIP; response completion,
disconnects, and generation failures close temporary files. Each application worker
allows two simultaneous bulk generations and asks further callers to retry.

## Spreadsheet imports

Open **Impor** in the admin navigation (`/admin/import`). Download the combined Students & Classes template, or edit a student export.
Both contain `instructions`, `students`, and `classes`. All classes are included,
even when student exports are filtered.
Upload one `.xlsx` file (up to 10 MiB) or one archive (up to 100 MiB).
ZIP, RAR, 7z, TAR, TAR.GZ/TGZ, TAR.BZ2/TBZ2, and TAR.XZ/TXZ are supported.
Each workbook is detected automatically from its sheet name and columns.
Archives can contain combined workbooks, with up to 100 workbooks and
10,000 data rows in total. The combined expanded archive and workbook contents
are bounded to 200 MiB each. Encrypted archives and links are rejected.

Archive layout (one enclosing folder is also accepted):

```text
students-and-classes-2026.xlsx
photos/                 # optional
  0012345678.jpg
  0012345679.png
```

Place every workbook at the root. Optional JPEG/PNG/WebP photos use a ten-digit
NISN as the filename and match student rows in the uploaded workbooks. Missing
photos are normal and never block importing; existing photos are retained.
Files with invalid names, unmatched NISNs, duplicate NISNs, or invalid image
contents produce explicit errors. Photos are validated during preview and
applied together with the entire valid import. Photo limits match the profile upload
service (5 MiB and 20 megapixels per image; 50 MiB of normalized photos total).

Keep sheet names, column names, student IDs and existing class IDs unchanged.
In `students`, enter `ID KELAS` manually (there is no dropdown). Excel validation
checks that it exists in `classes`. `JENJANG` and `NAMA KELAS` are protected,
visually subdued VLOOKUP formula columns: change class descriptions in `classes`
and the student cells recalculate automatically. Import resolves IDs directly and
never depends on formula caches or accepts independent student class descriptions.
New students require a class ID; existing students may clear it to become unassigned.

The generator reserves 100 new-class rows with literal, protected IDs `N1` through
`N100`. These are allocated before editing, not by a row-number formula: moving,
inserting, deleting or editing other rows never renumbers them. Fill both class
fields to use a reserved ID; unused slots are ignored. An incomplete/unknown ID
cannot be assigned to a student. Macro-free XLSX cannot safely assign persistent
IDs on edit, so Absensa finalizes them to numeric database IDs during import.
Temporary IDs are scoped to their workbook, including when importing archives.
For additional classes, import and download a fresh workbook with more reserved
slots. Blank-ID class rows are also finalized during import but cannot be referenced
by students until exported again with their database IDs.

Create classes only in `classes`. Class names and jenjang may change without changing
the ID, and students retain the same class relationship. New class rows with the same
jenjang and name automatically reuse one class, including across workbooks or when
the class already exists. Temporary IDs remain local to each workbook and resolve to
that shared database class. Repeated existing class IDs across workbooks are accepted
when their class values agree. Conflicting class edits, duplicate IDs within a
workbook, and undeclared student references reject the entire upload. Removing class rows never
deletes database records; use the Classes dashboard for explicit deletion. NISN and
guardian phone numbers should be text to retain leading zeros.

Uploads produce previews with create/update tables, highlighted changes, source
filenames, staged photos, editable drafts, and errors formatted as
`sheet > row:column > message` in Indonesian. Only real changes appear as edits;
unchanged students/classes and shared class declarations are skipped automatically.
Student comparisons use the resolved database class ID, and identical normalized
photos preserve the existing file. Imports are all-or-nothing: any error
rejects the entire upload, including valid rows and class changes. Confirmation
applies all rows in one transaction. Runtime failures roll back every database
change, remove new photo files and retain original photos. Canceling changes no
student/class data. Previews expire after one hour, belong to their uploading admin,
detect stale edits, and cannot be applied twice. Expired, cancelled and completed
previews discard staged photos. Standalone class XLSX downloads are retired;
the Classes dashboard still supports normal CRUD.

Install `web/requirements.txt` and run `.venv/bin/alembic upgrade head`
from `web/` before using this page; the migrations add `import_batches` and
`import_photos`. Archive support uses `libarchive-c` and requires the native
libarchive shared library (for example, `libarchive13` on Debian/Ubuntu or
`libarchive` on Arch; a recent build with RAR/7z support is recommended).

## Trusted devices and operators

Apply the database migration from `web/` with
`.venv/bin/alembic upgrade head`. Migration `0fbaf2d5ad9a` adds
`trusted_devices`, `operators`, and `operator_sessions`; existing school data is
unchanged. The existing `scripts/create_admin.py` bootstrap command still creates
administrators. Sign in at `/admin`, then open **Akses & Perangkat** (`/admin/access`)
to create, edit, deactivate, delete, or reset accounts. Device usernames are
case-insensitive. Operator names may repeat: sign-in uses the database ID, shown
alongside the display name. Password and PIN fields are never prefilled.

The browser signs in at `/trusteddevice/login`, then `/operator/login`, and arrives
at `/operator` to scan or enter a student's NISN. The public `/` landing page
does not redirect to login. The scanner shows the latest 30 school-wide attendance
records in the configured timezone, with a cursor-based link to load older records.
Each successful scan refreshes the history. **Log Presensi** in the admin navigation
is a disabled placeholder; no separate log page has been added. Authentication is checked through
`get_current_trusted_device`, `require_trusted_device`, `get_current_operator`, and
`require_operator`. Both layers must be valid for every operator-protected request.
Login pages redirect already-authenticated users; only the local `/operator`
destination (with an optional query) is accepted for return navigation.

Device passwords and six-digit operator PINs use the existing Argon2 implementation.
A device has one active binding, enforced under a PostgreSQL row lock. Only a SHA-256
digest of its random 256-bit token is stored. A bound account cannot sign in from
another browser, even if its original browser cookie was deleted. An administrator
must use **Reset koneksi** to invalidate the binding and its operator session before
rebinding. Disabling/deleting the device or replacing its password also revokes it.
Changing an operator PIN, disabling, or deleting that operator ends their sessions
on every device. Renaming an account does not end its sessions.

The separate `absensa_trusted_device` cookie is persistent and the binding has no
server-side expiry. Browsers cap cookie lifetimes; its 400-day Max-Age is refreshed
on authenticated device/operator requests. Cookie loss/expiry never frees the
server-side binding. `absensa_operator` has no Max-Age or Expires, so it is a normal
browser-session cookie (browser session restoration may preserve it). Neither
credential nor authentication state is stored in local/session storage. Both cookies
are HttpOnly, SameSite=Lax, and scoped to `/`. Set **ACCESS_COOKIE_SECURE=true** and
**ADMIN_COOKIE_SECURE=true** for HTTPS production; leave them false only for local
HTTP development.

Five consecutive incorrect PIN attempts lock the device's operator sign-in for
five minutes, using server-side UTC timestamps and serialized PostgreSQL updates.
Switching operators, reloading, or logging out/rebinding the device cannot bypass
this limit. A successful PIN login resets failures; an expired lock starts a fresh
window. An explicit administrator reset clears the lock too. The login page shows
the server's retry time, and locked responses include Retry-After.

Administrator and trusted-device password logins also reserve shared PostgreSQL
attempt budgets before checking passwords: five attempts per normalized account
and thirty per source address in a five-minute window. Successful attempts count
toward these budgets too; blocked requests return `429` and `Retry-After`. The
window expires without being extended by further attempts. Apply migration
`e61c89a1d702` before starting this version. It also widens attendance class-name
snapshots to twenty characters and adds attendance lookup indexes.

`POST /operator/logout` ends only the operator session. `POST /trusteddevice/logout`
revokes the device binding and its operator session. Tokens are invalidated in the
database, not merely removed from cookies. A stale operator cookie cannot authorize
requests after device revocation or be used with another device binding.

All unsafe HTTP methods now use fail-closed **same-origin CSRF validation**: Origin
must match the request's origin, with a same-origin Referer fallback. Missing/null
origins, foreign origins, and Sec-Fetch-Site: cross-site are rejected before any
mutation, including login, logout, admin reset, and uploads. Normal HTML forms and
HTMX work without adding JavaScript tokens. API clients must provide the matching
Origin header as well as authentication cookies. Behind a proxy, preserve the public
Host and configure trusted proxy headers so FastAPI sees the correct public scheme.
A permissive CORS setting does not bypass this check.

Legacy `/students`, `/classes`, their bulk operations, scan deletion, and individual
scan lookup now require the existing admin session. `/scans` GET/POST require both
device and operator authentication. Admin login now scopes its cookie to `/` for
these APIs and removes the former `/admin`-scoped cookie; existing admins may need
to sign in again for API access. No second administrator system was introduced.

The PIN enhancement uses a single password input with six decorative masked slots;
normal form submission also works without JavaScript. The Figma Starter quota blocked
design inspection and the CodePen could not be fetched, so the UI follows existing
Absensa components and the specified keyboard/paste behavior. The operator attendance
page extends the existing scan service because the original root was a placeholder.

`tests/test_access_auth.py` covers credentials, cookie lifetimes, routing, ownership,
revocation, administration, CSRF, lockout, and concurrent binding/PIN requests using
independent PostgreSQL connections. Existing data-service tests explicitly authenticate
through fixtures; authentication tests exercise the real dependency chain.

## Current To-Do

### Auth & Access

- [x] Operator model (PIN-based, browser-session login)
- [x] TrustedDevice model (admin-managed, password-based persistent binding)
- [x] Device/operator session handling and revocation
- [x] Administrator bootstrap and password authentication
- [x] Public, operator, and admin route protection
- [ ] Public NISN lookup endpoint with rate limiting

### Features

- [x] Bulk student and class endpoints (for spreadsheet feature)
- [x] Make .xlsx templates for importing
- [x] Admin: manage operators (create, edit, deactivate, reset PIN, delete)
- [x] Admin: manage trusted devices (create, edit, deactivate, revoke, delete)

### Infra & Deployment

- [x] Caddy HTTPS for LAN access, local CA, and Cloudflare DNS-01
- [x] Administrator password/PIN reset flow
- [x] Encrypted backups, isolated restoration, and mandatory backups before updates
- [x] Linux release installer, native Windows backend, parallel release builds, and provenance verification
- [ ] Publish the first stable release and field-test Windows and school DNS

### Testing

- [x] Single data factory for each table

<details>

  <summary>Previously Completed Tasks</summary>
  - [x] *~~Add `ON UPDATE CASCADE` to `scan_log.student_nisn`~~*
  - [x] *~~Create `class` table~~*
  - [x] *~~Add POST, PATCH, and DELETE /students endpoint~~*
  - [x] *~~Add GET and DELETE /scan endpoint~~*
  - [x] *~~Fix routes to work with Postgres like they did with CSV~~*
  - [x] *~~Initialize Postgres on Docker~~*
  - [x] *~~Migrate all mock CSV files to Postgres~~*
  - [x] *~~Initialize Alembic for database migrations~~*
</details>

## Run the web app

`web/` is the single FastAPI application. It serves the admin dashboard, the
TrustedDevice and Operator screens, the API, Jinja templates, HTMX, static assets,
and database migrations. Run Python commands from this directory so `.env`,
`alembic.ini`, and the default `photos/` path resolve correctly.

```bash
docker compose up -d
cd web
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.create_admin admin
.venv/bin/uvicorn app.main:app --reload
```

Set `DATABASE_URL` and `TEST_DATABASE_URL` in `web/.env` to match your PostgreSQL
ports and credentials. The default Compose host port is `5433`. Keep the test
database separate from the application database. The saved `photos/` directory
contains profile images and should be backed up with the database.

Run tests from `web/` with `ABSENSA_ALLOW_TEST_DATABASE_RESET=1 .venv/bin/pytest`.
The suite upgrades and then **drops the schema** in `TEST_DATABASE_URL`; use an
empty, disposable test database. It rejects a missing opt-in or a test URL that
targets the application database, including URLs with different credentials.

See [the pre-launch audit](AUDIT.md) for verified fixes and remaining launch work.

## Project layout

```text
web/                             Live FastAPI application (admin + operator)
  app/                           Routes, services, templates, and static assets
    templates/admin/pages/       Administrator pages
    templates/operator/pages/    Device and operator pages
    templates/public/            Public and error pages
  alembic/                       Database migrations
  scripts/                       Admin setup and database utilities
  tests/                         Python tests
services/whatsapp/               Express + whatsapp-web.js bridge
archive/operator-react-prototype/  Earlier standalone scanner prototype
```

The archived React project is not part of the running application. New operator
interface work belongs in `web/app/templates/` and `web/app/static/` beside the
admin interface. The WhatsApp bridge runs separately; see
[`services/whatsapp/README.md`](services/whatsapp/README.md) to configure its
shared token, install dependencies, and connect a school phone from the admin
dashboard.

WhatsApp absence notifications are scheduled by a **separate FastAPI job
process**. After applying migrations and starting the bridge, run
`cd web && .venv/bin/python -m app.jobs.whatsapp_notifications` alongside the
web server. Keep exactly one job process running under your process manager;
it checks the database settings every 30 seconds and uses the configured
`TIMEZONE`. For a single check, add `--once`. The daily run and per-student
delivery claims are persisted in `whatsapp_notification_logs`, so restarting
the job does not repeat claimed deliveries. A claim is recorded before the
external send: a crash in that narrow interval can leave a message unsent,
which favors avoiding duplicate WhatsApp messages.
The job also resumes an interrupted manual batch after its lease expires,
including when the automatic service is disabled; students already claimed
for that day are skipped.

For local notification tests, `web/scripts/seed_many_students.py` leaves
guardian numbers empty unless requested. Run it from `web/` with, for example,
`.venv/bin/python -m scripts.seed_many_students --count 500 --test-number 081234567890 --test-number-amount 5`
to assign that one number to five new students. The dashboard's Test action
uses an entered recipient number and real data from a randomly selected
active student; it does not require a stored guardian number.
Replace the example number with a number you control before sending messages.

Automated encrypted database/photo backups: see [deployment and offline recovery](deploy/BACKUPS.md).
