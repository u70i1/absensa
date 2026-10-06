# Native Windows validation record

Implementation date: 2026-10-06. Development host: Linux amd64. Branch:
`feat/native-windows-server`. No Windows machine was available to this session.
No merge, push, tag, or GitHub Release was performed.

## Executed locally

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

## CI implemented, not claimed executed here

`installer.yml` runs the shared Windows build/test action separately on
`windows-2022` and `windows-2025`. It runs PowerShell **5.1**, builds Cairo/libarchive
with a pinned vcpkg baseline, builds the same Caddy/Cloudflare versions as Linux,
installs wheels with `--only-binary`, installs locked npm modules, and builds and
extracts the real release ZIP. It verifies its entire file inventory and checksum.

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
7. Real previous stable → next stable update using public attested artifacts.
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
