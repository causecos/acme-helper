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
        raise SystemExit('{}: expected one regex match, found {}'.format(label, count))
    return text


core_path = ROOT / 'acme_cli.py'
core = core_path.read_text()

core = replace_exact(
    core,
    'OUTPUT_LAYOUTS = {"full", "minimal", "nginx", "none"}\nLISTRAW_HEADER =',
    'OUTPUT_LAYOUTS = {"full", "minimal", "nginx", "none"}\nCERT_MODES = {"merged", "separate"}\nLISTRAW_HEADER =',
    'cert mode constant',
)

old_domain_block = '''def parse_domains(spec):
    spec = spec.replace("\\r", " ").replace("\\n", " ")
    domains = spec.split()
    if not domains:
        die(_('domain list is empty'))
    for domain in domains:
        if domain.startswith("-"):
            die(_('invalid domain token: {}').format(domain))
    return domains


def show_domains(domains):
    eprint("")
    eprint(_('Domains on this certificate (one certificate / one private key):'))
    for index, domain in enumerate(domains, 1):
        eprint("  {}. {}".format(index, domain))
    if any(domain.startswith("*.") for domain in domains):
        eprint(_('Tip: *.example.com does not cover example.com; add the base domain separately when needed.'))


def sanitize_cert_name(domain):
    name = domain[2:] if domain.startswith("*.") else domain
    name = name.replace("/", "_").replace("\\t", "_").replace(" ", "_")
    return name if name not in ("", ".", "..") else "certificate"
'''

new_domain_block = '''def parse_domains(spec):
    spec = spec.replace("\\r", " ").replace("\\n", " ")
    domains = spec.split()
    if not domains:
        die(_('domain list is empty'))
    for domain in domains:
        if domain.startswith("-"):
            die(_('invalid domain token: {}').format(domain))
    return domains


def validate_cert_mode(value):
    if value not in CERT_MODES:
        die(_('certificate mode must be merged or separate: {}').format(value))


def choose_cert_mode(domains, current="merged"):
    validate_cert_mode(current)
    if len(domains) <= 1:
        return current
    eprint("")
    eprint(_('Multiple domains detected. Choose how certificates should be grouped.'))
    return choose_action(_('Certificate mode'), [
        ("merged", 'One SAN certificate containing all entered names'),
        ("separate", 'One independent certificate per entered name'),
    ], current)


def show_domains(domains, cert_mode="merged"):
    eprint("")
    if cert_mode == "separate" and len(domains) > 1:
        eprint(_('Domains to issue as separate certificates (one certificate / one private key per name):'))
    else:
        eprint(_('Domains on this certificate (one certificate / one private key):'))
    for index, domain in enumerate(domains, 1):
        eprint("  {}. {}".format(index, domain))
    if any(domain.startswith("*.") for domain in domains):
        eprint(_('Tip: *.example.com does not cover example.com; add the base domain separately when needed.'))


def sanitize_cert_name(domain):
    name = domain[2:] if domain.startswith("*.") else domain
    name = name.replace("/", "_").replace("\\t", "_").replace(" ", "_")
    return name if name not in ("", ".", "..") else "certificate"


def separate_cert_names(domains):
    names = []
    used = set()
    for domain in domains:
        stem = sanitize_cert_name(domain)
        if domain.startswith("*."):
            stem = "wildcard-" + stem
        candidate = stem
        suffix = 2
        while candidate.lower() in used:
            candidate = "{}-{}".format(stem, suffix)
            suffix += 1
        used.add(candidate.lower())
        names.append(candidate)
    return names


def validate_separate_domains(domains):
    seen = set()
    for domain in domains:
        key = domain.lower()
        if key in seen:
            die(_('Separate certificate mode requires unique domains; duplicate: {}').format(domain))
        seen.add(key)
'''
core = replace_exact(core, old_domain_block, new_domain_block, 'domain helpers')

shortcut_pattern = r'def _issue_shortcut_args\(result, domains, extra_preview=None\):\n.*?(?=\n\ndef _upstream_command_available)'
shortcut_replacement = '''def _issue_shortcut_args(result, domains, extra_preview=None):
    args = ["issue", "--server", result["server"], "--keylength", result["keylength"]]
    if result.get("cert_mode", "merged") != "merged":
        args.extend(["--cert-mode", result["cert_mode"]])
    mode = result.get("mode", "dns")
    if mode == "dns":
        args.extend(["--dns", result["dns"], "--dnssleep", result["delay"]])
    elif mode == "webroot":
        args.extend(["--webroot", result["validation_value"]])
    elif mode == "standalone":
        args.append("--standalone")
    elif mode == "alpn":
        args.append("--alpn")
    elif mode == "stateless":
        args.append("--stateless")
    elif mode == "apache":
        args.append("--apache")
    elif mode == "nginx":
        args.append("--nginx")
        if result.get("validation_value"):
            args.extend(["--nginx-config", result["validation_value"]])
    elif mode == "dns-manual":
        args.append("--manual-dns")
    elif mode == "dns-persist":
        args.append("--dns-persist")
    args.extend(["--output-layout", result["layout"]])
    if result["layout"] != "none":
        args.extend(["--output-root", result["output_root"]])
        if result.get("cert_name"):
            args.extend(["--cert-name", result["cert_name"]])
    if result.get("reloadcmd"):
        args.extend(["--reloadcmd", result["reloadcmd"]])
    args.append(" ".join(domains))
    if extra_preview:
        args.append("--")
        args.extend(extra_preview)
    return args
'''
core = replace_regex(core, shortcut_pattern, shortcut_replacement, 'issue shortcut')

core = replace_exact(
    core,
    '        "cert_name": "",\n        "reloadcmd": "",',
    '        "cert_name": "",\n        "cert_mode": "merged",\n        "reloadcmd": "",',
    'parse result cert mode',
)
core = replace_exact(
    core,
    '                   "-format", "--output-layout", "-reload", "--reloadcmd"):',
    '                   "-format", "--output-layout", "--cert-mode", "-reload", "--reloadcmd"):',
    'parse option list',
)
core = replace_exact(
    core,
    '            elif arg in ("-format", "--output-layout"):\n                result["layout"] = value\n            elif arg in ("-reload", "--reloadcmd"):',
    '            elif arg in ("-format", "--output-layout"):\n                result["layout"] = value\n            elif arg == "--cert-mode":\n                result["cert_mode"] = value\n            elif arg in ("-reload", "--reloadcmd"):',
    'parse cert mode assignment',
)

new_guided = '''def guided_issue(result):
    result["interactive"] = True
    eprint("")
    eprint(_('=== Detailed certificate wizard ==='))
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
        if result["cert_mode"] == "separate" and len(domains) > 1:
            result["cert_name"] = ""
            eprint(_('  Separate mode creates one output directory per domain automatically.'))
        else:
            default_name = sanitize_cert_name(domains[0])
            result["cert_name"] = prompt_validated_default(_('Certificate directory name'), default_name, validate_cert_name)
    eprint(_('  reloadcmd is optional. It runs after successful issuance and subsequent successful renewals.'))
    result["reloadcmd"] = prompt_line(_('Reload command (optional): '))

    eprint("")
    eprint(_('[5/5] Advanced'))
    eprint(_('  Select additional options from the installed acme.sh --help.'))
    result["advanced"] = prompt_yes_no(_('Add other upstream parameters?'), "n")
    return domains
'''
core = replace_regex(core, r'def guided_issue\(result\):\n.*?(?=\n\ndef issue\(args\):)', new_guided, 'guided issue')

new_issue = '''def _issue_plans(result, domains):
    validate_cert_mode(result.get("cert_mode", "merged"))
    if result["cert_mode"] == "separate" and len(domains) > 1:
        if result.get("cert_name"):
            die(_('--cert-name cannot be used with multiple separate certificates; output directory names are generated per domain'))
        validate_separate_domains(domains)
        names = separate_cert_names(domains)
        return [
            {"domains": [domain], "cert_name": name,
             "paths": output_paths(result["output_root"], name, result["layout"])}
            for domain, name in zip(domains, names)
        ]
    name = result.get("cert_name") or sanitize_cert_name(domains[0])
    return [{"domains": list(domains), "cert_name": name,
             "paths": output_paths(result["output_root"], name, result["layout"])}]


def _show_issue_output_plan(plans, layout, cert_mode):
    if cert_mode != "separate" or len(plans) == 1:
        show_output(plans[0]["paths"], layout)
        return
    eprint("")
    eprint(_('Output plan:'))
    for plan in plans:
        domain = plan["domains"][0]
        if layout == "none":
            eprint(_('  {} -> internal acme.sh storage').format(domain))
        else:
            eprint(_('  {} -> {}').format(domain, plan["paths"]["dir"]))


def _build_issue_command(result, domains, paths, extra):
    cmd = [find_acme_sh(), "--issue", "--server", result["server"], "--keylength", result["keylength"]]
    mode = result["mode"]
    if mode == "dns":
        cmd.extend(["--dns", result["dns"], "--dnssleep", result["delay"]])
    elif mode == "webroot":
        cmd.extend(["--webroot", result["validation_value"]])
    elif mode == "standalone":
        cmd.append("--standalone")
    elif mode == "alpn":
        cmd.append("--alpn")
    elif mode == "stateless":
        cmd.append("--stateless")
    elif mode == "apache":
        cmd.append("--apache")
    elif mode == "nginx":
        cmd.append("--nginx")
        if result["validation_value"]:
            cmd.append(result["validation_value"])
    elif mode == "dns-manual":
        cmd.extend(["--dns", "--yes-I-know-dns-manual-mode-enough-go-ahead-please"])
    elif mode == "dns-persist":
        cmd.append("--dns-persist")
    for domain in domains:
        cmd.extend(["-d", domain])
    if paths["cert"]:
        cmd.extend(["--cert-file", paths["cert"]])
    if paths["key"]:
        cmd.extend(["--key-file", paths["key"]])
    if paths["ca"]:
        cmd.extend(["--ca-file", paths["ca"]])
    if paths["fullchain"]:
        cmd.extend(["--fullchain-file", paths["fullchain"]])
    if result["reloadcmd"]:
        cmd.extend(["--reloadcmd", result["reloadcmd"]])
    cmd.extend(extra)
    return cmd


def issue(args):
    find_acme_sh()
    refresh_defaults()
    result = parse_issue_cli(args)
    if not result["spec"]:
        domains = guided_issue(result)
    else:
        domains = parse_domains(result["spec"])

    validate_cert_mode(result.get("cert_mode", "merged"))
    if not result["server"]:
        die(_('server cannot be empty'))
    validate_choice(result.get("mode", "dns"), {"dns","webroot","standalone","alpn","stateless","apache","nginx","dns-manual","dns-persist"}, "validation mode")
    if result["mode"] == "dns":
        if not result["dns"]:
            die(_('DNS provider cannot be empty'))
        provider = find_dns_provider(result["dns"])
        result["dns"] = provider["id"]
        validate_delay(result["delay"])
    elif result["mode"] == "webroot" and not result["validation_value"]:
        die(_('webroot validation requires a path'))
    validate_keylength(result["keylength"])
    validate_layout(result["layout"])
    if result.get("cert_name"):
        validate_cert_name(result["cert_name"])

    validate_extra_issue_args(result["extra"])
    extra = list(result["extra"])
    extra_preview = list(result["extra"])
    if result["advanced"]:
        unused_commands, params = parse_upstream_help()
        selected, preview = parameter_editor(params, skip_managed=True)
        extra.extend(selected)
        extra_preview.extend(preview)

    plans = _issue_plans(result, domains)
    show_domains(domains, result["cert_mode"])
    eprint("")
    eprint(_('Issuance settings:'))
    eprint(_('  server      {}').format(result["server"]))
    eprint(_('  certificate mode {}').format(result["cert_mode"]))
    eprint(_('  validation  {}').format(result["mode"]))
    if result["mode"] == "dns":
        eprint(_('  dns         {}').format(result["dns"]))
        eprint(_('  dnssleep    {} seconds').format(result["delay"]))
    elif result.get("validation_value"):
        eprint(_('  validation value {}').format(result["validation_value"]))
    eprint(_('  keylength   {}').format(result["keylength"]))
    if result["reloadcmd"]:
        eprint(_('  reloadcmd   {}').format(result["reloadcmd"]))
    _show_issue_output_plan(plans, result["layout"], result["cert_mode"])
    if extra_preview:
        eprint(_('  Extra upstream parameters: {}').format(quote_preview(extra_preview)))

    if result["interactive"] and sys.stdin.isatty():
        shortcut = _issue_shortcut_args(result, domains, extra_preview)
        note = None
        if "[hidden]" in shortcut:
            note = "Secret values are not printed. Replace [hidden] securely before reusing this shortcut."
        show_cli_shortcut(shortcut, note)
        if result["cert_mode"] == "separate" and len(plans) > 1:
            confirmed = prompt_yes_no(_('Start issuing {} separate certificates?').format(len(plans)), "y")
        else:
            confirmed = prompt_yes_no(_('Start issuing the certificate?'), "y")
        if not confirmed:
            eprint(_('acme: cancelled'))
            return 0

    for plan in plans:
        check_output_conflict(plan["paths"], plan["domains"][0], result["keylength"])

    completed = 0
    for index, plan in enumerate(plans, 1):
        if len(plans) > 1:
            eprint("")
            eprint(_('Issuing certificate {}/{}: {}').format(index, len(plans), plan["domains"][0]))
        ensure_output_dir(plan["paths"])
        rc = subprocess.call(_build_issue_command(result, plan["domains"], plan["paths"], extra))
        if rc != 0:
            eprint("")
            if len(plans) > 1:
                eprint(_('acme: certificate {}/{} failed for {}, acme.sh exit={}').format(index, len(plans), plan["domains"][0], rc))
                if completed:
                    eprint(_('acme: batch stopped after {}/{} certificates succeeded; successful certificates remain managed and are not rolled back.').format(completed, len(plans)))
            elif rc == 2:
                eprint(_('acme: acme.sh returned 2 (not due / unchanged). No new certificate was issued; inspect the upstream output.'))
            else:
                eprint(_('acme: certificate issue failed, acme.sh exit={}').format(rc))
            return rc
        try:
            write_domains_manifest(plan["paths"], plan["domains"])
        except Exception as exc:
            eprint(_('acme: warning: certificate succeeded but domains.txt could not be written: {}').format(exc))
        completed += 1

    eprint("")
    eprint(_('=== Complete ==='))
    if len(plans) > 1:
        eprint(_('{} separate certificates issued successfully.').format(len(plans)))
    else:
        eprint(_('Certificate issued successfully.'))
    eprint(_('Check renewal scheduling with acme cron status. New installations leave cron off; enable it explicitly or schedule manual renewal.'))
    _show_issue_output_plan(plans, result["layout"], result["cert_mode"])
    return 0
'''
core = replace_regex(core, r'def issue\(args\):\n.*?(?=\n\ndef _dnsapi_dirs)', new_issue, 'issue execution')

new_quick = '''def quick_issue(args):
    if args:
        return issue(args)
    find_acme_sh()
    refresh_defaults()
    eprint(_('Quick certificate: enter one or more names; with multiple names you can choose one SAN certificate or separate certificates.'))
    eprint(_('A wildcard such as *.example.com does not include example.com. Add both when needed.'))
    spec = prompt_validated_required(_('Domains, separated by spaces'), parse_domains)
    domains = parse_domains(spec)
    cert_mode = choose_cert_mode(domains, "merged")
    provider_id = _provider_choice(DEFAULT_DNS)
    provider = find_dns_provider(provider_id)
    configured = _provider_status(provider, _read_conf_text(resolve_account_conf(find_acme_sh())))
    if configured not in ("configured", "runtime-ready"):
        eprint(_('Credential status: {}. This is a local configuration check, not an API authentication test.').format(configured))
        if provider.get("groups") and prompt_yes_no(_('Configure this DNS provider now?'), "y"):
            configure_provider(provider_id)
        else:
            eprint(_('Supply the provider credentials through acme config or the upstream environment before issuance.'))
    eprint(_('Using saved settings: CA={}, DNS wait={}s, key={}, layout={}, output={}').format(DEFAULT_SERVER, DEFAULT_DELAY, DEFAULT_KEY_LENGTH, DEFAULT_OUTPUT_LAYOUT, DEFAULT_OUTPUT_ROOT))
    eprint(_('For HTTP validation or custom settings, use the detailed issue wizard from Advanced tools.'))
    shortcut_result = {
        "server": DEFAULT_SERVER, "mode": "dns", "dns": provider_id, "delay": DEFAULT_DELAY,
        "keylength": DEFAULT_KEY_LENGTH, "layout": DEFAULT_OUTPUT_LAYOUT, "output_root": DEFAULT_OUTPUT_ROOT,
        "cert_name": sanitize_cert_name(domains[0]) if cert_mode == "merged" or len(domains) == 1 else "",
        "cert_mode": cert_mode, "reloadcmd": "",
    }
    show_cli_shortcut(_issue_shortcut_args(shortcut_result, domains))
    if cert_mode == "separate" and len(domains) > 1:
        confirmed = prompt_yes_no(_('Start issuing {} separate certificates?').format(len(domains)), "n")
    else:
        confirmed = prompt_yes_no(_('Start issuing this certificate?'), "n")
    if not confirmed:
        eprint(_('acme: cancelled; no certificate request was sent'))
        return 0
    return issue(["-dns", provider_id, "--cert-mode", cert_mode, spec])
'''
core = replace_regex(core, r'def quick_issue\(args\):\n.*?(?=\n\ndef _interactive_rollback)', new_quick, 'quick issue')

core = replace_exact(
    core,
    '    "quick": "acme quick [\\"DOMAIN ...\\"]",\n    "issue": "acme issue [--validation MODE] [-dns PROVIDER] [-out DIR] [-name NAME] [-format LAYOUT] [\\"DOMAIN ...\\"] [SECONDS] [-- NATIVE_OPTIONS]",',
    '    "quick": "acme quick [--cert-mode merged|separate] [\\"DOMAIN ...\\"]",\n    "issue": "acme issue [--cert-mode merged|separate] [--validation MODE] [-dns PROVIDER] [-out DIR] [-name NAME] [-format LAYOUT] [\\"DOMAIN ...\\"] [SECONDS] [-- NATIVE_OPTIONS]",',
    'subcommand help',
)

core_path.write_text(core)

messages_en = {
    '  Enter one or more names separated by spaces.': '  Enter one or more names separated by spaces.',
    '  Multiple names can be merged into one SAN certificate or issued separately.': '  Multiple names can be merged into one SAN certificate or issued separately.',
    '  Separate mode creates one output directory per domain automatically.': '  Separate mode creates one output directory per domain automatically.',
    '  certificate mode {}': '  certificate mode {}',
    '  {} -> {}': '  {} -> {}',
    '  {} -> internal acme.sh storage': '  {} -> internal acme.sh storage',
    '--cert-name cannot be used with multiple separate certificates; output directory names are generated per domain': '--cert-name cannot be used with multiple separate certificates; output directory names are generated per domain',
    'Certificate mode': 'Certificate mode',
    'Domains to issue as separate certificates (one certificate / one private key per name):': 'Domains to issue as separate certificates (one certificate / one private key per name):',
    'Issuing certificate {}/{}: {}': 'Issuing certificate {}/{}: {}',
    'Multiple domains detected. Choose how certificates should be grouped.': 'Multiple domains detected. Choose how certificates should be grouped.',
    'One SAN certificate containing all entered names': 'One SAN certificate containing all entered names',
    'One independent certificate per entered name': 'One independent certificate per entered name',
    'Output plan:': 'Output plan:',
    'Quick certificate: enter one or more names; with multiple names you can choose one SAN certificate or separate certificates.': 'Quick certificate: enter one or more names; with multiple names you can choose one SAN certificate or separate certificates.',
    'Separate certificate mode requires unique domains; duplicate: {}': 'Separate certificate mode requires unique domains; duplicate: {}',
    'Start issuing {} separate certificates?': 'Start issuing {} separate certificates?',
    'Supports DNS, webroot, standalone, ALPN, Apache/Nginx, manual DNS, DNS persist, multiple SANs and separate certificates. Enter accepts the default in brackets.': 'Supports DNS, webroot, standalone, ALPN, Apache/Nginx, manual DNS, DNS persist, multiple SANs and separate certificates. Enter accepts the default in brackets.',
    'acme: batch stopped after {}/{} certificates succeeded; successful certificates remain managed and are not rolled back.': 'acme: batch stopped after {}/{} certificates succeeded; successful certificates remain managed and are not rolled back.',
    'acme: certificate {}/{} failed for {}, acme.sh exit={}': 'acme: certificate {}/{} failed for {}, acme.sh exit={}',
    'certificate mode must be merged or separate: {}': 'certificate mode must be merged or separate: {}',
    '{} separate certificates issued successfully.': '{} separate certificates issued successfully.',
}
messages_zh = {
    '  Enter one or more names separated by spaces.': '  輸入一個或多個網域，使用空白分隔。',
    '  Multiple names can be merged into one SAN certificate or issued separately.': '  多個名稱可合併為一張 SAN 憑證，或各自簽發獨立憑證。',
    '  Separate mode creates one output directory per domain automatically.': '  獨立模式會依每個網域自動建立不同輸出目錄。',
    '  certificate mode {}': '  憑證模式    {}',
    '  {} -> {}': '  {} -> {}',
    '  {} -> internal acme.sh storage': '  {} -> 僅使用 acme.sh 內部儲存',
    '--cert-name cannot be used with multiple separate certificates; output directory names are generated per domain': '多張獨立憑證不能共用 --cert-name；輸出目錄會依各網域自動產生',
    'Certificate mode': '憑證模式',
    'Domains to issue as separate certificates (one certificate / one private key per name):': '將分別簽發以下網域（每個名稱各一張憑證／一把私鑰）：',
    'Issuing certificate {}/{}: {}': '正在簽發第 {}/{} 張：{}',
    'Multiple domains detected. Choose how certificates should be grouped.': '偵測到多個網域。請選擇憑證組合方式。',
    'One SAN certificate containing all entered names': '所有名稱合併為一張 SAN 憑證',
    'One independent certificate per entered name': '每個輸入名稱各自一張獨立憑證',
    'Output plan:': '輸出規劃：',
    'Quick certificate: enter one or more names; with multiple names you can choose one SAN certificate or separate certificates.': '快速簽發：輸入一個或多個網域；多個網域時可選擇合併 SAN 或各自獨立憑證。',
    'Separate certificate mode requires unique domains; duplicate: {}': '獨立憑證模式要求網域不可重複；重複：{}',
    'Start issuing {} separate certificates?': '開始簽發 {} 張獨立憑證？',
    'Supports DNS, webroot, standalone, ALPN, Apache/Nginx, manual DNS, DNS persist, multiple SANs and separate certificates. Enter accepts the default in brackets.': '支援 DNS、webroot、standalone、ALPN、Apache/Nginx、manual DNS、DNS persist、多 SAN 與獨立憑證；括號中的值可直接按 Enter 採用。',
    'acme: batch stopped after {}/{} certificates succeeded; successful certificates remain managed and are not rolled back.': 'acme: 批次已停止；{}/{} 張已成功，成功的憑證會保留在 acme.sh 管理中，不會自動回滾。',
    'acme: certificate {}/{} failed for {}, acme.sh exit={}': 'acme: 第 {}/{} 張憑證 {} 簽發失敗，acme.sh exit={}',
    'certificate mode must be merged or separate: {}': '憑證模式只能是 merged 或 separate：{}',
    '{} separate certificates issued successfully.': '{} 張獨立憑證全部簽發成功。',
}
for rel, additions in [('locales/en.json', messages_en), ('locales/zh-TW.json', messages_zh)]:
    path = ROOT / rel
    data = json.loads(path.read_text())
    data.update(additions)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

review_path = ROOT / 'tests/review_v19.py'
review = review_path.read_text()
review = replace_exact(
    review,
    "                s.expect(ui('Domains, separated by spaces')).line('quick.test *.quick.test')\n                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('/namesilo')",
    "                s.expect(ui('Domains, separated by spaces')).line('quick.test *.quick.test')\n                s.expect(ui('Certificate mode')).expect(chooser).line('separate')\n                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('/namesilo')",
    'review quick cert mode prompt',
)
review = replace_exact(
    review,
    "(\"acme issue --server letsencrypt --keylength ec-256 --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root \" + e['ACME_OUTPUT_ROOT'] + \" --cert-name quick.test 'quick.test *.quick.test'\")",
    "(\"acme issue --server letsencrypt --keylength ec-256 --cert-mode separate --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root \" + e['ACME_OUTPUT_ROOT'] + \" 'quick.test *.quick.test'\")",
    'review quick separate shortcut',
)
review_path.write_text(review)

flow_path = ROOT / 'tests/flow_matrix.py'
flow = flow_path.read_text()
flow = replace_exact(
    flow,
    "            s.expect('Domains:').line('*.pty1.test *.pty2.test')\n            s.expect('ACME Server').line('')",
    "            s.expect('Domains:').line('*.pty1.test *.pty2.test')\n            s.expect('Certificate mode').expect('Choose a number or command').line('merged')\n            s.expect('ACME Server').line('')",
    'flow detailed merged choice',
)
flow_path.write_text(flow)

test_path = ROOT / 'tests/review_cert_modes.py'
test_path.write_text(r'''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import stat
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
        wrapper.write_text(r'''#!/usr/bin/env bash
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
''')
        wrapper.chmod(0o755)
        shutil.copytree(str(ROOT / 'tests' / 'dnsapi'), str(upstream / 'dnsapi'))
        history = td / 'history.log'
        output = td / 'out'
        account = td / 'account.conf'
        account.write_text("SAVED_Namesilo_Key='test-only'\n")
        env = os.environ.copy()
        env.update({
            'ACME_SH_BIN': str(wrapper),
            'REAL_MOCK': str(real_mock),
            'MOCK_HISTORY': str(history),
            'MOCK_LOG': str(td / 'argv.log'),
            'ACME_OUTPUT_ROOT': str(output),
            'ACME_ACCOUNT_CONF': str(account),
            'ACME_WRAPPER_CONFIG': str(td / 'wrapper.ini'),
            'ACME_HELPER_LANG': 'en',
            'HOME': str(td / 'home'),
            'TMPDIR': str(td / 'tmp'),
        })
        Path(env['HOME']).mkdir()
        Path(env['TMPDIR']).mkdir()

        def run(args, extra=None):
            if history.exists():
                history.unlink()
            merged = env.copy()
            merged.update(extra or {})
            return subprocess.run([ACME] + args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged, timeout=40)

        p = run(['issue', '--output-layout', 'none', 'a.test b.test'])
        calls = issue_calls(history)
        t.check('backward-default-merged', p.returncode == 0 and len(calls) == 1 and domain_args(calls[0]) == ['a.test', 'b.test'], p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'merged', '--output-layout', 'none', 'a.test b.test'])
        calls = issue_calls(history)
        t.check('explicit-merged-one-upstream-request', p.returncode == 0 and len(calls) == 1 and domain_args(calls[0]) == ['a.test', 'b.test'], p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'a.test b.test c.test'])
        calls = issue_calls(history)
        t.check('separate-one-request-per-domain', p.returncode == 0 and [domain_args(row) for row in calls] == [['a.test'], ['b.test'], ['c.test']], p.stderr[-1200:])

        p = run(['quick', '--cert-mode', 'separate', '--output-layout', 'none', 'q1.test q2.test'])
        calls = issue_calls(history)
        t.check('quick-cli-supports-separate', p.returncode == 0 and [domain_args(row) for row in calls] == [['q1.test'], ['q2.test']], p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'invalid', '--output-layout', 'none', 'a.test b.test'])
        t.check('invalid-mode-refused-before-upstream', p.returncode == 2 and not issue_calls(history), p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'dup.test DUP.test'])
        t.check('separate-duplicate-refused', p.returncode == 2 and not issue_calls(history) and 'duplicate' in p.stderr.lower(), p.stderr[-1200:])

        p = run(['issue', '--cert-mode', 'separate', '--cert-name', 'shared', '--output-layout', 'minimal', 'a.test b.test'])
        t.check('shared-cert-name-refused-for-separate-batch', p.returncode == 2 and not issue_calls(history), p.stderr[-1200:])

        shutil.rmtree(output, ignore_errors=True)
        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'minimal', 'example.test *.example.test wildcard-example.test'])
        expected = {
            'example.test': output / 'example.test' / 'domains.txt',
            '*.example.test': output / 'wildcard-example.test' / 'domains.txt',
            'wildcard-example.test': output / 'wildcard-example.test-2' / 'domains.txt',
        }
        ok = p.returncode == 0
        for domain, path in expected.items():
            ok = ok and path.is_file() and path.read_text().strip() == domain
        t.check('separate-output-names-are-deterministic-and-collision-safe', ok, p.stderr[-1600:])

        p = run(['issue', '--cert-mode', 'separate', '--output-layout', 'none', 'ok.test fail.test later.test'], {'CERT_MODE_FAIL_DOMAIN': 'fail.test'})
        calls = issue_calls(history)
        t.check('batch-stops-on-first-failure-with-partial-state-explicit', p.returncode == 17 and [domain_args(row) for row in calls] == [['ok.test'], ['fail.test']] and '1/3 certificates succeeded' in p.stderr and 'not rolled back' in p.stderr, p.stderr[-1800:])

    return t.finish()


if __name__ == '__main__':
    raise SystemExit(main())
''')
test_path.chmod(0o755)

run_all_path = ROOT / 'tests/run_all.py'
run_all = run_all_path.read_text()
run_all = replace_exact(
    run_all,
    "suites = ['ablation','adversarial','flow_matrix','review_v19','review_v110','review_issue_diagnostics']",
    "suites = ['ablation','adversarial','flow_matrix','review_v19','review_v110','review_issue_diagnostics','review_cert_modes']",
    'run_all suite list',
)
run_all = replace_exact(
    run_all,
    "'diagnostic': ['ablation','adversarial','review_v19','review_v110','review_issue_diagnostics'],",
    "'diagnostic': ['ablation','adversarial','review_v19','review_v110','review_issue_diagnostics','review_cert_modes'],",
    'diagnostic profile',
)
run_all = replace_exact(
    run_all,
    "        'review_issue_diagnostics': 240,\n        'adversarial': 240,",
    "        'review_issue_diagnostics': 240,\n        'review_cert_modes': 240,\n        'adversarial': 240,",
    'suite timeout',
)
run_all_path.write_text(run_all)

readme_path = ROOT / 'README.md'
readme = readme_path.read_text()
readme = replace_exact(
    readme,
    '安裝內容是 `<PREFIX>/bin/acme`、`<PREFIX>/lib/acme/acme_cli.py` 與 `<PREFIX>/lib/acme/locales/*.json`。請勿只複製 launcher；缺少語系檔會退回英文，缺少核心則無法執行。',
    '安裝內容是 `<PREFIX>/bin/acme`、`<PREFIX>/lib/acme/acme_cli.py`、`<PREFIX>/lib/acme/acme_runtime.py` 與 `<PREFIX>/lib/acme/locales/*.json`。請勿只複製 launcher；缺少語系檔會退回英文，缺少核心則無法執行；缺少 runtime 時 `issue/quick` 仍可相容執行，但不具自動失敗診斷。',
    'zh install docs',
)
readme = replace_exact(
    readme,
    '之後選 1，輸入網域、選擇實際代管 DNS 的服務商。缺少認證資料時，可直接進入安全輸入流程。搜尋用 `/cloud` 之類的關鍵字，列出結果後輸入編號，不必背 `dns_cf`。',
    '之後選 1，輸入網域；輸入多個網域時可選 `merged`（全部 SAN 合併為一張憑證）或 `separate`（每個輸入名稱各自一張憑證），再選擇實際代管 DNS 的服務商。缺少認證資料時，可直接進入安全輸入流程。搜尋用 `/cloud` 之類的關鍵字，列出結果後輸入編號，不必背 `dns_cf`。',
    'zh quick docs',
)
readme = replace_exact(
    readme,
    'acme -out /srv/ssl -format nginx "example.com *.example.com"\nacme config defaults',
    'acme -out /srv/ssl -format nginx "example.com *.example.com"\nacme issue --cert-mode merged "example.com *.example.com"\nacme issue --cert-mode separate "example.com *.example.com api.example.com"\nacme config defaults',
    'zh CLI examples',
)
readme = replace_exact(
    readme,
    '`*.example.com` 不涵蓋 `example.com` 或多一層的 `www.api.example.com`。一個命令裡的所有網域共用一張憑證與私鑰。',
    '`*.example.com` 不涵蓋 `example.com` 或多一層的 `www.api.example.com`。多網域預設維持 `merged`，所有名稱共用一張 SAN 憑證與私鑰；指定 `--cert-mode separate` 時，每個輸入名稱會各自建立一張憑證與私鑰。獨立模式會自動為每張憑證建立輸出目錄；`*.example.com` 使用 `wildcard-example.com` 避免與 `example.com` 撞名，若仍有名稱碰撞會加上 `-2`、`-3`。多張獨立憑證不能共用 `--cert-name`。批次遇到第一個簽發錯誤就停止後續請求；先前已成功的憑證會保留，不做可能造成更多外部副作用的自動回滾。',
    'zh cert mode semantics',
)
readme_path.write_text(readme)

readme_en_path = ROOT / 'README.en.md'
readme_en = readme_en_path.read_text()
readme_en = replace_exact(
    readme_en,
    'The quick wizard asks for domains, lets you search providers with `/term`, and offers credential setup when local values are missing. Installation is a separate explicit operation. Email is optional; new cron installation is off.',
    'The quick wizard asks for domains. When more than one name is entered it offers `merged` (one SAN certificate) or `separate` (one independent certificate per entered name), then lets you search providers with `/term` and offers credential setup when local values are missing. Installation is a separate explicit operation. Email is optional; new cron installation is off.',
    'en quick docs',
)
readme_en = replace_exact(
    readme_en,
    'acme -dns dns_cf "example.com *.example.com"\nacme certs',
    'acme -dns dns_cf "example.com *.example.com"\nacme issue --cert-mode merged "example.com *.example.com"\nacme issue --cert-mode separate "example.com *.example.com api.example.com"\nacme certs',
    'en CLI examples',
)
readme_en = replace_exact(
    readme_en,
    "Defaults remain Let's Encrypt, dns_namesilo, 120-second DNS wait, ec-256 and minimal PEM output. All names in one issuance share one certificate. A wildcard does not include its base name. `domains.txt` is retained as a requested-SAN manifest, not an authoritative certificate database. Known managed-certificate output collisions are refused.",
    "Defaults remain Let's Encrypt, dns_namesilo, 120-second DNS wait, ec-256 and minimal PEM output. Multiple names default to `merged`, where all names share one SAN certificate. `--cert-mode separate` issues one certificate per entered name. Wildcard/base pairs receive distinct deterministic output directories (`*.example.com` becomes `wildcard-example.com`); remaining collisions receive `-2`, `-3`, and so on. A shared `--cert-name` is rejected for a multi-certificate separate batch. The batch stops on the first issuance error and does not roll back certificates that already succeeded. A wildcard does not include its base name. `domains.txt` is retained as a requested-SAN manifest, not an authoritative certificate database. Known managed-certificate output collisions are refused.",
    'en cert mode semantics',
)
readme_en_path.write_text(readme_en)

coverage_path = ROOT / 'FEATURE_COVERAGE.md'
coverage = coverage_path.read_text()
coverage = replace_exact(
    coverage,
    '| 快速 DNS 簽發 | 一個任務精靈、預設值、搜尋編號、缺少設定時引導輸入 | 中英雙語 PTY、取消、成功、argv 一致測試 |',
    '| 快速 DNS 簽發 | 一個任務精靈、預設值、搜尋編號、缺少設定時引導輸入；多網域可選 merged SAN 或 separate 獨立憑證 | 中英雙語 PTY、取消、成功、argv 一致測試；獨立模式逐域名 request、碰撞與部分失敗回歸 |',
    'coverage quick row',
)
coverage = replace_exact(
    coverage,
    '| 憑證/SAN | 列全部網域、讀取、續期、安裝、部署、撤銷、停用授權、移除管理 | RSA/ECC 選取身分不再二次查找；跨憑證輸出路徑防衝突 |',
    '| 憑證/SAN | 列全部網域、讀取、續期、安裝、部署、撤銷、停用授權、移除管理；簽發可選單張多 SAN 或逐名稱獨立憑證 | RSA/ECC 選取身分不再二次查找；跨憑證輸出路徑防衝突；wildcard/base 獨立輸出不撞名 |',
    'coverage cert row',
)
coverage = replace_exact(
    coverage,
    '| 安裝資源 | 自訂 PREFIX、核心與兩份語系檔一起安裝 | 完整安裝流程測試，非僅工作目錄直接執行 |',
    '| 安裝資源 | 自訂 PREFIX、launcher、核心、runtime 與兩份語系檔一起安裝 | 完整安裝流程測試，非僅工作目錄直接執行 |',
    'coverage install row',
)
coverage_path.write_text(coverage)

normal_workflow = '''name: Offline regression

on:
  push:
    branches:
      - main
      - "fix/**"
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
      - name: Verify repository checksums
        run: sha256sum -c SHA256SUMS
      - name: Prepare system fallback fixture path
        run: |
          sudo install -d -m 755 /usr/local/lib/acme
          sudo chown "$(id -u):$(id -g)" /usr/local/lib/acme
      - name: Run full offline regression
        run: python3 -S tests/run_all.py --report-dir test-results
      - name: Print regression logs on failure
        if: failure() && hashFiles('test-results/*.log') != ''
        run: |
          for file in test-results/*.log; do
            echo "===== $file ====="
            cat "$file"
          done
'''
(ROOT / '.github/workflows/offline-regression.yml').write_text(normal_workflow)

manifest_path = ROOT / 'SHA256SUMS'
lines = manifest_path.read_text().splitlines()
paths = []
for line in lines:
    parts = line.split('  ', 1)
    if len(parts) != 2:
        raise SystemExit('invalid SHA256SUMS line: ' + line)
    paths.append(parts[1])
new_entry = './tests/review_cert_modes.py'
if new_entry not in paths:
    insert_at = paths.index('./tests/review_issue_diagnostics.py') if './tests/review_issue_diagnostics.py' in paths else len(paths)
    paths.insert(insert_at, new_entry)
updated = []
for rel in paths:
    file_path = ROOT / rel[2:] if rel.startswith('./') else ROOT / rel
    if not file_path.is_file():
        raise SystemExit('manifest path missing: ' + rel)
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    updated.append('{}  {}'.format(digest, rel))
manifest_path.write_text('\n'.join(updated) + '\n')

print('PATCH_APPLIED')
