#!/usr/bin/env bash
# ACME Helper v1.10.1 installer
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
PREFIX=${PREFIX:-/usr/local}
BINDIR="$PREFIX/bin"
LIBDIR="$PREFIX/lib/acme"

if [[ "$(uname -s)" != "Linux" ]]; then
  printf 'ACME Helper installer: Linux is the tested platform; current platform is %s\n' "$(uname -s)" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'ACME Helper installer: python3 >= 3.6 is required\n' >&2
  exit 2
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 6) else 1)'; then
  printf 'ACME Helper installer: python3 >= 3.6 is required; found %s\n' "$(python3 --version 2>&1)" >&2
  exit 2
fi
if ! command -v install >/dev/null 2>&1; then
  printf 'ACME Helper installer: the POSIX install utility is required\n' >&2
  exit 2
fi
if [[ ! -r "$SCRIPT_DIR/acme" || ! -r "$SCRIPT_DIR/acme_cli.py" || ! -r "$SCRIPT_DIR/acme_runtime.py" ]]; then
  printf 'ACME Helper installer: acme, acme_cli.py and acme_runtime.py must be beside install.sh\n' >&2
  exit 2
fi

for lang in en zh-TW; do
  if [[ ! -r "$SCRIPT_DIR/locales/$lang.json" ]]; then
    printf 'Missing language catalog: %s\n' "$SCRIPT_DIR/locales/$lang.json" >&2
    exit 2
  fi
done
install -d -m 755 "$BINDIR" "$LIBDIR" "$LIBDIR/locales"
install -m 644 "$SCRIPT_DIR/locales/en.json" "$LIBDIR/locales/en.json"
install -m 644 "$SCRIPT_DIR/locales/zh-TW.json" "$LIBDIR/locales/zh-TW.json"
install -m 755 "$SCRIPT_DIR/acme_cli.py" "$LIBDIR/acme_cli.py"
install -m 755 "$SCRIPT_DIR/acme_runtime.py" "$LIBDIR/acme_runtime.py"
install -m 755 "$SCRIPT_DIR/acme" "$BINDIR/acme"

printf 'Installed ACME Helper to %s\n' "$BINDIR/acme"
"$BINDIR/acme" --version
VERSION_DETAILS=$("$BINDIR/acme" version)
printf '%s\n' "$VERSION_DETAILS"
if [[ "$VERSION_DETAILS" == *"acme_sh_path=not-installed"* ]]; then
  printf 'acme.sh is not installed yet. Next: %s install\n' "$BINDIR/acme"
else
  printf 'acme.sh detected. Run: %s version\n' "$BINDIR/acme"
fi
