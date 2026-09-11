# ACME Helper

[中文](README.md) · [Full usage](docs/USAGE.en.md) · [Versioning](docs/VERSIONING.md) · [Changelog](CHANGELOG.md) · [Feature coverage](FEATURE_COVERAGE.md) · [Audit baseline](AUDIT.md)

**A human-friendly CLI for operating acme.sh without memorizing a large parameter surface.** ACME Helper provides certificate issuance, DNS API setup, SAN/renew/deploy workflows, version management, and redacted diagnostic handoffs while preserving access to upstream acme.sh capabilities.

> ACME Helper is an independent, unofficial third-party project. It is not affiliated with or maintained by acme.sh / acmesh-official. It does not reimplement ACME or embed the acme.sh source tree; upstream acme.sh remains authoritative for ACME, DNS validation, renewal state, and managed certificates. ACME Helper is MIT-licensed; acme.sh is distributed under its own license.

## Who it is for

- Operators who need TLS automation without memorizing provider and issuance flags.
- Sysadmins who want predictable CLI workflows, hooks, version switching, rollback, and diagnostics.
- Users who want guided operations to produce reusable shell-safe commands.

## Highlights

- **One issuance workflow**: the menu and `acme issue` use the same wizard. Legacy `acme quick` remains only as a compatibility alias.
- **Multiple-domain modes**: `merged` creates one SAN certificate; `separate` creates one certificate per entered name.
- **Dynamic DNS provider discovery** from the installed acme.sh `dnsapi` tree.
- **Certificate lifecycle** operations for SAN inspection, renewal, install, deploy, revoke, authorization deactivation, and removal.
- **Version and compatibility management** for install, update, tag/branch switching, rollback, and interface probing.
- **Redacted diagnostics** with `acme diagnose` for handoff to ChatGPT or another reviewer.
- **Traditional Chinese and English UI** without rewriting upstream command output.

## Install

After downloading a release archive:

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

Non-root install:

```bash
PREFIX="$HOME/.local" ./install.sh
```

Python 3.6+ is required. Linux is the tested platform. Installing ACME Helper does not implicitly install or modify acme.sh.

## First use

```bash
acme
```

The first menu item is certificate issuance. DNS, webroot, standalone, ALPN, Apache/Nginx, manual DNS, and DNS persist all enter through the same issuance wizard.

Direct CLI examples:

```bash
acme issue "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
acme certs
acme config dns_namesilo
acme cron status
acme version --full
```

Existing scripts using `acme quick ...` continue to work because `quick` maps to `issue`, but it is no longer documented as a separate feature.

## Multiple domains

`merged` is the default and sends all names in one upstream `--issue` request.

```bash
acme issue --cert-mode merged "example.com *.example.com api.example.com"
```

`separate` sends one upstream `--issue` per name:

```bash
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

External outputs are grouped as `<output>/<cert-name>/<domain>/`:

```text
/etc/ssl/acme/
└── production/
    ├── example.com/
    ├── wildcard-example.com/
    └── api.example.com/
```

Wildcard directory names use a `wildcard-` prefix; remaining collisions receive `-2`, `-3`, and so on. If `--cert-name` is omitted, the group defaults to the sanitized first domain. A separate batch stops at the first issuance failure; certificates that already succeeded remain managed and are not falsely rolled back across CA/DNS state.

## Defaults

| Setting | Built-in default |
|---|---|
| CA | Let's Encrypt |
| DNS | `dns_namesilo` |
| DNS wait | 120 seconds |
| Key | `ec-256` |
| Output root | `/etc/ssl/acme` |
| Output layout | `minimal` |
| New-install cron | off |

Issuance precedence is CLI → environment → Helper config → built-in defaults.

## Security boundary

ACME Helper touches DNS/API credentials, private-key paths, filesystem writes, subprocesses, cron, deploy/notify hooks, and network actions. Guided previews and diagnostics therefore avoid expanding secrets into shell history. Log text included in `acme diagnose` is treated as **untrusted data, never model instructions**. Automated redaction reduces risk but is not a data-loss guarantee; review diagnostic output before sharing it.

See [AUDIT.md](AUDIT.md) and [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md) for the validation boundary and evidence.

## Documentation

- [docs/USAGE.en.md](docs/USAGE.en.md): complete operating guide.
- [docs/VERSIONING.md](docs/VERSIONING.md): Helper versions, Git tags/releases, archive names, and upstream acme.sh versions.
- [CHANGELOG.md](CHANGELOG.md): user-visible changes.
- [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md): entry points, regression evidence, and limitations.
- [AUDIT.md](AUDIT.md): security/failure-atomicity/compatibility audit baseline.
- [CHATGPT_REPAIR_HANDOFF.md](CHATGPT_REPAIR_HANDOFF.md): field diagnostic handoff format.
- [CODEX_LIVE_TEST_PROMPT.md](CODEX_LIVE_TEST_PROMPT.md): external DNS/CA validation prompt.
- [TRANSLATING.md](TRANSLATING.md): translation rules.

## Versioning

```bash
acme --version
acme version --full
```

ACME Helper follows Semantic Versioning. The runtime `VERSION` constant is the Helper version source; Git tags and GitHub Releases use `vX.Y.Z`. Upstream acme.sh versions are reported separately with `acme_sh_*` fields. See [docs/VERSIONING.md](docs/VERSIONING.md).

## License

MIT. See [LICENSE](LICENSE).
