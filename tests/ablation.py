#!/usr/bin/env python3
import importlib.util
import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACME = str(ROOT / "acme")
CORE = ROOT / "acme_cli.py"
MOCK = ROOT / "tests" / "mock-acme.sh"
DNS = ROOT / "tests" / "dnsapi"
checks = []


def ck(name, cond, note):
    checks.append((name, bool(cond), note))


def make_home(base, name="upstream"):
    home = pathlib.Path(base) / name
    home.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(MOCK), str(home / "acme.sh"))
    os.chmod(str(home / "acme.sh"), 0o755)
    shutil.copytree(str(DNS), str(home / "dnsapi"))
    for sub in ("deploy", "notify"):
        src = ROOT / "tests" / sub
        if src.exists(): shutil.copytree(str(src), str(home / sub))
    completion = ROOT / "tests" / "acme.sh.completion"
    if completion.exists(): shutil.copy2(str(completion), str(home / "acme.sh.completion"))
    return home


def env_for(base, home):
    return {
        "ACME_SH_BIN": str(home / "acme.sh"),
        "ACME_HELPER_LANG": "en",
        "ACME_ACCOUNT_CONF": str(pathlib.Path(base) / "account.conf"),
        "ACME_WRAPPER_CONFIG": str(pathlib.Path(base) / "wrapper.ini"),
        "ACME_OUTPUT_ROOT": str(pathlib.Path(base) / "out"),
        "ACME_VERSION_BACKUP_DIR": str(pathlib.Path(base) / "backups"),
        "MOCK_LOG": str(pathlib.Path(base) / "argv.log"),
    }


def run(args, env, data=None, executable=ACME):
    merged = os.environ.copy(); merged.update(env)
    return subprocess.run([str(executable)] + args, input=data, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged)


td = tempfile.mkdtemp(prefix="acme-v17-ablate-")
try:
    home = make_home(td)
    env = env_for(td, home)

    # A1: friendly output is UX, not issuance core.
    p = run(["-format", "none", "*.a.test"], env)
    argv = pathlib.Path(env["MOCK_LOG"]).read_text().splitlines()
    ck("A1-output-layer-optional", p.returncode == 0 and "--cert-file" not in argv and "--fullchain-file" not in argv,
       "keep friendly output because user requested it, not because issuance requires it")

    # A2: domains.txt is noncritical UX manifest.
    spec = importlib.util.spec_from_file_location("ac", str(CORE)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    os.environ.update(env)
    def fail_manifest(_paths, _domains):
        raise OSError("ablation")
    original_manifest = m.write_domains_manifest
    m.write_domains_manifest = fail_manifest
    rc = m.issue(["-out", str(pathlib.Path(td)/"manifest"), "*.m1.test *.m2.test"])
    m.write_domains_manifest = original_manifest
    ck("A2-domains-manifest-noncritical", rc == 0,
       "certificate success survives manifest failure; retain domains.txt solely for requested multi-SAN UX")

    # A3: static upstream parameter catalog is unnecessary.
    future = pathlib.Path(td) / "future-help.sh"
    src = MOCK.read_text().replace("  --password <password>             Export password.\n",
                                   "  --password <password>             Export password.\n  --future-param <value>            Future option.\n")
    future.write_text(src); os.chmod(str(future), 0o755)
    os.environ["ACME_SH_BIN"] = str(future)
    _, params = m.parse_upstream_help(str(future))
    ck("A3-static-upstream-catalog-unneeded", any(x[0] == "--future-param" for x in params) and "--future-param" not in CORE.read_text(),
       "dynamic --help parsing removes version-locked duplication")

    # A4: hidden options need only raw native passthrough.
    log = pathlib.Path(td) / "hidden.log"; e = dict(env); e["MOCK_LOG"] = str(log)
    p = run(["native", "--future-hidden", "x"], e)
    ck("A4-hidden-option-passthrough", p.returncode == 0 and log.read_text().splitlines() == ["--future-hidden", "x"],
       "do not build a second catalog for unpublished aliases")

    # A5: custom raw-byte Bash line editor stays removed.
    ck("A5-custom-line-editor-removed", not (ROOT/"read_line_edit.sh").exists() and "read_line_edit" not in CORE.read_text(),
       "stdlib input avoids maintaining a second terminal editor")

    # A6: persistent wrapper config is optional.
    absent = pathlib.Path(td) / "absent.ini"; e = dict(env); e["ACME_WRAPPER_CONFIG"] = str(absent)
    p = run(["*.fallback.test"], e)
    aa = pathlib.Path(e["MOCK_LOG"]).read_text().splitlines()
    def has_pair(argv, key, value):
        return any(argv[i:i+2] == [key, value] for i in range(len(argv)-1))
    ck("A6-persistent-config-optional", p.returncode == 0 and has_pair(aa, "--server", "letsencrypt") and has_pair(aa, "--dns", "dns_namesilo") and has_pair(aa, "--dnssleep", "120") and has_pair(aa, "--keylength", "ec-256"),
       "built-ins remain sufficient when config file is absent")

    # A7: persistent surface remains only six reusable defaults.
    core_text = CORE.read_text()
    persisted = ("server", "dns", "dnssleep", "keylength", "output_root", "output_layout")
    ck("A7-config-surface-small", all('"{}"'.format(k) in core_text for k in persisted) and "reloadcmd" not in core_text[core_text.find("def write_wrapper_defaults"):core_text.find("def configure_defaults")],
       "cert name/reload/advanced args stay per-issue")

    # A8: wrapper install does not silently perform network/upstream install.
    prefix = pathlib.Path(td) / "prefix"; ihome = pathlib.Path(td) / "install-home"; ihome.mkdir()
    ie = os.environ.copy(); ie.update({"PREFIX":str(prefix), "HOME":str(ihome)})
    q = subprocess.run([str(ROOT/"install.sh")], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ie)
    ck("A8-wrapper-upstream-install-separated", q.returncode == 0 and (prefix/"bin"/"acme").exists() and not (ihome/".acme.sh").exists(),
       "offline wrapper installation and network upstream installation stay separate")

    # A9: custom PREFIX core lookup is required by documented installation path.
    installed = prefix / "bin" / "acme"; mutated = pathlib.Path(td) / "acme-no-prefix-core"
    launch = installed.read_text().replace('elif [[ -r "$PREFIX_CORE" ]]; then\n  CORE=$PREFIX_CORE\n', '')
    mutated.write_text(launch); os.chmod(str(mutated),0o755)
    q = subprocess.run([str(mutated), "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env={"PATH":os.environ.get("PATH", ""), "HOME":str(ihome)})
    ck("A9-prefix-core-lookup-required", q.returncode != 0 and "acme_cli.py not found" in q.stderr,
       "custom-prefix support is functional, not decorative")

    # A10: no hardcoded 200+ provider table is needed. A never-seen provider appears instantly.
    fresh = home / "dnsapi" / "dns_never_seen.sh"
    fresh.write_text("dns_never_seen_info='Never Seen DNS\\nSite: never.invalid\\nOptions:\\nNEVER_TOKEN API Token\\n'\\n_f(){ _saveaccountconf_mutable NEVER_TOKEN x; }\\n")
    p = run(["providers", "never_seen"], env)
    ck("A10-static-provider-list-unneeded", p.returncode == 0 and "dns_never_seen" in p.stdout and "dns_never_seen" not in CORE.read_text(),
       "installed dnsapi files are the source of truth; future providers need no wrapper release")

    # A11: runtime-only variables should not be asked for then discarded.
    p = run(["config", "dns_runtime"], env, "")
    ck("A11-runtime-input-prompt-removed", p.returncode == 0 and 'not through this form' in p.stderr,
       "removing a meaningless secret-input step simplifies UX without losing persistence")

    # A12: alternative credential cleanup is necessary, not defensive decoration.
    acct = pathlib.Path(env["ACME_ACCOUNT_CONF"])
    p = run(["config", "dns_cf"], env, "2\nTOKEN-A\nACCOUNT-A\n\n")
    p2 = run(["config", "dns_cf"], env, "1\nKEY-B\nops@example.com\n")
    current = acct.read_text()
    ck("A12-alt-credential-cleanup-required", p.returncode == 0 and p2.returncode == 0 and "SAVED_CF_Token" not in current and "SAVED_CF_Key=" in current,
       "without clearing stale alternative groups upstream can keep preferring old credentials")

    # A13: version rollback is necessary. Wrapper switch rejects a false target and restores old program.
    vhome = make_home(td, "version-home"); ve = env_for(td, vhome); ve["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td)/"vbackups"); ve["MOCK_UPGRADE_VERSION"] = "9.9.9"
    p = run(["switch", "3.1.4"], ve)
    after = run(["version"], env_for(td, vhome))
    ck("A13-version-rollback-required", p.returncode == 3 and "acme_sh_version=3.1.5" in after.stdout,
       "a target/version mismatch would otherwise leave the newly replaced program active")

    # A14: version backups deliberately omit account/certificate material.
    secret_conf = vhome / "account.conf"; secret_conf.write_text("SAVED_SECRET='x'\n")
    certdir = vhome / "example_ecc"; certdir.mkdir(); (certdir/"example.key").write_text("PRIVATE")
    ve2 = env_for(td, vhome); ve2["ACME_ACCOUNT_CONF"] = str(secret_conf); ve2["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td)/"scope-backups")
    p = run(["switch", "3.1.4"], ve2)
    backups = list(pathlib.Path(ve2["ACME_VERSION_BACKUP_DIR"]).glob("*"))
    copied = {x.name for x in backups[-1].rglob("*")} if backups else set()
    ck("A14-backup-scope-minimal", p.returncode == 0 and "account.conf" not in copied and "example.key" not in copied and "acme.sh" in copied and "dnsapi" in copied,
       "rollback only needs program assets; copying secrets/certs would enlarge risk and storage")

    # A15: no duplicate Python-version subprocess in the tiny launcher.
    launcher = (ROOT/"acme").read_text()
    ck("A15-no-duplicate-python-version-guard", "sys.version_info" not in launcher and "python3 -c" not in launcher,
       "the core already enforces Python >=3.6; launcher only checks python3 exists")

    # A16: do not bypass upstream's own upgrade hash check with --force.
    hash_home = make_home(td, "hash-upstream")
    hash_env = env_for(td, hash_home)
    hash_env["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td) / "hash-backups")
    hash_env["MOCK_HISTORY"] = str(pathlib.Path(td) / "hash-history")
    p = run(["switch", "3.1.4"], hash_env)
    history = pathlib.Path(hash_env["MOCK_HISTORY"]).read_text() if pathlib.Path(hash_env["MOCK_HISTORY"]).exists() else ""
    ck("A16-upstream-hash-check-preserved", p.returncode == 0 and "CALL\t--upgrade\t--branch\t3.1.4" in history and "--force" not in history,
       "removing wrapper --force lets acme.sh skip unchanged refs using its own repository hash")

    # A17: already-on-target semantic releases should not create another backup/download cycle.
    before_backups = len(list(pathlib.Path(hash_env["ACME_VERSION_BACKUP_DIR"]).glob("*")))
    p = run(["update", "--version", "3.1.4"], hash_env)
    after_backups = len(list(pathlib.Path(hash_env["ACME_VERSION_BACKUP_DIR"]).glob("*")))
    ck("A17-same-version-noop", p.returncode == 0 and "already on v3.1.4" in p.stderr and after_backups == before_backups,
       "same-version updates do not add redundant backups or invoke the network path")

    # A18: email must remain optional at wrapper install boundary; do not add a second CA-account policy.
    install_slice = core_text[core_text.find("def install_acme_sh"):core_text.find("def parse_domains")]
    ck("A18-install-email-optional", 'email = ""' in install_slice and 'if email: sh_args.append("email={}".format(email))' in install_slice,
       "installation should not invent a mandatory-email rule that upstream/CA account registration does not universally require")

    # A19: cron control delegates to upstream rather than maintaining a second crontab implementation.
    cron_log = pathlib.Path(td) / "cron-argv.log"
    ce = dict(env); ce["MOCK_LOG"] = str(cron_log); ce["MOCK_CRON_STATE"] = str(pathlib.Path(td)/"cron-state")
    p = run(["cron", "on"], ce)
    ck("A19-cron-delegates-upstream", p.returncode == 0 and cron_log.read_text().splitlines() == ["--install-cronjob"],
       "retain only a thin cron switch; upstream owns the actual cron entry format")

    # A20: managed cert/SAN inventory must come from acme.sh, not wrapper domains.txt.
    certs = pathlib.Path(td) / "managed-certs.raw"
    certs.write_text("Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\n*.auth.test|ec-256|*.alt1.test,*.alt2.test||LetsEncrypt|2026-01-01|2026-03-01\n")
    infos = pathlib.Path(td) / "cert-info"; infos.mkdir()
    (infos / "_wild_.auth.test.info").write_text("Le_Domain=*.auth.test\nLe_Alt=*.alt1.test,*.alt2.test\nLe_Webroot=dns_namesilo\n")
    ae = dict(env); ae["MOCK_CERT_LIST"] = str(certs); ae["MOCK_CERT_INFO_DIR"] = str(infos)
    p = run(["certs", "list"], ae)
    ck("A20-authoritative-cert-inventory", p.returncode == 0 and "*.auth.test, *.alt1.test, *.alt2.test" in p.stdout and "dns_namesilo" in p.stdout,
       "domains.txt stays a UX manifest; read/update/delete use acme.sh managed state as source of truth")

    # A21: current upstream command surface is routed without reimplementing the commands.
    os.environ["ACME_SH_BIN"] = str(home / "acme.sh")
    commands, _ = m.parse_upstream_help(str(home / "acme.sh"))
    ck("A21-all-cli-functions-routed", all(item[0] in m.FRIENDLY_ROUTE_MAP for item in commands),
       "all help/completion-visible commands have a friendly route while execution remains upstream")

    # A22: deploy/notify hook lists are runtime-discovered, not static catalogs.
    (home / "deploy").mkdir(exist_ok=True); future_deploy = home / "deploy" / "future_ship.sh"
    future_deploy.write_text("#!/bin/sh\n# Future deploy hook\nfuture_ship_deploy(){ :; }\n")
    p = run(["hooks", "deploy", "future_ship"], env)
    ck("A22-hook-catalog-dynamic", p.returncode == 0 and "future_ship" in p.stdout and "future_ship" not in CORE.read_text(),
       "installed hook files remain the source of truth; no second deploy/notify registry")

    # A23: validation-mode wizard delegates to upstream flags rather than implementing ACME challenges itself.
    vmode_log = pathlib.Path(td) / "validation-mode.log"; ve = dict(env); ve["MOCK_LOG"] = str(vmode_log)
    p = run(["issue", "--webroot", "/srv/www", "-format", "none", "webroot.test"], ve)
    vmode_argv = vmode_log.read_text().splitlines()
    ck("A23-validation-modes-delegate", p.returncode == 0 and "--webroot" in vmode_argv and "--dns" not in vmode_argv,
       "friendly HTTP/DNS/ALPN modes stay thin argv adapters over acme.sh")

    # A24: uninstall is intentionally not a wrapper-owned purge implementation.
    uh = pathlib.Path(td) / "uninstall-history"; ue = dict(env); ue["MOCK_HISTORY"] = str(uh)
    p = run(["uninstall", "--yes"], ue)
    uninstall_slice = core_text[core_text.find("def uninstall_cmd"):core_text.find("def deploy_cmd")]
    ck("A24-uninstall-no-wrapper-purge", p.returncode == 0 and "CALL\t--uninstall" in uh.read_text() and "shutil.rmtree" not in uninstall_slice and "os.remove" not in uninstall_slice,
       "uninstall delegates program/cron removal upstream and does not silently purge certs or credentials")
    # A25: shortcut preview needs one central fail-safe redaction boundary.
    mutant_dir = pathlib.Path(td) / "shortcut-redaction-mutant"
    mutant_dir.mkdir()
    mutant_core = mutant_dir / "acme_cli.py"
    original_core = CORE.read_text()
    marker = "    safe_args = _redact_shortcut_args(args)\n"
    assert marker in original_core
    mutant_core.write_text(original_core.replace(marker, "    safe_args = list(args)\n", 1))
    spec_mut = importlib.util.spec_from_file_location("acme_shortcut_mutant", str(mutant_core))
    mut = importlib.util.module_from_spec(spec_mut); spec_mut.loader.exec_module(mut)
    capture = io.StringIO()
    with contextlib.redirect_stderr(capture):
        mut.show_cli_shortcut(["native", "--password", "ABLATION-SECRET"])
    ck("A25-shortcut-central-redaction-required", "ABLATION-SECRET" in capture.getvalue(),
       "removing central shortcut redaction reproduces secret disclosure even if an individual caller forgets to sanitize")

    # A26: ChatGPT handoff redaction must remain centralized before logs can be shared.
    diagnostic_mutant = mutant_dir / "diagnostic_mutant.py"
    diag_marker = '    return "\\n".join(out)\n\n\ndef _diagnostic_path'
    assert diag_marker in original_core
    diagnostic_mutant.write_text(original_core.replace(diag_marker, '    return text\n\n\ndef _diagnostic_path', 1))
    diag_spec = importlib.util.spec_from_file_location("acme_diag_mutant", str(diagnostic_mutant))
    diag_mut = importlib.util.module_from_spec(diag_spec); diag_spec.loader.exec_module(diag_mut)
    leaked = diag_mut._diagnostic_redact("MY_CREDENTIAL: ABLATION-DIAGNOSTIC-SECRET")
    ck("A26-diagnostic-central-redaction-required", "ABLATION-DIAGNOSTIC-SECRET" in leaked,
       "removing the central diagnostic line-redaction boundary reproduces a handoff secret leak")

    # A27: opt-in log evidence should not leave a second, unused auto-discovery path.
    ck("A27-diagnostic-auto-log-discovery-removed", "_diagnostic_log_candidates" not in original_core and "extra_logs or []" in original_core,
       "after choosing explicit --log only, remove dead automatic log discovery instead of maintaining two evidence paths")

finally:
    shutil.rmtree(td, ignore_errors=True)

bad = [x for x in checks if not x[1]]
for name, ok, note in checks:
    print(("PASS" if ok else "FAIL"), name, "-", note)
print("SUMMARY {}/{}".format(len(checks)-len(bad), len(checks)))
raise SystemExit(1 if bad else 0)
