#!/usr/bin/env sh
# shellcheck disable=SC2034
dns_alt_info='Alternative Credential Fixture
Site: example.invalid
Docs: https://example.invalid/alt
Options:
ALT_TOKEN Preferred token
OptionsAlt:
ALT_USER Legacy user
ALT_PASS Legacy password
'
_alt_load() { ALT_TOKEN="${ALT_TOKEN:-$(_readaccountconf_mutable ALT_TOKEN)}"; ALT_USER="${ALT_USER:-$(_readaccountconf_mutable ALT_USER)}"; ALT_PASS="${ALT_PASS:-$(_readaccountconf_mutable ALT_PASS)}"; }
