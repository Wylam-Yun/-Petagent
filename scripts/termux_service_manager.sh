#!/data/data/com.termux/files/usr/bin/sh

HOME_DIR="${HOME_DIR:-/data/data/com.termux/files/home}"
PREFIX_DIR="${PREFIX_DIR:-/data/data/com.termux/files/usr}"
LOCK_DIR="$HOME_DIR/.termux_service_manager.lock"
LOG_FILE="$HOME_DIR/.service_manager.log"
OLD_LOG_FILE="$HOME_DIR/.service_manager.log.old"
PETAGENT_LOG="$HOME_DIR/.petagent_runtime_manager.log"
MAX_LOG_SIZE=102400
CHECK_INTERVAL="${CHECK_INTERVAL:-120}"
SU_CHECK_INTERVAL="${SU_CHECK_INTERVAL:-600}"
MAX_FAILS="${MAX_FAILS:-5}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-600}"
SSHD_PORT="${SSHD_PORT:-8022}"
PETAGENT_DIR="${PETAGENT_DIR:-$HOME_DIR/Petagent}"
PETAGENT_PORT="${PETAGENT_PORT:-8000}"
PETAGENT_START_GRACE_SECONDS="${PETAGENT_START_GRACE_SECONDS:-180}"
NETWORK_WAIT_SECONDS="${NETWORK_WAIT_SECONDS:-180}"
PROXY_START_SCRIPT="${PROXY_START_SCRIPT:-/data/local/tmp/start-proxy.sh}"
PROXY_DISABLE_FILE="${PROXY_DISABLE_FILE:-/data/local/tmp/.petagent_no_proxy_autostart}"

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
    su -c "restorecon -R '$PETAGENT_DIR' '$LOCK_DIR' 2>/dev/null" >/dev/null 2>&1 || true
}

rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        size="$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)"
        if [ "${size:-0}" -gt "$MAX_LOG_SIZE" ]; then
            cp "$LOG_FILE" "$OLD_LOG_FILE" 2>/dev/null
            : > "$LOG_FILE"
            log "Rotated log file"
        fi
    fi
}

cleanup_lock() {
    rm -rf "$LOCK_DIR" 2>/dev/null || {
        repair_android_context
        rm -rf "$LOCK_DIR" 2>/dev/null || true
    }
}

cleanup_and_exit() {
    cleanup_lock
    exit 0
}

take_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_DIR/pid"
        trap cleanup_lock EXIT
        trap cleanup_and_exit INT TERM
        return 0
    fi

    old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        exit 0
    fi

    rm -rf "$LOCK_DIR" 2>/dev/null || {
        repair_android_context
        rm -rf "$LOCK_DIR" 2>/dev/null || true
    }
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_DIR/pid"
        trap cleanup_lock EXIT
        trap cleanup_and_exit INT TERM
        return 0
    fi

    echo "Could not acquire service manager lock" >> "$LOG_FILE"
    exit 1
}

acquire_wake_lock() {
    if command -v termux-wake-lock >/dev/null 2>&1; then
        if termux-wake-lock >/dev/null 2>&1; then
            log "Acquired Termux wake lock"
        else
            log "WARNING: termux-wake-lock returned non-zero"
        fi
    else
        log "WARNING: termux-wake-lock not found"
    fi
}

wait_for_network() {
    waited=0
    while [ "$waited" -lt "$NETWORK_WAIT_SECONDS" ]; do
        route="$(ip route get 1.1.1.1 2>/dev/null || true)"
        if printf '%s\n' "$route" | grep -q ' src '; then
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    log "WARNING: network route not ready after ${NETWORK_WAIT_SECONDS}s"
    return 1
}

check_port_listen() {
    port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | grep -E "[:.]$port[[:space:]]" | grep -q LISTEN && return 0
    fi

    if command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | grep -E "[:.]$port[[:space:]]" | grep -q LISTEN && return 0
    fi

    return 1
}

check_sshd_listen() {
    check_port_listen "$SSHD_PORT" && return 0
    grep -qi ":1F56 .* 0A " /proc/net/tcp /proc/net/tcp6 2>/dev/null
}

start_sshd() {
    wait_for_network || true
    log "Starting sshd"
    err="$($PREFIX_DIR/bin/sshd -4 2>&1)"
    status=$?
    if [ "$status" -ne 0 ]; then
        log "sshd exited with status $status: $err"
    fi

    sleep 2
    if check_sshd_listen; then
        log "sshd is listening on port $SSHD_PORT"
        return 0
    fi

    log "ERROR: sshd is not listening after start attempt"
    return 1
}

check_su() {
    out="$(su -c id 2>&1)"
    status=$?
    if [ "$status" -eq 0 ] && printf '%s\n' "$out" | grep -q "uid=0(root)"; then
        return 0
    fi

    log "WARNING: su health check failed: $out"
    return 1
}

start_proxy_once() {
    [ -f "$PROXY_DISABLE_FILE" ] && return 0
    [ -x "$PROXY_START_SCRIPT" ] || return 0
    check_port_listen 7897 && return 0

    if su -c "$PROXY_START_SCRIPT" >> "$LOG_FILE" 2>&1; then
        log "Proxy start script executed"
    else
        log "WARNING: proxy start script failed"
    fi
}

petagent_pid() {
    cat "$PETAGENT_DIR/backend/data/runtime.pid" 2>/dev/null || true
}

petagent_pid_age() {
    pid_file="$PETAGENT_DIR/backend/data/runtime.pid"
    [ -f "$pid_file" ] || {
        echo 999999
        return 0
    }
    now="$(date +%s 2>/dev/null || echo 0)"
    modified="$(stat -c %Y "$pid_file" 2>/dev/null || echo 0)"
    echo $((now - modified))
}

petagent_process_alive() {
    pid="$(petagent_pid)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

petagent_port_listening() {
    check_port_listen "$PETAGENT_PORT"
}

petagent_health() {
    command -v curl >/dev/null 2>&1 || return 1
    curl -fsS --connect-timeout 3 --max-time 8 "http://127.0.0.1:$PETAGENT_PORT/api/health" 2>/dev/null | grep -q '"ok":true'
}

petagent_layered_check() {
    # Returns 0 if healthy, 1 if process dead, 2 if port down, 3 if HTTP fail
    if ! petagent_process_alive; then
        return 1
    fi
    if ! petagent_port_listening; then
        return 2
    fi
    if ! petagent_health; then
        return 3
    fi
    return 0
}

stop_unhealthy_petagent() {
    pid="$(petagent_pid)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        age="$(petagent_pid_age)"
        if [ "$age" -lt "$PETAGENT_START_GRACE_SECONDS" ]; then
            log "PetAgent pid $pid is still within startup grace (${age}s); waiting"
            return 1
        fi
        log "Stopping unhealthy PetAgent pid $pid"
        kill "$pid" 2>/dev/null || true
        sleep 2
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PETAGENT_DIR/backend/data/runtime.pid" 2>/dev/null || {
        repair_android_context
        rm -f "$PETAGENT_DIR/backend/data/runtime.pid" 2>/dev/null || true
    }
    return 0
}

start_petagent() {
    [ -d "$PETAGENT_DIR" ] || {
        log "PetAgent directory missing: $PETAGENT_DIR"
        return 1
    }
    [ -f "$PETAGENT_DIR/scripts/start.sh" ] || {
        log "PetAgent start script missing"
        return 1
    }

    wait_for_network || true
    log "Starting PetAgent runtime"
    (
        cd "$PETAGENT_DIR" || exit 1
        HOST=0.0.0.0 PORT="$PETAGENT_PORT" sh scripts/start.sh
    ) >> "$PETAGENT_LOG" 2>&1

    if petagent_health; then
        log "PetAgent runtime is healthy on port $PETAGENT_PORT"
        return 0
    fi

    log "ERROR: PetAgent health check failed after start"
    return 1
}

ensure_petagent() {
    check_result=$(petagent_layered_check 2>&1) || true
    rc=$?
    case "$rc" in
        0) return 0 ;;
        1) log "PetAgent check: process not running" ;;
        2) log "PetAgent check: port $PETAGENT_PORT not listening" ;;
        3) log "PetAgent check: HTTP health failed" ;;
    esac
    return 1
}

restart_petagent() {
    if ! stop_unhealthy_petagent; then
        return 1
    fi
    start_petagent
}

main() {
    repair_android_context
    take_lock
    log "Service manager started with PID $$"
    acquire_wake_lock
    start_proxy_once

    ssh_fail_count=0
    petagent_fail_count=0
    su_fail_count=0
    last_su_check="$(date +%s 2>/dev/null || echo 0)"

    while true; do
        rotate_log

        if check_sshd_listen; then
            ssh_fail_count=0
        else
            log "sshd is not listening; attempting restart"
            if start_sshd; then
                ssh_fail_count=0
            else
                ssh_fail_count=$((ssh_fail_count + 1))
                if [ "$ssh_fail_count" -ge "$MAX_FAILS" ]; then
                    log "CRITICAL: sshd failed $MAX_FAILS times; backing off ${BACKOFF_SECONDS}s"
                    ssh_fail_count=0
                    sleep "$BACKOFF_SECONDS"
                fi
            fi
        fi

        if ensure_petagent; then
            petagent_fail_count=0
        else
            # Process dead = immediate restart; HTTP fail = wait for consecutive failures
            if ! petagent_process_alive; then
                log "PetAgent process not running; restarting immediately"
                if restart_petagent; then
                    petagent_fail_count=0
                else
                    log "CRITICAL: PetAgent restart failed; backing off ${BACKOFF_SECONDS}s"
                    sleep "$BACKOFF_SECONDS"
                fi
            else
                petagent_fail_count=$((petagent_fail_count + 1))
                log "PetAgent consecutive health fail: $petagent_fail_count/$MAX_FAILS"
                if [ "$petagent_fail_count" -ge "$MAX_FAILS" ]; then
                    log "PetAgent health failed $MAX_FAILS times; restarting"
                    if restart_petagent; then
                        petagent_fail_count=0
                    else
                        log "CRITICAL: PetAgent restart failed; backing off ${BACKOFF_SECONDS}s"
                        petagent_fail_count=0
                        sleep "$BACKOFF_SECONDS"
                    fi
                fi
            fi
        fi

        now="$(date +%s 2>/dev/null || echo 0)"
        if [ $((now - last_su_check)) -ge "$SU_CHECK_INTERVAL" ]; then
            last_su_check="$now"
            if check_su; then
                su_fail_count=0
            else
                su_fail_count=$((su_fail_count + 1))
                if [ "$su_fail_count" -ge "$MAX_FAILS" ]; then
                    log "CRITICAL: su failed $MAX_FAILS consecutive checks"
                    su_fail_count=0
                fi
            fi
        fi

        sleep "$CHECK_INTERVAL"
    done
}

main "$@"
