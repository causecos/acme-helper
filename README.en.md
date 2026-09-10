# ACME Helper v1.10.1

[繁體中文](README.md) · [ChatGPT repair handoff](CHATGPT_REPAIR_HANDOFF.md) · [Translation maintenance](TRANSLATING.md)

ACME Helper makes acme.sh approachable for beginners and fast for operators. It provides task-oriented menus while retaining concise commands and native passthrough. It does not implement ACME or maintain a second certificate database.

### v1.10.1 maintenance fix

Failed version switches now restore both presence and absence of `acme.sh/dnsapi/deploy/notify` according to the new backup `assets=` manifest, so a hook directory created only by the target version cannot survive rollback. Legacy backups without `assets=` are restored conservatively without guessing prior absence. Version-drift tests also no longer treat a mock that only changed its version text as evidence of real legacy compatibility; a reduced 3.1.3-like surface missing required commands is explicitly `incompatible`.

## Install

```bash
tar -xzf acme-helper-v1.10.1.tar.gz
cd acme-helper-v1.10.1
sha256sum -c SHA256SUMS
sudo ./install.sh
```

Unprivileged installation:

```bash
PREFIX="$HOME/.local" ./install.sh
"$HOME/.local/bin/acme" --lang en
```

Change the output root with `acme config defaults` when `/etc/ssl/acme` is not writable. The installer copies the launcher, Python core and language catalogs. It does not delete credentials, certificates or an existing scheduler.

## Start without memorizing flags

```bash
acme --lang en
acme language en
```

The menu groups quick DNS issuance, existing certificates, DNS credentials, scheduling/notifications, installation/versions, advanced tools and preferences. Enter a number or an existing command name. `:back` leaves normal input forms; Ctrl-C cancels. Secret input treats `:back` as data. Operations return to the main menu.

The quick wizard asks for domains, lets you search providers with `/term`, and offers credential setup when local values are missing. Installation is a separate explicit operation. Email is optional; new cron installation is off.

### Copy the resulting CLI for next time

After a guided flow resolves its final settings and before it executes or asks for the final confirmation, Helper prints an equivalent `acme ...` command. Copy that line next time to skip the wizard. Read-only guided tasks such as version, defaults, status, provider browsing and hook browsing also expose their direct command. Expert/direct CLI calls remain quiet.

The preview uses shell-safe quoting. Tokens, passwords, EAB HMAC values, DNS credentials and deploy/notify hook environment values are never expanded into the shortcut. Replay-safe secret paths use `--password-stdin` or `--eab-hmac-stdin`; generic native secrets are shown only as `[hidden]`. The central preview layer also fail-safe redacts known `--password` and `--eab-hmac-key` values. Destructive shortcuts intentionally omit `--yes`, so copied revoke/delete/deactivate/uninstall commands still confirm. Version switch/rollback previews explicitly warn when the copied non-interactive form executes immediately.

## Repair handoff to ChatGPT without Codex on the server

No Codex installation is required on the target host. Run:

```bash
acme diagnose
```

In a TTY, Helper asks whether to include managed domain names, an explicitly saved error log, and bundled offline regression tests. The safe defaults omit domains/logs/tests. Non-interactive use creates the same conservative snapshot directly.

To include saved terminal/acme.sh output after redaction:

```bash
acme diagnose --log /tmp/acme-error.log
```

Other useful forms:

```bash
acme diagnose --stdout
acme diagnose --include-domains
acme diagnose --run-tests
```

The handoff includes Helper version/core SHA-256, OS/Python, acme.sh compatibility, non-secret defaults, config-file metadata, provider state, certificate count, cron state, and only logs explicitly supplied with `--log`. Logs are never read automatically and domain names are omitted by default. `--run-tests` uses a bounded diagnostic profile and explicitly reports `flow_matrix` as omitted; full release verification remains `python3 -S tests/run_all.py`. Offline suites run with isolated HOME/TMPDIR and do not inherit production ACME/provider credentials, account paths, BASH_ENV or PYTHONPATH. Installed runtimes without `tests/` report `NOT_RUN` rather than pretending regression tests passed.

Token/Key/password/EAB HMAC, authorization/cookie headers, URL passwords, common provider IDs and private-key blocks are redacted. The file is created mode 0600, existing output files are never overwritten, and symlink logs are rejected. Automatic redaction is not a disclosure guarantee: review the prompt before sharing it. Paste the prompt into ChatGPT; if a source patch is needed, also attach the exact matching ACME Helper archive/version.

See `CHATGPT_REPAIR_HANDOFF.md`.

## Short commands

```bash
acme install
acme config dns_cf
acme -dns dns_cf "example.com *.example.com"
acme certs
acme certs update "example.com"
acme cron on
acme help certs
acme native
acme diagnose
```

Defaults remain Let's Encrypt, dns_namesilo, 120-second DNS wait, ec-256 and minimal PEM output. All names in one issuance share one certificate. A wildcard does not include its base name. `domains.txt` is retained as a requested-SAN manifest, not an authoritative certificate database. Known managed-certificate output collisions are refused.

`update` upgrades upstream acme.sh, not Helper. The pinned target remains 3.1.4; this is not a claim about the latest release. Install another Helper release using its installer.

## Language contract

Priority: leading `--lang` > `ACME_HELPER_LANG` (or `ACME_LANG`) > saved `[ui] language` > `zh-TW`. Supported catalogs: Traditional Chinese (Taiwan) and English. Unknown languages are rejected. Missing/invalid JSON catalogs fall back to English source messages.

Helper-owned menus, prompts, guidance and errors are localized. Identifiers, flags, tokens, file paths and machine-readable keys are not translated. Upstream output, hook metadata and installer bootstrap diagnostics may remain English. Native arguments are forwarded unchanged.

## Support boundaries

Runtime tested on Linux, Bash 5.2.37 and Python 3.13.5. Python 3.6+ remains a source/API compatibility target, not a separately executed runtime certification. Test harness: Python 3.7+. DNS/deploy/notify inventories are dynamic; missing provider metadata is explicitly reported as manual-schema. Local configured status is not a live API authentication test.

Custom account configuration uses `ACME_ACCOUNT_CONF`/upstream `ACCOUNT_CONF_PATH`; explicit `LE_WORKING_DIR` and `LE_CONFIG_HOME` are preserved. Independent cron/service jobs must use matching environment/configuration. New-format version backups restore both present and absent program assets; legacy backups without `assets=` restore only stored assets. Version rollback is still not a crash-atomic multi-directory transaction.

```bash
python3 -S tests/run_all.py --report-dir /tmp/acme-helper-tests
```

The suite uses local fixtures and real PTYs. `tests/review_v110.py` specifically exercises the diagnostic handoff, redaction, read-only boundary and bilingual UX. It is not live DNS/CA/deployment certification and does not establish 100% source branch coverage.
