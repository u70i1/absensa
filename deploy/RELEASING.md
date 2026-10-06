# Release maintenance and publishing

The project's Git remote is `git@github.com:u70i1/absensa.git`; its discovered
default branch is `refs/remotes/origin/main`. The installer pins this repository
identity. Forks must update the verifier, workflows, and bootstrap URLs together.

## Before the first release

1. Review and merge the `deploy/v1.0.0` release branch into `main` after the tests pass.
2. Make the repository public so Raw files, anonymous release downloads, and
   public Sigstore attestations are available. Enable Actions with package,
   attestation, and OIDC permissions scoped to the release workflow. Protect
   workflow changes and release tags with rulesets and owner review. Never run
   untrusted pull request code with release credentials.
3. Allow the workflow to build the GHCR images `absensa-web`, `absensa-backup`,
   `absensa-whatsapp`, and `absensa-caddy`. After their initial creation, set each
   package's visibility to **public**. `GITHUB_TOKEN` is used only in Actions;
   school installations must not require GHCR login or a personal access token.
4. Choose a `vMAJOR.MINOR.PATCH` version, then create and push its tag on the
   reviewed commit **after owner authorization**. The implementation work has
   not pushed any changes.
5. `release.yml` validates one tag, then independently builds `build-linux` and
   `build-windows`. Linux retains digest-pinned GHCR images, BuildKit provenance,
   SBOM and container smoke tests. Windows builds a ready-to-run ZIP on
   `windows-2025` and runs native service/migration/TLS/backup/update tests.
   The `release` job requires **both** jobs to succeed, re-verifies checksums and
   attestations, then creates **one draft** GitHub Release. Installers ignore drafts.
6. Check smoke test results, source commit metadata, public image access, and
   anonymous downloads. Complete the release notes and publish the draft as a
   stable release. Then test the Raw installation commands on a clean VM.
   These code changes do not mean that a release has already been published.

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

Windows input/output inventories include `release.json`, `files.sha256.json`,
`python-install-report.json` and Caddy build module metadata. Python dependencies
reuse application requirements (Windows excludes uvloop and uses psycopg2-binary;
tzdata supplies IANA zones). Byte-identical rebuilds are not promised: Python
transitive ranges and toolchain inputs still need a lock refresh process. Each
published archive is immutable and digest-verifiable.

Do not publish the draft until the [Windows field gates](windows/VALIDATION.md)
are recorded, including Server 2019 PostgreSQL/Chromium startup and a reboot.
Build success alone does not establish that a clean school machine works.

The archive contains `manage.py`, `release.py`, `compose.yml`, `release.json`, and
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
bash -n install.sh
shellcheck install.sh
python3 deploy/installer/build_bootstrap.py
git diff --exit-code -- install.sh
```

`install.sh` is generated from `bootstrap.sh.in` and `release.py`; do not edit the
embedded verifier directly. Pull request CI runs PowerShell 5.1 validation and native package/service drills
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
