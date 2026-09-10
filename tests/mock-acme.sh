#!/usr/bin/env bash
set -u
embedded_version="3.1.5"
version="${MOCK_ACME_VERSION:-$embedded_version}"
if [[ -n "${MOCK_VERSION_FILE:-}" && -r "${MOCK_VERSION_FILE}" ]]; then
  version=$(cat -- "${MOCK_VERSION_FILE}")
fi
log_history() {
  if [[ -n "${MOCK_HISTORY:-}" ]]; then
    {
      printf 'CALL'
      for item in "$@"; do printf '\t%s' "$item"; done
      printf '\n'
    } >> "${MOCK_HISTORY}"
  fi
}
log_history "$@"
if [[ -n "${MOCK_ENV_LOG:-}" ]]; then
  {
    printf 'TESTDEPLOY_TOKEN=%s\n' "${TESTDEPLOY_TOKEN:-}"
    printf 'TESTDEPLOY_HOST=%s\n' "${TESTDEPLOY_HOST:-}"
    printf 'TESTNOTIFY_TOKEN=%s\n' "${TESTNOTIFY_TOKEN:-}"
  } >> "$MOCK_ENV_LOG"
fi
if [[ "${1:-}" == "--version" ]]; then
printf '%s\n' 'https://github.com/acmesh-official/acme.sh' "v${version}"
exit 0
fi
if [[ "${1:-}" == "--help" ]]; then
cat <<'HELP'
https://github.com/acmesh-official/acme.sh
v3.1.5
Usage: acme.sh <command> ... [parameters ...]
Commands:
  -h, --help               Show this help message.
  -v, --version            Show version info.
  --install                Install acme.sh to your system.
  --uninstall              Uninstall acme.sh.
  --upgrade                Upgrade acme.sh.
  --issue                  Issue a cert.
  --deploy                 Deploy the cert.
  -i, --install-cert       Install the issued cert.
  -r, --renew              Renew a cert.
  --renew-all              Renew all certs.
  --revoke                 Revoke a cert.
  --remove                 Remove a cert.
  --list                   List certs.
  --info                   Show configs.
  --to-pkcs12              Export pfx.
  --to-pkcs8               Convert to pkcs8.
  --sign-csr               Sign CSR.
  --show-csr               Show CSR.
  -ccr, --create-csr       Create CSR.
  --create-domain-key      Create domain key.
  --update-account         Update account.
  --update-account-key     Rotate account key.
  --register-account       Register account.
  --deactivate-account     Deactivate account.
  --make-dns-persist-value Make dns persist value.
  --create-account-key     Create account key.
  --install-cronjob        Install cron.
  --uninstall-cronjob      Uninstall cron.
  --cron                   Run cron.
  --set-notify             Set notify.
  --deactivate             Deactivate authz.
  --set-default-ca         Set default CA.
  --set-default-chain      Set default chain.
Parameters:
  -d, --domain <domain.tld>         Domain.
  --challenge-alias <domain.tld>    Challenge alias.
  --domain-alias <domain.tld>       Domain alias.
  --preferred-chain <chain>         Preferred chain.
  --cert-profile, --certificate-profile <profile>  Certificate profile.
  --valid-to <date-time>            NotAfter.
  --valid-from <date-time>          NotBefore.
  -f, --force                       Force.
  --staging, --test                 Staging.
  --debug [0|1|2|3]                 Debug.
  --output-insecure                 Show secrets.
  -w, --webroot <directory>         Webroot.
  --standalone                      Standalone.
  --alpn                            ALPN.
  --stateless                       Stateless.
  --apache                          Apache.
  --dns [dns_hook]                  DNS.
  --dns-persist                     DNS persist.
  --dnssleep <seconds>              DNS sleep.
  -k, --keylength <bits>            Key length.
  -ak, --accountkeylength <bits>    Account key length.
  --log [file]                      Log.
  --log-level <1|2>                 Log level.
  --syslog <0|3|6|7>                Syslog.
  --eab-kid <eab_key_id>            EAB kid.
  --eab-hmac-key <eab_hmac_key>     EAB secret.
  --dns-persist-wildcard            DNS persist wildcard.
  --dns-persist-ca-name <name>      DNS persist CA.
  --dns-persist-days <N>            DNS persist days.
  --cert-file <file>                Cert output.
  --key-file <file>                 Key output.
  --ca-file <file>                  CA output.
  --fullchain-file <file>           Fullchain output.
  --reloadcmd <command>             Reload command.
  --server <server_uri>             Server.
  --accountconf <file>              Account conf.
  --home <directory>                Home.
  --cert-home <directory>           Cert home.
  --config-home <directory>         Config home.
  --useragent <string>              User agent.
  -m, --email <email>               Email.
  --accountkey <file>               Account key.
  --days <ndays>                    Renew days.
  --httpport <port>                 HTTP port.
  --tlsport <port>                  TLS port.
  --local-address <ip>              Local address.
  --listraw                         Raw list.
  -se, --stop-renew-on-error        Stop renewal.
  --treat-skip-as-success           Treat skip success.
  --insecure                        Insecure TLS.
  --ca-bundle <file>                CA bundle.
  --ca-path <directory>             CA path.
  --no-cron                         No cron.
  --no-profile                      No profile.
  --no-color                        No color.
  --force-color                     Force color.
  --ecc                             ECC.
  --csr <file>                      CSR.
  --pre-hook <command>              Pre hook.
  --post-hook <command>             Post hook.
  --renew-hook <command>            Renew hook.
  --deploy-hook <hookname>          Deploy hook.
  --extended-key-usage <string>     Extended key usage.
  --ocsp, --ocsp-must-staple        OCSP staple.
  --always-force-new-domain-key     New key every renewal.
  --auto-upgrade [0|1]              Auto upgrade.
  --listen-v4                       Listen IPv4.
  --listen-v6                       Listen IPv6.
  --request-v4                      Request IPv4.
  --request-v6                      Request IPv6.
  --openssl-bin <file>              OpenSSL.
  --use-wget                        Use wget.
  --yes-I-know-dns-manual-mode-enough-go-ahead-please  Manual DNS ack.
  -b, --branch <branch>             Branch.
  --notify-level <0|1|2|3>          Notify level.
  --notify-mode <0|1>               Notify mode.
  --notify-hook <hookname>          Notify hook.
  --notify-source <server name>     Notify source.
  --revoke-reason <0-10>            Revoke reason.
  --password <password>             Export password.
HELP
exit 0
fi

log="${MOCK_LOG:-/tmp/mock-acme.log}"
printf '%s\n' "$@" > "$log"
if [[ "${1:-}" == "--list" && " ${*} " == *" --listraw "* ]]; then
  if [[ -n "${MOCK_CERT_LIST:-}" && -r "${MOCK_CERT_LIST}" ]]; then
    cat -- "$MOCK_CERT_LIST"
  else
    printf '%s\n' 'Main_Domain|KeyLength|SAN_Domains|Profile|CA|Created|Renew'
  fi
  exit 0
fi
if [[ "${1:-}" == "--info" ]]; then
  domain=''
  prev=''
  for item in "$@"; do
    if [[ "$prev" == "-d" || "$prev" == "--domain" ]]; then domain=$item; break; fi
    prev=$item
  done
  if [[ -n "${MOCK_CERT_INFO_DIR:-}" && -n "$domain" ]]; then
    safe=${domain//\*/_wild_}
    safe=${safe//\//_}
    info="${MOCK_CERT_INFO_DIR}/${safe}.info"
    if [[ -r "$info" ]]; then cat -- "$info"; exit 0; fi
  fi
  printf '%s\n' "Le_Domain=$domain" "Le_Alt=no" "Le_Webroot=dns_namesilo"
  exit 0
fi
if [[ "${1:-}" == "--install-cronjob" ]]; then
  [[ -n "${MOCK_CRON_STATE:-}" ]] && printf 'enabled\n' > "$MOCK_CRON_STATE"
  exit "${MOCK_CRON_RC:-0}"
fi
if [[ "${1:-}" == "--uninstall-cronjob" ]]; then
  [[ -n "${MOCK_CRON_STATE:-}" ]] && printf 'disabled\n' > "$MOCK_CRON_STATE"
  exit "${MOCK_CRON_RC:-0}"
fi
if [[ "${1:-}" == "--cron" ]]; then
  exit "${MOCK_CRON_RC:-0}"
fi
if [[ " ${*} " == *" --fail "* ]]; then
  exit 17
fi
prev=''
for arg in "$@"; do
  case "$prev" in
    --cert-file|--key-file|--ca-file|--fullchain-file)
      mkdir -p -- "$(dirname -- "$arg")"
      printf 'MOCK %s\n' "$prev" > "$arg"
      ;;
  esac
  prev="$arg"
done
if [[ "${1:-}" == "--upgrade" ]]; then
  if [[ "${MOCK_UPGRADE_FAIL:-0}" == "1" ]]; then
    exit 23
  fi
  if [[ "${MOCK_UPGRADE_CREATE_NOTIFY:-0}" == "1" ]]; then
    mkdir -p -- "$(dirname -- "$0")/notify"
    printf 'target-only\n' > "$(dirname -- "$0")/notify/target-only.sh"
  fi
  target=''
  prev=''
  for item in "$@"; do
    if [[ "$prev" == "--branch" ]]; then target=$item; break; fi
    prev=$item
  done
  if [[ -n "$target" ]]; then
    normalized=${target#v}
    next_version=''
    if [[ -n "${MOCK_UPGRADE_VERSION:-}" ]]; then
      next_version=$MOCK_UPGRADE_VERSION
    elif [[ "$normalized" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      next_version=$normalized
    fi
    if [[ -n "$next_version" ]]; then
      if [[ -n "${MOCK_VERSION_FILE:-}" ]]; then
        printf '%s\n' "$next_version" > "$MOCK_VERSION_FILE"
      else
        tmp="${0}.tmp.$$"
        sed "s/^embedded_version=.*/embedded_version=\"$next_version\"/" "$0" > "$tmp"
        chmod --reference="$0" "$tmp" 2>/dev/null || chmod 755 "$tmp"
        mv -- "$tmp" "$0"
      fi
    fi
  fi
fi
exit 0
