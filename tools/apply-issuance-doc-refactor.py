#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_exact(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit('{}: expected one anchor, found {}'.format(label, count))
    return text.replace(old, new, 1)


def replace_regex(text, pattern, replacement, label):
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit('{}: expected one match, found {}'.format(label, count))
    return text


# ---- core: one issuance workflow, quick only as a hidden compatibility alias ----
core_path = ROOT / 'acme_cli.py'
core = core_path.read_text()
core = replace_exact(core, '# ACME Helper core v1.10.1\n', '# ACME Helper core\n', 'core version comment')
core = replace_exact(core, 'VERSION = "1.10.1"', 'VERSION = "1.11.0"', 'runtime version')

new_usage = '''def usage():
    eprint(_('ACME Helper - make acme.sh approachable without hiding its capabilities.'))
    eprint(_('Start here: acme (guided menu), acme issue (certificate issuance), acme certs (existing certificates).'))
    eprint(_('Certificate issuance: acme "example.com *.example.com" 120'))
    eprint(_('Setup: install, config, defaults, language, providers, status'))
    eprint(_('Maintenance: certs, cron, deploy, notify, version, versions, update, switch, rollback, uninstall, diagnose'))
    eprint(_('Advanced: account, csr, export, ca, hooks, native'))
    eprint(_('Language: acme --lang zh-TW COMMAND or acme --lang en COMMAND; acme language en saves the preference.'))
    eprint(_('Help: acme COMMAND --help. Native passthrough: acme native [UPSTREAM_ARGS].'))
    eprint(_('Defaults: letsencrypt / dns_namesilo / 120 seconds / ec-256 / minimal output; installation cron is off.'))
    eprint(_('Multiple names can be merged into one SAN certificate or issued as separate certificates.'))
'''
core = replace_regex(core, r'def usage\(\):\n.*?(?=\n\ndef locate_acme_sh)', new_usage, 'usage')

# Add a clearer product version key while keeping wrapper_version for compatibility.
core = replace_exact(
    core,
    '    print("wrapper_version={}".format(VERSION))\n',
    '    print("helper_version={}".format(VERSION))\n    print("wrapper_version={}".format(VERSION))\n',
    'version fields',
)

new_guided = '''def guided_issue(result):
    result["interactive"] = True
    eprint("")
    eprint(_('=== Certificate issuance wizard ==='))
    eprint(_('Supports DNS, webroot, standalone, ALPN, Apache/Nginx, manual DNS, DNS persist, multiple SANs and separate certificates. Enter accepts the default in brackets.'))
    eprint("")
    eprint(_('[1/5] Domains'))
    eprint(_('  Enter one or more names separated by spaces.'))
    eprint(_('  Multiple names can be merged into one SAN certificate or issued separately.'))
    eprint(_('  Example: example.com *.example.com *.api.example.com'))
    result["spec"] = prompt_validated_required(_('Domains'), parse_domains)
    domains = parse_domains(result["spec"])
    result["cert_mode"] = choose_cert_mode(domains, result.get("cert_mode", "merged"))
    show_domains(domains, result["cert_mode"])

    eprint("")
    eprint(_('[2/5] Validation'))
    eprint(_('  Modes: dns / webroot / standalone / alpn / stateless / apache / nginx / dns-manual / dns-persist.'))
    eprint(_('  Wildcards normally need DNS validation; webroot/standalone/ALPN may suit ordinary websites.'))
    result["server"] = prompt_default(_('ACME Server'), result["server"])
    result["mode"] = prompt_validated_default(_('Validation mode'), result.get("mode", "dns"), lambda v: validate_choice(v, {"dns","webroot","standalone","alpn","stateless","apache","nginx","dns-manual","dns-persist"}, "validation mode"))
    if result["mode"] == "dns":
        eprint(_('  DNS: all installed DNS API drivers are discovered; enter ? to search.'))
        result["dns"] = _provider_choice(result["dns"])
        selected_provider = find_dns_provider(result["dns"])
        eprint(_('  provider：{} ({})').format(selected_provider["name"], selected_provider["id"]))
        if selected_provider["docs"]:
            eprint(_('  docs：{}').format(selected_provider["docs"]))
        configured = _provider_status(selected_provider, _read_conf_text(resolve_account_conf(find_acme_sh())))
        if configured not in ("configured", "runtime-ready"):
            eprint(_('Credential status: {}. This is a local configuration check, not an API authentication test.').format(configured))
            if sys.stdin.isatty() and selected_provider.get("groups") and prompt_yes_no(_('Configure this DNS provider now?'), "y"):
                configure_provider(result["dns"])
            else:
                eprint(_('Supply the provider credentials through acme config or the upstream environment before issuance.'))
        result["delay"] = prompt_validated_default(_('DNS wait in seconds'), result["delay"], validate_delay)
    elif result["mode"] == "webroot":
        result["validation_value"] = prompt_required(_('Webroot path'))
    elif result["mode"] == "nginx":
        result["validation_value"] = prompt_line(_('Nginx configuration path (Enter=automatic detection): ')).strip()
    elif result["mode"] == "dns-manual":
        eprint(_('  Manual DNS requires adding TXT records by hand and cannot renew unattended like DNS API validation.'))
    elif result["mode"] == "dns-persist":
        eprint(_('  DNS persist is draft persistent validation; confirm CA support before use.'))

    eprint(_('[3/5] Key'))
    eprint(_('  ec-256 is compact and efficient; use RSA for older-device compatibility when necessary.'))
    result["keylength"] = prompt_validated_default(_('Key length'), result["keylength"], validate_keylength)

    eprint("")
    eprint(_('[4/5] Output'))
    eprint(_('  full=four PEM files; minimal=key+fullchain; nginx=privkey+fullchain; none=internal only.'))
    result["layout"] = prompt_validated_default(_('Output layout'), result["layout"], validate_layout)
    if result["layout"] != "none":
        result["output_root"] = prompt_default(_('Output root directory'), result["output_root"])
        default_name = sanitize_cert_name(domains[0])
        if result["cert_mode"] == "separate" and len(domains) > 1:
            result["cert_name"] = prompt_validated_default(_('Certificate group directory name'), default_name, validate_cert_name)
            eprint(_('  Separate mode stores each certificate under <output>/<certificate group>/<domain>.'))
        else:
            result["cert_name"] = prompt_validated_default(_('Certificate directory name'), default_name, validate_cert_name)
    eprint(_('  reloadcmd is optional. It runs after successful issuance and subsequent successful renewals.'))
    result["reloadcmd"] = prompt_line(_('Reload command (optional): '))

    eprint("")
    eprint(_('[5/5] Advanced'))
    eprint(_('  Select additional options from the installed acme.sh --help.'))
    result["advanced"] = prompt_yes_no(_('Add other upstream parameters?'), "n")
    return domains
'''
core = replace_regex(core, r'def guided_issue\(result\):\n.*?(?=\n\ndef _issue_plans)', new_guided, 'guided issue')

new_plans = '''def _issue_plans(result, domains):
    validate_cert_mode(result.get("cert_mode", "merged"))
    if result["cert_mode"] == "separate" and len(domains) > 1:
        validate_separate_domains(domains)
        group_name = result.get("cert_name") or sanitize_cert_name(domains[0])
        validate_cert_name(group_name)
        names = separate_cert_names(domains)
        group_root = os.path.join(result["output_root"], group_name)
        return [
            {"domains": [domain], "cert_name": name,
             "paths": output_paths(group_root, name, result["layout"])}
            for domain, name in zip(domains, names)
        ]
    name = result.get("cert_name") or sanitize_cert_name(domains[0])
    return [{"domains": list(domains), "cert_name": name,
             "paths": output_paths(result["output_root"], name, result["layout"])}]
'''
core = replace_regex(core, r'def _issue_plans\(result, domains\):\n.*?(?=\n\ndef _show_issue_output_plan)', new_plans, 'issue plans')

# Remove the second issuance implementation. `quick` remains only as a command alias.
core = replace_regex(core, r'def quick_issue\(args\):\n.*?(?=\n\ndef _interactive_rollback)', '', 'quick implementation')

core = replace_exact(
    core,
    '        "quick": lambda: quick_issue([]), "issue": lambda: issue([]),\n',
    '        "issue": lambda: issue([]),\n',
    'interactive handler',
)
core = replace_exact(
    core,
    '        "6": (\'Advanced tools\', [("issue", \'Detailed certificate wizard / all validation modes\'), ("deploy", \'Deploy a managed certificate\'),',
    '        "6": (\'Advanced tools\', [("deploy", \'Deploy a managed certificate\'),',
    'advanced menu duplicate issue',
)
core = replace_exact(core, "        eprint(_('  1. Quick certificate (DNS API)'))", "        eprint(_('  1. Issue certificate'))", 'main menu issuance')
core = replace_exact(
    core,
    '                action = {"1": "quick", "2": "certs", "3": "dns-config"}.get(action, action)',
    '                action = {"1": "issue", "2": "certs", "3": "dns-config"}.get(action, action)',
    'main menu mapping',
)
core = replace_exact(
    core,
    '    "quick": "acme quick [--cert-mode merged|separate] [\\"DOMAIN ...\\"]",\n',
    '',
    'quick public help',
)
core = replace_exact(
    core,
    '        if len(argv) == 2 and argv[1] in SUBCOMMAND_HELP:\n            return subcommand_help(argv[1])',
    '        if len(argv) == 2 and (argv[1] in SUBCOMMAND_HELP or argv[1] == "quick"):\n            return subcommand_help("issue" if argv[1] == "quick" else argv[1])',
    'help quick alias',
)
core = replace_exact(
    core,
    '    command = argv[0]\n    if command == "help":',
    '    command = "issue" if argv[0] == "quick" else argv[0]\n    if command == "help":',
    'command alias',
)
core = replace_exact(core, '    if command == "quick": return quick_issue(argv[1:])\n', '', 'quick dispatch')
core_path.write_text(core)

# ---- i18n ----
messages_en = {
    '=== Certificate issuance wizard ===': '=== Certificate issuance wizard ===',
    '  1. Issue certificate': '  1. Issue certificate',
    'Certificate group directory name': 'Certificate group directory name',
    '  Separate mode stores each certificate under <output>/<certificate group>/<domain>.': '  Separate mode stores each certificate under <output>/<certificate group>/<domain>.',
    'Start here: acme (guided menu), acme issue (certificate issuance), acme certs (existing certificates).': 'Start here: acme (guided menu), acme issue (certificate issuance), acme certs (existing certificates).',
    'Certificate issuance: acme "example.com *.example.com" 120': 'Certificate issuance: acme "example.com *.example.com" 120',
    'Advanced: account, csr, export, ca, hooks, native': 'Advanced: account, csr, export, ca, hooks, native',
    'Multiple names can be merged into one SAN certificate or issued as separate certificates.': 'Multiple names can be merged into one SAN certificate or issued as separate certificates.',
}
messages_zh = {
    '=== Certificate issuance wizard ===': '=== 憑證簽發精靈 ===',
    '  1. Issue certificate': '  1. 簽發憑證',
    'Certificate group directory name': '憑證群組目錄名稱',
    '  Separate mode stores each certificate under <output>/<certificate group>/<domain>.': '  獨立模式會將每張憑證放在 <輸出>/<憑證群組>/<網域>。',
    'Start here: acme (guided menu), acme issue (certificate issuance), acme certs (existing certificates).': '從這裡開始：acme（引導選單）、acme issue（憑證簽發）、acme certs（既有憑證）。',
    'Certificate issuance: acme "example.com *.example.com" 120': '憑證簽發：acme "example.com *.example.com" 120',
    'Advanced: account, csr, export, ca, hooks, native': '進階：account、csr、export、ca、hooks、native',
    'Multiple names can be merged into one SAN certificate or issued as separate certificates.': '多個名稱可合併成一張 SAN 憑證，也可各自簽發獨立憑證。',
}
for rel, additions in [('locales/en.json', messages_en), ('locales/zh-TW.json', messages_zh)]:
    path = ROOT / rel
    data = json.loads(path.read_text())
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

# ---- version contract ----
install_path = ROOT / 'install.sh'
install = install_path.read_text()
install = replace_exact(install, '# ACME Helper v1.10.1 installer', '# ACME Helper installer', 'installer version comment')
install_path.write_text(install)

flow_path = ROOT / 'tests/flow_matrix.py'
flow = flow_path.read_text()
flow = replace_exact(flow, "VERSION = '1.10.1'", "VERSION = '1.11.0'", 'flow version')
flow_path.write_text(flow)

v110_path = ROOT / 'tests/review_v110.py'
v110 = v110_path.read_text()
v110 = replace_exact(v110, "t.check('drift-i18n','version-is-v1.10.1',core.VERSION=='1.10.1',core.VERSION)", "t.check('drift-i18n','version-is-v1.11.0',core.VERSION=='1.11.0',core.VERSION)", 'review current version')
v110_path.write_text(v110)

# ---- focused certificate-mode regression ----
cert_test = r'''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACME = str(ROOT / 'acme')
MOCK = str(ROOT / 'tests' / 'mock-acme.sh')


class T:
    def __init__(self):
        self.total = 0
        self.failed = []

    def check(self, name, condition, detail=''):
        self.total += 1
        if condition:
            print('PASS ' + name)
        else:
            self.failed.append((name, detail))
            print('FAIL ' + name + (': ' + detail if detail else ''))

    def finish(self):
        print('SUMMARY {}/{}'.format(self.total - len(self.failed), self.total))
        return 1 if self.failed else 0


def issue_calls(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) > 1 and parts[0] == 'CALL' and parts[1] == '--issue':
            rows.append(parts[1:])
    return rows


def domain_args(call):
    result = []
    for index, item in enumerate(call):
        if item == '-d' and index + 1 < len(call):
            result.append(call[index + 1])
    return result


def main():
    t = T()
    with tempfile.TemporaryDirectory(prefix='acme-cert-modes-') as raw:
        td = Path(raw)
        upstream = td / 'upstream'
        upstream.mkdir()
        real_mock = upstream / 'mock-acme.sh'
        shutil.copy2(MOCK, str(real_mock))
        real_mock.chmod(0o755)
        wrapper = upstream / 'acme.sh'
        wrapper.write_text(r"""#!/usr/bin/env bash
set -u
args=("$@")
fail=0
prev=''
for item in "${args[@]}"; do
  if [[ "$prev" == "-d" && -n "${CERT_MODE_FAIL_DOMAIN:-}" && "$item" == "$CERT_MODE_FAIL_DOMAIN" ]]; then
    fail=1
  fi
  prev="$item"
done
if [[ "$fail" == "1" ]]; then
  exec "${REAL_MOCK}" "${args[@]}" --fail
fi
exec "${REAL_MOCK}" "${args[@]}"
""")
        wrapper.chmod(0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(upstream / 'dnsapi'))
        history = td / 'history.log'
        output = td / 'out'
        account = td / 'account.conf'
        account.write_text("SAVED_Namesilo_Key='test-only'\n")
        env = os.environ.copy()
        env.update({
            'ACME_SH_BIN': str(wrapper), 'REAL_MOCK': str(real_mock),
            'MOCK_HISTORY': str(history), 'MOCK_LOG': str(td / 'argv.log'),
            'ACME_OUTPUT_ROOT': str(output), 'ACME_ACCOUNT_CONF': str(account),
            'ACME_WRAPPER_CONFIG': str(td / 'wrapper.ini'), 'ACME_HELPER_LANG': 'en',
            'HOME': str(td / 'home'), 'TMPDIR': str(td / 'tmp'),
        })
        Path(env['HOME']).mkdir(); Path(env['TMPDIR']).mkdir()

        def run(args, extra=None):
            if history.exists(): history.unlink()
            merged = env.copy(); merged.update(extra or {})
            return subprocess.run([ACME] + args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged, timeout=40)

        p = run(['issue', '--output-layout', 'none', 'a.test b.test'])
        calls = issue_calls(history)
        t.check('backward-default-merged', p.returncode == 0 and len(calls) == 1 and domain_args(calls[0]) == ['a.test', 'b.test'], p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'a.test b.test c.test'])
        calls = issue_calls(history)
        t.check('separate-one-request-per-domain', p.returncode == 0 and [domain_args(row) for row in calls] == [['a.test'], ['b.test'], ['c.test']], p.stderr[-1200:])

        p = run(['quick', '--cert-mode', 'separate', '--output-layout', 'none', 'q1.test q2.test'])
        calls = issue_calls(history)
        t.check('quick-is-issue-compatibility-alias', p.returncode == 0 and [domain_args(row) for row in calls] == [['q1.test'], ['q2.test']], p.stderr[-1200:])

        p = run(['help', 'quick'])
        t.check('quick-help-resolves-to-issue', p.returncode == 0 and 'acme issue' in p.stderr and 'acme quick' not in p.stderr, p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'invalid', '--output-layout', 'none', 'a.test b.test'])
        t.check('invalid-mode-refused-before-upstream', p.returncode == 2 and not issue_calls(history), p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'dup.test DUP.test'])
        t.check('separate-duplicate-refused', p.returncode == 2 and not issue_calls(history) and 'duplicate' in p.stderr.lower(), p.stderr[-1200:])

        shutil.rmtree(output, ignore_errors=True)
        p = run(['issue', '--cert-mode', 'separate', '--cert-name', 'production', '--output-layout', 'minimal', 'example.test *.example.test wildcard-example.test'])
        expected = {
            'example.test': output / 'production' / 'example.test' / 'domains.txt',
            '*.example.test': output / 'production' / 'wildcard-example.test' / 'domains.txt',
            'wildcard-example.test': output / 'production' / 'wildcard-example.test-2' / 'domains.txt',
        }
        ok = p.returncode == 0
        for domain, path in expected.items():
            ok = ok and path.is_file() and path.read_text().strip() == domain
        t.check('separate-path-is-output-group-domain', ok, p.stderr[-1800:])

        shutil.rmtree(output, ignore_errors=True)
        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'minimal', 'first.test second.test'])
        ok = (output / 'first.test' / 'first.test' / 'domains.txt').is_file() and (output / 'first.test' / 'second.test' / 'domains.txt').is_file()
        t.check('separate-default-group-is-first-domain', p.returncode == 0 and ok, p.stderr[-1600:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'ok.test fail.test later.test'], {'CERT_MODE_FAIL_DOMAIN': 'fail.test'})
        calls = issue_calls(history)
        t.check('batch-stops-on-first-failure-with-partial-state-explicit', p.returncode == 17 and [domain_args(row) for row in calls] == [['ok.test'], ['fail.test']] and '1/3 certificates succeeded' in p.stderr and 'not rolled back' in p.stderr, p.stderr[-1800:])

    return t.finish()


if __name__ == '__main__':
    raise SystemExit(main())
'''
(ROOT / 'tests/review_cert_modes.py').write_text(cert_test)

# ---- documentation ----
readme_zh = r'''# ACME Helper

[English](README.en.md) · [完整使用說明](docs/USAGE.md) · [版本規則](docs/VERSIONING.md) · [Changelog](CHANGELOG.md) · [功能覆蓋](FEATURE_COVERAGE.md) · [稽核基線](AUDIT.md)

**讓 acme.sh 不必靠記憶大量參數才能安全維運。** ACME Helper 是一個偏向人類操作的 CLI 前端：提供憑證簽發、DNS API 設定、SAN/續期/部署、版本管理與可遮蔽敏感資訊的診斷交接，同時保留 acme.sh 原生能力。

> ACME Helper 是獨立、非官方的第三方專案，不隸屬於 acme.sh / acmesh-official。本倉庫不重新實作 ACME 協定，也不內嵌 acme.sh 原始碼；真正的 ACME、DNS 驗證與憑證狀態仍由上游 acme.sh 負責。ACME Helper 採 MIT License；acme.sh 依其自身授權發布。

## 適合誰

- 第一次維護 TLS 憑證，不想背 DNS provider、SAN、輸出與續期參數的人。
- 需要可預測 CLI、部署/通知 hook、版本切換與診斷資訊的系統管理者。
- 希望互動操作最後能得到可複製 CLI，而不是只能重新走一次選單的人。

## 核心能力

- **單一簽發入口**：互動選單與 `acme issue` 使用同一套流程；舊的 `acme quick` 僅保留為相容別名，不再是第二套功能。
- **多網域模式**：`merged` 將所有名稱放在一張 SAN 憑證；`separate` 每個名稱各簽一張。
- **DNS provider 動態發現**：從已安裝的 acme.sh `dnsapi` 取得 provider，不維護第二份固定清單。
- **憑證生命週期**：列出 SAN、續期、安裝、部署、撤銷、停用授權與移除管理。
- **版本與相容性**：安裝、更新、指定 tag/branch、切換、回滾及介面探測。
- **診斷交接**：`acme diagnose` 產生遮蔽敏感資訊的唯讀診斷資料，可交給 ChatGPT 分析。
- **雙語介面**：繁體中文與英文；指令、參數、路徑與上游錯誤保持原樣。

## 安裝

下載 release 壓縮包後：

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

非 root 安裝：

```bash
PREFIX="$HOME/.local" ./install.sh
```

需要 Python 3.6+；目前以 Linux 為正式測試平台。Helper 安裝與 acme.sh 安裝是兩件事，不會因安裝 Helper 就自動下載或改動上游。

## 第一次使用

```bash
acme
```

主選單第一項就是「簽發憑證」。DNS、webroot、standalone、ALPN、Apache/Nginx、手動 DNS 與 DNS persist 都從同一個簽發精靈進入。

熟悉 CLI 後可直接：

```bash
acme issue "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
acme certs
acme config dns_namesilo
acme cron status
acme version --full
```

舊版腳本中的 `acme quick ...` 仍會轉到 `acme issue ...`，但新文件與選單不再把它當成獨立功能。

## 多網域憑證

### 合併：`merged`（預設）

```bash
acme issue --cert-mode merged "example.com *.example.com api.example.com"
```

一次呼叫上游 `--issue`，所有名稱共用一張憑證與私鑰。

### 分離：`separate`

```bash
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

每個名稱各自呼叫一次上游 `--issue`。外部輸出依群組收納：

```text
/etc/ssl/acme/
└── production/
    ├── example.com/
    │   ├── key.pem
    │   ├── fullchain.pem
    │   └── domains.txt
    ├── wildcard-example.com/
    │   ├── key.pem
    │   ├── fullchain.pem
    │   └── domains.txt
    └── api.example.com/
        ├── key.pem
        ├── fullchain.pem
        └── domains.txt
```

也就是 `<output>/<cert-name>/<domain>/`。萬用字元目錄使用 `wildcard-` 前綴，避免與 base domain 撞名；其他碰撞會以 `-2`、`-3` 遞增。若未指定 `--cert-name`，群組名稱預設取第一個網域的安全化名稱。

批次在第一個簽發錯誤時停止。已成功的憑證保留在 acme.sh 管理中，不假裝對 CA/DNS 外部狀態做交易式回滾。

## 預設值

| 項目 | 內建預設 |
|---|---|
| CA | Let's Encrypt |
| DNS | `dns_namesilo` |
| DNS 等待 | 120 秒 |
| 金鑰 | `ec-256` |
| 輸出根目錄 | `/etc/ssl/acme` |
| 輸出格式 | `minimal` |
| 新安裝 cron | off |

簽發設定優先序：CLI → 環境變數 → Helper 設定檔 → 內建值。

## 安全邊界

ACME Helper 會接觸 DNS/API credential、私鑰路徑、檔案寫入、子程序、cron、deploy/notify hook 與網路動作，因此預覽與診斷刻意避免把秘密展開到 shell history。`acme diagnose` 的 log 內容被視為**不可信資料，不是 AI 指令**；自動遮蔽仍不是資料外洩保證，分享前應人工檢查。

完整威脅與驗證證據見 [AUDIT.md](AUDIT.md) 與 [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md)。

## 文件

- [docs/USAGE.md](docs/USAGE.md)：完整安裝、簽發、憑證、排程、hook、版本與診斷操作。
- [docs/VERSIONING.md](docs/VERSIONING.md)：Helper 版本、Git tag、release archive 與 acme.sh 上游版本如何區分。
- [CHANGELOG.md](CHANGELOG.md)：使用者可見變更。
- [FEATURE_COVERAGE.md](FEATURE_COVERAGE.md)：功能入口、測試證據與限制。
- [AUDIT.md](AUDIT.md)：已完成的安全／失敗原子性／相容性稽核基線。
- [CHATGPT_REPAIR_HANDOFF.md](CHATGPT_REPAIR_HANDOFF.md)：真機故障交接格式。
- [CODEX_LIVE_TEST_PROMPT.md](CODEX_LIVE_TEST_PROMPT.md)：需要外部 DNS/CA 的實機驗收提示詞。
- [TRANSLATING.md](TRANSLATING.md)：翻譯規則。

## 版本

執行：

```bash
acme --version
acme version --full
```

Helper 採 Semantic Versioning。程式內的 `VERSION` 是執行期版本來源；Git tag / GitHub Release 使用 `vX.Y.Z`。acme.sh 自身版本會以 `acme_sh_*` 欄位獨立顯示，不能把兩者混成同一個版本號。詳細規則見 [docs/VERSIONING.md](docs/VERSIONING.md)。

## License

MIT. See [LICENSE](LICENSE).
'''

readme_en = r'''# ACME Helper

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
'''
(ROOT / 'README.md').write_text(readme_zh)
(ROOT / 'README.en.md').write_text(readme_en)

usage_zh = r'''# ACME Helper 完整使用說明

回到 [README](../README.md)。

## 1. 安裝 Helper

```bash
sha256sum -c SHA256SUMS
sudo ./install.sh
```

非 root：

```bash
PREFIX="$HOME/.local" ./install.sh
```

Helper 不會因自身安裝而自動安裝 acme.sh。需要上游時使用：

```bash
acme install
```

新安裝 cron 預設關閉。

## 2. 單一簽發入口

互動：

```bash
acme
```

選 1「簽發憑證」，或直接：

```bash
acme issue
```

兩者進入相同精靈。舊的 `acme quick` 僅是 `acme issue` 的相容別名，不再有獨立 UI、預設或執行路徑。

精靈依序處理：網域 → 驗證方式 → 金鑰 → 輸出 → 進階上游參數。正式執行前會顯示可複製的 shell-safe Helper CLI。

## 3. 多網域：合併或分離

輸入多個名稱後可選：

- `merged`：一張憑證、一把私鑰、多個 SAN。這是預設。
- `separate`：每個輸入名稱各一張憑證與私鑰。

```bash
acme issue --cert-mode merged "example.com *.example.com"
acme issue --cert-mode separate --cert-name production "example.com *.example.com api.example.com"
```

### separate 輸出規則

外部輸出使用：

```text
<output-root>/<cert-name>/<domain>/
```

例如：

```text
/etc/ssl/acme/production/example.com/
/etc/ssl/acme/production/wildcard-example.com/
/etc/ssl/acme/production/api.example.com/
```

`--cert-name` 在 merged 模式是該張憑證的輸出目錄；在多張 separate 模式則是整批憑證的父目錄。若 separate 未指定 `--cert-name`，預設取第一個網域的安全化名稱。

`*.example.com` 的子目錄使用 `wildcard-example.com`，避免與 `example.com` 撞名；若安全化後仍撞名，依序加 `-2`、`-3`。

在第一張送出前會檢查本機已知輸出路徑衝突。批次第一個上游失敗會停止後續請求；已成功的憑證不自動撤銷或移除。

## 4. 驗證方式

同一個 `acme issue` 精靈支援：

- DNS API（預設）
- webroot
- standalone
- ALPN
- stateless
- Apache
- Nginx
- manual DNS
- DNS persist

萬用字元通常需要 DNS 驗證。DNS API provider 由實際安裝的 acme.sh `dnsapi` 動態發現。

## 5. DNS credential

列出 provider：

```bash
acme providers
acme providers cloud
```

安全輸入 credential：

```bash
acme config dns_namesilo
acme config dns_cf
```

credential 不接受直接放在 Helper CLI argv。互動式 DNS 簽發偵測到本機尚未設定 provider 時，也可直接進入相同安全設定流程。

## 6. 憑證管理

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

acme.sh 的 managed state 是權威來源；`domains.txt` 只保存 Helper 當次要求的名稱，不是第二套憑證資料庫。

## 7. cron、deploy、notify

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

Deploy/notify hook 可能執行 shell 或連線外部服務；正式使用前應確認上游 hook 文件與所需環境變數。

## 8. 預設值與語言

```bash
acme config defaults
acme defaults
acme language zh-TW
acme language en
acme --lang en issue
```

設定優先序：CLI → 對應環境變數 → Helper 設定檔 → 內建預設。

## 9. 版本與相容性

```bash
acme --version
acme version
acme version --full
acme versions
acme update
acme switch TAG_OR_BRANCH
acme rollback
```

Helper 版本與 acme.sh 版本是兩個不同命名空間；詳細規則見 [VERSIONING.md](VERSIONING.md)。

## 10. 真機故障診斷

```bash
acme diagnose
acme diagnose --log /tmp/acme-error.log
acme diagnose --stdout
```

預設不列 managed domain、不自動讀 log、不執行離線測試。需要時明確加入：

```bash
acme diagnose --include-domains
acme diagnose --run-tests
```

輸出會遮蔽已知 Token/Key/Password/EAB HMAC、Authorization/Cookie、URL 密碼、常見 provider ID 與 private key block。指定 log 仍須人工檢查；log 內容一律視為不可信資料，不是模型指令。

## 11. 原生 acme.sh 功能

```bash
acme native
acme native --help
```

Helper 會從已安裝的 acme.sh help/completion 動態取得命令與參數，不維護一份永遠落後的完整副本。對於 Helper 尚未提供專用 UX 的功能，使用 native 入口。
'''

usage_en = r'''# ACME Helper full usage

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
'''

docs = ROOT / 'docs'
docs.mkdir(exist_ok=True)
(docs / 'USAGE.md').write_text(usage_zh)
(docs / 'USAGE.en.md').write_text(usage_en)

versioning = r'''# Versioning policy

ACME Helper 使用 [Semantic Versioning](https://semver.org/) 的 `MAJOR.MINOR.PATCH`。

## 標示規則

| 對象 | 格式 | 範例 |
|---|---|---|
| 程式執行期版本 | `X.Y.Z` | `1.11.0` |
| CLI 短版顯示 | `ACME Helper vX.Y.Z` | `ACME Helper v1.11.0` |
| Git tag / GitHub Release | `vX.Y.Z` | `v1.11.0` |
| Release 壓縮包 | `acme-helper-vX.Y.Z.tar.gz` | `acme-helper-v1.11.0.tar.gz` |
| 上游 acme.sh | `acme.sh X.Y.Z` / `acme_sh_*` | `acme_sh_version=3.1.4` |

`v` 只用在人類可讀的 release/tag 標籤，不放進 Python `VERSION` 值。

## 單一來源

`acme_cli.py` 的 `VERSION` 是 Helper 的執行期版本來源。`acme --version` 與 `acme version` 都從這個值輸出。

README 不再把「目前版本」寫進標題或大量安裝命令，避免每次 release 產生無意義版本漂移。歷史版本只應出現在：

- Git tag / GitHub Release；
- `CHANGELOG.md`；
- 特定版本的 audit/test 歷史證據。

測試可以明確 pin 預期 release 版本，用來防止忘記 bump；這是驗證契約，不是第二個 runtime version source。

## 何時升版本

- **PATCH**：向後相容的 bug fix、安全修正、文件更正，沒有新的公開能力。
- **MINOR**：向後相容的新功能、公開 CLI/UX 能力、可選行為或重要操作流程重構。
- **MAJOR**：刻意移除/改變既有公開 CLI、設定、檔案格式或其他需要使用者遷移的不相容變更。

保留舊命令作 alias 時，通常不視為 MAJOR；若 alias 之後要移除，必須先在 changelog 記錄 deprecation，再於 major release 移除。

## Helper 與 acme.sh 版本不可混用

ACME Helper 自身版本只描述 Helper 程式。上游另有：

- `acme_sh_version`：目前偵測到的上游版本；
- `acme_sh_stable_target`：Helper 預設安裝/更新所 pin 的穩定目標；
- `acme_sh_interface_reference`：Helper 用來比對介面能力的參考版本。

因此「ACME Helper v1.11.0」不代表「acme.sh v1.11.0」，也不代表 bundled acme.sh；本專案並不內嵌上游。
'''
(docs / 'VERSIONING.md').write_text(versioning)

changelog = r'''# Changelog

All notable user-visible changes to ACME Helper are recorded here. The project follows Semantic Versioning.

## [1.11.0] - 2026-09-12

### Changed

- Consolidated certificate issuance into one workflow: the main menu and `acme issue` now use the same wizard.
- Kept `acme quick` only as a backward-compatible alias to `acme issue`; it is no longer a separate documented workflow.
- Changed multi-certificate `separate` output layout to `<output>/<cert-name>/<domain>/`.
- In separate mode, `--cert-name` now names the parent certificate group instead of being rejected.
- Interactive DNS issuance can reuse the existing secure provider-credential configuration flow when local credentials are missing.
- Added `helper_version=` to detailed version output while retaining `wrapper_version=` for compatibility.
- Refactored project documentation into concise README files, detailed usage guides, this changelog, and an explicit versioning policy.

### Compatibility

- Existing direct issuance syntax and `merged` default behavior remain unchanged.
- Existing `acme quick ...` scripts continue to work through the compatibility alias.

## [1.10.1]

- Hardened version rollback so new-format backups restore both presence and prior absence of `acme.sh`, `dnsapi`, `deploy`, and `notify` program assets.
- Tightened version-drift evidence so reduced older interfaces are rejected instead of trusting a version string alone.

## [1.10.0]

- Added the redacted, read-only `acme diagnose` handoff for field troubleshooting.
- Added bounded offline diagnostic regression and prompt-injection/secret-redaction boundaries for supplied logs.

## [1.9.0]

- Standardized guided operations to print a shell-safe reusable CLI before final execution or confirmation.
'''
(ROOT / 'CHANGELOG.md').write_text(changelog)

coverage = r'''# ACME Helper：功能覆蓋與 UX 邊界

本文件描述**目前主線功能邊界**；版本歷史請看 [CHANGELOG.md](CHANGELOG.md)，特定安全驗證證據請看 [AUDIT.md](AUDIT.md)。

## 三個不同的證據層級

**入口可達**：功能可經 Helper 專用路徑、動態原生編輯器或 native 呼叫。  
**引導可操作**：能從選單選取目標、看到用途與風險、處理取消或錯誤。  
**外部實機成功**：DNS/CA、部署、通知等真實外部服務完成。

離線回歸只能證明前兩層與本機邊界；不能把 mock/PTY 通過寫成所有 provider、CA 或 hook 的外部成功。

## 功能矩陣

| 範圍 | 入口與 UX | 主要證據／限制 |
|---|---|---|
| 憑證簽發 | 主選單 1 與 `acme issue` 為同一精靈；DNS、webroot、standalone、ALPN、stateless、Apache、Nginx、manual DNS、DNS persist | CLI/PTY 與參數轉送回歸；`acme quick` 只保留相容 alias |
| 多網域 | `merged` 單張 SAN；`separate` 每名稱獨立憑證 | separate 逐域名 request、重複名稱、部分失敗、輸出碰撞與 `<output>/<cert-name>/<domain>` 路徑回歸 |
| DNS provider | 實際安裝樹動態清單、metadata 認證精靈 | 不維護第二份 vendor schema；configured 不等於真實 API 認證成功 |
| 憑證/SAN | 列全部 SAN、讀取、續期、安裝、部署、撤銷、停用授權、移除管理 | acme.sh managed state 為權威；`domains.txt` 只是要求內容 manifest |
| cron | 查看、啟用、停用、執行一次 | 新安裝預設 off；仍由上游管理實際 cron 格式 |
| deploy / notify | 動態 hook、環境欄位、確認 | 外部服務成功需真機 credential/target 驗證 |
| 帳號 / CA / CSR / key / export | 進階工具與既有命令 | 敏感輸入採隱藏/遮蔽路徑；高風險操作保留確認 |
| 原生命令與參數 | native/all 動態 help/completion + 原樣轉送 | 不宣稱固定上游命令總數；未知新功能保持原廠文字 |
| 互動快捷 CLI | guided 執行在正式動作前顯示可複製 `acme ...` | shell-safe quoting；secret/HMAC/PFX/hook env 不展開；破壞性命令不偷偷加 `--yes` |
| ChatGPT 修復交接 | `acme diagnose`，可選 `--log`、`--include-domains`、`--run-tests` | 唯讀、log opt-in、0600、集中遮蔽、prompt-injection trust boundary、獨立 HOME/TMPDIR |
| 語言 | zh-TW / en | Helper UI 翻譯；不改寫上游錯誤、網域、路徑、token 或機器欄位 |
| 安裝與版本 | Helper installer；acme.sh install/update/switch/rollback/uninstall | Helper 與 upstream 版本分開顯示；完整版本規則見 `docs/VERSIONING.md` |

## UX 原則

- 主選單按「任務」分組，不把同一件事拆成兩個近似入口。
- 初學者與熟手使用相同核心行為；互動模式只是幫忙解析參數與確認。
- acme.sh 擁有 ACME、provider/hook catalog、managed certificate state 與 renewal/cron 行為；Helper 不建立第二套引擎或資料庫。
- 對外部不可逆或有副作用的動作，錯誤時 fail closed；不做無法保證一致性的假 transaction。

## 保留限制

- 真實 DNS/CA、deploy、notify 成功仍需要對應 provider credential 與外部環境驗收。
- Python 3.6 是 runtime 語法/API floor；CI 可能使用較新 Python 執行同一份相容語法。
- 自訂環境只作用於本次程序；獨立排程需要相同設定來源。
- 自動 secret redaction 是風險降低措施，不是任意 log 的資料外洩保證。
- `diagnose --run-tests` 是有界診斷 profile；完整 release regression 仍使用 `python3 -S tests/run_all.py`。
- 測試案例數不等於 100% 程式碼分支覆蓋率。
'''
(ROOT / 'FEATURE_COVERAGE.md').write_text(coverage)

# ---- ensure runtime/test source does not retain the removed second workflow ----
if 'def quick_issue(' in core_path.read_text():
    raise SystemExit('quick implementation still exists')

# ---- checksum manifest ----
manifest_path = ROOT / 'SHA256SUMS'
existing = []
for line in manifest_path.read_text().splitlines():
    parts = line.split('  ', 1)
    if len(parts) != 2:
        raise SystemExit('invalid checksum line: ' + line)
    existing.append(parts[1])
for rel in ['./CHANGELOG.md', './docs/USAGE.md', './docs/USAGE.en.md', './docs/VERSIONING.md']:
    if rel not in existing:
        existing.append(rel)
existing = sorted(set(existing))
lines = []
for rel in existing:
    path = ROOT / rel[2:] if rel.startswith('./') else ROOT / rel
    if not path.is_file():
        raise SystemExit('checksum path missing: ' + rel)
    lines.append('{}  {}'.format(hashlib.sha256(path.read_bytes()).hexdigest(), rel))
manifest_path.write_text('\n'.join(lines) + '\n')

print('REFACTOR_APPLIED')
