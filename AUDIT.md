# ACME Helper v1.10.1 Audit

## Scope

v1.10.1 is a maintenance release over v1.10.0. It keeps the v1.9 guided replay contract and the v1.10 diagnostic handoff unchanged while correcting version-rollback state restoration and tightening version-drift test evidence. Every guided operation still resolves its effective settings and prints a shell-safe equivalent `acme ...` command **before** final execution or confirmation. Direct expert CLI remains quiet.

`acme diagnose`, introduced in v1.10.0, remains a read-only diagnostic handoff that creates a redacted prompt suitable for pasting into ChatGPT when the target machine has no Codex/AI agent installed.

This audit distinguishes local/mock/PTY evidence from external DNS/CA/deploy/notify success. No external provider credential is used as sandbox evidence.

## v1.10/v1.10.1 diagnostic contract

Default `acme diagnose` behavior:

- does not modify ACME accounts, certificates, DNS, cron, deploy targets or notify targets;
- does not automatically read any log;
- omits managed domain names unless `--include-domains` is explicit;
- reports account/wrapper config file metadata rather than account.conf values;
- reports provider configured/runtime-ready state, never credential values;
- creates an exclusive mode-0600 prompt file and refuses to overwrite an existing path;
- accepts explicitly supplied `--log FILE` only when it is a readable regular file and rejects symlinks;
- final Linux log open uses `O_NOFOLLOW` plus `fstat` to close the check/open symlink race;
- bounds log input to the tail and runs centralized redaction before handoff;
- marks log/upstream content as **untrusted evidence data, never model instructions**, protecting the ChatGPT handoff from embedded prompt-injection text;
- runs bundled offline tests only with explicit `--run-tests`; installed runtimes without tests report `NOT_RUN`;
- records Helper core and launcher paths/SHA-256 when launched normally;
- in one interactive process, a failed guided action can be followed immediately by Diagnose and retain action, exit code and the already-redacted guided shortcut.

Automatic redaction covers representative Token/Key/password/credential/HMAC assignments and flags, Authorization, Cookie/API-key headers, URL passwords, common provider Account/Zone/Tenant/Client/Subscription IDs and PEM private-key blocks. This is a risk reduction boundary, not a guarantee that arbitrary business data in user-supplied logs cannot appear; the generated prompt explicitly requires human review before sharing.

## Simplification / ablation

Frozen result: **27/27 PASS**.

New evidence:

- A25 retains the existing centralized guided-shortcut redactor: removing it reproduces secret disclosure.
- A26 retains centralized diagnostic handoff redaction: removing the line-level boundary reproduces a credential leak.
- A27 confirms that after log collection was changed to explicit `--log` only, the unused automatic-log discovery path was removed instead of leaving two competing evidence mechanisms.

Prior simplification decisions remain unchanged: upstream owns ACME, renewal, provider/hook catalogs, cert state and cron format; Helper stays a UX/validation adapter rather than a second ACME engine or monitoring daemon.

## Code Review

### Frozen static checks

- `bash -n acme`: PASS
- `bash -n install.sh`: PASS
- bundled shell fixtures syntax: PASS
- Python compile: PASS
- bundled ShellCheck 0.11.0 at warning severity: **12 targets, 0 findings**
- launcher complexity: **0 / KEEP_BASH**
- installer complexity: **2 / KEEP_BASH**
- unexpected dynamic execution (`shell=True`, `os.system`, `os.popen`, `eval`, `exec`): **0**
- zh-TW/en catalog keys: **715 / 715**, parity PASS

### v1.10.1 findings discovered and resolved

| Severity | Area | Finding | Resolution |
|---|---|---|---|
| high | version rollback | A failed version switch restored backed-up files but did not remove a target-only `dnsapi`/`deploy`/`notify` directory when that asset had been absent before the switch | New-format `assets=` manifests are now validated and restore both presence and absence; legacy backups without `assets=` remain conservative and never infer absence |
| test evidence | version drift | Several synthetic tests changed only the mock version string to `3.1.3` while retaining later command/parameter surface, which could be misread as proof of real 3.1.3 compatibility | Successful switch tests now use stable/current branch surfaces; a dedicated 3.1.3-like reduced interface asserts `incompatible` and names missing required commands |

### v1.10.0 findings retained and regression-tested

| Severity | Area | Finding | Resolution |
|---|---|---|---|
| UX | baseline review | The requested pre-execution copyable CLI was already implemented in v1.9; rebuilding it would create duplicate behavior | Kept the existing centralized shortcut implementation and regression tests |
| privacy | diagnostic design | Initial prototype considered auto-reading common acme.sh log paths | Changed to explicit `--log FILE` only; removed the now-dead auto-discovery function |
| medium | diagnostics | `acme diagnose` handler existed but was missing from the visible Advanced Tools menu | Added a visible bilingual menu entry and real PTY tests |
| UX | diagnostics | Direct `acme diagnose` in a TTY did not follow the global “omit args for guided mode” contract | TTY no-argument invocation now uses the guided diagnose flow; non-TTY remains deterministic |
| medium | installed diagnosis | Core under `<PREFIX>/lib/acme` could fail to locate a launcher invoked by full path, making launcher self-check `NOT_RUN` | Thin launcher exports its own absolute path; prompt includes launcher/core path and SHA-256 |
| security | log read | `islink()` followed by normal `open()` left a local TOCTOU window | Final open uses `O_NOFOLLOW` and `fstat`; static symlink paths are rejected earlier as UX feedback |
| security | AI handoff | User-supplied logs could contain prompt-injection text | Top-level handoff explicitly marks logs/upstream text as untrusted evidence, never instructions |
| security/privacy | redaction | Generic provider/HTTP log patterns needed broader coverage | Added Authorization/Cookie/API-key header, URL userinfo, common provider-ID and private-key-block redaction |
| correctness | diagnose input | “readable regular file” validation checked file type but not read access | Added explicit readability check; final secure open remains authoritative |
| test drift | v1.10 version bump | Canonical flow matrix still expected v1.9 in five version/installer assertions | Confirmed product behavior was correct, updated the single test VERSION constant, reran all 311 cases |
| high | offline diagnostic tests | `--run-tests` initially inherited production `ACME_SH_BIN`, account paths and provider credentials; one mock review failed and real secrets could enter test subprocesses/logs | `run_all.py` now uses a strict environment allowlist plus per-suite isolated HOME/TMPDIR; polluted-environment regression and real `diagnose --run-tests` both pass without value leakage |
| UX/performance | offline diagnostic tests | Full release regression inside `acme diagnose --run-tests` made field diagnosis unbounded/too slow | Split `run_all.py` into full release and bounded diagnostic profiles; diagnostic omits long `flow_matrix` and states that omission explicitly |

No unresolved runtime blocker remains in the frozen work tree.

## Adversarial verification

Fresh frozen-runtime results:

| Threat model | Result |
|---|---:|
| correctness / data and control flow | **72/72 PASS** |
| security / failure atomicity | **71/71 PASS** |
| compatibility / provider / version drift | **30/30 PASS** |

Total adversarial assertions: **173/173 PASS**.

These rounds remain independent threat models rather than three copies of one smoke suite. The failure-atomicity round now includes target-only hook-directory cleanup, manifest/physical-asset mismatch fail-closed behavior, and conservative restoration of legacy backups that lack an `assets=` manifest. The drift round includes a reduced 3.1.3-like interface that must be rejected instead of trusting its version string.

## Upstream interface snapshot — 2026-09-08

The current official GitHub Releases/Tags surfaces still show **3.1.4** as the latest released/tagged version, while the current `master` source self-reports **3.1.5**. Therefore `STABLE_VERSION=3.1.4` and `INTERFACE_REFERENCE_VERSION=3.1.5` remain intentionally different.

The official 3.1.4 `--help` exposes the required account-key rollover and DNS-persist interfaces, while its completion file does not enumerate every first-command help entry. Helper therefore continues to merge help/completion evidence rather than treating completion alone as the authority. The official 3.1.3 source lacks the newer required interface, matching the new reduced-interface rejection fixture.

The sandbox did not execute a freshly downloaded upstream program because direct raw-file materialization into the execution container was unavailable. This snapshot is a source/interface comparison, not an external-service E2E result.

## Public Flow and independent UX reviews

- canonical `tests/flow_matrix.py`: **311/311 PASS**
- v1.9 guided-shortcut / UX / i18n independent review: **106/106 PASS**
- v1.10 diagnostic-handoff independent review: **59/59 PASS**

The v1.10 diagnostic suite covers correctness 26/26, security 17/17, i18n/drift 7/7, PTY UX 7/7 and focused ablation 2/2. It specifically verifies:

- no-log/no-domain safe defaults;
- explicit log inclusion and bounded tail;
- central secret redaction and prompt-injection boundary;
- output mode 0600, no overwrite, symlink rejection, `O_NOFOLLOW` contract;
- read-only upstream call history and no account/wrapper config mutation;
- normal error handoff hint without recursive Diagnose errors;
- en/zh-TW prompt instructions and stable machine section names;
- direct TTY Diagnose and Advanced Tools menu discovery;
- same-process failed-operation handoff carrying action/rc/safe shortcut;
- installed/minimal runtime truthfully reporting offline tests `NOT_RUN`;
- diagnose still works when acme.sh itself is not installed;
- offline regression suites discard production ACME/provider variables and run with isolated HOME/TMPDIR;
- a deliberately polluted production-like environment completes the bounded diagnostic profile without leaking those values into reports.

Counts are scenario/assertion evidence and overlap across suites; they are **not** a claim of 100% source branch coverage.

## Guided CLI replay contract retained

v1.9 behavior remains required and regression-tested:

- preview occurs after effective settings resolve and before final execution/confirmation;
- preview is always an ACME Helper command, not only raw upstream argv;
- shell-safe quoting is centralized;
- Token/Key/password/EAB HMAC/DNS/hook environment values are not expanded;
- PKCS#12 and EAB use safe stdin replay paths where available;
- destructive previews omit `--yes` so replay still confirms;
- direct expert CLI does not print a redundant self-preview.

`acme diagnose` itself follows the same rule in guided mode: it shows the reusable `acme diagnose ...` form before creating the handoff file.

## Live-only boundaries

Not proven by this sandbox audit:

- every real DNS provider credential/API;
- public-CA issuance/renewal;
- real deploy/notify target success;
- production cron environment;
- Python 3.6 interpreter execution (source/API compatibility target only; test harness requires 3.7+);
- crash-atomic rollback across multiple directories.

`acme diagnose` makes remote handoff possible without installing an AI agent on the target machine, but it does not convert local configured state or offline mock tests into external-service proof.

See `CHATGPT_REPAIR_HANDOFF.md` for the operator handoff and `CODEX_LIVE_TEST_PROMPT.md` (legacy filename) for the full engineering/live-verification procedure.
