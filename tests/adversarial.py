#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACME = str(ROOT / "acme")
CORE = ROOT / "acme_cli.py"
MOCK_TEMPLATE = ROOT / "tests" / "mock-acme.sh"
DNS_TEMPLATE = ROOT / "tests" / "dnsapi"


class T:
    def __init__(self, name):
        self.name = name
        self.n = 0
        self.fail = []

    def ok(self, cond, msg):
        self.n += 1
        if not cond:
            self.fail.append(msg)

    def done(self):
        passed = self.n - len(self.fail)
        if self.fail:
            print("FAIL {} {}/{}:".format(self.name, passed, self.n))
            for item in self.fail:
                print(" - " + item)
            return 1
        print("PASS {} {}/{}".format(self.name, self.n, self.n))
        return 0


def make_mock_home(td, name="upstream"):
    home = pathlib.Path(td) / name
    home.mkdir(parents=True, exist_ok=True)
    acme = home / "acme.sh"
    shutil.copy2(str(MOCK_TEMPLATE), str(acme))
    os.chmod(str(acme), 0o755)
    shutil.copytree(str(DNS_TEMPLATE), str(home / "dnsapi"))
    for sub in ("deploy", "notify"):
        src = ROOT / "tests" / sub
        if src.exists(): shutil.copytree(str(src), str(home / sub))
    completion = ROOT / "tests" / "acme.sh.completion"
    if completion.exists(): shutil.copy2(str(completion), str(home / "acme.sh.completion"))
    return home, acme


def base_env(td, acme=None):
    if acme is None:
        _, acme = make_mock_home(td)
    return {
        "ACME_SH_BIN": str(acme),
        "ACME_HELPER_LANG": "en",
        "MOCK_LOG": str(pathlib.Path(td) / "argv.log"),
        "MOCK_HISTORY": str(pathlib.Path(td) / "history.log"),
        "ACME_ACCOUNT_CONF": str(pathlib.Path(td) / "account.conf"),
        "ACME_WRAPPER_CONFIG": str(pathlib.Path(td) / "wrapper.ini"),
        "ACME_OUTPUT_ROOT": str(pathlib.Path(td) / "out"),
        "ACME_VERSION_BACKUP_DIR": str(pathlib.Path(td) / "version-backups"),
    }


def run(args, env=None, data=None):
    merged = os.environ.copy()
    merged.update(env or {})
    merged.setdefault("ACME_HELPER_LANG", "en")
    return subprocess.run([ACME] + args, input=data, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged)


def argvlog(env):
    path = pathlib.Path(env["MOCK_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def history(env):
    path = pathlib.Path(env["MOCK_HISTORY"])
    return path.read_text().splitlines() if path.exists() else []


def conf_text(env):
    path = pathlib.Path(env["ACME_ACCOUNT_CONF"])
    return path.read_text() if path.exists() else ""


def load_core(acme_path):
    os.environ["ACME_SH_BIN"] = str(acme_path)
    spec = importlib.util.spec_from_file_location("acme_core_test", str(CORE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def round1():
    t = T("round1-correctness")
    td = tempfile.mkdtemp(prefix="acme-v17-r1-")
    try:
        home, upstream = make_mock_home(td)
        env = base_env(td, upstream)

        # Minimal multi-SAN issuance and defaults.
        p = run(["*.aa.bb *.dd.bb *.gg.bb"], env)
        a = argvlog(env)
        expected = ["--issue", "--server", "letsencrypt", "--keylength", "ec-256",
                    "--dns", "dns_namesilo", "--dnssleep", "120",
                    "-d", "*.aa.bb", "-d", "*.dd.bb", "-d", "*.gg.bb"]
        t.ok(p.returncode == 0, "default issue rc")
        t.ok(a[:len(expected)] == expected, "default managed argv")
        out = pathlib.Path(env["ACME_OUTPUT_ROOT"]) / "aa.bb"
        t.ok((out / "key.pem").is_file(), "minimal key")
        t.ok((out / "fullchain.pem").is_file(), "minimal fullchain")
        t.ok((out / "domains.txt").read_text().splitlines() == ["*.aa.bb", "*.dd.bb", "*.gg.bb"], "domains manifest")
        t.ok(not (out / "cert.pem").exists() and not (out / "ca.pem").exists(), "minimal omits full-only files")

        # Every external output layout.
        layouts = {
            "full": (["cert.pem", "key.pem", "ca.pem", "fullchain.pem", "domains.txt"], []),
            "minimal": (["key.pem", "fullchain.pem", "domains.txt"], ["cert.pem", "ca.pem"]),
            "nginx": (["privkey.pem", "fullchain.pem", "domains.txt"], ["cert.pem", "key.pem", "ca.pem"]),
        }
        for layout, (present, absent) in layouts.items():
            domain = "*.{}.layout.test".format(layout)
            p = run(["-format", layout, domain], env)
            root = pathlib.Path(env["ACME_OUTPUT_ROOT"]) / "{}.layout.test".format(layout)
            t.ok(p.returncode == 0, layout + " issue rc")
            t.ok(all((root / f).is_file() for f in present), layout + " present files")
            t.ok(all(not (root / f).exists() for f in absent), layout + " omitted files")
        p = run(["-format", "none", "*.none.layout.test"], env)
        t.ok(p.returncode == 0 and all(x not in argvlog(env) for x in ["--cert-file", "--key-file", "--fullchain-file"]), "none layout leaves upstream storage only")

        # Provider catalog is dynamic and all installed drivers are reachable.
        p = run(["providers"], env)
        for provider in ("dns_namesilo", "dns_cf", "dns_gd", "dns_raw", "dns_runtime", "dns_alt", "dns_legacy"):
            t.ok(provider in p.stdout, "provider listed " + provider)
        p = run(["providers", "cloud"], env)
        t.ok(p.returncode == 0 and "dns_cf" in p.stdout and "dns_gd" not in p.stdout, "provider search")
        p = run(["providers", "does-not-exist"], env)
        t.ok(p.returncode == 2, "provider search no match fails explicitly")
        p = run(["-dns", "dns_does_not_exist", "*.x.test"], env)
        t.ok(p.returncode == 2 and "provider not found" in p.stderr.lower(), "issue rejects provider typo")

        # Generic provider credential schemas.
        p = run(["config", "dns_namesilo"], env, "NS-KEY\n")
        t.ok(p.returncode == 0 and "Namesilo_Key=" in conf_text(env) and "SAVED_Namesilo_Key" not in conf_text(env), "raw upstream persistence honored")
        p = run(["config", "dns_gd"], env, "GD-KEY\nGD-SECRET\n")
        text = conf_text(env)
        t.ok(p.returncode == 0 and "SAVED_GD_Key=" in text and "SAVED_GD_Secret=" in text, "mutable persistence honored")

        # Cloudflare OptionsAlt token mode; optional Zone ID may be blank.
        p = run(["config", "dns_cf"], env, "2\nCF-TOKEN\nACCOUNT-ID\n\n")
        text = conf_text(env)
        t.ok(p.returncode == 0, "alternative credential group selection")
        t.ok("SAVED_CF_Token=" in text and "SAVED_CF_Account_ID=" in text, "token group stored")
        t.ok("SAVED_CF_Zone_ID" not in text, "optional blank field does not block token group")
        t.ok("SAVED_CF_Key" not in text and "SAVED_CF_Email" not in text, "unused alternative cleared")
        p = run(["status", "dns_cf"], env)
        t.ok("dns_cf=configured" in p.stdout, "optional provider fields do not cause false not-configured")

        # Switch credential mode and confirm stale alternative is cleared only after real changes.
        p = run(["config", "dns_cf"], env, "1\nCF-KEY\nops@example.com\n")
        text = conf_text(env)
        t.ok(p.returncode == 0 and "SAVED_CF_Key=" in text and "SAVED_CF_Email=" in text, "legacy group stored")
        t.ok("SAVED_CF_Token" not in text and "SAVED_CF_Account_ID" not in text and "SAVED_CF_Zone_ID" not in text, "stale alternative group cleared")
        before = text
        p = run(["config", "dns_cf"], env, "1\n\n\n")
        t.ok(p.returncode == 0 and conf_text(env) == before, "inspection with all Enter makes no credential changes")

        p = run(["config", "dns_raw"], env, "RAW-SECRET\n")
        t.ok(p.returncode == 0 and "RAW_TOKEN=" in conf_text(env) and "SAVED_RAW_TOKEN" not in conf_text(env), "generic raw provider")
        before = conf_text(env)
        p = run(["config", "dns_runtime"], env)
        t.ok(p.returncode == 0 and conf_text(env) == before, "runtime-only provider does not persist fake credential")
        t.ok("runtime-only" in p.stderr and 'not through this form' in p.stderr, "runtime-only UX explains environment requirement")
        p = run(["config", "dns_legacy"], env)
        t.ok(p.returncode == 0 and "structured Options metadata" in p.stderr, "legacy provider remains reachable with honest manual schema fallback")
        p = run(["config", "dns_alt"], env, "2\nlegacy-user\nlegacy-pass\n")
        t.ok(p.returncode == 0 and "SAVED_ALT_USER=" in conf_text(env) and "SAVED_ALT_PASS=" in conf_text(env), "generic OptionsAlt fixture")

        # Status summary never assumes only three providers.
        p = run(["status", "--all"], env)
        t.ok(p.returncode == 0 and "dns_provider_total=7" in p.stdout, "all-provider status total")
        t.ok("dns_runtime=runtime-only" in p.stdout, "runtime provider status")
        t.ok("dns_legacy=manual-schema" in p.stdout, "legacy provider status")

        # v1.7 complete issue validation surface delegates to upstream without reimplementing validation.
        issue_modes = [
            (["issue", "--validation", "webroot", "--webroot", "/srv/www", "mode.test"], ["--webroot", "/srv/www"]),
            (["issue", "--standalone", "mode.test"], ["--standalone"]),
            (["issue", "--alpn", "mode.test"], ["--alpn"]),
            (["issue", "--stateless", "mode.test"], ["--stateless"]),
            (["issue", "--apache", "mode.test"], ["--apache"]),
            (["issue", "--nginx", "--nginx-config", "/etc/nginx/nginx.conf", "mode.test"], ["--nginx", "/etc/nginx/nginx.conf"]),
            (["issue", "--manual-dns", "mode.test"], ["--dns", "--yes-I-know-dns-manual-mode-enough-go-ahead-please"]),
            (["issue", "--dns-persist", "mode.test"], ["--dns-persist"]),
        ]
        for args, expected_mode in issue_modes:
            p = run(args, env)
            a = argvlog(env)
            t.ok(p.returncode == 0 and all(x in a for x in expected_mode), "friendly issue mode " + expected_mode[0])

        # Dynamic deploy/notify hooks and top-level friendly deploy route.
        p = run(["hooks", "deploy"], env)
        t.ok(p.returncode == 0 and "testdeploy" in p.stdout, "deploy hooks dynamically listed")
        p = run(["hooks", "notify"], env)
        t.ok(p.returncode == 0 and "testnotify" in p.stdout, "notify hooks dynamically listed")

        # Managed cert/SAN inventory, saved provider reuse, and cron delegation.
        cert_list = pathlib.Path(td) / "cert-list.raw"
        cert_list.write_text("Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\n*.aa.test|ec-256|*.bb.test,*.cc.test||LetsEncrypt|2026-01-01|2026-03-01\nexample.test|2048|www.example.test||LetsEncrypt|2026-01-02|2026-03-02\n")
        info_dir = pathlib.Path(td) / "cert-info"; info_dir.mkdir()
        (info_dir / "_wild_.aa.test.info").write_text("Le_Domain=*.aa.test\nLe_Alt=*.bb.test,*.cc.test\nLe_Webroot=dns_namesilo\nLe_RealKeyPath=/srv/aa/key.pem\nLe_RealFullChainPath=/srv/aa/fullchain.pem\n")
        (info_dir / "example.test.info").write_text("Le_Domain=example.test\nLe_Alt=www.example.test\nLe_Webroot=dns_cf,dns_namesilo\n")
        ce = dict(env, MOCK_CERT_LIST=str(cert_list), MOCK_CERT_INFO_DIR=str(info_dir))
        p = run(["certs", "list"], ce)
        t.ok(p.returncode == 0 and "*.aa.test, *.bb.test, *.cc.test" in p.stdout and "dns_namesilo" in p.stdout and "example.test, www.example.test" in p.stdout and "dns_cf, dns_namesilo" in p.stdout, "cert inventory lists every SAN and saved DNS provider(s)")
        p = run(["certs", "read", "*.bb.test"], ce)
        t.ok(p.returncode == 0 and "Main domain: *.aa.test" in p.stdout and "DNS provider(s): dns_namesilo" in p.stdout and "/srv/aa/fullchain.pem" in p.stdout, "cert read accepts SAN selector and shows saved metadata")
        p = run(["certs", "update", "1"], ce)
        t.ok(p.returncode == 0 and argvlog(ce) == ["--renew", "-d", "*.aa.test", "--ecc"], "cert update delegates renew without re-entering provider")
        cron_state = pathlib.Path(td) / "cron-state"
        cre = dict(env, MOCK_CRON_STATE=str(cron_state))
        p = run(["cron", "on"], cre)
        t.ok(p.returncode == 0 and cron_state.read_text().strip() == "enabled" and argvlog(cre) == ["--install-cronjob"], "cron on delegates upstream")
        p = run(["cron", "off"], cre)
        t.ok(p.returncode == 0 and cron_state.read_text().strip() == "disabled" and argvlog(cre) == ["--uninstall-cronjob"], "cron off delegates upstream")
        p = run(["cron", "run"], cre)
        t.ok(p.returncode == 0 and argvlog(cre) == ["--cron"], "cron run delegates upstream")

        # Version compatibility reporting.
        p = run(["version"], env)
        t.ok(p.returncode == 0 and "acme_sh_compatibility=probed-compatible" in p.stdout, "reference version compatibility is probed, not provenance-tested")
        t.ok("dns_providers=7" in p.stdout and "dns_provider_credential_schema=6/7" in p.stdout, "provider schema metrics")
        t.ok("acme_sh_source_provenance=not-cryptographically-verified-by-wrapper" in p.stdout, "source provenance is not overstated")
        t.ok("public_command_guidance=35/35" in p.stdout and "public_parameter_guidance=80/80" in p.stdout, "public help guidance coverage")

        # Switch to development head, update back to pinned stable release, and rollback program assets.
        branch_env = dict(env); branch_env["MOCK_UPGRADE_VERSION"] = "3.1.6"
        p = run(["switch", "master"], branch_env)
        t.ok(p.returncode == 0, "switch to explicit development branch")
        p = run(["version"], env)
        t.ok("acme_sh_version=3.1.6" in p.stdout and "acme_sh_compatibility=probed-compatible" in p.stdout, "switched branch is compatibility-probed")
        t.ok(len(list(pathlib.Path(env["ACME_VERSION_BACKUP_DIR"]).glob("*"))) >= 1, "switch creates program backup")
        p = run(["update"], env)
        t.ok(p.returncode == 0 and "acme_sh_version=3.1.4" in run(["version"], env).stdout, "update pins stable release target")
        h = "\n".join(history(env))
        t.ok("CALL\t--upgrade\t--branch\tmaster" in h, "explicit branch passed to upstream branch/tag mechanism")
        t.ok("CALL\t--upgrade\t--branch\t3.1.4" in h, "default update uses pinned stable release ref")

        p = run(["versions"], env)
        t.ok(p.returncode == 0 and "stable_target=3.1.4" in p.stdout and "interface_reference=3.1.5" in p.stdout and "backups=" in p.stdout, "versions inventory")
        p = run(["rollback"], env)
        t.ok(p.returncode in (0, 3), "rollback command executes latest backup")
        return t.done()
    finally:
        shutil.rmtree(td, ignore_errors=True)


def round2():
    t = T("round2-security-failure-atomicity")
    td = tempfile.mkdtemp(prefix="acme-v17-r2-")
    try:
        home, upstream = make_mock_home(td)
        env = base_env(td, upstream)
        conf = pathlib.Path(env["ACME_ACCOUNT_CONF"])

        # Secret shell metacharacters must round-trip as data, never execute.
        marker = pathlib.Path(td) / "PWNED"
        secret = "x'y;$(touch {});`touch {}`; # space".format(marker, marker)
        p = run(["config", "dns_cf"], env, "2\n{}\nacct\n\n".format(secret))
        t.ok(p.returncode == 0, "hostile token config rc")
        t.ok(not marker.exists(), "credential content not executed")
        t.ok(secret not in p.stdout + p.stderr, "secret not echoed")
        text = conf.read_text()
        t.ok("SAVED_CF_Token=" in text, "secret stored with shell-safe quoting")
        check = subprocess.run(["sh", "-c", '. "$1"; [ "$SAVED_CF_Token" = "$2" ]', "sh", str(conf), secret])
        t.ok(check.returncode == 0, "secret survives shell parse exactly")
        t.ok((conf.stat().st_mode & 0o777) == 0o600, "account.conf mode 600")

        # Broken old config must be preserved.
        conf.write_text("BROKEN='unterminated\n")
        os.chmod(str(conf), 0o600)
        before = conf.read_bytes()
        p = run(["config", "dns_namesilo"], env, "safe-key\n")
        t.ok(p.returncode == 2, "broken account.conf rejected")
        t.ok(conf.read_bytes() == before, "broken account.conf remains byte-identical")

        # Symlink protection on both persistent config files.
        real = pathlib.Path(td) / "real-account"
        real.write_text("KEEP=1\n"); os.chmod(str(real), 0o600)
        link = pathlib.Path(td) / "account-link"; link.symlink_to(real)
        e = dict(env); e["ACME_ACCOUNT_CONF"] = str(link)
        p = run(["config", "dns_gd"], e, "k\ns\n")
        t.ok(p.returncode == 2 and real.read_text() == "KEEP=1\n", "account.conf symlink refused")
        realw = pathlib.Path(td) / "real-wrapper.ini"; realw.write_text("[defaults]\nserver=sentinel\n"); os.chmod(str(realw),0o600)
        linkw = pathlib.Path(td) / "wrapper-link.ini"; linkw.symlink_to(realw)
        e = dict(env); e["ACME_WRAPPER_CONFIG"] = str(linkw)
        p = run(["config", "defaults"], e, "\n\n\n\n\n\n")
        t.ok(p.returncode == 2 and "sentinel" in realw.read_text(), "wrapper config symlink refused")

        # Command-line secret options are rejected before reaching upstream.
        for opt in ("--password", "--eab-hmac-key"):
            p = run(["*.x.test", "120", "--", opt, "visible-secret"], env)
            t.ok(p.returncode == 2, "secret CLI rejected " + opt)
            t.ok("visible-secret" not in p.stdout + p.stderr, "secret CLI value not reflected " + opt)

        # Dangerous/path-like refs are rejected, not passed to upgrade.
        for ref in ("../evil", "/absolute", "master//oops", "x;touch", "x$(id)"):
            p = run(["switch", ref], env)
            t.ok(p.returncode == 2, "invalid version ref rejected " + ref)

        # Upgrade failure restores program assets.
        old_hash = upstream.read_bytes()
        e = dict(env); e["MOCK_UPGRADE_FAIL"] = "1"
        p = run(["switch", "3.1.4"], e)
        t.ok(p.returncode == 23, "upstream switch failure propagated")
        t.ok(upstream.read_bytes() == old_hash, "failed switch rolls program executable back")
        t.ok("acme_sh_version=3.1.5" in run(["version"], env).stdout, "failed switch keeps old version")

        # Claimed target mismatch must rollback.
        e = dict(env); e["MOCK_UPGRADE_VERSION"] = "9.9.9"
        p = run(["switch", "3.1.4"], e)
        t.ok(p.returncode == 3, "tag/version mismatch rejected")
        t.ok("acme_sh_version=3.1.5" in run(["version"], env).stdout, "version mismatch rollback restored executable")

        # Compatibility failure after successful replacement must rollback.
        incompatible = pathlib.Path(td) / "incompatible-home"
        shutil.copytree(home, incompatible)
        bad_acme = incompatible / "acme.sh"
        bad = bad_acme.read_text().replace("  -b, --branch <branch>             Branch.\n", "")
        bad_acme.write_text(bad); os.chmod(str(bad_acme),0o755)
        e = base_env(td, bad_acme); e["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td)/"bad-backups")
        p = run(["switch", "master"], e)
        t.ok(p.returncode == 3, "compatibility gate rejects missing required option")
        post = run(["version"], e)
        t.ok("acme_sh_compatibility=incompatible" in post.stdout and "--branch" in post.stdout, "rollback restores the pre-switch incompatible program state without mixing versions")

        # Program backup scope must exclude secrets/certs/config.
        conf.write_text("SAVED_SECRET='do-not-copy'\n"); os.chmod(str(conf),0o600)
        cert = home / "example.com_ecc"; cert.mkdir(exist_ok=True); (cert / "example.com.key").write_text("PRIVATE")
        p = run(["switch", "3.1.4"], env)
        t.ok(p.returncode == 0, "switch for backup-scope inspection")
        backups = sorted(pathlib.Path(env["ACME_VERSION_BACKUP_DIR"]).glob("*"))
        newest = backups[-1]
        names = {x.name for x in newest.rglob("*")}
        t.ok("account.conf" not in names and "example.com.key" not in names, "version backup excludes account config/private cert material")
        t.ok({"acme.sh", "dnsapi", "MANIFEST"}.issubset(names), "version backup contains program assets")
        t.ok((newest / "MANIFEST").stat().st_mode & 0o777 == 0o600, "backup manifest mode 600")

        # Backup inventory itself must not be writable by other users or redirected by symlink.
        unsafe_root = pathlib.Path(td) / "unsafe-backup-root"
        unsafe_root.mkdir(); os.chmod(str(unsafe_root), 0o777)
        unsafe_env = dict(env); unsafe_env["ACME_VERSION_BACKUP_DIR"] = str(unsafe_root)
        before_mode = unsafe_root.stat().st_mode & 0o777
        p = run(["switch", "master"], unsafe_env)
        t.ok(p.returncode == 2 and "must not be group/world writable" in p.stderr, "world-writable backup root is rejected")
        t.ok((unsafe_root.stat().st_mode & 0o777) == before_mode, "wrapper does not chmod an existing shared backup root")
        real_backup_root = pathlib.Path(td) / "real-backup-root"; real_backup_root.mkdir()
        backup_link = pathlib.Path(td) / "backup-root-link"; backup_link.symlink_to(real_backup_root)
        link_env = dict(env); link_env["ACME_VERSION_BACKUP_DIR"] = str(backup_link)
        p = run(["switch", "master"], link_env)
        t.ok(p.returncode == 2 and "symlinked version backup root" in p.stderr, "symlinked backup root is rejected")

        # A backup copy failure must leave no half-valid backup in inventory.
        fail_home = pathlib.Path(td) / "backup-fail-home"
        shutil.copytree(home, fail_home)
        fifo = fail_home / "dnsapi" / "copy-failure.fifo"
        os.mkfifo(str(fifo))
        fail_backups = pathlib.Path(td) / "backup-fail-store"
        fail_env = base_env(td, fail_home / "acme.sh")
        fail_env["ACME_VERSION_BACKUP_DIR"] = str(fail_backups)
        p = run(["switch", "master"], fail_env)
        t.ok(p.returncode == 2 and "cannot create complete acme.sh program backup" in p.stderr, "backup copy failure is reported without traceback")
        listed = run(["versions"], fail_env)
        t.ok("backups=0" in listed.stdout, "partial backup is removed and excluded from inventory")

        # Rollback stages all backup assets before touching the live executable.
        broken_root = pathlib.Path(td) / "broken-rollback-store"
        broken = broken_root / "broken-backup"
        (broken / "dnsapi").mkdir(parents=True)
        shutil.copy2(upstream, broken / "acme.sh")
        (broken / "MANIFEST").write_text("from_version=3.1.4\ntarget=broken\nacme_home={}\n".format(home))
        os.chmod(str(broken / "MANIFEST"), 0o600)
        os.mkfifo(str(broken / "dnsapi" / "stage-failure.fifo"))
        before_live = upstream.read_bytes()
        rb_env = dict(env); rb_env["ACME_VERSION_BACKUP_DIR"] = str(broken_root)
        p = run(["rollback", "broken-backup"], rb_env)
        t.ok(p.returncode == 2 and "rollback failed" in p.stderr, "rollback staging failure is reported")
        t.ok(upstream.read_bytes() == before_live, "rollback staging failure leaves live executable untouched")

        # New-format rollback restores absence as well as backed-up files.
        absence_home, absence_acme = make_mock_home(td, "rollback-absence-home")
        shutil.rmtree(str(absence_home / "notify"), ignore_errors=True)
        absence_env = base_env(td, absence_acme)
        absence_env["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td) / "rollback-absence-store")
        absence_env["MOCK_UPGRADE_CREATE_NOTIFY"] = "1"
        absence_env["MOCK_UPGRADE_VERSION"] = "9.9.9"
        p = run(["switch", "3.1.4"], absence_env)
        t.ok(p.returncode == 3, "rollback-absence fixture reaches post-upgrade rollback")
        t.ok(not (absence_home / "notify").exists(), "rollback removes target-only asset that was absent before switch")
        t.ok("acme_sh_version=3.1.5" in run(["version"], absence_env).stdout, "rollback-absence restores original executable version")

        # A new-format manifest/backup mismatch fails before touching the live tree.
        mismatch_root = pathlib.Path(td) / "manifest-mismatch-store"
        mismatch = mismatch_root / "manifest-mismatch"
        mismatch.mkdir(parents=True)
        shutil.copy2(upstream, mismatch / "acme.sh")
        (mismatch / "MANIFEST").write_text("from_version=3.1.4\ntarget=mismatch\nacme_home={}\nassets=acme.sh,notify\n".format(home))
        os.chmod(str(mismatch / "MANIFEST"), 0o600)
        before_live = upstream.read_bytes()
        mismatch_env = dict(env); mismatch_env["ACME_VERSION_BACKUP_DIR"] = str(mismatch_root)
        p = run(["rollback", "manifest-mismatch"], mismatch_env)
        t.ok(p.returncode == 2 and "backup manifest is invalid or inconsistent" in p.stderr, "manifest/physical asset mismatch fails closed")
        t.ok(upstream.read_bytes() == before_live, "invalid manifest leaves live executable untouched")

        # Legacy backups without assets= must remain conservative and never infer absence.
        legacy_root = pathlib.Path(td) / "legacy-rollback-store"
        legacy_backup = legacy_root / "legacy-backup"
        (legacy_backup / "dnsapi").mkdir(parents=True)
        shutil.copy2(upstream, legacy_backup / "acme.sh")
        for item in (home / "dnsapi").iterdir():
            if item.is_file():
                shutil.copy2(item, legacy_backup / "dnsapi" / item.name)
        (legacy_backup / "MANIFEST").write_text("from_version=3.1.5\ntarget=legacy\nacme_home={}\n".format(home))
        os.chmod(str(legacy_backup / "MANIFEST"), 0o600)
        legacy_sentinel = home / "notify" / "legacy-live-only.sh"
        legacy_sentinel.parent.mkdir(exist_ok=True)
        legacy_sentinel.write_text("keep\n")
        legacy_env = dict(env); legacy_env["ACME_VERSION_BACKUP_DIR"] = str(legacy_root)
        p = run(["rollback", "legacy-backup"], legacy_env)
        t.ok(p.returncode == 0, "legacy backup without assets manifest remains restorable")
        t.ok(legacy_sentinel.exists(), "legacy rollback does not guess that an unrecorded live asset was previously absent")

        # A backup from another acme.sh home must never be offered or restored.
        foreign_root = pathlib.Path(td) / "foreign-backup-store"
        foreign = foreign_root / "foreign-backup"
        foreign.mkdir(parents=True)
        shutil.copy2(upstream, foreign / "acme.sh")
        (foreign / "MANIFEST").write_text("from_version=3.1.4\ntarget=foreign\nacme_home=/definitely/another/acme-home\n")
        os.chmod(str(foreign / "MANIFEST"), 0o600)
        foreign_env = dict(env); foreign_env["ACME_VERSION_BACKUP_DIR"] = str(foreign_root)
        listed = run(["versions"], foreign_env)
        t.ok("backups=0" in listed.stdout, "foreign-home backup is excluded from inventory")
        p = run(["rollback", "foreign-backup"], foreign_env)
        t.ok(p.returncode == 2 and ("version backup not found" in p.stderr or "no version backups available" in p.stderr), "foreign-home backup cannot be restored explicitly")

        # Runtime-only credential is not accidentally copied into config or output.
        e = dict(env); e["RUNTIME_TOKEN"] = "RUNTIME-VERY-SECRET"
        before = conf.read_text()
        p = run(["config", "dns_runtime"], e)
        t.ok(p.returncode == 0 and conf.read_text() == before, "runtime-only provider writes nothing")
        t.ok("RUNTIME-VERY-SECRET" not in p.stdout + p.stderr, "runtime secret value never printed")
        p = run(["status", "dns_runtime"], e)
        t.ok("dns_runtime=configured" in p.stdout or "dns_runtime=runtime-ready" in p.stdout, "runtime environment recognized without revealing value")

        # Malicious metadata is parsed as text, never evaluated.
        evil = home / "dnsapi" / "dns_evil.sh"
        evil_marker = pathlib.Path(td) / "METADATA_PWNED"
        evil.write_text("dns_evil_info='Evil $(touch {})\\nSite: example.invalid\\nOptions:\\nEVIL_TOKEN API Token\\n'\\n_saveaccountconf_mutable EVIL_TOKEN x\\n".format(evil_marker))
        p = run(["providers", "evil"], env)
        t.ok(p.returncode == 0 and "dns_evil" in p.stdout, "untrusted provider metadata remains data")
        t.ok(not evil_marker.exists(), "provider metadata cannot execute command substitution")

        # Online installer email guard still rejects shell/glob characters before downloader.
        fakebin = pathlib.Path(td) / "fakebin"; fakebin.mkdir()
        download_marker = pathlib.Path(td) / "DOWNLOADER_RAN"
        curl = fakebin / "curl"; curl.write_text('#!/bin/sh\ntouch "{}"\nexit 0\n'.format(download_marker)); os.chmod(str(curl),0o755)
        for name in ("bash", "python3", "sh", "touch"):
            target = shutil.which(name)
            if target: os.symlink(target, str(fakebin/name))
        for email in ("ops@example.com;touch-pwn", "ops*@example.com"):
            p = run(["install", "--email", email], {"HOME": str(pathlib.Path(td)/"install-home"), "PATH": str(fakebin)})
            t.ok(p.returncode == 2, "installer rejects unsafe email " + email)
        t.ok(not download_marker.exists(), "unsafe installer input rejected before network downloader")

        # Managed cert input is parsed as data; malformed/ambiguous state fails closed.
        cert_list = pathlib.Path(td) / "cert-list.raw"
        cert_list.write_text("Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\n*.evil.test|ec-256|shared.test||LetsEncrypt|2026-01-01|2026-03-01\nother.test|2048|shared.test||LetsEncrypt|2026-01-02|2026-03-02\n")
        info_dir = pathlib.Path(td) / "cert-info"; info_dir.mkdir(exist_ok=True)
        info_marker = pathlib.Path(td) / "CERT_INFO_PWNED"
        (info_dir / "_wild_.evil.test.info").write_text("Le_Domain=*.evil.test\nLe_Alt=shared.test\nLe_Webroot=dns_cf;$(touch {})\n".format(info_marker))
        (info_dir / "other.test.info").write_text("Le_Domain=other.test\nLe_Alt=shared.test\nLe_Webroot=dns_namesilo\n")
        ce = dict(env, MOCK_CERT_LIST=str(cert_list), MOCK_CERT_INFO_DIR=str(info_dir))
        p = run(["certs", "read", "*.evil.test"], ce)
        t.ok(p.returncode == 0 and not info_marker.exists(), "certificate info values never execute shell content")
        p = run(["certs", "read", "shared.test"], ce)
        t.ok(p.returncode == 2 and "ambiguous" in p.stderr, "ambiguous SAN selector fails closed")
        p = run(["certs", "delete", "other.test"], ce)
        t.ok(p.returncode == 2 and "requires --yes" in p.stderr and argvlog(ce)[0] != "--remove", "noninteractive certificate delete requires explicit yes")
        malformed = pathlib.Path(td) / "bad-cert-list.raw"
        malformed.write_text("Domain|Key|SAN|CA\nexample.test|2048|www.example.test|LetsEncrypt\n")
        me = dict(env, MOCK_CERT_LIST=str(malformed), MOCK_CERT_INFO_DIR=str(info_dir))
        p = run(["certs", "list"], me)
        t.ok(p.returncode == 2 and "unsupported acme.sh --listraw format" in p.stderr, "malformed certificate inventory format rejected")

        # Destructive and secret-bearing v1.7 routes fail closed or keep secrets out of output.
        sentinel = home / "KEEP_AFTER_UNINSTALL"
        sentinel.write_text("keep")
        p = run(["uninstall"], env)
        t.ok(p.returncode == 2 and "requires --yes" in p.stderr and "--uninstall" not in argvlog(env), "uninstall requires explicit noninteractive confirmation")
        p = run(["uninstall", "--yes"], env)
        t.ok(p.returncode == 0 and argvlog(env) == ["--uninstall"], "uninstall delegates exactly once to upstream")
        t.ok(sentinel.exists() and conf.exists(), "uninstall does not purge wrapper-managed or account data")

        pfx_secret = "PFX-ADVERSARIAL-'-$()-SECRET"
        p = run(["export", "pkcs12", "*.evil.test", "--password-stdin"], ce, pfx_secret + "\n")
        t.ok(p.returncode == 0 and "--to-pkcs12" in argvlog(ce), "PKCS12 stdin password delegates through upstream argv")
        t.ok(pfx_secret not in p.stdout + p.stderr, "PKCS12 stdin password is never echoed")

        p = run(["certs", "revoke", "other.test"], ce)
        t.ok(p.returncode == 2 and "requires --yes" in p.stderr and "--revoke" not in argvlog(ce), "certificate revoke requires explicit confirmation")
        p = run(["deploy", "other.test", "--hook", "missing", "--yes"], ce)
        t.ok(p.returncode == 2 and "hook not found" in p.stderr.lower(), "unknown deploy hook fails closed")

        # Hook credentials stay in the invocation environment, not wrapper files or output.
        hook_env_log = pathlib.Path(td) / "HOOK_ENV.log"
        he = dict(ce, MOCK_ENV_LOG=str(hook_env_log), TESTDEPLOY_TOKEN="DEPLOY-ENV-SECRET", TESTDEPLOY_HOST="host.example")
        p = run(["deploy", "other.test", "--hook", "testdeploy", "--yes"], he)
        hook_text = hook_env_log.read_text() if hook_env_log.exists() else ""
        t.ok(p.returncode == 0 and "TESTDEPLOY_TOKEN=DEPLOY-ENV-SECRET" in hook_text, "deploy hook receives caller environment without wrapper persistence")
        t.ok("DEPLOY-ENV-SECRET" not in p.stdout + p.stderr and "DEPLOY-ENV-SECRET" not in conf_text(env), "deploy hook secret is not echoed or copied into account.conf")
        hook_env_log.write_text("")
        ne = dict(env, MOCK_ENV_LOG=str(hook_env_log), TESTNOTIFY_TOKEN="NOTIFY-ENV-SECRET")
        p = run(["notify", "set", "--hook", "testnotify", "--level", "2"], ne)
        hook_text = hook_env_log.read_text() if hook_env_log.exists() else ""
        t.ok(p.returncode == 0 and "TESTNOTIFY_TOKEN=NOTIFY-ENV-SECRET" in hook_text, "notify hook receives caller environment for upstream test notification")
        t.ok("NOTIFY-ENV-SECRET" not in p.stdout + p.stderr and "NOTIFY-ENV-SECRET" not in conf_text(env), "notify hook secret is not echoed or copied into account.conf")

        # Hook files are inspected as text only; hostile comment/code content must never execute.
        hook_marker = pathlib.Path(td) / "HOOK_METADATA_PWNED"
        evil_hook = home / "deploy" / "evilhook.sh"
        evil_hook.write_text("#!/bin/sh\n# Evil $(touch {})\n# export EVIL_HOOK_TOKEN=...\nevilhook_deploy() {{ :; }}\n".format(hook_marker))
        os.chmod(str(evil_hook), 0o755)
        p = run(["hooks", "deploy"], env)
        t.ok(p.returncode == 0 and "evilhook" in p.stdout and not hook_marker.exists(), "hook metadata discovery never sources or executes hook files")

        # Cron failures must be visible rather than reported as enabled.
        cre = dict(env, MOCK_CRON_RC="17", MOCK_CRON_STATE=str(pathlib.Path(td)/"cron-state"))
        p = run(["cron", "on"], cre)
        t.ok(p.returncode == 17, "upstream cron installation failure propagated")
        return t.done()
    finally:
        shutil.rmtree(td, ignore_errors=True)


def round3():
    t = T("round3-drift-provider-version")
    td = tempfile.mkdtemp(prefix="acme-v17-r3-")
    try:
        home, upstream = make_mock_home(td)
        env = base_env(td, upstream)

        # Future provider appears with no wrapper source change and is immediately usable.
        future = home / "dnsapi" / "dns_futurecorp.sh"
        future.write_text("""#!/usr/bin/env sh\ndns_futurecorp_info='FutureCorp DNS\nSite: future.invalid\nDocs: https://future.invalid/docs\nOptions:\nFUTURE_TOKEN API Token\n'\n_f() { FUTURE_TOKEN=\"${FUTURE_TOKEN:-$(_readaccountconf_mutable FUTURE_TOKEN)}\"; }\n""")
        p = run(["providers", "future"], env)
        t.ok(p.returncode == 0 and "dns_futurecorp" in p.stdout, "future provider dynamically discovered")
        p = run(["config", "dns_futurecorp"], env, "future-secret\n")
        t.ok(p.returncode == 0 and "SAVED_FUTURE_TOKEN=" in conf_text(env), "future provider credential UI generated from metadata")
        p = run(["-dns", "dns_futurecorp", "*.future.test"], env)
        t.ok(p.returncode == 0 and "dns_futurecorp" in argvlog(env), "future provider available to issue path")

        # A future legacy driver is reachable but not falsely given invented credentials.
        legacy = home / "dnsapi" / "dns_futurelegacy.sh"
        legacy.write_text("#!/usr/bin/env sh\ndns_futurelegacy_add(){ :; }\ndns_futurelegacy_rm(){ :; }\n")
        p = run(["providers", "futurelegacy"], env)
        t.ok(p.returncode == 0 and "schema:manual" in p.stdout, "future legacy driver gets honest manual schema")
        p = run(["config", "dns_futurelegacy"], env)
        t.ok(p.returncode == 0 and "structured Options metadata" in p.stderr, "legacy config fallback does not guess credential names")

        # Provider removal is detected rather than silently issuing with a typo/stale selection.
        (home / "dnsapi" / "dns_raw.sh").unlink()
        p = run(["-dns", "dns_raw", "*.removed.test"], env)
        t.ok(p.returncode == 2 and "not found" in p.stderr.lower(), "removed provider detected")

        # Home-level custom provider overrides same-name packaged driver.
        custom = home / "dns_cf.sh"
        custom.write_text("dns_cf_info='Custom Cloudflare Override\nSite: local.invalid\nOptions:\nCUSTOM_CF_TOKEN API Token\n'\n_f(){ _saveaccountconf_mutable CUSTOM_CF_TOKEN x; }\n")
        p = run(["providers", "dns_cf"], env)
        t.ok("Custom Cloudflare Override" in p.stdout, "home custom driver takes precedence over dnsapi copy")

        # Parser covers OptionsAlt2, duplicate variables, optional fields and quote style.
        complexp = home / "dnsapi" / "dns_complex.sh"
        complexp.write_text('''dns_complex_info="Complex Provider\nSite: complex.invalid\nOptions:\nC_TOKEN API Token\nC_TOKEN duplicate line\nOptionsAlt:\nC_USER Username\nC_PASS Password\nOptionsAlt2:\nC_KEY API Key\nC_OPTION Optional.\nIssues: none\nThis prose must not become a variable\n"\n_f(){ _saveaccountconf_mutable C_TOKEN x; _saveaccountconf_mutable C_USER x; _saveaccountconf_mutable C_PASS x; _saveaccountconf C_KEY x; _saveaccountconf C_OPTION x; }\n''')
        core = load_core(upstream)
        item = core.find_dns_provider("dns_complex")
        t.ok(len(item["groups"]) == 3, "OptionsAlt2 parsed")
        t.ok(sum(1 for o in item["groups"][0]["options"] if o["var"] == "C_TOKEN") == 1, "duplicate variable deduplicated")
        t.ok(item["groups"][2]["options"][1]["optional"] is True, "optional metadata parsed")
        t.ok(all(o["var"] != "This" for g in item["groups"] for o in g["options"]), "prose after Issues not parsed as credential")

        # Future completion-only commands/hooks appear without wrapper registry edits and retain raw/native fallback.
        completion = home / "acme.sh.completion"
        if completion.exists():
            text = completion.read_text()
            marker = "--list-profiles\n"
            if marker in text:
                completion.write_text(text.replace(marker, marker + "--future-completion-command\n", 1))
        future_deploy = home / "deploy" / "futuredeploy.sh"
        future_deploy.write_text("#!/bin/sh\n# Future deploy hook\nfuturedeploy_deploy(){ :; }\n")
        os.chmod(str(future_deploy), 0o755)
        p = run(["hooks", "deploy"], env)
        t.ok(p.returncode == 0 and "futuredeploy" in p.stdout, "future deploy hook dynamically discovered")
        core = load_core(upstream)
        commands, _ = core.parse_upstream_help()
        names = [x[0] for x in commands]
        t.ok("--future-completion-command" in names, "future completion-only command joins callable surface")
        p = run(["native", "--future-completion-command"], env)
        t.ok(p.returncode == 0 and argvlog(env) == ["--future-completion-command"], "future completion-only command remains executable through native fallback")

        # Future upstream help remains reachable with honest guidance fallback.
        futuristic = pathlib.Path(td) / "future-upstream"
        shutil.copytree(home, futuristic)
        f_acme = futuristic / "acme.sh"
        src = f_acme.read_text().replace('embedded_version="3.1.5"', 'embedded_version="3.1.6"')
        src = src.replace("  --set-default-chain      Set default chain.\n", "  --set-default-chain      Set default chain.\n  --future-command         Future command.\n")
        src = src.replace("  --password <password>             Export password.\n", "  --password <password>             Export password.\n  --future-param <value>            Future parameter.\n")
        f_acme.write_text(src); os.chmod(str(f_acme),0o755)
        e = base_env(td, f_acme); e["ACME_VERSION_BACKUP_DIR"] = str(pathlib.Path(td)/"future-backups")
        p = run(["version"], e)
        t.ok("acme_sh_version=3.1.6" in p.stdout and "acme_sh_compatibility=probed-compatible" in p.stdout, "future version probed not falsely labeled tested")
        t.ok("public_command_guidance=35/37" in p.stdout and "public_parameter_guidance=80/81" in p.stdout, "unknown future help items reported as fallback coverage")
        p = run(["native", "--future-command", "--future-param", "x"], e)
        t.ok(p.returncode == 0 and argvlog(e) == ["--future-command", "--future-param", "x"], "future native argv remains usable")

        # A 3.1.3-like surface must not be treated as compatible merely because its version string is old.
        legacy = pathlib.Path(td) / "legacy-313-surface"
        shutil.copytree(home, legacy)
        legacy_acme = legacy / "acme.sh"
        legacy_text = legacy_acme.read_text().replace('embedded_version="3.1.5"', 'embedded_version="3.1.3"')
        for line in (
            "  --update-account-key     Rotate account key.\n",
            "  --make-dns-persist-value Make dns persist value.\n",
            "  --dns-persist                     DNS persist.\n",
            "  --dns-persist-wildcard            DNS persist wildcard.\n",
            "  --dns-persist-ca-name <name>      DNS persist CA.\n",
            "  --dns-persist-days <N>            DNS persist days.\n",
        ):
            legacy_text = legacy_text.replace(line, "")
        legacy_acme.write_text(legacy_text); os.chmod(str(legacy_acme), 0o755)
        legacy_completion = legacy / "acme.sh.completion"
        if legacy_completion.exists():
            completion_text = legacy_completion.read_text()
            for token in ("--update-account-key\n", "--make-dns-persist-value\n", "--dns-persist\n", "--dns-persist-wildcard\n", "--dns-persist-ca-name\n", "--dns-persist-days\n"):
                completion_text = completion_text.replace(token, "")
            legacy_completion.write_text(completion_text)
        legacy_env = base_env(td, legacy_acme)
        p = run(["version"], legacy_env)
        t.ok("acme_sh_version=3.1.3" in p.stdout and "acme_sh_compatibility=incompatible" in p.stdout, "legacy feature surface is rejected instead of trusting version text")
        t.ok("--update-account-key" in p.stdout and "--make-dns-persist-value" in p.stdout, "legacy compatibility report names missing required commands")

        # Missing required wrapper option is incompatible.
        incompatible = pathlib.Path(td) / "missing-core"
        shutil.copytree(home, incompatible)
        i_acme = incompatible / "acme.sh"
        i_acme.write_text(i_acme.read_text().replace("  --ca-file <file>                  CA output.\n", "")); os.chmod(str(i_acme),0o755)
        e2 = base_env(td, i_acme)
        p = run(["version"], e2)
        t.ok("acme_sh_compatibility=incompatible" in p.stdout and "--ca-file" in p.stdout, "missing wrapper-required parameter detected")

        # New v1.6 cert/cron surface is part of compatibility, not an optional afterthought.
        nocron = pathlib.Path(td) / "missing-cron"
        shutil.copytree(home, nocron)
        c_acme = nocron / "acme.sh"
        c_acme.write_text(c_acme.read_text().replace("  --install-cronjob        Install cron.\n", "")); os.chmod(str(c_acme),0o755)
        completion = nocron / "acme.sh.completion"
        if completion.exists():
            completion.write_text(completion.read_text().replace("--install-cronjob\n", ""))
        ecron = base_env(td, c_acme)
        p = run(["version"], ecron)
        t.ok("acme_sh_compatibility=incompatible" in p.stdout and "--install-cronjob" in p.stdout, "missing cron command detected by compatibility probe")
        nolistraw = pathlib.Path(td) / "missing-listraw"
        shutil.copytree(home, nolistraw)
        l_acme = nolistraw / "acme.sh"
        l_acme.write_text(l_acme.read_text().replace("  --listraw                         Raw list.\n", "")); os.chmod(str(l_acme),0o755)
        elist = base_env(td, l_acme)
        p = run(["version"], elist)
        t.ok("acme_sh_compatibility=incompatible" in p.stdout and "--listraw" in p.stdout, "missing SAN inventory parameter detected by compatibility probe")

        changed_list = pathlib.Path(td) / "future-list-format.raw"
        changed_list.write_text("Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew\nexample.test|2048|www.example.test||LetsEncrypt|2026-01-01|2026-03-01\n")
        eformat = dict(env, MOCK_CERT_LIST=str(changed_list))
        p = run(["version", "--full"], eformat)
        t.ok("acme_sh_compatibility=degraded" in p.stdout and "readonly_smoke=fail" in p.stdout, "changed listraw format degrades compatibility before cert UX is used")

        # Missing hard default provider degrades compatibility.
        nodefault = pathlib.Path(td) / "no-default"
        shutil.copytree(home, nodefault)
        (nodefault / "dnsapi" / "dns_namesilo.sh").unlink()
        n_acme = nodefault / "acme.sh"
        e3 = base_env(td, n_acme)
        p = run(["version"], e3)
        t.ok("acme_sh_compatibility=degraded" in p.stdout, "missing default provider degrades compatibility")

        # v-prefixed semantic tag is normalized for exact version verification.
        p = run(["switch", "v3.1.4"], env)
        t.ok(p.returncode == 0 and "acme_sh_version=3.1.4" in run(["version"], env).stdout, "v-prefixed release tag exact-check normalized")
        hist = pathlib.Path(env["MOCK_HISTORY"]).read_text()
        t.ok("CALL\t--upgrade\t--branch\t3.1.4" in hist, "v-prefixed release ref is normalized before upstream invocation")
        p = run(["update"], env)
        t.ok(p.returncode == 0 and "acme_sh_version=3.1.4" in run(["version"], env).stdout, "update returns to pinned stable version")

        # Branch can move to a different reported version and remains only probed-compatible.
        e = dict(env); e["MOCK_UPGRADE_VERSION"] = "3.1.6"
        p = run(["switch", "master"], e)
        t.ok(p.returncode == 0, "branch switch accepts compatible non-release ref")
        t.ok("acme_sh_version=3.1.6" in run(["version"], env).stdout, "branch switch reports actual resulting version")

        # Direct parser coverage for current mock help.
        code = """import importlib.util,os; s=importlib.util.spec_from_file_location('a',os.environ['CORE']);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);c,p=m.parse_upstream_help();print(len(c),sum(1 for x in c if x[0] in m.COMMAND_GUIDANCE));print(len(p),sum(1 for x in p if x[0] in m.PARAM_HINTS))"""
        ee = os.environ.copy(); ee.update(env); ee["CORE"] = str(CORE)
        q = subprocess.run(["python3", "-S", "-c", code], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ee)
        t.ok(q.returncode == 0 and q.stdout.splitlines() == ["36 35", "80 80"], "current public command/parameter guidance remains complete")
        return t.done()
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    rc = 0
    for fn in (round1, round2, round3):
        rc |= fn()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
