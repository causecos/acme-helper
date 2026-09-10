#!/usr/bin/env sh
# shellcheck disable=SC2034
dns_runtime_info='Runtime Only Fixture
Site: example.invalid
Docs: https://example.invalid/runtime
Options:
RUNTIME_TOKEN Runtime-only token
'
_runtime_load() { : "${RUNTIME_TOKEN:-}"; }
