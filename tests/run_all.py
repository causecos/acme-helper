#!/usr/bin/env python3
"""Offline regression entry point. Test reports are not production certification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


SAFE_SUITE_ENV_KEYS = {
    'PATH', 'TERM', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ',
    'PYTHONIOENCODING', 'PYTHONUTF8', 'SHELL',
}


def clean_suite_env(dest, name, source=None):
    """Build an isolated environment for offline regression suites.

    Production ACME/provider variables are intentionally not inherited. Each suite gets
    its own HOME and TMPDIR so mock/offline checks cannot accidentally read the host's
    ~/.acme.sh, account.conf, provider credentials, or test fixtures.
    """
    source = os.environ if source is None else source
    env = {key: source[key] for key in SAFE_SUITE_ENV_KEYS if key in source}
    env.setdefault('PATH', os.defpath)
    env.setdefault('TERM', 'xterm')
    home = Path(dest) / ('.suite-home-' + name)
    tmp = Path(dest) / ('.suite-tmp-' + name)
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env['HOME'] = str(home)
    env['TMPDIR'] = str(tmp)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    suites = ['ablation','adversarial','flow_matrix','review_v19','review_v110','review_issue_diagnostics','review_cert_modes']
    parser.add_argument('--report-dir', default='test-results')
    parser.add_argument('--suite', choices=suites, help='Run one suite for bounded CI jobs; omit to use --profile')
    parser.add_argument('--profile', choices=['all','diagnostic'], default='all', help='all = release regression; diagnostic = bounded handoff checks without the long canonical flow matrix')
    args = parser.parse_args()
    if args.suite and args.profile != 'all':
        parser.error('--suite and a non-default --profile are mutually exclusive')
    dest = Path(args.report_dir).resolve(); dest.mkdir(parents=True, exist_ok=True)
    if sys.version_info < (3, 7):
        print('The test harness requires Python 3.7+; runtime syntax targets 3.6+.', file=sys.stderr)
        return 2
    for path in [ROOT/'acme_cli.py', ROOT/'acme_runtime.py'] + sorted((ROOT/'tests').glob('*.py')):
        compile(path.read_text(), str(path), 'exec')
    all_names = suites
    profile_names = {
        'all': all_names,
        'diagnostic': ['ablation','adversarial','review_v19','review_v110','review_issue_diagnostics','review_cert_modes'],
    }
    names = [args.suite] if args.suite else profile_names[args.profile]
    report = {'python': sys.version, 'profile': args.profile if not args.suite else 'suite:'+args.suite,
              'omitted_suites': [name for name in all_names if name not in names],
              'runtime_sha256': {}, 'suites': []}
    for relative in ['acme', 'acme_cli.py', 'acme_runtime.py', 'install.sh', 'locales/en.json', 'locales/zh-TW.json']:
        report['runtime_sha256'][relative] = hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    static_env = clean_suite_env(dest, 'static')
    syntax = subprocess.run(['bash','-n',str(ROOT/'acme')], check=False, env=static_env)
    installer = subprocess.run(['bash','-n',str(ROOT/'install.sh')], check=False, env=static_env)
    if syntax.returncode or installer.returncode:
        print('FAIL: Bash syntax', file=sys.stderr); return 1
    failed = False
    suite_timeouts = {
        'flow_matrix': 600,
        'review_v19': 240,
        'review_v110': 240,
        'review_issue_diagnostics': 240,
        'review_cert_modes': 240,
        'adversarial': 240,
        'ablation': 240,
    }
    for name in names:
        start = time.monotonic(); env = clean_suite_env(dest, name)
        env['ACME_TEST_REPORT'] = str(dest/('{}-cases.json'.format(name)))
        command = [sys.executable, '-u', '-S', str(ROOT/'tests'/(name+'.py'))]
        log_path = dest/(name+'.log')
        # Stream directly to disk: interrupted CI jobs retain the last completed case.
        with log_path.open('w') as log:
            try:
                result = subprocess.run(command, cwd=str(ROOT), env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=suite_timeouts[name])
                rc = result.returncode
            except subprocess.TimeoutExpired:
                log.write('\nFAIL: test suite exceeded {} seconds\n'.format(suite_timeouts[name])); rc = 124
        output = log_path.read_text(errors='replace')
        has_count = bool(re.search(r'(?:SUMMARY(?: PASS)? |PASS round[^\n]* )\d+/[1-9]\d*', output))
        good = rc == 0 and has_count
        failed |= not good
        row = {'suite':name,'exit_code':rc,'passed':good,'nonzero_case_count':has_count,'seconds':round(time.monotonic()-start,3)}
        report['suites'].append(row)
        print(('PASS' if good else 'FAIL')+' '+name+' -> '+str(dest/(name+'.log')), flush=True)
    (dest/('summary-'+args.suite+'.json' if args.suite else 'summary.json')).write_text(json.dumps(report,indent=2)+'\n')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
