# Installer inspection and validation results

Date: October 2, 2026. Implementation branch: `feat/installer`.
No changes, tags, GHCR images, or GitHub Releases were pushed or published during
this work. See [RELEASING.md](RELEASING.md) for the first publication steps.

## Implementation basis

Inspection covered FastAPI configuration and authentication, models and Alembic,
Dockerfiles and Compose, the WhatsApp bridge and LocalAuth, workers, photo/logo
storage, encrypted backups, initialization scripts, documentation, Git remote and
default branch, and CI configuration. The application uses PostgreSQL 18 and the
existing Argon2 admin password hashing. Application backups already include a
PostgreSQL dump and photos/logos encrypted with AES-256-GCM. The installer reuses
that mechanism and adds deployment configuration, WhatsApp sessions, and CA data
for complete installation recovery.

The old installer built from source without a verified release distribution path.
The new path uses versioned artifacts, GitHub provenance, and digest-pinned images.
Legacy Compose remains available for existing source deployments. Old volumes
are not automatically adopted, and existing accounts are not replaced.

## Main files

| Component | Location |
| --- | --- |
| Linux and Windows bootstraps | `install.sh`, `install.ps1` |
| Artifact verification and installation management | `deploy/installer/release.py`, `manage.py`, `bootstrap.sh.in`, `build_bootstrap.py` |
| Production Compose and Caddy | `deploy/installer/compose.yml`, `deploy/caddy/Dockerfile` |
| Packaging, unit tests, and integration tests | `deploy/installer/package_release.py`, `test_safety.py`, `test_pipe.py`, `smoke.py` |
| Release and validation CI | `.github/workflows/release.yml`, `installer.yml`, `.github/dependabot.yml` |
| Full snapshots and worker health | `web/app/jobs/deployment_archive.py`, `worker_health.py`, `backups.py`, `whatsapp_notifications.py` |
| First-admin bootstrap | `web/app/services/admin_auth_service.py`, `web/scripts/create_admin.py`, `web/tests/test_installer_bootstrap.py` |
| Documentation | `README.md`, `RUNNING.md`, `deploy/README.md`, `BACKUPS.md`, `RELEASING.md`, `RELEASE-NOTES.md` |

The web Dockerfile also prepares the private socket directory. `deploy/install.py`
delegates to the new bootstrap. `.gitignore` excludes installation artifacts and
keys to reduce the risk of accidentally adding them to Git.

## Completed checks

Actual environment: a Linux amd64 host with Docker Engine 29.8.1 and Compose 5.5.1.
This development host is not a clean Ubuntu/Debian VM. Container tests used
randomly named projects, dedicated loopback ports, and synthetic school data.

| Check | Result |
| --- | --- |
| Installer unit tests and pipe execution through a pseudo-terminal | 32 passed |
| Legacy deployment script compatibility tests | 4 passed |
| `bash -n`, ShellCheck, generated bootstrap consistency | Passed |
| Ruff for installer modules and new Python modules | Passed |
| Workflow/Compose YAML, actionlint, `docker compose config` | Passed |
| PowerShell 7.5 parser in a Linux container | Passed; not a Windows execution test |
| Web runtime and backup image builds with PostgreSQL 18 client | Passed |
| Caddy v2.11.6 build with Cloudflare module v0.2.4 | Passed |
| Caddy v2.11.6: verified local HTTPS and Cloudflare DNS configuration adaptation | Passed |
| Python application tests with isolated PostgreSQL | 649 distinct tests passed; 4 skipped, as explained below |
| WhatsApp bridge Node tests | 13 passed |
| Git whitespace check | Passed |

The first full Python suite run produced 648 passes, 4 skips, and one failing
backup integration test because the test database URL omitted the explicit
`5432` port. That test reads the URL's port into `PGPORT`. After correcting the
test URL, the real backup test and all three new admin bootstrap tests were rerun
and passed. Application code was not changed to work around the failure. Skipped
optional tests are not counted as passes; browser suites require additional test
dependencies and tooling.

The end-to-end Docker test installed without starting services, then exercised
migrations, admin creation, CA-verified HTTPS, login/CSRF/Secure cookies, synthetic
data creation, and web container recreation. It verified persistence of accounts,
password hashes, photos, students, and scans. Full backups were authenticated,
exported, and restored into a new database and volumes. The restored CA matched;
WhatsApp and the scheduler remained stopped in the recovery exercise. The update
path ran against a subsequent test version. A deliberately invalid Alembic
revision then demonstrated that web stayed stopped and the recovery journal was
retained. Repair resumed the target version without downgrading the database.
The final test also restored an archive into a new project while the source still
had a failed-migration journal, confirming that source services remained stopped.
This end-to-end test passed with Caddy v2.11.6.

Unit coverage includes unsafe artifacts and path traversal, checksum/provenance
failures, drafts/prereleases, malicious input, Docker port conflicts, inherited
environment overrides, cancellation without network work, idempotent admin
creation, deferred startup, failed backups before updates, migration journals,
orphaned maintenance containers, restore isolation, missing data volume rejection,
and recovery of missing manager/launcher files.

Local tests use image aliases and simulated release metadata fetching **only in
the test harness**. The packaged installer has no verification bypass. Release CI
runs smoke tests against built image digests and then verifies the actual
provenance bundle before creating a draft.

## Validation limits and deployment follow-up

- Windows 10/11, actual WSL2, Windows Server/Hyper-V, and clean Linux VMs were not
  tested. PowerShell parsing alone does not establish Windows compatibility.
- APT installation, sudo, fresh Docker installation, actual cron scheduling, and
  server reboot were not exercised on a school machine. No firewall, router, or
  virtualization settings were changed.
- Cloudflare validation covered module compilation and configuration validity.
  DNS-01 issuance and renewal with a school's account/token were not tested.
- Internal HTTPS was verified from the test host. CA distribution to Android,
  iOS, and Windows, local DNS, school Wi-Fi, WSL NAT, and existing school reverse
  proxies require field testing.
- Actual WhatsApp pairing and message delivery were not performed. Bridge
  liveness does not establish that a WhatsApp session is connected.
- Public GHCR access, anonymous release downloads, successful provenance
  verification from this project's workflow, and Raw commands targeting `main`
  can only be tested after the first authorized publication.
- Backup tests used small synthetic datasets, not a large school's data. Full
  disks, physical power loss, disconnected USB/NAS storage, and recovery onto
  different hardware were not tested. Journaling and simulated migration
  failures cover some related failure paths.
- Official installation artifacts support Linux **amd64** only; no ARM artifact
  is provided.
- Original releases and images must remain available for restoration. Automated
  offline restoration is not provided.

Other school containers were not stopped or reconfigured. Tests stopped their
own project services afterward and retained volumes and archives for diagnosis.
No `docker system prune` or bulk volume deletion was performed.

Before school deployment, the owner must review and merge the changes, authorize
the release workflow/tag, make GHCR packages public, and publish the stable draft.
School IT still needs to arrange IP/DNS, CA distribution or DNS credentials,
external backup storage, recovery key custody, and WhatsApp pairing.
