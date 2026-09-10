#!/usr/bin/env sh
# shellcheck disable=SC2034,SC2154
dns_namesilo_info='NameSilo.com
Site: NameSilo.com
Docs: github.com/acmesh-official/acme.sh/wiki/dnsapi#dns_namesilo
Options:
Namesilo_Key API Key
Author: fixture
'
_namesilo_load() { _saveaccountconf Namesilo_Key "$Namesilo_Key"; }
