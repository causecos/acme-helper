#!/usr/bin/env sh
# shellcheck disable=SC2034
dns_gd_info='GoDaddy
Site: GoDaddy.com
Docs: https://github.com/acmesh-official/acme.sh/wiki/dnsapi#godaddy
Options:
GD_Key Production API Key
GD_Secret Production API Secret
'
_gd_load() { GD_Key="${GD_Key:-$(_readaccountconf_mutable GD_Key)}"; GD_Secret="${GD_Secret:-$(_readaccountconf_mutable GD_Secret)}"; }
