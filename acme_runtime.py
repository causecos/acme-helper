#!/usr/bin/env python3
"""Minimal runtime wrapper for automatic `acme issue` failure diagnostics.

Non-issue commands exec the existing core unchanged. Explicit issue/quick flows keep
stdin/stdout/stderr attached to the same terminal, while the upstream acme.sh process
inherits a private LOG_FILE for diagnostic evidence. No --log argument is injected,
so ACME Helper does not cause acme.sh to persist a temporary log path in account.conf.
"""
import configparser
import os
import stat
import subprocess
import sys
import tempfile

DIAGNOSTIC_NAME = "last-issue-diagnostic.txt"
RAW_FALLBACK_NAME = "last-issue-evidence.log"
MAX_RAW_FALLBACK_BYTES = 131072


def _wrapper_config_path():
    configured = os.environ.get("ACME_WRAPPER_CONFIG")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(os.path.abspath(os.path.expanduser(xdg)), "acme-wrapper", "config.ini")
    home = os.environ.get("HOME")
    if home:
        return os.path.join(os.path.abspath(os.path.expanduser(home)), ".config", "acme-wrapper", "config.ini")
    return ""


def _language(argv):
    if len(argv) >= 2 and argv[0] == "--lang" and argv[1] in ("zh-TW", "en"):
        return argv[1]
    env_lang = os.environ.get("ACME_HELPER_LANG") or os.environ.get("ACME_LANG")
    if env_lang in ("zh-TW", "en"):
        return env_lang
    path = _wrapper_config_path()
    if path and os.path.isfile(path):
        parser = configparser.RawConfigParser()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                parser.read_file(handle)
            if parser.has_option("ui", "language"):
                saved = parser.get("ui", "language")
                if saved in ("zh-TW", "en"):
                    return saved
        except (OSError, configparser.Error):
            pass
    return "zh-TW"


def _messages(lang):
    if lang == "en":
        return {
            "saved": "acme: redacted issue-failure diagnostic saved: {}",
            "review": "acme: review this file before sharing it with ChatGPT; the private automatic capture was deleted.",
            "fallback": "acme: automatic redacted diagnostic failed; private raw evidence kept at: {}",
            "fallback_warn": "acme: WARNING: raw evidence is not redacted. Do not share it directly; run: acme diagnose --log FILE",
            "user_log_fail": "acme: automatic redaction failed; your explicitly selected upstream log was left unchanged: {}",
        }
    return {
        "saved": "acme: 已自動保存本次簽發失敗的遮蔽診斷：{}",
        "review": "acme: 請先人工檢查後再提供給 ChatGPT；自動建立的原始私有紀錄已刪除。",
        "fallback": "acme: 無法自動產生遮蔽診斷；原始私有失敗紀錄保留於：{}",
        "fallback_warn": "acme: 警告：原始紀錄尚未遮蔽，請勿直接分享；請執行：acme diagnose --log FILE",
        "user_log_fail": "acme: 無法自動完成遮蔽；你明確指定的上游 log 保持原樣：{}",
    }


def _issue_intent(argv):
    args = list(argv)
    if len(args) >= 2 and args[0] == "--lang":
        args = args[2:]
    return bool(args and args[0] in ("issue", "quick"))


def _explicit_log(argv):
    """Return (present, path). User --log is only valid in raw upstream arguments."""
    items = list(argv)
    for index, item in enumerate(items):
        if item.startswith("--log="):
            return True, item.split("=", 1)[1]
        if item == "--log":
            if index + 1 < len(items) and not str(items[index + 1]).startswith("-"):
                return True, str(items[index + 1])
            return True, ""
    return False, ""


def _private_temp(prefix, suffix=""):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return path


def _diagnostic_path():
    override = os.environ.get("ACME_HELPER_DIAGNOSTIC_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = os.environ.get("HOME")
    if home:
        return os.path.join(os.path.abspath(os.path.expanduser(home)), ".cache", "acme-wrapper", "diagnostics")
    return os.path.join(tempfile.gettempdir(), "acme-helper-{}".format(os.geteuid()), "diagnostics")


def _diagnostic_dir(create=True):
    path = _diagnostic_path()
    if create:
        os.makedirs(path, mode=0o700, exist_ok=True)
    elif not os.path.lexists(path):
        return ""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RuntimeError("diagnostic path is not a real directory: {}".format(path))
    if st.st_uid != os.geteuid():
        raise RuntimeError("diagnostic directory is not owned by uid {}: {}".format(os.geteuid(), path))
    if st.st_mode & 0o077:
        raise RuntimeError("diagnostic directory must be private (0700): {}".format(path))
    return path


def _regular_nonempty(path):
    if not path:
        return False
    try:
        st = os.lstat(path)
        return stat.S_ISREG(st.st_mode) and st.st_size > 0
    except OSError:
        return False


def _generic_failure_evidence(rc):
    path = _private_temp("acme-helper-issue-failure-", ".log")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("[ACME_HELPER_ISSUE_FAILURE]\n")
        handle.write("exit_code={}\n".format(rc))
        handle.write("upstream_log=not captured; the failure occurred before logging or an existing acme.sh LOG_FILE overrode the temporary environment value\n")
        handle.write("note=use the visible terminal error together with this diagnostic; if acme.sh has a persistent log, pass it explicitly with acme diagnose --log FILE\n")
    os.chmod(path, 0o600)
    return path


def _read_bounded_raw(path):
    fd = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        with os.fdopen(fd, "rb") as handle:
            fd = None
            if st.st_size > MAX_RAW_FALLBACK_BYTES:
                handle.seek(st.st_size - MAX_RAW_FALLBACK_BYTES)
                handle.readline()
            return handle.read(MAX_RAW_FALLBACK_BYTES)
    except OSError:
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _persist_raw_fallback(evidence_path):
    data = _read_bounded_raw(evidence_path)
    if data is None:
        return evidence_path
    try:
        directory = _diagnostic_dir()
        final_raw = os.path.join(directory, RAW_FALLBACK_NAME)
        if os.path.lexists(final_raw):
            st = os.lstat(final_raw)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid():
                return evidence_path
            os.unlink(final_raw)
        fd, staged = tempfile.mkstemp(prefix=".last-issue-evidence.", suffix=".tmp", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                fd = None
                handle.write(data)
            os.replace(staged, final_raw)
            os.chmod(final_raw, 0o600)
            return final_raw
        finally:
            if fd is not None:
                os.close(fd)
            if os.path.exists(staged):
                os.unlink(staged)
    except (OSError, RuntimeError):
        return evidence_path


def _clear_stale():
    try:
        directory = _diagnostic_dir(create=False)
        if not directory:
            return
    except Exception:
        return
    for name in (DIAGNOSTIC_NAME, RAW_FALLBACK_NAME):
        path = os.path.join(directory, name)
        try:
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid():
                os.unlink(path)
        except OSError:
            pass


def _make_diagnostic(core_path, evidence_path, evidence_owned, lang):
    """Return a raw evidence path that must be retained, or an empty string."""
    messages = _messages(lang)
    try:
        directory = _diagnostic_dir()
        final_path = os.path.join(directory, DIAGNOSTIC_NAME)
        fd, staged = tempfile.mkstemp(prefix=".last-issue-diagnostic.", suffix=".tmp", dir=directory)
        os.close(fd)
        os.unlink(staged)
        proc = subprocess.run(
            [sys.executable, "-S", core_path, "diagnose", "--output", staged, "--log", evidence_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=300,
        )
        if proc.returncode == 0 and os.path.isfile(staged):
            os.chmod(staged, 0o600)
            os.replace(staged, final_path)
            sys.stderr.write(messages["saved"].format(final_path) + "\n")
            sys.stderr.write(messages["review"] + "\n")
            sys.stderr.flush()
            return ""
        try:
            if os.path.exists(staged):
                os.unlink(staged)
        except OSError:
            pass
    except Exception:
        pass

    if not evidence_owned:
        sys.stderr.write(messages["user_log_fail"].format(evidence_path) + "\n")
        sys.stderr.flush()
        return ""

    raw_path = _persist_raw_fallback(evidence_path)
    sys.stderr.write(messages["fallback"].format(raw_path) + "\n")
    sys.stderr.write(messages["fallback_warn"] + "\n")
    sys.stderr.flush()
    return raw_path if raw_path == evidence_path else ""


def _run_issue(core_path, argv):
    lang = _language(argv)
    explicit, user_log = _explicit_log(argv)
    automatic_log = _private_temp("acme-helper-upstream-issue-", ".log")
    child_env = os.environ.copy()
    child_env["LOG_FILE"] = automatic_log
    retain = ""
    try:
        rc = subprocess.call([sys.executable, "-S", core_path] + list(argv), env=child_env)
        if rc == 0:
            _clear_stale()
            return 0

        if explicit and user_log and _regular_nonempty(user_log):
            evidence = user_log
            evidence_owned = False
        elif _regular_nonempty(automatic_log):
            evidence = automatic_log
            evidence_owned = True
        else:
            evidence = _generic_failure_evidence(rc)
            evidence_owned = True
        try:
            retain = _make_diagnostic(core_path, evidence, evidence_owned, lang)
        finally:
            if evidence_owned and evidence != retain:
                try:
                    os.unlink(evidence)
                except OSError:
                    pass
        return rc
    except KeyboardInterrupt:
        return 130
    finally:
        if automatic_log != retain:
            try:
                os.unlink(automatic_log)
            except OSError:
                pass


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("acme: runtime wrapper requires the acme_cli.py path\n")
        return 2
    core_path = os.path.abspath(sys.argv[1])
    argv = list(sys.argv[2:])
    if not _issue_intent(argv):
        os.execv(sys.executable, [sys.executable, "-S", core_path] + argv)
    return _run_issue(core_path, argv)


if __name__ == "__main__":
    raise SystemExit(main())
