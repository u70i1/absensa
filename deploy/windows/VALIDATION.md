# Native Windows validation record

## v1.1.0 release preparation — 2026-10-07

Preparation started from a clean checkout and fast-forwarded local `main` to
`b29fe7f6eb` (the existing native Windows merge). No local VM, WSL, Windows guest,
or native Windows execution was used. The checks below validate this preparation
working tree; the CI links identify the earlier tested commits explicitly.

### Verified GitHub Actions evidence

- [Main installer run 37505387710](https://github.com/u70i1/absensa/actions/runs/37505387710),
  source `b29fe7f6eb`: `safety`, `windows-2022`, and `windows-2025` **success**.
- [Windows branch run 37506216193](https://github.com/u70i1/absensa/actions/runs/37506216193),
  source `c394996ae4`: the same three jobs **success**.
- [Published v1.0.0 release run 37398416209](https://github.com/u70i1/absensa/actions/runs/37398416209)
  **success**. Its published assets are Linux-only: TAR.GZ, `SHA256SUMS`,
  and `provenance.jsonl`. They were inspected read-only and not replaced.

Native jobs execute the shared `windows-package` action: PowerShell 5.1,
service-account regression, dependency builds, real ZIP/inventory verification,
and `smoke.py` for services, migrations, CA-verified TLS, persistent paths with
spaces, backup/restore, candidate update, migration failure/repair, Cairo,
libarchive, and sandboxed Chrome under the WhatsApp service identity.

### Checks run for this preparation

Commands run from the repository root unless stated otherwise:

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s deploy/installer -p 'test_*.py'` | 36 passed; Linux package checksums/provenance rejection, generation and pipe tests |
| `python3 -m unittest discover -s deploy/windows -p 'test_*.py'` | 29 passed; configuration, quoting, service/update safety and packaged guide links |
| `python3 -m unittest discover -s deploy -p 'test_*.py'` | 4 passed |
| `bash -n install.sh` | Passed |
| `python3 deploy/installer/build_bootstrap.py` then `git diff --exit-code -- install.sh` | Passed; generated bootstrap unchanged |
| `web/.venv/bin/ruff check web/app web/tests deploy` | Passed after minimal lint corrections in Windows-related code |
| `web/.venv/bin/ruff format --check deploy/windows/manage.py deploy/windows/package.py deploy/windows/smoke.py deploy/windows/test_windows.py deploy/windows/windows_archive.py deploy/installer/package_release.py deploy/installer/test_safety.py web/app/jobs/worker_health.py web/app/services/backup_service.py` | 9 files passed |
| `npm test --prefix services/whatsapp` | 13 passed with mocked WhatsApp clients |
| `.venv-docs/bin/python -m mkdocs build --strict` | Passed |
| `git diff --check` | Passed |

Already-cached Linux containers supplied optional tools without downloads:

```bash
docker run --rm --pull=never --network none -v /home/shared/Codes/absensa:/repo:ro -w /repo koalaman/shellcheck:stable install.sh
docker run --rm --pull=never --network none -v /home/shared/Codes/absensa:/repo:ro -w /repo rhysd/actionlint:latest -shellcheck=
docker run --rm --pull=never --network none -v /home/shared/Codes/absensa:/repo:ro -w /repo mcr.microsoft.com/powershell:7.5-ubuntu-24.04 pwsh -NoProfile -File deploy/windows/test-bootstrap.ps1
```

All three passed. PowerShell 7 on Linux checks parsing, checksum/ZIP safety,
source-download fallback fixtures and DLL-name fixtures; it does **not** validate
PowerShell 5.1, SCM, NTFS ACLs or PE binaries. Those are covered by native CI.

The full application suite used an isolated, disposable PostgreSQL 18.4 container
from the cached image, limited to 256 MB and one CPU, on loopback port 55439.
The existing PostgreSQL container was untouched. From `web/`:

```bash
DATABASE_URL=postgresql+psycopg2://unused:unused@127.0.0.1:1/unused \
TEST_DATABASE_URL=postgresql+psycopg2://postgres:absensa-release-test@127.0.0.1:55439/absensa_release_test \
ABSENSA_ALLOW_TEST_DATABASE_RESET=1 ABSENSA_TEST_REAL_BACKUP=1 .venv/bin/pytest -q
```

**692 passed, no skips**, including real Alembic upgrade/downgrade, browser tests,
and encrypted backup/restore with PostgreSQL 18 clients. The password above is
only the disposable fixture password. Initial sandbox runs could not open local
sockets; the blocked pytest run was interrupted and both affected suites rerun
with local access. Those environment failures are not counted as passing runs.

Additional local checks: YAML parsing for workflows/actions and Compose files;
relative link targets in 14 operational documents; and execution of the release
validation shell guard with fixtures for a new version, an existing release, and
an API failure (all behaved as expected). Conflict-marker and version/WSL/TODO
searches were reviewed. Remaining TODOs are the existing roadmap and hidden
comments in explicitly unfinished user documentation, not installer instructions.
The accidentally tracked WhatsApp cache was removed and cache/session paths
ignored. `install.ps1` is maintained directly; packaging copies its exact bytes.

### Limits and publication gates

The preparation commit itself has not been pushed or run on Windows CI. Its
changes repair documentation, packaged guide links, CI guards and lint findings;
they do not change the deployment architecture or dependency pins. Review its
normal `installer.yml` run when pushed. The tag workflow must still build the
actual v1.1.0 artifacts, run Linux integration and native Windows 2025 smoke,
and verify real OIDC attestations before creating a draft. Full Linux container
smoke was not repeated locally; `release.yml` → `build-linux` covers it using
newly built release images.

**Readiness for a release tag is not approval to publish production support.**
Keep the resulting release a draft until the field gates below are satisfied.
Server 2019 has no runtime result or CI runner. Reboot without login, real WhatsApp
pairing/reconnect/delivery, Cloudflare issuance/renewal, clean hosts without build
tools, cross-platform restore and uninstall/recovery still require native field
evidence. No current GitHub Actions job fully covers those field checks.

## Historical implementation record — 2026-10-06

Implementation date: 2026-10-06. Development host: Linux amd64. Branch:
`feat/native-windows-server`. No Windows machine was available to this session.
No merge, push, tag, or GitHub Release was performed.

### Executed locally in the original implementation

- Existing installer safety/packaging/pipe tests: 36 passed.
- Existing legacy deployment tests: 4 passed.
- Windows backend configuration/service XML/storage/update failure tests: 20 passed.
- Application suite against an isolated PostgreSQL 18 container, including real
  pg_dump/pg_restore with `ABSENSA_TEST_REAL_BACKUP=1`: final run **672 passed,
  5 skipped** (three tests require Playwright; two require optional zxingcpp).
- Full Linux Docker deployment smoke passed: installation, migrations, idempotent
  admin creation, verified HTTPS/CSRF/Secure cookies, persistence, encrypted full
  backup, isolated restore with original CA, update, failed migration and repair.
  Fixture report: `/tmp/absensa-smoke-yl55l465`; disposable containers cleaned up.
- Ruff on changed Python files, actionlint, ShellCheck, `bash -n`, generated Linux
  bootstrap consistency, `git diff --check`, and strict MkDocs build passed.
- WhatsApp bridge tests: 13 passed. Initial sandbox run could not bind loopback;
  rerun with approved localhost access passed.
- PowerShell 7.5 on Linux: parser, supported-build fixture checks for 17763/20348/26100,
  checksum tampering rejection and unsafe ZIP extraction rejection passed.
  **This is not a PowerShell 5.1 or Windows execution result.**
- Direct CPython 3.13 win_amd64 wheels for all selected application requirements
  downloaded successfully from PyPI. A full cross-platform pip resolution on
  Linux evaluated uvicorn's host OS marker and attempted uvloop; actual Windows
  resolution is performed by CI. No compiler fallback is allowed in packaging.
- All pinned upstream runtime archives downloaded and SHA-256 values recorded:
  Python, Node, PostgreSQL, Chrome, GitHub CLI and WinSW. Executing their PE binaries
  was not possible on this Linux host.

## Native CI coverage

The following checks passed in the linked pre-preparation runs. A successful
run applies to its recorded source SHA, not automatically to later commits.

`installer.yml` runs the shared Windows build/test action separately on
`windows-2022` and `windows-2025`. It runs PowerShell **5.1**, builds Cairo/libarchive
with a pinned vcpkg baseline, builds the same Caddy/Cloudflare versions as Linux,
installs wheels with `--only-binary`, installs locked npm modules, and builds and
extracts the real release ZIP. It verifies its entire file inventory and checksum.

Before compiling native dependencies, `test-service-account.ps1` creates a unique
stopped SCM fixture and uses the production host operation twice to verify a
virtual account, service SID resolution and unchanged manual/stopped state. It
deletes only that fixture. This catches account configuration failures such as
error 1057 without rebuilding the package first. Virtual accounts require a NULL
password; `host.ps1` omits `sc.exe`'s password option rather than passing an empty
string. This regression test requires Windows Administrator privileges. It passed in
the native CI runs linked above; it cannot execute on the Linux development host.

The Administrator service smoke test uses new roots containing spaces under
Program Files/ProgramData and refuses pre-existing Absensa service names. It
registers actual services, uses actual virtual identities/ACLs, initializes a
real PostgreSQL cluster, runs migrations and all workers, validates Caddy HTTPS
against its local CA, checks persistence and secrets across repair, takes real
encrypted database/full backups, restores into new database/photo trees, updates,
forces a migration failure, checks its backup/journal, then repairs it. It checks
SCM automatic startup and account names. It instruments only the installed fixture to launch packaged Chrome headlessly
in Session 0 as the actual WhatsApp virtual identity, loads Cairo/libarchive DLLs,
renders an actual student card PNG, reads
an archive and loads IANA timezone data. Cleanup removes only fixture services
and the fixture firewall rule; logs/data stay on the ephemeral runner.

Release jobs are explicit: validate → build-linux + build-windows → release.
Both builds must pass before a draft is created. Native Windows release smoke
runs on 2025. The tests do not bypass verification in production: fixture calls
inject already-staged candidate directories only inside the test process.
Public download and actual attestation verification need an authorized tag run.

## Required field gates before publishing production support

Record OS build/edition, patch level, package digest, tag, logs and result for
**each** of Server 2019, 2022 and 2025. Run on disposable systems, then a small
school pilot. Do not run the CI smoke script on an existing school server.

1. Clean installation from 64-bit PowerShell 5.1 with no Git, Python, Node, Go,
   package manager, compiler, Docker, WSL or logged-in service user. Include
   Indonesian Windows, Server Core and Desktop Experience separately.
2. **Server 2019:** execute bundled PostgreSQL 18.4 and Chrome, render actual
   student card PNGs, import ZIP/7z/RAR, migrate and back up/restore. EDB's published
   PostgreSQL 18 test matrix names 2022/2025 only; it does not certify 2019.
   Keep this as an explicit unresolved compatibility gate. If runtime tests expose
   an OS API blocker, record the exact missing API/version; do not silently remove
   2019 support or substitute a Linux VM.
3. Reboot after healthy install with nobody logged in: all six services become
   healthy; LAN HTTPS/login, scheduler heartbeat and scheduled backup work.
   Repeat after stop (must stay stopped), interrupted backup/update, and restore
   awaiting activation (must not send messages/start an old application).
4. Chromium under **NT SERVICE\AbsensaWhatsApp** in Session 0, with sandbox:
   QR pairing, persisted session, disconnect, controlled test message to an
   authorized test number, graceful stop and reboot/reconnect. CI synthetic page launch does not establish real WhatsApp pairing/reconnection. Check antivirus/AppLocker behavior.
5. ACL negative tests as an ordinary local user and each service: no access to
   master configuration/recovery key/other service secrets; no write access to
   immutable binaries or PostgreSQL from the web service. Check Windows Event Log
   and wrapper restart behavior by terminating one fixture process.
6. Confirm only chosen TCP HTTPS port is reachable from approved LAN; PG/web/WA
   remain loopback. Test Domain and Private profiles, Public rejection, other
   VLANs, existing IIS/e-Rapor port conflicts, local DNS and certificate trust on
   actual phones/scanners. Test Cloudflare issuance and renewal with an approved
   zone/token separately.
7. Public attested installation of v1.1.0. For later Windows releases, test
   previous stable → next stable update using public attested artifacts. v1.1.0
   is the first Windows package; v1.0.0 has no Windows upgrade source. CI currently
   exercises updates with locally staged candidate packages.
   Kill power/process at each journal phase; test disk full, corrupt ZIP, invalid
   checksum/attestation, unavailable internet and missing data volumes.
8. Restore real encrypted `.absbackup` Linux → Windows and Windows → Linux,
   compare pupils/scans/admin hashes, schema, photos/logo bytes and timezones.
   Full deployment configs are platform-specific: only data/photos are imported
   from Linux `.absfull`; Windows preserves its native configuration. Relink WA.
9. Uninstall through launcher: services/firewall/binaries removed, all school
   data/config/keys/backups retained. Verify recovery on another machine with
   original tag and separate recovery key. Confirm behavior with WDAC/AllSigned.

## Architecture references

- [PostgreSQL Windows distribution and EDB test matrix](https://www.postgresql.org/download/windows/)
- [Native pg_ctl service registration](https://www.postgresql.org/docs/18/app-pg-ctl.html)
- [PostgreSQL restricted initdb token](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/common/restricted_token.c)
- [WinSW 2.12 service configuration](https://github.com/winsw/winsw/blob/v2.12.0/doc/xmlConfigFile.md)
- [Windows service identities](https://learn.microsoft.com/windows/security/identity-protection/access-control/service-accounts)
- [Python embedded distribution](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)
- [CairoCFFI Windows DLL requirements](https://doc.courtbouillon.org/cairocffi/stable/overview.html)

The documentation describes the implemented path and its testing limits. Neither
syntax checks nor successful Linux tests are a claim that Windows Server support
has completed field qualification.
