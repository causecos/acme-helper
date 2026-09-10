# Public Flow Inventory — ACME Helper v1.10.1

`tests/flow_matrix.py` retains 311 canonical regression checkpoints. `tests/review_v19.py` keeps the guided-shortcut/i18n regression, and `tests/review_v110.py` adds 59 focused diagnostic-handoff checks across correctness, security, i18n, PTY UX and ablation. These are scenario inventories, not a 100% source branch-coverage claim.

Newer flows include seven task categories, numeric/name selection, returning to the main menu, :back, quick issue with provider search and missing-credential setup, bilingual secret input, language persistence/precedence, pre-execution copyable CLI shortcuts with central secret redaction, read-only shortcut routes, offline help for every Helper command, custom-prefix catalog installation, Ctrl-C/D and readline editing. v1.10 additionally covers `acme diagnose`: main-menu/direct TTY routes, mode-0600 exclusive output, opt-in domain/log evidence, no automatic log reads, O_NOFOLLOW log reads, prompt-injection boundary, bilingual repair request, read-only upstream calls, honest NOT_RUN when installed runtimes lack tests, and isolated offline-test HOME/TMPDIR with production ACME/provider environment removed.

Run `python3 -S tests/run_all.py --report-dir /tmp/acme-helper-tests`. The report directory contains fresh logs, per-case JSON for the new suite, runtime hashes, exit codes and suite counts.

## Launcher / package

- same-directory / prefix / `/usr/local` core lookup
- missing core / Python
- Python too old
- install.sh success/custom PREFIX
- non-Linux / missing Python / missing `install` / missing payload

## Main dispatcher

- install / uninstall
- issue
- certs
- deploy / notify / account / csr / export / ca / hooks
- cron / providers / config / status / defaults
- version / versions / update / switch / rollback
- native / all
- diagnose / ChatGPT repair handoff
- help/version / shorthand issue
- invalid and removed legacy aliases

## acme.sh install / version lifecycle

- no-email install
- email / comma email
- stable version / explicit tag / explicit branch
- version+branch conflict
- cron default off / explicit on / conflict
- no-profile
- curl / wget / downloader failures
- invalid email/ref / invalid ACME_SH_BIN
- compatibility gate
- versions / switch / update / same-version no-op
- backup / rollback / cancellation / invalid id
- new-format rollback restores both asset presence and recorded absence
- inconsistent `assets=` manifest fails closed without replacing the live executable
- legacy backup without `assets=` restores stored assets conservatively without deleting unrecorded live directories
- upstream failure → rollback
- reduced 3.1.3-like interface rejected as incompatible instead of trusting the version string
- uninstall require-confirm / PTY cancel / PTY confirm

## Issue

Validation modes:

- dns
- webroot
- standalone
- alpn
- stateless
- apache
- nginx
- dns-manual
- dns-persist

Also:

- all wrapper defaults and aliases
- multi-SAN / wildcard
- full/minimal/nginx/none outputs
- domains.txt
- reload command
- advanced native parameter editor
- managed-option collision rejection
- upstream rc propagation
- interactive final confirmation/cancel

## DNS provider

- dynamic provider inventory/search
- typo/removal rejection
- raw persistence
- mutable persistence
- runtime-only
- manual-schema legacy
- OptionsAlt credential groups
- status all/single
- hidden secrets
- future provider
- custom home-level override

## Managed certificate / SAN lifecycle

- list all SANs/provider(s)
- read by index/main/SAN
- ambiguous selector failure
- renew/update and force
- renew-all
- install-cert + output layout
- deploy
- revoke + reason/confirmation
- deactivate authorization
- remove/delete + confirmation
- RSA/ECC selection behavior

## Deploy / Notify / Hook surface

- dns/deploy/notify hook dynamic discovery
- unknown hook rejection
- deploy by selected managed cert
- deploy interactive hook environment wizard
- deploy secret hidden + environment delivered
- notify status/hooks/set
- notify test-send warning + confirmation
- notify interactive hook environment wizard
- notify secret hidden + environment delivered
- malicious hook metadata never executed

## Account

- status
- register
- update
- account key rotation
- deactivate + confirmation/cancel
- EAB safe input path

## CSR / key

- show CSR
- sign CSR
- create CSR
- domain key
- account key
- interactive key-length prompts

## Export

- PKCS#12 interactive hidden password
- PKCS#12 `--password-stdin`
- PKCS#8

## CA

- default CA
- preferred chain
- list profiles
- dns-persist TXT generation
- wildcard / ca-name / days

## Cron

- status/on/off/run
- upstream failure propagation

## Native / complete callable surface

- help-derived command editor
- completion-derived command editor
- all 35 current callable commands guided/cancel branch
- all reference public parameters hinted
- direct raw passthrough
- future help command/parameter fallback
- future completion-only command fallback

## Diagnostic / ChatGPT repair handoff

- direct `acme diagnose` and advanced-menu discovery
- guided CLI shortcut before generation
- stdout / mode-0600 file output
- exclusive output; no overwrite
- default domain names omitted
- `--include-domains` explicit opt-in
- no automatic log reads
- `--log FILE` regular-file / symlink rejection / bounded tail
- `O_NOFOLLOW + fstat` final log open on Linux
- Token/Key/password/EAB/Auth/Cookie/URL userinfo/provider-ID/private-key redaction
- prompt-injection boundary: logs/upstream messages are untrusted evidence, never instructions
- account.conf values excluded; provider state only
- read-only upstream invocation contract
- normal failure prints diagnose handoff hint
- diagnose self-error does not recursively print handoff hint
- full package `--run-tests`; installed/minimal runtime reports NOT_RUN
- en/zh-TW prompt request parity
- central-redaction mutation reproduces leak when removed

## Terminal/non-TTY

- PTY menu branches
- secret no-echo
- invalid input retry
- Ctrl-C 130, no traceback
- Ctrl-D 1, no traceback
- non-TTY EOF
- pipe guided issue
