# Absensa - School Attendance System (Working Name!)

An ongoing project.

Contributions are welcomed! Please check out the to-do list below for current priorities.

## Student profile photos

After installing `backend/requirements.txt`, run `.venv/bin/alembic upgrade head`
from `backend/` to add the nullable `students.photo_path` column.

The student edit dialog uploads multipart field `photo` to
`POST /admin/students/{student_id}/photo`. Both this endpoint and
`GET /admin/students/{student_id}/photo` require an active admin session.
The upload returns `student_id`, `photo_path`, and `photo_url`.

JPEG, PNG, and WebP images are accepted up to 5 MiB and 20 megapixels. Images
are resized to fit 1024 × 1024, stripped of metadata, and saved as JPEG with
generated filenames under `PHOTOS_DIR` (default: `photos`, relative to the
backend working directory). Keep this directory persistent and back it up
alongside the database. Replacing a photo removes the previous file after
the database update succeeds. Existing students keep their initials until
a photo is uploaded.

## Spreadsheet imports

Open **Impor** in the admin navigation (`/admin/import`). Download the student
or class template, or edit an existing export from `app/spreadsheet_templates/`.
Upload one `.xlsx` file (up to 10 MiB) or one archive (up to 100 MiB).
ZIP, RAR, 7z, TAR, TAR.GZ/TGZ, TAR.BZ2/TBZ2, and TAR.XZ/TXZ are supported.
Each workbook is detected automatically from its sheet name and columns.
Archives can mix student and class workbooks, with up to 100 workbooks and
10,000 data rows in total. The combined expanded archive and workbook contents
are bounded to 200 MiB each. Encrypted archives and links are rejected.

Archive layout (one enclosing folder is also accepted):

```text
students-2026.xlsx
classes-2026.xlsx
photos/                 # optional
  0012345678.jpg
  0012345679.png
```

Place every workbook at the root. Optional JPEG/PNG/WebP photos use a ten-digit
NISN as the filename and match student rows in the uploaded workbooks. Missing
photos are normal and never block importing; existing photos are retained.
Files with invalid names, unmatched NISNs, duplicate NISNs, or invalid image
contents produce explicit errors. Photos are validated during preview and
only applied for selected student rows. Photo limits match the profile upload
service (5 MiB and 20 megapixels per image; 50 MiB of normalized photos total).

The `students` and `classes` sheets use the export columns unchanged. A blank
ID creates a record; an existing ID updates that record. Empty rows and the
“Tentang Ekspor” sheet are ignored. Formulas are rejected; NISN and guardian
phone values should be stored as text to preserve leading zeros.

Uploads produce a preview with separate create/update tables, highlighted
changes, source filenames, staged photos, and cell-specific errors. Exclude
individual rows before confirming. Only selected valid rows are saved in one
transaction; failed saves remove new photo files and retain original photos.
Canceling leaves student/class data unchanged. Previews expire after one hour,
belong to the uploading admin, detect stale edits, and cannot be applied twice.
Expired previews and their staged photos are cleaned up when another file is
uploaded. Canceling or completing a preview also discards its staged photos.
Student `ID KELAS` values must already exist. Import new classes first to obtain
their generated IDs before assigning students to them.

Install `backend/requirements.txt` and run `.venv/bin/alembic upgrade head`
from `backend/` before using this page; the migrations add `import_batches` and
`import_photos`. Archive support uses `libarchive-c` and requires the native
libarchive shared library (for example, `libarchive13` on Debian/Ubuntu or
`libarchive` on Arch; a recent build with RAR/7z support is recommended).

## Trusted devices and operators

Apply the database migration from `backend/` with
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

- [ ] Bulk student and class endpoints (for spreadsheet feature) *(in progress)*
- [ ] Make an .xlsx template for importing
- [x] Admin: manage operators (create, edit, deactivate, reset PIN, delete)
- [x] Admin: manage trusted devices (create, edit, deactivate, revoke, delete)

### Infra & Deployment

- [ ] HTTPS setup (mkcert + reverse proxy) for LAN deployment
- [x] Administrator password/PIN reset flow
- [ ] Backups strategy for the database

### Testing

- [x] Single data factory for each table

### Frontend

--

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

## How to Run the Backend Server

This project isn't expected to run properly yet, but if you want to run it anyway (maybe you're planning to contribute, thank you!), follow these steps:

1. Clone this repository.

2. Configure `docker-compose.yml` to your liking, then spin up a PostgreSQL container with:

    ```
    docker compose up -d
    ```

    Once it's running, note the port you set under the `ports` key (5433 by default) -- you'll need it in the next step.

3. In the `backend` folder, copy `.env.example` to a new file named `.env`. Update the values as needed -- most importantly `DATABASE_URL`, which should match how you configured `docker-compose.yml`:

    ```
    DATABASE_URL="postgresql+psycopg2://POSTGRES_USER:POSTGRES_PASSWORD@localhost:port/attendance"
    ```

4. Set up a Python environment and install the dependencies from `requirements.txt`.

5. Run the initial Alembic migration:

    ```
    alembic upgrade head
    ```

6. That's it! The API is ready to run. Start it with `uvicorn`.

### Running Tests

To run the test suite with `pytest`, you'll need a local PostgreSQL install and a dedicated test database. Create it with:

```
createdb -h localhost -p 5433 -U attendance test_attendance
```

(Again, swap `5433` for whatever port you set in `docker-compose.yml`.)

This creates a `test_attendance` database, which `pytest` reads from an environment variable.
