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


replace_once(ROOT / 'acme_cli.py', 'VERSION = "1.11.0"', 'VERSION = "1.11.1"', 'runtime version')
replace_once(ROOT / 'tests' / 'flow_matrix.py', "VERSION = '1.11.0'", "VERSION = '1.11.1'", 'flow version')
replace_once(
    ROOT / 'tests' / 'review_v110.py',
    "t.check('drift-i18n','version-is-v1.11.0',core.VERSION=='1.11.0',core.VERSION)",
    "t.check('drift-i18n','version-is-v1.11.1',core.VERSION=='1.11.1',core.VERSION)",
    'review version contract',
)
replace_once(
    ROOT / 'tests' / 'review_v110.py',
    "'helper_version=1.11.0' in text",
    "'helper_version=1.11.1' in text",
    'diagnostic version contract',
)
replace_once(ROOT / 'CHANGELOG.md', '## Unreleased\n', '## [1.11.1] - 2026-09-12\n', 'changelog release heading')

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
print('VERSION_1_11_1_APPLIED')
