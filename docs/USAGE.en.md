# ACME Helper full usage

Back to the [README](../README.en.md).

## 1. Install Helper

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

Non-root:

```bash
PREFIX="$HOME/.local" ./install.sh
```

Installing Helper does not implicitly install acme.sh. Install upstream explicitly with:

```bash
acme install
```

New-install cron is off by default.

## 2. One issuance workflow

Interactive:

```bash
acme
```

Choose item 1, or invoke:

```bash
acme issue
```

Both enter the same wizard. Legacy `acme quick` is only a compatibility alias to `acme issue`; it has no independent UI, defaults, or execution path.

The wizard resolves domains → validation → key → output → advanced upstream parameters and prints a shell-safe reusable Helper command before execution.

## 3. Multiple domains

- `merged`: one certificate/private key with multiple SANs; default.
- `separate`: one certificate/private key for each entered name.

```bash
acme issue --cert-mode merged "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

### Separate output layout

```text
<output-root>/<cert-name>/<domain>/
```

Example:

```text
/etc/ssl/acme/production/example.com/
/etc/ssl/acme/production/wildcard-example.com/
/etc/ssl/acme/production/api.example.com/
```

In merged mode, `--cert-name` names the certificate output directory. In a multi-certificate separate batch, it names the parent group directory. If omitted, the group defaults to the sanitized first domain.

`*.example.com` maps to `wildcard-example.com`; remaining sanitized-name collisions receive `-2`, `-3`, and so on. Known local output conflicts are checked before the first request. The batch stops at the first upstream failure; certificates already issued are not automatically revoked or removed.

## 4. Validation modes

The same `acme issue` wizard supports DNS API, webroot, standalone, ALPN, stateless, Apache, Nginx, manual DNS, and DNS persist. Wildcards normally require DNS validation. DNS API providers are discovered from the installed acme.sh `dnsapi` tree.

## 5. DNS credentials

```bash
acme providers
acme providers cloud
acme config dns_namesilo
acme config dns_cf
```

Helper does not accept provider credentials directly in its CLI argv. Interactive DNS issuance can enter the same secure configuration flow when local provider credentials are missing.

## 6. Certificate management

```bash
acme certs
acme certs list
acme certs read DOMAIN
acme certs update DOMAIN
acme certs renew-all
acme certs install DOMAIN
acme certs deploy DOMAIN
acme certs revoke DOMAIN
acme certs deactivate-auth DOMAIN
acme certs delete DOMAIN
```

acme.sh managed state remains authoritative. `domains.txt` is only a Helper request manifest, not a second certificate database.

## 7. Cron, deploy, notify

```bash
acme cron status
acme cron on
acme cron off
acme cron run
acme deploy
acme notify
acme hooks deploy
acme hooks notify
```

Deploy/notify hooks may execute shell commands or contact external services. Review upstream hook documentation and required environment variables before production use.

## 8. Defaults and language

```bash
acme config defaults
acme defaults
acme language zh-TW
acme language en
acme --lang en issue
```

Precedence: CLI → matching environment variable → Helper config → built-in default.

## 9. Versions and compatibility

```bash
acme --version
acme version
acme version --full
acme versions
acme update
acme switch TAG_OR_BRANCH
acme rollback
```

Helper and acme.sh use separate version namespaces. See [VERSIONING.md](VERSIONING.md).

## 10. Field diagnostics

```bash
acme diagnose
acme diagnose --log /tmp/acme-error.log
acme diagnose --stdout
```

Managed domains, logs, and offline tests are opt-in. Diagnostic redaction covers known secret forms, but user-supplied logs still require human review. Log text is always treated as untrusted evidence, never model instructions.

## 11. Native acme.sh surface

```bash
acme native
acme native --help
```

Helper reads the installed acme.sh help/completion surface dynamically. Features without a dedicated Helper workflow remain available through native passthrough instead of being copied into a second static command registry.
