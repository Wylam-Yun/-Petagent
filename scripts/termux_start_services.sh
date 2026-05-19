#!/data/data/com.termux/files/usr/bin/sh

HOME_DIR="${HOME_DIR:-/data/data/com.termux/files/home}"
PREFIX_DIR="${PREFIX_DIR:-/data/data/com.termux/files/usr}"
LOG_FILE="$HOME_DIR/.service_manager.log"
LOCK_DIR="$HOME_DIR/.termux_service_manager.lock"
SSHD_PORT="${SSHD_PORT:-8022}"
NETWORK_WAIT_SECONDS="${NETWORK_WAIT_SECONDS:-180}"
LEGACY_MANAGER_SCRIPT="$HOME_DIR/.service_manager.sh"

export HOME="$HOME_DIR"
export PREFIX="$PREFIX_DIR"
export PATH="$PREFIX_DIR/bin:$PREFIX_DIR/bin/applets:/system/bin:/system/xbin:/su/bin"
export LD_LIBRARY_PATH="$PREFIX_DIR/lib"
export LD_PRELOAD="$PREFIX_DIR/lib/libtermux-exec-ld-preload.so"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

process_exists() {
    pid="$1"
    [ -n "$pid" ] && [ -d "/proc/$pid" ]
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

install_legacy_manager_shim() {
    repo_manager="$HOME_DIR/Petagent/scripts/termux_service_manager.sh"
    [ -x "$repo_manager" ] || return 0

    if [ -f "$LEGACY_MANAGER_SCRIPT" ] && grep -q "PetAgent legacy service manager shim" "$LEGACY_MANAGER_SCRIPT" 2>/dev/null; then
        return 0
    fi

    if [ -f "$LEGACY_MANAGER_SCRIPT" ]; then
        backup="$LEGACY_MANAGER_SCRIPT.legacy.$(date +%Y%m%d%H%M%S 2>/dev/null || echo backup)"
        mv "$LEGACY_MANAGER_SCRIPT" "$backup" 2>/dev/null || true
        log "start_services: moved legacy manager to $backup"
    fi

    {
        printf '%s\n' '#!/data/data/com.termux/files/usr/bin/sh'
        printf '%s\n' '# PetAgent legacy service manager shim.'
        printf '%s\n' 'exec "$HOME/Petagent/scripts/termux_service_manager.sh" "$@"'
    } > "$LEGACY_MANAGER_SCRIPT" 2>/dev/null || return 0
    chmod 700 "$LEGACY_MANAGER_SCRIPT" 2>/dev/null || true
    log "start_services: installed legacy manager shim"
}

stop_legacy_manager_processes() {
    for cmdline in /proc/[0-9]*/cmdline; do
        [ -r "$cmdline" ] || continue
        if tr '\000' ' ' < "$cmdline" 2>/dev/null | grep -q "$HOME_DIR/.service_manager.sh"; then
            pid="${cmdline%/cmdline}"
            pid="${pid##*/}"
            [ "$pid" = "$$" ] && continue
            if kill -9 "$pid" 2>/dev/null; then
                log "start_services: stopped legacy manager process $pid"
            elif command -v su >/dev/null 2>&1; then
                su -c "kill -9 '$pid' 2>/dev/null" >/dev/null 2>&1 && log "start_services: stopped legacy manager process $pid via su"
            fi
        fi
    done
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
    process_exists "$pid"
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
        waited=0
        while [ "$waited" -lt 15 ]; do
            if manager_is_running; then
                log "start_services: service manager confirmed running"
                return 0
            fi
            sleep 1
            waited=$((waited + 1))
        done
        log "start_services: WARNING service manager not confirmed after launch"
        return 1
    fi

    log "start_services: ERROR missing executable $MANAGER_SCRIPT"
    return 1
}

repair_android_context
install_legacy_manager_shim
stop_legacy_manager_processes
start_sshd_if_needed
start_manager_if_needed
