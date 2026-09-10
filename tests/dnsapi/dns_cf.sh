#!/usr/bin/env sh
# shellcheck disable=SC2034
dns_cf_info='CloudFlare
Site: CloudFlare.com
Docs: github.com/acmesh-official/acme.sh/wiki/dnsapi#dns_cf
Options:
CF_Key API Key
CF_Email Your account email
OptionsAlt:
CF_Token API Token
CF_Account_ID Account ID
CF_Zone_ID Zone ID. Optional.
'
_cf_legacy() { CF_Key="${CF_Key:-$(_readaccountconf_mutable CF_Key)}"; CF_Email="${CF_Email:-$(_readaccountconf_mutable CF_Email)}"; }
_cf_token() { CF_Token="${CF_Token:-$(_readaccountconf_mutable CF_Token)}"; CF_Account_ID="${CF_Account_ID:-$(_readaccountconf_mutable CF_Account_ID)}"; CF_Zone_ID="${CF_Zone_ID:-$(_readaccountconf_mutable CF_Zone_ID)}"; }
