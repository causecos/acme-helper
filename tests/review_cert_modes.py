#!/usr/bin/env python3
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
