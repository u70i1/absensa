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
Upload one `.xlsx` file at a time (up to 10 MiB and 10,000 data rows).

The `students` and `classes` sheets use the export columns unchanged. A blank
ID creates a record; an existing ID updates that record. Empty rows and the
“Tentang Ekspor” sheet are ignored. Formulas are rejected; NISN and guardian
phone values should be stored as text to preserve leading zeros.

Uploads produce a preview with separate create/update tables, highlighted
changes, and cell-specific errors. Exclude individual rows before confirming.
Only selected valid rows are saved, in one transaction. Photos are preserved.
Canceling leaves student/class data unchanged. Previews expire after one hour,
belong to the uploading admin, detect stale edits, and cannot be applied twice.
Expired previews are cleaned up when another file is uploaded.

Install `backend/requirements.txt` and run `.venv/bin/alembic upgrade head`
from `backend/` before using this page; the migration adds `import_batches`.

## Current To-Do

### Auth & Access
- [ ] Operator model (PIN-based, short-session login)
- [ ] TrustedClient model (registration by Superadmin, password-based, long-session login)
- [ ] Session handling (login, expiry, invalidate-on-relogin)
- [ ] Superadmin (bootstrap script, password auth)
- [ ] Role-based route protection (public / operator / superadmin)
- [ ] Public NISN lookup endpoint with rate limiting
### Features
- [ ] Bulk student and class endpoints (for spreadsheet feature) *(in progress)*
- [ ] Make an .xlsx template for importing
- [ ] Superadmin: manage operators (create, deactivate)
- [ ] Superadmin: manage clients (register, revoke)
### Infra & Deployment
- [ ] HTTPS setup (mkcert + reverse proxy) for LAN deployment
- [ ] Password/PIN reset flow
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
