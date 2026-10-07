# Release maintenance and publishing

The project's Git remote is `git@github.com:u70i1/absensa.git`; its discovered
default branch is `refs/remotes/origin/main`. The installer pins this repository
identity. Forks must update the verifier, workflows, and bootstrap URLs together.

## Preparing v1.1.0

v1.0.0 is already published and remains immutable. v1.1.0 introduces the native
Windows package alongside the existing Linux container deployment. Preparing a
commit, creating a tag, creating a draft, and publishing are separate steps.

1. Review the release-preparation commit on `main`, run the maintainer checks
   below, and inspect `installer.yml` results for `safety`, `windows-2022` and
   `windows-2025`. See [Windows evidence and limitations](windows/VALIDATION.md).
2. Confirm the repository and existing GHCR packages (`absensa-web`,
   `absensa-backup`, `absensa-whatsapp`, `absensa-caddy`) remain public. Retain
   Actions package, attestation and OIDC permissions. Protect workflow changes
   and release tags; never give untrusted pull requests release credentials.
3. After reviewing the commit, the maintainer creates the next tag:

   ```bash
   git tag -a v1.1.0 -m "Absensa v1.1.0"
   git push origin v1.1.0
   ```

   Confirm `HEAD` is the intended `main` commit first. Never move or recreate
   `v1.0.0`. Pushing a tag triggers the release workflow even if the commit has
   not yet been pushed as a branch; keep remote `main` synchronized through the
   normal review process.
4. `release.yml` validates the version and refuses a tag with an existing release
   (including a draft) before building images. It then runs `build-linux` and
   `build-windows`. Linux builds digest-pinned GHCR images with provenance/SBOMs
   and runs its container smoke test. Windows builds the ready-to-run ZIP and
   runs native package/service/migration/TLS/backup/restore/update drills on
   `windows-2025`. Pre-tag installer CI covers both 2022 and 2025.
5. The `release` job requires **both builds to succeed**, rechecks both checksum
   files and all three attested subjects (Linux archive, Windows ZIP,
   Windows bootstrap), then creates **one draft**. Installers ignore drafts and
   prereleases.
6. Before publishing, inspect the tag-run results, package metadata, notes,
   provenance, public image access, and [Windows field gates](windows/VALIDATION.md).
   Keep the release a draft while those gates remain open. Test anonymous asset
   downloads and the public bootstrap after publication on clean native hosts;
   no local VM or WSL is required. School installations need no GitHub/GHCR login.

A tag run may be retried after a transient build failure while no release exists.
Once a draft exists, review that artifact rather than rebuilding the same version.
Never replace published tags, images, checksums or release assets; use a new
version for corrections. A repository ruleset must prevent tag deletion/movement;
the workflow cannot stop an owner from bypassing repository settings.

Required assets:

- `absensa-linux-amd64.tar.gz`, `SHA256SUMS`, `provenance.jsonl` (existing Linux contract).
- `absensa-windows-amd64.zip`, `install.ps1`, `SHA256SUMS.windows`, `provenance-windows.jsonl`.

`SHA256SUMS` deliberately remains Linux-only because already-installed Linux
verifiers require exactly that one entry. Windows checksums cover the ZIP and
bootstrap; one Windows provenance bundle covers both. Both bundles enforce the
same repository, workflow identity and exact source tag, and reject self-hosted
build provenance. Do not combine the checksum files and break older Linux
installations. No separate Windows application version exists.

The Windows ZIP includes embedded CPython, Windows wheels, Node and locked npm
modules, PostgreSQL 18, Chrome for Testing, Caddy with Cloudflare, WinSW and native
Cairo/libarchive DLLs. It is not a source-only artifact. Client servers never run
pip/npm/Go/compiler tools. See `deploy/windows/dependencies.lock.json` for reviewed
upstream binary SHA-256 pins. vcpkg uses a committed baseline and SHA512 source
pins; Caddy matches the Linux source/module versions. Dependency upgrade review
must include Server 2019 compatibility and Chromium session tests.

Native compilation happens only on CI runners. School servers install the built
ZIP; they never download vcpkg or compile Cairo/libarchive. The build seeds gperf
from GNU mirrors using the exact version and SHA512 read from the pinned vcpkg
checkout, and vcpkg verifies the file again. This handles primary GNU endpoint
timeouts without changing source versions or disabling integrity checks. If all
mirrors fail, the job fails and no combined release draft is created. Rerun failed
jobs for a transient outage; push a new commit when a script needs fixing. Do not
follow generic advice to update vcpkg to latest during a pinned release build.

Windows input/output inventories include `release.json`, `files.sha256.json`,
`python-install-report.json` and Caddy build module metadata. Python dependencies
reuse application requirements (Windows excludes uvloop and uses psycopg2-binary;
tzdata supplies IANA zones). Byte-identical rebuilds are not promised: Python
transitive ranges and toolchain inputs still need a lock refresh process. Each
published archive is immutable and digest-verifiable.

Do not publish the draft until the [Windows field gates](windows/VALIDATION.md)
are recorded, including Server 2019 PostgreSQL/Chromium startup and a reboot.
Build success alone does not establish that a clean school machine works.

The Linux archive contains `manage.py`, `release.py`, `compose.yml`, `release.json`, and
an operator guide. Application images are not built on school servers. Python
packages follow the project's existing dependency pins; the existing Faker
version range needs review if byte-for-byte reproducible builds are required.
Installed versions are reproducible through **image digests**; rebuilding the
same source is not assumed to produce identical bytes.

The packaged guide's cross-document links point to the same release tag on GitHub,
because the installed artifact is not a full repository checkout. Those extra
documents require network access; the main guide is included as `PANDUAN.md`.

Archive provenance binds the image digests in the manifest to the workflow and
tag. Verification uses `gh attestation verify --bundle`, the exact certificate
identity, repository and source ref, and rejects self-hosted runners. There is no
verification bypass. Review and update the GitHub APT key pin when the official
key rotates. Once verified, a release must not fetch additional shell code from
`main` to complete installation.

Keep old images and release artifacts available: restoration needs the original
version. Never replace a published version tag; create a new patch release.
A PostgreSQL major upgrade requires a separate migration procedure, **not** just
an image change. This deployment uses PostgreSQL 18. Changes to the environment
schema or state format require an explicit, tested migrator before incrementing
`format`.

## Maintainer checks

```bash
python3 -m unittest discover -s deploy/installer -p 'test_*.py'
python3 -m unittest discover -s deploy/windows -p 'test_*.py'
python3 -m unittest discover -s deploy -p 'test_*.py'
bash -n install.sh
shellcheck install.sh
python3 deploy/installer/build_bootstrap.py
git diff --exit-code -- install.sh
```

`install.sh` is generated from `bootstrap.sh.in` and `release.py`; do not edit the
embedded verifier directly.
`install.ps1` is maintained directly and copied byte-for-byte into the Windows
ZIP and release assets by `deploy/windows/package.py`; it has no generator.
Pull request CI runs PowerShell 5.1 validation and native package/service drills
on Windows 2022 and 2025. Real Server 2019 remains an explicit field gate.
Actions are pinned to reviewed commit SHAs. Dependabot tracks Actions and base
images. Review dependency changes alongside build results; do not assume major
upgrades are compatible.

The release workflow runs `python3 deploy/installer/smoke.py dist/release` against
actual release images. Local tests use `--local` and explicitly named test images.
That shim exists only in the test harness and is **not packaged** in the installer
artifact. Release fetching is simulated in the smoke test because the release is
not public yet. After attestation, the workflow verifies the real provenance
bundle before creating the draft.

The smoke test creates randomly named projects and synthetic data. It exercises
deferred startup, migrations, idempotent admin creation, CA-verified HTTPS,
CSRF/Secure cookies, persistence, full backups, PostgreSQL/photo restoration,
failed migrations, and repair. It stops the projects it creates and retains
volumes and files for diagnosis. It never deletes pre-existing containers or
volumes. CI runners are ephemeral; before cleaning local test resources, check
which project owns them.

For repeated local runs, use `--local --cleanup` to remove only that run's test
containers and networks afterward. Named data volumes and files are retained.
Without `--cleanup`, stopped test projects retain networks and repeated runs can
exhaust Docker's default subnet pools. Never use a system-wide prune to clear
school application resources.

## Existing source deployments

`compose.production.yml` and `deploy/configure.py` remain available for existing
source installations and developer workflows. They are not the installation path
for new school deployments. `deploy/install.py` now delegates to the release
bootstrap. Do not use it to adopt old volumes automatically. Back up through the
old worker, retain the old environment configuration, and follow `BACKUPS.md` for
isolated restoration with technical assistance. Validate accounts, photos,
database contents, and sessions before switching over. Volumes named `absensa_*`
or `praesens_*` are never moved automatically.
