#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REMOTE_USER=""
REMOTE_HOST=""
SSH_PORT="22"
SSH_PASSWORD=""
ASK_PASSWORD="0"
IDENTITY_FILE=""
REMOTE_PATH="/usr/local/bin/vpn-agent"
REMOTE_TMP_DIR="/tmp"
GOARCH_VALUE="amd64"
LOCAL_BINARY=""
SKIP_BUILD="0"
SKIP_INSPECT="0"

SUDO_MODE="auto"
SUDO_PASSWORD=""
ASK_SUDO_PASSWORD="0"
REUSE_PASSWORD_FOR_SUDO="0"

CONTAINER="amnezia-awg2"
INTERFACE="awg0"
CONFIG_PATH="/opt/amnezia/awg/awg0.conf"
CLIENTS_TABLE_PATH="/opt/amnezia/awg/clientsTable"
LOCK_PATH="/var/lock/vpn-agent.lock"
ENDPOINT_HOST=""

INSTALL_SERVICE="0"
SERVICE_NAME="vpn-agent"
LISTEN="127.0.0.1:8090"
HMAC_KEY_ID=""
HMAC_SECRET=""
ALLOW_IPS="127.0.0.1,::1"
ALLOW_NO_AUTH="0"

KEEP_ARTIFACT="0"
VERBOSE="0"

BUILD_DIR=""

usage() {
    cat <<USAGE
Usage:
  $SCRIPT_NAME --user USER --host IP_OR_HOST [options]

Required:
  --user USER                 SSH username, for example root
  --host IP_OR_HOST           SSH host/IP

Authentication:
  --password PASSWORD         SSH password. Requires sshpass on local machine
  --ask-password              Prompt for SSH password. Requires sshpass
  --identity-file PATH        SSH private key path. Optional; default SSH config/agent is used
  --ssh-port PORT             SSH port. Default: 22

Privilege escalation on remote host:
  --sudo                      Use sudo for install commands
  --no-sudo                   Do not use sudo
  --sudo-password PASSWORD    Password for sudo -S
  --ask-sudo-password         Prompt for sudo password
  --reuse-password-for-sudo   Reuse SSH password as sudo password

Build/upload:
  --remote-path PATH          Install path. Default: /usr/local/bin/vpn-agent
  --remote-tmp-dir PATH       Remote temp dir. Default: /tmp
  --arch ARCH                 Target GOARCH. Default: amd64
  --binary PATH               Upload this already-built binary
  --skip-build                Do not build; requires --binary
  --skip-inspect              Do not run vpn-agent inspect after install
  --keep-artifact             Keep local temporary build artifact

Agent defaults:
  --container NAME            Default: amnezia-awg2
  --interface NAME            Default: awg0
  --config-path PATH          Default: /opt/amnezia/awg/awg0.conf
  --clients-table-path PATH   Default: /opt/amnezia/awg/clientsTable
  --lock-path PATH            Default: /var/lock/vpn-agent.lock
  --endpoint-host HOST        Stored in systemd env and used by serve/issue callers

Optional systemd service:
  --install-service           Install and restart a systemd service for vpn-agent serve
  --service-name NAME         Default: vpn-agent
  --listen ADDR               Default: 127.0.0.1:8090
  --hmac-key-id KEY_ID        HMAC key id for HTTP API
  --hmac-secret SECRET        HMAC secret for HTTP API
  --allow-ip LIST             Comma-separated allowed IPs/CIDRs. Default: 127.0.0.1,::1
  --allow-no-auth             Allow unsigned HTTP requests when HMAC secret is empty

Other:
  --verbose                   Print commands before executing
  -h, --help                  Show this help

Examples:
  $SCRIPT_NAME --user root --host 203.0.113.10

  $SCRIPT_NAME --user root --host 203.0.113.10 --ask-password

  $SCRIPT_NAME --user ubuntu --host 203.0.113.10 --identity-file ~/.ssh/id_ed25519 --sudo

  $SCRIPT_NAME --user root --host 203.0.113.10 \\
    --install-service \\
    --endpoint-host 203.0.113.10 \\
    --hmac-key-id backend \\
    --hmac-secret 'change-me'
USAGE
}

log() {
    printf '[deploy-agent] %s\n' "$*" >&2
}

die() {
    printf '[deploy-agent] error: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

shell_quote() {
    local value="${1-}"
    printf "'%s'" "${value//\'/\'\\\'\'}"
}

env_quote() {
    local value="${1-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --user)
                REMOTE_USER="${2-}"; shift 2 ;;
            --host)
                REMOTE_HOST="${2-}"; shift 2 ;;
            --password)
                SSH_PASSWORD="${2-}"; shift 2 ;;
            --ask-password)
                ASK_PASSWORD="1"; shift ;;
            --identity-file|-i)
                IDENTITY_FILE="${2-}"; shift 2 ;;
            --ssh-port|-p)
                SSH_PORT="${2-}"; shift 2 ;;
            --sudo)
                SUDO_MODE="yes"; shift ;;
            --no-sudo)
                SUDO_MODE="no"; shift ;;
            --sudo-password)
                SUDO_PASSWORD="${2-}"; shift 2 ;;
            --ask-sudo-password)
                ASK_SUDO_PASSWORD="1"; shift ;;
            --reuse-password-for-sudo)
                REUSE_PASSWORD_FOR_SUDO="1"; shift ;;
            --remote-path)
                REMOTE_PATH="${2-}"; shift 2 ;;
            --remote-tmp-dir)
                REMOTE_TMP_DIR="${2-}"; shift 2 ;;
            --arch)
                GOARCH_VALUE="${2-}"; shift 2 ;;
            --binary)
                LOCAL_BINARY="${2-}"; shift 2 ;;
            --skip-build)
                SKIP_BUILD="1"; shift ;;
            --skip-inspect)
                SKIP_INSPECT="1"; shift ;;
            --keep-artifact)
                KEEP_ARTIFACT="1"; shift ;;
            --container)
                CONTAINER="${2-}"; shift 2 ;;
            --interface)
                INTERFACE="${2-}"; shift 2 ;;
            --config-path)
                CONFIG_PATH="${2-}"; shift 2 ;;
            --clients-table-path)
                CLIENTS_TABLE_PATH="${2-}"; shift 2 ;;
            --lock-path)
                LOCK_PATH="${2-}"; shift 2 ;;
            --endpoint-host)
                ENDPOINT_HOST="${2-}"; shift 2 ;;
            --install-service)
                INSTALL_SERVICE="1"; shift ;;
            --service-name)
                SERVICE_NAME="${2-}"; shift 2 ;;
            --listen)
                LISTEN="${2-}"; shift 2 ;;
            --hmac-key-id)
                HMAC_KEY_ID="${2-}"; shift 2 ;;
            --hmac-secret)
                HMAC_SECRET="${2-}"; shift 2 ;;
            --allow-ip)
                ALLOW_IPS="${2-}"; shift 2 ;;
            --allow-no-auth)
                ALLOW_NO_AUTH="1"; shift ;;
            --verbose)
                VERBOSE="1"; shift ;;
            -h|--help)
                usage; exit 0 ;;
            *)
                die "unknown argument: $1" ;;
        esac
    done
}

validate_args() {
    [[ -n "$REMOTE_USER" ]] || die "--user is required"
    [[ -n "$REMOTE_HOST" ]] || die "--host is required"
    [[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "--ssh-port must be a number"
    [[ -n "$REMOTE_PATH" ]] || die "--remote-path cannot be empty"
    [[ -n "$REMOTE_TMP_DIR" ]] || die "--remote-tmp-dir cannot be empty"
    [[ -n "$GOARCH_VALUE" ]] || die "--arch cannot be empty"
    [[ -n "$CONTAINER" ]] || die "--container cannot be empty"
    [[ -n "$INTERFACE" ]] || die "--interface cannot be empty"
    [[ -n "$CONFIG_PATH" ]] || die "--config-path cannot be empty"
    [[ -n "$CLIENTS_TABLE_PATH" ]] || die "--clients-table-path cannot be empty"
    [[ -n "$LOCK_PATH" ]] || die "--lock-path cannot be empty"
    [[ -n "$SERVICE_NAME" ]] || die "--service-name cannot be empty"
    [[ "$SERVICE_NAME" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "--service-name contains unsupported characters"

    if [[ "$SKIP_BUILD" == "1" && -z "$LOCAL_BINARY" ]]; then
        die "--skip-build requires --binary"
    fi
    if [[ -n "$LOCAL_BINARY" && ! -f "$LOCAL_BINARY" ]]; then
        die "binary does not exist: $LOCAL_BINARY"
    fi
    if [[ -n "$IDENTITY_FILE" && ! -f "$IDENTITY_FILE" ]]; then
        die "identity file does not exist: $IDENTITY_FILE"
    fi
    if [[ -n "$IDENTITY_FILE" && ( -n "$SSH_PASSWORD" || "$ASK_PASSWORD" == "1" ) ]]; then
        die "--identity-file cannot be combined with --password/--ask-password: password mode disables pubkey authentication"
    fi
    if [[ "$ALLOW_NO_AUTH" == "1" && -n "$HMAC_SECRET" ]]; then
        die "--allow-no-auth is only meaningful when --hmac-secret is empty"
    fi
    if [[ "$INSTALL_SERVICE" == "1" && -z "$HMAC_SECRET" && "$ALLOW_NO_AUTH" != "1" ]]; then
        die "--install-service with empty --hmac-secret requires --allow-no-auth, or provide --hmac-secret"
    fi
    if [[ -z "$ENDPOINT_HOST" ]]; then
        ENDPOINT_HOST="$REMOTE_HOST"
    fi
}

prompt_passwords() {
    if [[ "$ASK_PASSWORD" == "1" && -z "$SSH_PASSWORD" ]]; then
        read -r -s -p "SSH password for $REMOTE_USER@$REMOTE_HOST: " SSH_PASSWORD
        printf '\n' >&2
    fi
    if [[ "$REUSE_PASSWORD_FOR_SUDO" == "1" ]]; then
        [[ -n "$SSH_PASSWORD" ]] || die "--reuse-password-for-sudo requires --password or --ask-password"
        SUDO_PASSWORD="$SSH_PASSWORD"
    fi
    if [[ "$ASK_SUDO_PASSWORD" == "1" && -z "$SUDO_PASSWORD" ]]; then
        read -r -s -p "sudo password for $REMOTE_USER@$REMOTE_HOST: " SUDO_PASSWORD
        printf '\n' >&2
    fi
}

init_tools() {
    need_cmd ssh
    need_cmd scp
    if [[ -n "$SSH_PASSWORD" ]]; then
        need_cmd sshpass
    fi
    if [[ "$SKIP_BUILD" != "1" && -z "$LOCAL_BINARY" ]]; then
        need_cmd go
    fi
}

ssh_args() {
    local args=(
        -p "$SSH_PORT"
        -o BatchMode=yes
        -o StrictHostKeyChecking=accept-new
        -o ConnectTimeout=10
    )
    if [[ -n "$SSH_PASSWORD" ]]; then
        args=(
            -p "$SSH_PORT"
            -o PubkeyAuthentication=no
            -o PreferredAuthentications=password
            -o StrictHostKeyChecking=accept-new
            -o ConnectTimeout=10
        )
    fi
    if [[ -n "$IDENTITY_FILE" ]]; then
        args+=(-i "$IDENTITY_FILE")
    fi
    printf '%s\0' "${args[@]}"
}

scp_args() {
    local args=(
        -P "$SSH_PORT"
        -o BatchMode=yes
        -o StrictHostKeyChecking=accept-new
        -o ConnectTimeout=10
    )
    if [[ -n "$SSH_PASSWORD" ]]; then
        args=(
            -P "$SSH_PORT"
            -o PubkeyAuthentication=no
            -o PreferredAuthentications=password
            -o StrictHostKeyChecking=accept-new
            -o ConnectTimeout=10
        )
    fi
    if [[ -n "$IDENTITY_FILE" ]]; then
        args+=(-i "$IDENTITY_FILE")
    fi
    printf '%s\0' "${args[@]}"
}

remote_target() {
    printf '%s@%s' "$REMOTE_USER" "$REMOTE_HOST"
}

read_null_args() {
    local -n out_ref="$1"
    out_ref=()
    while IFS= read -r -d '' item; do
        out_ref+=("$item")
    done
}

remote_exec() {
    local command="$1"
    local target
    local args
    target="$(remote_target)"
    read_null_args args < <(ssh_args)
    if [[ "$VERBOSE" == "1" ]]; then
        log "ssh $target $command"
    fi
    if [[ -n "$SSH_PASSWORD" ]]; then
        SSHPASS="$SSH_PASSWORD" sshpass -e ssh "${args[@]}" "$target" "$command"
    else
        ssh "${args[@]}" "$target" "$command"
    fi
}

remote_exec_stdin() {
    local input="$1"
    local command="$2"
    local target
    local args
    target="$(remote_target)"
    read_null_args args < <(ssh_args)
    if [[ "$VERBOSE" == "1" ]]; then
        log "ssh $target $command"
    fi
    if [[ -n "$SSH_PASSWORD" ]]; then
        printf '%s' "$input" | SSHPASS="$SSH_PASSWORD" sshpass -e ssh "${args[@]}" "$target" "$command"
    else
        printf '%s' "$input" | ssh "${args[@]}" "$target" "$command"
    fi
}

remote_copy() {
    local source="$1"
    local dest="$2"
    local target
    local args
    target="$(remote_target)"
    read_null_args args < <(scp_args)
    if [[ "$VERBOSE" == "1" ]]; then
        log "scp $source $target:$dest"
    fi
    if [[ -n "$SSH_PASSWORD" ]]; then
        SSHPASS="$SSH_PASSWORD" sshpass -e scp "${args[@]}" "$source" "$target:$dest"
    else
        scp "${args[@]}" "$source" "$target:$dest"
    fi
}

effective_sudo_mode() {
    if [[ "$SUDO_MODE" == "yes" || "$SUDO_MODE" == "no" ]]; then
        printf '%s' "$SUDO_MODE"
        return
    fi
    if [[ "$REMOTE_USER" == "root" ]]; then
        printf 'no'
    else
        printf 'yes'
    fi
}

remote_exec_privileged() {
    local command="$1"
    local sudo
    sudo="$(effective_sudo_mode)"
    if [[ "$sudo" == "no" ]]; then
        remote_exec "$command"
        return
    fi

    if [[ -n "$SUDO_PASSWORD" ]]; then
        remote_exec_stdin "$SUDO_PASSWORD"$'\n' "sudo -S -p '' sh -lc $(shell_quote "$command")"
    else
        remote_exec "sudo -n sh -lc $(shell_quote "$command")"
    fi
}

cleanup() {
    if [[ -n "$BUILD_DIR" && "$KEEP_ARTIFACT" != "1" && -d "$BUILD_DIR" ]]; then
        rm -rf "$BUILD_DIR"
    fi
}

build_binary() {
    if [[ -n "$LOCAL_BINARY" ]]; then
        printf '%s' "$LOCAL_BINARY"
        return
    fi

    BUILD_DIR="$(mktemp -d)"
    local out="$BUILD_DIR/vpn-agent-linux-$GOARCH_VALUE"
    log "building linux/$GOARCH_VALUE binary"
    (
        cd "$AGENT_DIR"
        GOOS=linux GOARCH="$GOARCH_VALUE" CGO_ENABLED=0 go build -o "$out" ./cmd/vpn-agent
    )
    printf '%s' "$out"
}

install_binary() {
    local binary="$1"
    local remote_tmp="$REMOTE_TMP_DIR/vpn-agent.deploy.$(date +%s).$$"
    log "uploading binary to $(remote_target):$remote_tmp"
    remote_copy "$binary" "$remote_tmp"

    log "installing binary to $REMOTE_PATH"
    remote_exec_privileged "mkdir -p $(shell_quote "$(dirname "$REMOTE_PATH")") && install -m 0755 $(shell_quote "$remote_tmp") $(shell_quote "$REMOTE_PATH") && rm -f $(shell_quote "$remote_tmp")"
}

write_temp_file() {
    local content="$1"
    local suffix="$2"
    if [[ -z "$BUILD_DIR" ]]; then
        BUILD_DIR="$(mktemp -d)"
    fi
    local file="$BUILD_DIR/$suffix"
    printf '%s' "$content" > "$file"
    printf '%s' "$file"
}

install_service() {
    local service_path="/etc/systemd/system/$SERVICE_NAME.service"
    local env_dir="/etc/vpn-agent"
    local env_path="$env_dir/$SERVICE_NAME.env"
    local remote_env_tmp="$REMOTE_TMP_DIR/$SERVICE_NAME.env.deploy.$(date +%s).$$"
    local remote_service_tmp="$REMOTE_TMP_DIR/$SERVICE_NAME.service.deploy.$(date +%s).$$"
    local allow_no_auth_value=""
    if [[ "$ALLOW_NO_AUTH" == "1" ]]; then
        allow_no_auth_value="1"
    fi

    local env_content
    env_content="$(cat <<EOF
VPN_AGENT_BIN=$(env_quote "$REMOTE_PATH")
VPN_AGENT_CONTAINER=$(env_quote "$CONTAINER")
VPN_AGENT_INTERFACE=$(env_quote "$INTERFACE")
VPN_AGENT_CONFIG_PATH=$(env_quote "$CONFIG_PATH")
VPN_AGENT_CLIENTS_TABLE_PATH=$(env_quote "$CLIENTS_TABLE_PATH")
VPN_AGENT_LOCK_PATH=$(env_quote "$LOCK_PATH")
VPN_AGENT_ENDPOINT_HOST=$(env_quote "$ENDPOINT_HOST")
VPN_AGENT_LISTEN=$(env_quote "$LISTEN")
VPN_AGENT_KEY_ID=$(env_quote "$HMAC_KEY_ID")
VPN_AGENT_SECRET=$(env_quote "$HMAC_SECRET")
VPN_AGENT_ALLOW_IPS=$(env_quote "$ALLOW_IPS")
VPN_AGENT_ALLOW_NO_AUTH=$(env_quote "$allow_no_auth_value")
EOF
)"

    local service_content
    service_content="$(cat <<'EOF'
[Unit]
Description=vpn-agent
After=docker.service
Requires=docker.service

[Service]
Type=simple
EnvironmentFile=/etc/vpn-agent/vpn-agent.env
ExecStart=/bin/sh -lc 'exec "$VPN_AGENT_BIN" serve --container "$VPN_AGENT_CONTAINER" --interface "$VPN_AGENT_INTERFACE" --config-path "$VPN_AGENT_CONFIG_PATH" --clients-table-path "$VPN_AGENT_CLIENTS_TABLE_PATH" --lock-path "$VPN_AGENT_LOCK_PATH" --endpoint-host "$VPN_AGENT_ENDPOINT_HOST" --listen "$VPN_AGENT_LISTEN" --allow-ip "$VPN_AGENT_ALLOW_IPS" ${VPN_AGENT_ALLOW_NO_AUTH:+--allow-no-auth}'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
)"
    service_content="${service_content//\/etc\/vpn-agent\/vpn-agent.env/$env_path}"

    local env_file
    local service_file
    env_file="$(write_temp_file "$env_content"$'\n' "$SERVICE_NAME.env")"
    service_file="$(write_temp_file "$service_content"$'\n' "$SERVICE_NAME.service")"

    log "uploading systemd unit and env file"
    remote_copy "$env_file" "$remote_env_tmp"
    remote_copy "$service_file" "$remote_service_tmp"

    log "installing systemd service $SERVICE_NAME"
    remote_exec_privileged "mkdir -p $(shell_quote "$env_dir") && install -m 0600 $(shell_quote "$remote_env_tmp") $(shell_quote "$env_path") && install -m 0644 $(shell_quote "$remote_service_tmp") $(shell_quote "$service_path") && rm -f $(shell_quote "$remote_env_tmp") $(shell_quote "$remote_service_tmp") && systemctl daemon-reload && systemctl enable $(shell_quote "$SERVICE_NAME") && systemctl restart $(shell_quote "$SERVICE_NAME")"
}

verify_remote_basics() {
    log "checking remote host"
    remote_exec "command -v docker >/dev/null && docker --version"
    remote_exec_privileged "test -x $(shell_quote "$REMOTE_PATH") && $(shell_quote "$REMOTE_PATH") --help >/dev/null"
}

run_inspect() {
    if [[ "$SKIP_INSPECT" == "1" ]]; then
        log "skipping inspect"
        return
    fi
    log "running remote inspect"
    remote_exec_privileged "$(shell_quote "$REMOTE_PATH") inspect --container $(shell_quote "$CONTAINER") --interface $(shell_quote "$INTERFACE") --config-path $(shell_quote "$CONFIG_PATH") --clients-table-path $(shell_quote "$CLIENTS_TABLE_PATH") --lock-path $(shell_quote "$LOCK_PATH")"
}

print_summary() {
    cat <<EOF >&2

[deploy-agent] deployment completed
  target:       $(remote_target)
  binary:       $REMOTE_PATH
  container:    $CONTAINER
  interface:    $INTERFACE
  config:       $CONFIG_PATH
  clientsTable: $CLIENTS_TABLE_PATH
EOF
    if [[ "$INSTALL_SERVICE" == "1" ]]; then
        cat <<EOF >&2
  service:      $SERVICE_NAME
  listen:       $LISTEN

Useful remote commands:
  ssh -p $SSH_PORT $(remote_target) 'systemctl status $SERVICE_NAME --no-pager'
  ssh -p $SSH_PORT $(remote_target) '$REMOTE_PATH peers'
EOF
    else
        cat <<EOF >&2

Useful remote command:
  ssh -p $SSH_PORT $(remote_target) '$REMOTE_PATH peers'
EOF
    fi
}

main() {
    parse_args "$@"
    validate_args
    prompt_passwords
    init_tools
    trap cleanup EXIT

    local binary
    binary="$(build_binary)"
    install_binary "$binary"
    verify_remote_basics
    if [[ "$INSTALL_SERVICE" == "1" ]]; then
        install_service
    fi
    run_inspect
    print_summary
}

main "$@"
