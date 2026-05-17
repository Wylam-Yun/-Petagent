#!/data/data/com.termux/files/usr/bin/sh

HOME_DIR="${HOME_DIR:-/data/data/com.termux/files/home}"
PREFIX_DIR="${PREFIX_DIR:-/data/data/com.termux/files/usr}"
LOG_FILE="$HOME_DIR/.service_manager.log"
LOCK_DIR="$HOME_DIR/.termux_service_manager.lock"
SSHD_PORT="${SSHD_PORT:-8022}"
NETWORK_WAIT_SECONDS="${NETWORK_WAIT_SECONDS:-180}"

export HOME="$HOME_DIR"
export PREFIX="$PREFIX_DIR"
export PATH="$PREFIX_DIR/bin:$PREFIX_DIR/bin/applets:/system/bin:/system/xbin:/su/bin"
export LD_LIBRARY_PATH="$PREFIX_DIR/lib"
export LD_PRELOAD="$PREFIX_DIR/lib/libtermux-exec-ld-preload.so"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

repair_android_context() {
    [ "${PETAGENT_RESTORECON:-1}" = "0" ] && return 0
    command -v su >/dev/null 2>&1 || return 0
    su -c "restorecon -R '$HOME_DIR/Petagent' '$LOCK_DIR' 2>/dev/null" >/dev/null 2>&1 || true
}

remove_lock_dir() {
    rm -rf "$LOCK_DIR" 2>/dev/null && return 0
    repair_android_context
    rm -rf "$LOCK_DIR" 2>/dev/null || true
}

wait_for_network() {
    waited=0
    while [ "$waited" -lt "$NETWORK_WAIT_SECONDS" ]; do
        route="$(ip route get 1.1.1.1 2>/dev/null || true)"
        if printf '%s\n' "$route" | grep -q ' src '; then
            log "start_services: network route ready: $route"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    log "start_services: WARNING network route not ready after ${NETWORK_WAIT_SECONDS}s"
    return 1
}

check_sshd_listen() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | grep -E "[:.]$SSHD_PORT[[:space:]]" | grep -q LISTEN && return 0
    fi

    if command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | grep -E "[:.]$SSHD_PORT[[:space:]]" | grep -q LISTEN && return 0
    fi

    grep -qi ":1F56 .* 0A " /proc/net/tcp /proc/net/tcp6 2>/dev/null
}

start_sshd_once() {
    "$PREFIX_DIR/bin/sshd" -4 2>&1
}

start_sshd_if_needed() {
    if check_sshd_listen; then
        return 0
    fi

    wait_for_network || true

    attempt=1
    while [ "$attempt" -le 5 ]; do
        if check_sshd_listen; then
            log "start_services: sshd is listening on port $SSHD_PORT"
            return 0
        fi

        log "start_services: sshd not listening; starting attempt $attempt"
        err="$(start_sshd_once 2>&1)"
        status=$?
        if [ "$status" -ne 0 ]; then
            log "start_services: sshd exited with status $status: $err"
        fi

        sleep 3
        if check_sshd_listen; then
            log "start_services: sshd is listening on port $SSHD_PORT"
            return 0
        fi
        attempt=$((attempt + 1))
    done

    log "start_services: ERROR sshd is still not listening"
    return 1
}

manager_is_running() {
    pid="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_manager_if_needed() {
    if manager_is_running; then
        return 0
    fi

    if [ -d "$LOCK_DIR" ]; then
        remove_lock_dir
    fi

    MANAGER_SCRIPT="$HOME_DIR/Petagent/scripts/termux_service_manager.sh"
    if [ -x "$MANAGER_SCRIPT" ]; then
        nohup "$MANAGER_SCRIPT" >/dev/null 2>&1 &
        log "start_services: launched service manager from repo"
        sleep 1
        if manager_is_running; then
            log "start_services: service manager confirmed running"
            return 0
        fi
        log "start_services: WARNING service manager not confirmed after launch"
        return 1
    fi

    log "start_services: ERROR missing executable $MANAGER_SCRIPT"
    return 1
}

repair_android_context
start_sshd_if_needed
start_manager_if_needed
