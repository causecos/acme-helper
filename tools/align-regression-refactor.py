#!/usr/bin/env python3
from pathlib import Path
import hashlib


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit('{}: expected one anchor, found {}'.format(label, text.count(old)))
    return text.replace(old, new, 1)


p = Path('tests/review_v110.py')
text = p.read_text()
text = replace_once(text, "'helper_version=1.10.1' in text", "'helper_version=1.11.0' in text", 'review_v110 version')
p.write_text(text)

p = Path('tests/review_v19.py')
text = p.read_text()
text = text.replace("'acme quick' in p.stderr and 'acme certs' in p.stderr", "'acme issue' in p.stderr and 'acme certs' in p.stderr")
text = text.replace("'catalog unavailable' in p.stderr and 'acme quick' in p.stderr", "'catalog unavailable' in p.stderr and 'acme issue' in p.stderr")

start = text.index('            def quick_cancel(s):')
end = text.index("            Path(e['ACME_ACCOUNT_CONF']).write_text(\"SAVED_Namesilo_Key=''\\n\")", start)
old = text[start:end]
new = '''            def quick_cancel(s):
                s.expect(ui('Domains')).line('cancel.test')
                s.expect(ui('ACME Server')).line('')
                s.expect(ui('Validation mode')).line('')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('')
                s.expect(ui('Configure this DNS provider now?')).line('n')
                s.expect(ui('DNS wait in seconds')).line('')
                s.expect(ui('Key length')).line('')
                s.expect(ui('Output layout')).line('')
                s.expect(ui('Output root directory')).line('')
                s.expect(ui('Certificate directory name')).line('')
                s.expect(ui('Reload command (optional): ')).line('')
                s.expect(ui('Add other upstream parameters?')).line('n')
                s.expect(ui('Start issuing the certificate?')).line('n')
            clear(e)
            pty_check(t,'quick-alias-cancel-'+lang,['quick'],e,quick_cancel,lambda rc,out:rc==0 and '--issue' not in argv(e) and ui('CLI shortcut for next time:') in out and ('acme issue --server letsencrypt --keylength ec-256 --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root ' + e['ACME_OUTPUT_ROOT'] + ' --cert-name cancel.test cancel.test') in out)
            def quick_ok(s):
                s.expect(ui('Domains')).line('quick.test *.quick.test')
                s.expect(ui('Certificate mode')).expect(chooser).line('separate')
                s.expect(ui('ACME Server')).line('')
                s.expect(ui('Validation mode')).line('')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('/namesilo')
                s.expect(ui('DNS API (Enter=default, ?=browse, /term=search)')).line('1')
                s.expect(ui('Configure this DNS provider now?')).line('y')
                s.expect('Namesilo_Key').line('PTY-HIDDEN-KEY')
                s.expect(ui('DNS wait in seconds')).line('')
                s.expect(ui('Key length')).line('')
                s.expect(ui('Output layout')).line('')
                s.expect(ui('Output root directory')).line('')
                s.expect(ui('Certificate group directory name')).line('production')
                s.expect(ui('Reload command (optional): ')).line('')
                s.expect(ui('Add other upstream parameters?')).line('n')
                s.expect(ui('Start issuing {} separate certificates?').format(2)).line('y')
            clear(e);Path(e['ACME_ACCOUNT_CONF']).write_text("SAVED_Namesilo_Key=''\\n")
            pty_check(t,'quick-alias-config-issue-'+lang,['quick'],e,quick_ok,lambda rc,out:rc==0 and 'PTY-HIDDEN-KEY' not in out and '--issue' in argv(e) and '*.quick.test' in argv(e) and ui('CLI shortcut for next time:') in out and ("acme issue --server letsencrypt --keylength ec-256 --cert-mode separate --dns dns_namesilo --dnssleep 120 --output-layout minimal --output-root " + e['ACME_OUTPUT_ROOT'] + " --cert-name production 'quick.test *.quick.test'") in out)
'''
text = text[:start] + new + text[end:]
p.write_text(text)

manifest = Path('SHA256SUMS')
lines = manifest.read_text().splitlines()
for rel in ('./tests/review_v19.py', './tests/review_v110.py'):
    target = Path(rel[2:])
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    matches = [i for i, line in enumerate(lines) if line.endswith('  ' + rel)]
    if len(matches) != 1:
        raise SystemExit('checksum anchor changed: ' + rel)
    lines[matches[0]] = digest + '  ' + rel
manifest.write_text('\n'.join(lines) + '\n')
print('REGRESSION_CONTRACTS_ALIGNED')
