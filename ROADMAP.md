# Development roadmap

Work tracked by maintainers. For setup, see [RUNNING.md](RUNNING.md); for
implementation details, see [DEVELOPMENT.md](DEVELOPMENT.md). Release preparation
and validation are documented in the [release checklist](deploy/RELEASING.md).

## Auth & Access

- [x] Operator model (PIN-based, browser-session login)
- [x] TrustedDevice model (admin-managed, password-based persistent binding)
- [x] Device/operator session handling and revocation
- [x] Administrator bootstrap and password authentication
- [x] Public, operator, and admin route protection
- [ ] Public NISN lookup endpoint with rate limiting

## Features

- [x] Bulk student and class endpoints (for spreadsheet feature)
- [x] Make .xlsx templates for importing
- [x] Admin: manage operators (create, edit, deactivate, reset PIN, delete)
- [x] Admin: manage trusted devices (create, edit, deactivate, revoke, delete)

## Infra & Deployment

- [x] Caddy HTTPS for LAN access, local CA, and Cloudflare DNS-01
- [x] Administrator password/PIN reset flow
- [x] Encrypted backups, isolated restoration, and mandatory backups before updates
- [x] Linux release installer, native Windows backend, parallel release builds, and provenance verification
- [ ] Publish the prepared v1.1.1 fixes and field-test Windows and school DNS

## Testing

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

