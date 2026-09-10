#!/usr/bin/env sh
# shellcheck disable=SC2034
dns_raw_info='Raw Persist Fixture
Site: example.invalid
Docs: https://example.invalid/raw
Options:
RAW_TOKEN Raw-persisted token
'
_raw_load() { RAW_TOKEN="${RAW_TOKEN:-$(_readaccountconf RAW_TOKEN)}"; }
