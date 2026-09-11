#!/usr/bin/env python3
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, old, new, label):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit('{}: expected one anchor, found {}'.format(label, count))
    path.write_text(text.replace(old, new, 1))


runtime = ROOT / 'acme_runtime.py'
replace_once(
    runtime,
    '''def _language(argv):
    if len(argv) >= 2 and argv[0] == "--lang" and argv[1] in ("zh-TW", "en"):
        return argv[1]
    env_lang = os.environ.get("ACME_HELPER_LANG") or os.environ.get("ACME_LANG")
''',
    '''def _language(argv):
    if len(argv) >= 2 and argv[0] == "--lang" and argv[1] in ("zh-TW", "en"):
        return argv[1]
    if argv and argv[0].startswith("--lang="):
        value = argv[0].split("=", 1)[1]
        if value in ("zh-TW", "en"):
            return value
    env_lang = os.environ.get("ACME_HELPER_LANG") or os.environ.get("ACME_LANG")
''',
    'runtime language equals form',
)
replace_once(
    runtime,
    '''def _issue_intent(argv):
    args = list(argv)
    if len(args) >= 2 and args[0] == "--lang":
        args = args[2:]
    return bool(args and args[0] in ("issue", "quick"))
''',
    '''def _issue_intent(argv):
    args = list(argv)
    if len(args) >= 2 and args[0] == "--lang":
        args = args[2:]
    elif args and args[0].startswith("--lang="):
        args = args[1:]
    return bool(args and args[0] in ("issue", "quick"))
''',
    'runtime issue intent language equals form',
)
replace_once(runtime, 'RAW_FALLACK_NAME', 'RAW_FALLBACK_NAME', 'runtime raw fallback constant')

replace_once(
    ROOT / 'acme',
    '# ACME Helper v1.10.1 - thin launcher\n',
    '# ACME Helper - thin launcher\n',
    'launcher stale version comment',
)

review = ROOT / 'tests' / 'review_issue_diagnostics.py'
text = review.read_text()
anchor = '''        transient = list(temp_root.glob("acme-helper-upstream-issue-*.log")) + list(temp_root.glob("acme-helper-issue-failure-*.log"))
        t.check("security", "owned-raw-temporary-files-removed", not transient, transient)

        success_env = dict(env, MOCK_ISSUE_RC="0")
'''
insert = '''        transient = list(temp_root.glob("acme-helper-upstream-issue-*.log")) + list(temp_root.glob("acme-helper-issue-failure-*.log"))
        t.check("security", "owned-raw-temporary-files-removed", not transient, transient)

        # The core accepts --lang=VALUE as well as --lang VALUE. The runtime wrapper
        # must classify that form as an issue too, otherwise automatic diagnostics are bypassed.
        if final.exists():
            final.unlink()
        issue_history.write_text("")
        equals_env = dict(failed_env, ACME_HELPER_LANG="zh-TW")
        p = call(["--lang=en"] + issue_args, equals_env)
        calls = history_lines(issue_history)
        t.check("compatibility", "lang-equals-issue-still-wrapped", p.returncode == 17 and len(calls) == 1 and final.is_file(), p.stderr[-1800:])
        t.check("ux", "lang-equals-controls-runtime-message-language", "redacted issue-failure diagnostic saved" in p.stderr, p.stderr[-1800:])

        # Force the redacted-final replace to fail after diagnose itself succeeds. This
        # exercises the private raw-fallback persistence path, including its constant name,
        # while preserving the original upstream exit code.
        if final.exists():
            final.unlink()
        final.mkdir()
        if raw_fallback.exists():
            raw_fallback.unlink()
        p = call(issue_args, failed_env)
        raw_mode = stat.S_IMODE(raw_fallback.stat().st_mode) if raw_fallback.exists() else -1
        t.check("correctness", "post-diagnose-fallback-preserves-issue-code", p.returncode == 17, p.stderr[-1800:])
        t.check("security", "post-diagnose-fallback-persists-private-raw", raw_fallback.is_file() and raw_mode == 0o600, p.stderr[-1800:])
        t.check("ux", "post-diagnose-fallback-warns-not-redacted", "not redacted" in p.stderr and "Do not share it directly" in p.stderr, p.stderr[-1800:])
        final.rmdir()
        if raw_fallback.exists():
            raw_fallback.unlink()

        success_env = dict(env, MOCK_ISSUE_RC="0")
'''
if text.count(anchor) != 1:
    raise SystemExit('review_issue_diagnostics insertion anchor changed')
review.write_text(text.replace(anchor, insert, 1))

changelog = ROOT / 'CHANGELOG.md'
text = changelog.read_text()
anchor = '# Changelog\n\nAll notable user-visible changes to ACME Helper are recorded here. The project follows Semantic Versioning.\n\n'
insert = '''# Changelog

All notable user-visible changes to ACME Helper are recorded here. The project follows Semantic Versioning.

## Unreleased

### Fixed

- Preserve the original certificate-issuance exit code when redacted diagnostic creation fails after staging and the runtime must retain a private raw fallback.
- Route `--lang=en issue`, `--lang=zh-TW issue`, and the equivalent `quick` compatibility alias through the same automatic issue-failure diagnostic wrapper as `--lang VALUE`.
- Remove the stale hard-coded launcher version comment so runtime version output remains the version source of truth.

'''
if text.count(anchor) != 1:
    raise SystemExit('changelog anchor changed')
changelog.write_text(text.replace(anchor, insert, 1))

manifest = ROOT / 'SHA256SUMS'
lines = []
for raw in manifest.read_text().splitlines():
    digest, sep, rel = raw.partition('  ')
    if not sep:
        raise SystemExit('invalid SHA256SUMS line: ' + raw)
    path = ROOT / rel[2:] if rel.startswith('./') else ROOT / rel
    if not path.is_file():
        raise SystemExit('manifest path missing: ' + rel)
    lines.append('{}  {}'.format(hashlib.sha256(path.read_bytes()).hexdigest(), rel))
manifest.write_text('\n'.join(lines) + '\n')

print('SOLO_REVIEW_FIX_APPLIED')
