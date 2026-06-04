#!/data/data/com.termux/files/usr/bin/sh

HOME_DIR="${HOME_DIR:-/data/data/com.termux/files/home}"
PREFIX_DIR="${PREFIX_DIR:-/data/data/com.termux/files/usr}"
LOCK_DIR="$HOME_DIR/.termux_service_manager.lock"
LOG_FILE="${PETAGENT_DIR:-$HOME_DIR/Petagent}/logs/manager.log"
OLD_LOG_FILE="${PETAGENT_DIR:-$HOME_DIR/Petagent}/logs/manager.log.old"
PETAGENT_LOG="$HOME_DIR/.petagent_runtime_manager.log"
MAX_LOG_SIZE=102400
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
SU_CHECK_INTERVAL="${SU_CHECK_INTERVAL:-600}"
MAX_FAILS="${MAX_FAILS:-5}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-120}"
SSHD_PORT="${SSHD_PORT:-8022}"
PETAGENT_DIR="${PETAGENT_DIR:-$HOME_DIR/Petagent}"
PETAGENT_PORT="${PETAGENT_PORT:-8000}"
PETAGENT_START_GRACE_SECONDS="${PETAGENT_START_GRACE_SECONDS:-45}"
NETWORK_WAIT_SECONDS="${NETWORK_WAIT_SECONDS:-180}"
FRONTEND_STARTUP_SECONDS="${FRONTEND_STARTUP_SECONDS:-120}"
STUCK_MAX="${STUCK_MAX:-3}"
HTTP_FAIL_MAX="${HTTP_FAIL_MAX:-5}"
HEALTH_CONNECT_TIMEOUT="${HEALTH_CONNECT_TIMEOUT:-2}"
HEALTH_MAX_TIME="${HEALTH_MAX_TIME:-8}"
HEALTH_CONFIRM_MAX_TIME="${HEALTH_CONFIRM_MAX_TIME:-15}"
WATCHDOG_CONNECT_TIMEOUT="${WATCHDOG_CONNECT_TIMEOUT:-2}"
WATCHDOG_MAX_TIME="${WATCHDOG_MAX_TIME:-8}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-300}"
WAKE_LOCK_REFRESH_INTERVAL="${WAKE_LOCK_REFRESH_INTERVAL:-300}"
RUNTIME_TAIL_LINES="${RUNTIME_TAIL_LINES:-12}"
MANAGER_VERSION="android-context-health-guard-20260604"

export HOME="$HOME_DIR"
export PREFIX="$PREFIX_DIR"
export PATH="$PREFIX_DIR/bin:$PREFIX_DIR/bin/applets:/system/bin:/system/xbin:/su/bin"
export LD_LIBRARY_PATH="$PREFIX_DIR/lib"
export LD_PRELOAD="$PREFIX_DIR/lib/libtermux-exec-ld-preload.so"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

refuse_root_manager() {
    uid="$(id -u 2>/dev/null || echo "")"
    if [ "$uid" = "0" ]; then
        log "ERROR: refusing to run service manager as root; start it as Termux app user"
        cleanup_lock
        exit 1
    fi
}

android_identity_summary() {
    identity="$(id 2>/dev/null || true)"
    selinux="$(cat /proc/self/attr/current 2>/dev/null | tr -d '\000' || true)"
    echo "${identity:-id=unknown} selinux=${selinux:-unknown}"
}

has_android_inet_group() {
    identity="$(id 2>/dev/null || true)"
    case "$identity" in
        *"3003("*|*"3003,"*|*=",3003"*)
            return 0
            ;;
    esac
    return 1
}

refuse_non_termux_network_context() {
    [ -d "$PREFIX_DIR" ] || return 0
    if has_android_inet_group; then
        return 0
    fi

    log "ERROR: refusing to run service manager outside the real Termux app network context"
    log "ERROR: open the Termux app or use Termux:Boot; adb/su u0_a137 lacks Android inet group 3003"
    log "ERROR: current identity: $(android_identity_summary)"
    cleanup_lock
    exit 1
}

process_state() {
    pid="$1"
    [ -r "/proc/$pid/status" ] || return 0
    while IFS= read -r key value rest; do
        [ "$key" = "State:" ] && {
            echo "$value"
            return 0
        }
    done < "/proc/$pid/status"
}

process_has_android_inet_group() {
    pid="$1"
    [ -r "/proc/$pid/status" ] || return 1
    while IFS= read -r line; do
        case "$line" in
            Groups:*)
                groups="${line#Groups:}"
                groups="$(printf '%s' "$groups" | tr '\011' ' ')"
                case " $groups " in
                    *" 3003 "*)
                        return 0
                        ;;
                esac
                return 1
                ;;
        esac
    done < "/proc/$pid/status"
    return 1
}

process_exists() {
    pid="$1"
    [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
    [ "$(process_state "$pid")" != "Z" ]
}

process_uid() {
    pid="$1"
    awk '/^Uid:/{print $2; exit}' "/proc/$pid/status" 2>/dev/null || true
}

process_cmdline() {
    pid="$1"
    [ -r "/proc/$pid/cmdline" ] || return 0
    tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

is_manager_process() {
    pid="$1"
    cmdline="$(process_cmdline "$pid")"
    case "$cmdline" in
        *"termux_service_manager.sh"*|*".service_manager.sh"*)
            return 0
            ;;
    esac
    return 1
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

remove_stale_lock() {
    rm -rf "$LOCK_DIR" 2>/dev/null && return 0
    repair_android_context
    rm -rf "$LOCK_DIR" 2>/dev/null && return 0
    command -v su >/dev/null 2>&1 || return 1
    su -c "rm -rf '$LOCK_DIR' 2>/dev/null" >/dev/null 2>&1
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
    if process_exists "$old_pid"; then
        current_uid="$(id -u 2>/dev/null || echo "")"
        old_uid="$(process_uid "$old_pid")"
        if [ "$old_uid" = "$current_uid" ] && is_manager_process "$old_pid"; then
            if process_has_android_inet_group "$old_pid"; then
                exit 0
            fi
            log "Stopping service manager process $old_pid without Android inet group 3003"
            kill "$old_pid" 2>/dev/null || {
                command -v su >/dev/null 2>&1 && su -c "kill -9 '$old_pid' 2>/dev/null" >/dev/null 2>&1 || true
            }
        fi
        if is_manager_process "$old_pid"; then
            log "Stopping foreign service manager process $old_pid owned by uid ${old_uid:-unknown}"
            kill "$old_pid" 2>/dev/null || {
                command -v su >/dev/null 2>&1 && su -c "kill -9 '$old_pid' 2>/dev/null" >/dev/null 2>&1 || true
            }
        else
            log "Manager lock points to non-manager pid $old_pid owned by uid ${old_uid:-unknown}; clearing lock"
        fi
    fi

    remove_stale_lock || true
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
    if ! command -v termux-wake-lock >/dev/null 2>&1; then
        log "WARNING: termux-wake-lock not found"
        return 0
    fi

    log "termux-wake-lock command found"
    wake_lock_acquired=0
    if termux-wake-lock >/dev/null 2>&1; then
        wake_lock_acquired=1
        log "termux-wake-lock returned success"
    else
        log "WARNING: termux-wake-lock returned non-zero"
    fi

    if ! command -v dumpsys >/dev/null 2>&1; then
        log "WARNING: dumpsys not available; wake lock visibility cannot be verified"
        return 0
    fi

    summary="$(dumpsys power 2>/dev/null | grep -i -E 'Wake Locks|termux|wake-lock|mWakeLockSummary' | head -n 80 || true)"
    if [ -z "$summary" ]; then
        log "WARNING: dumpsys power returned no wake lock summary"
        return 0
    fi

    compact_summary="$(printf '%s' "$summary" | tr '\n' ';' | sed 's/[[:space:]][[:space:]]*/ /g')"
    log "wake lock post-check: $compact_summary"
    if [ "$wake_lock_acquired" -eq 1 ] && ! printf '%s\n' "$summary" | grep -qi -E 'termux|wake-lock'; then
        log "WARNING: termux-wake-lock succeeded but dumpsys did not show a Termux wake lock"
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

process_rss_kb() {
    pid="$1"
    awk '/^VmRSS:/{print $2; exit}' "/proc/$pid/status" 2>/dev/null || true
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
    process_exists "$pid"
}

petagent_port_listening() {
    check_port_listen "$PETAGENT_PORT"
}

petagent_within_startup_grace() {
    petagent_process_alive || return 1
    age="$(petagent_pid_age)"
    [ "$age" -lt "$PETAGENT_START_GRACE_SECONDS" ]
}

petagent_start_in_progress() {
    start_lock="$PETAGENT_DIR/backend/data/start.lock"
    [ -d "$start_lock" ] || return 1
    start_pid="$(cat "$start_lock/pid" 2>/dev/null || true)"
    process_exists "$start_pid"
}

petagent_health() {
    command -v curl >/dev/null 2>&1 || return 1
    curl -fsS --connect-timeout "$HEALTH_CONNECT_TIMEOUT" --max-time "$HEALTH_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health" 2>/dev/null | grep -q '"ok":true'
}

petagent_health_json() {
    command -v curl >/dev/null 2>&1 || return 1
    curl -fsS --connect-timeout "$HEALTH_CONNECT_TIMEOUT" --max-time "$HEALTH_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health" 2>/dev/null
}

petagent_health_confirm() {
    command -v curl >/dev/null 2>&1 || return 1
    resp="$(curl -fsS --connect-timeout "$HEALTH_CONNECT_TIMEOUT" --max-time "$HEALTH_CONFIRM_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health" 2>&1)" || {
        log "PetAgent health confirm failed: $resp"
        return 1
    }
    printf '%s' "$resp" | grep -q '"ok":true'
}

petagent_watchdog() {
    # Returns 0 if not stuck, 1 if stuck, 2 if unreachable
    command -v curl >/dev/null 2>&1 || return 2
    resp="$(curl -fsS --connect-timeout "$WATCHDOG_CONNECT_TIMEOUT" --max-time "$WATCHDOG_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health/watchdog" 2>/dev/null)" || return 2
    printf '%s' "$resp" | grep -q '"stuck":true' && return 1
    return 0
}

watchdog_summary() {
    command -v curl >/dev/null 2>&1 || {
        echo "watchdog=unknown"
        return 0
    }
    resp="$(curl -fsS --connect-timeout "$WATCHDOG_CONNECT_TIMEOUT" --max-time "$WATCHDOG_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health/watchdog" 2>/dev/null || true)"
    if [ -z "$resp" ]; then
        echo "watchdog=unreachable"
        return 0
    fi
    heartbeat_age="$(printf '%s' "$resp" | sed -n 's/.*"frontend_heartbeat_age_s":\([^,}]*\).*/\1/p' | head -n 1 | tr -d '" ')"
    stuck="$(printf '%s' "$resp" | sed -n 's/.*"stuck":\([^,}]*\).*/\1/p' | head -n 1 | tr -d '" ')"
    echo "watchdog=ok frontend_heartbeat_age_s=${heartbeat_age:-unknown} stuck=${stuck:-unknown}"
}

wake_lock_status() {
    if ! command -v dumpsys >/dev/null 2>&1; then
        echo "unknown"
        return 0
    fi
    raw="$(dumpsys power 2>&1 || true)"
    case "$raw" in
        *"Permission Denial"*|*"permission denied"*)
            echo "unavailable_permission_denied"
            return 0
            ;;
    esac
    summary="$(printf '%s\n' "$raw" | grep -i -E 'Wake Locks|termux|wake-lock|mWakeLockSummary' | head -n 80 || true)"
    if [ -z "$summary" ]; then
        echo "unknown"
    elif printf '%s\n' "$summary" | grep -qi -E 'termux|wake-lock'; then
        echo "held"
    elif printf '%s\n' "$summary" | grep -qi -E 'Wake Locks: size=0|mWakeLockSummary=0x0'; then
        echo "not_held"
    else
        echo "unknown"
    fi
}

refresh_wake_lock() {
    if ! command -v termux-wake-lock >/dev/null 2>&1; then
        log "WARNING: termux-wake-lock not found during refresh"
        return 0
    fi
    if termux-wake-lock >/dev/null 2>&1; then
        log "termux-wake-lock refresh returned success"
    else
        log "WARNING: termux-wake-lock refresh returned non-zero"
    fi
}

compact_runtime_tail() {
    [ -f "$PETAGENT_DIR/backend/data/logs/runtime.log" ] || return 0
    tail -n "$RUNTIME_TAIL_LINES" "$PETAGENT_DIR/backend/data/logs/runtime.log" 2>/dev/null \
        | tr '\n' ';' \
        | sed 's/[[:space:]][[:space:]]*/ /g'
}

runtime_snapshot() {
    label="$1"
    pid="$(petagent_pid)"
    pid_state="missing"
    pid_rss="unknown"
    pid_age="$(petagent_pid_age)"
    if process_exists "$pid"; then
        pid_state="$(process_state "$pid")"
        pid_rss="$(process_rss_kb "$pid")"
    fi
    if petagent_port_listening; then
        port_state="listening"
    else
        port_state="down"
    fi
    if check_sshd_listen; then
        sshd_state="listening"
    else
        sshd_state="down"
    fi
    health_summary="$(petagent_health_json 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g' || true)"
    [ -n "$health_summary" ] || health_summary="unreachable"
    log "runtime_snapshot label=$label pid=${pid:-none} pid_state=$pid_state pid_age_s=$pid_age pid_rss_kb=${pid_rss:-unknown} port=$port_state sshd=$sshd_state wake_lock=$(wake_lock_status) $(watchdog_summary) health=$health_summary"
    tail_summary="$(compact_runtime_tail)"
    [ -n "$tail_summary" ] && log "runtime_tail label=$label tail=$tail_summary"
}

manager_heartbeat() {
    runtime_snapshot "heartbeat"
}

run_browser_relaunch_command() {
    label="$1"
    shift

    cmd_output="$("$@" 2>&1)"
    cmd_status=$?
    log "Browser relaunch $label exit=$cmd_status output=$cmd_output"
    return "$cmd_status"
}

ensure_browser() {
    # Relaunch browser if frontend heartbeat is stale and runtime is healthy
    target_url="http://127.0.0.1:$PETAGENT_PORT/"
    command -v curl >/dev/null 2>&1 || {
        log "Browser relaunch check skipped: curl not available"
        return 0
    }
    resp="$(curl -fsS --connect-timeout "$WATCHDOG_CONNECT_TIMEOUT" --max-time "$WATCHDOG_MAX_TIME" "http://127.0.0.1:$PETAGENT_PORT/api/health/watchdog" 2>/dev/null)" || {
        log "Browser relaunch check skipped: watchdog endpoint unreachable"
        return 0
    }
    heartbeat_age="$(printf '%s' "$resp" | sed -n 's/.*"frontend_heartbeat_age_s":\([0-9.]*\).*/\1/p')"
    [ -z "$heartbeat_age" ] && {
        log "Browser relaunch check skipped: frontend_heartbeat_age_s missing"
        return 0
    }
    # Compare: if heartbeat_age > FRONTEND_STARTUP_SECONDS, relaunch
    age_int="${heartbeat_age%%.*}"
    if [ "${age_int:-0}" -gt "$FRONTEND_STARTUP_SECONDS" ]; then
        log "Frontend heartbeat stale (${heartbeat_age}s); relaunching browser target=$target_url"

        if command -v termux-am >/dev/null 2>&1; then
            if run_browser_relaunch_command "termux-am start" termux-am start -a android.intent.action.VIEW -d "$target_url"; then
                return 0
            fi
            case "$cmd_output" in
                *"Could not connect to socket"*|*"TermuxAm server is not enabled"*)
                    log "WARNING: termux-am socket unavailable; open Termux and enable its am socket server, or use adb am only for field validation"
                    ;;
            esac
        else
            log "WARNING: termux-am command not available; trying am fallback"
        fi

        if ! command -v am >/dev/null 2>&1; then
            log "WARNING: am command not available; cannot relaunch browser target=$target_url"
            return 0
        fi

        am_path="$(command -v am 2>/dev/null || true)"
        log "Browser relaunch am command path=${am_path:-unknown}"
        if [ -n "$PREFIX_DIR" ] && [ "$am_path" = "$PREFIX_DIR/bin/am" ] && [ ! -f "$PREFIX_DIR/libexec/termux-am/am.apk" ]; then
            log "WARNING: Termux am wrapper apk missing at $PREFIX_DIR/libexec/termux-am/am.apk; am may abort before returning stderr"
        fi
        run_browser_relaunch_command "am start" am start -a android.intent.action.VIEW -d "$target_url" || {
            if [ -z "$cmd_output" ]; then
                log "WARNING: am start failed with empty stderr; check adb logcat for Termux am wrapper or ActivityManager access errors"
            fi
        }
    fi
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
        HOST=0.0.0.0 PORT="$PETAGENT_PORT" PETAGENT_FOREGROUND=0 sh scripts/start.sh
    ) >> "$PETAGENT_LOG" 2>&1

    if petagent_health || petagent_health_confirm; then
        log "PetAgent runtime is healthy on port $PETAGENT_PORT"
        return 0
    fi

    if petagent_start_in_progress; then
        log "PetAgent runtime start is already in progress"
        return 0
    fi

    if petagent_within_startup_grace; then
        age="$(petagent_pid_age)"
        log "PetAgent runtime is still starting (${age}s); waiting"
        return 0
    fi

    log "ERROR: PetAgent health check failed after start"
    return 1
}

ensure_petagent() {
    rc=0
    petagent_layered_check || rc=$?
    case "$rc" in
        0) return 0 ;;
        1) log "PetAgent check: process not running" ;;
        2) log "PetAgent check: port $PETAGENT_PORT not listening" ;;
        3) log "PetAgent check: HTTP health failed" ;;
    esac
    return 1
}

main() {
    take_lock
    refuse_root_manager
    refuse_non_termux_network_context
    repair_android_context
    mkdir -p "$PETAGENT_DIR/logs" 2>/dev/null || true
    log "Service manager started with PID $$ ($MANAGER_VERSION)"
    acquire_wake_lock
    runtime_snapshot "manager_started"

    ssh_fail_count=0
    petagent_fail_count=0
    stuck_count=0
    su_fail_count=0
    http_fail_count=0
    last_su_check="$(date +%s 2>/dev/null || echo 0)"
    last_heartbeat="$last_su_check"
    last_wake_lock_check="$last_su_check"

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

        # Watchdog stuck detection
        if petagent_layered_check; then
            watchdog_rc=0
            petagent_watchdog || watchdog_rc=$?
            if [ "$watchdog_rc" -eq 1 ]; then
                stuck_count=$((stuck_count + 1))
                log "PetAgent watchdog reports stuck ($stuck_count/$STUCK_MAX)"
                if [ "$stuck_count" -ge "$STUCK_MAX" ]; then
                    log "CRITICAL: PetAgent stuck for $STUCK_MAX cycles; restarting"
                    runtime_snapshot "watchdog_stuck_restart"
                    stuck_count=0
                    pid="$(petagent_pid)"
                    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
                    sleep 2
                    start_petagent || true
                fi
            elif [ "$watchdog_rc" -eq 0 ]; then
                stuck_count=0
            fi
            # Browser relaunch check
            ensure_browser
        fi

        petagent_rc=0
        petagent_layered_check || petagent_rc=$?
        case "$petagent_rc" in
            0)
                petagent_fail_count=0
                http_fail_count=0
                ;;
            1)
                if petagent_start_in_progress; then
                    log "PetAgent start is already in progress; waiting"
                    http_fail_count=0
                    petagent_fail_count=0
                elif petagent_port_listening; then
                    if petagent_health; then
                        log "PetAgent pid file is stale or missing, but port $PETAGENT_PORT is healthy; leaving runtime untouched"
                        http_fail_count=0
                        petagent_fail_count=0
                    else
                        http_fail_count=$((http_fail_count + 1))
                        log "PetAgent pid file is missing and port $PETAGENT_PORT is HTTP half-alive ($http_fail_count/$HTTP_FAIL_MAX)"
                        if [ "$http_fail_count" -ge "$HTTP_FAIL_MAX" ]; then
                            http_fail_count=0
                            if petagent_health_confirm; then
                                log "PetAgent orphan HTTP health recovered during confirm; not restarting"
                            else
                                log "CRITICAL: PetAgent orphan HTTP half-alive state persisted after confirm; attempting runtime restart"
                                runtime_snapshot "orphan_http_restart"
                                cleanup_duplicate_runtimes ""
                                start_petagent || log "CRITICAL: PetAgent restart failed while orphan HTTP was half-alive"
                            fi
                        fi
                        petagent_fail_count=0
                    fi
                else
                    log "PetAgent process not running; starting runtime"
                    runtime_snapshot "process_missing_start"
                    http_fail_count=0
                    if start_petagent; then
                        petagent_fail_count=0
                    else
                        log "CRITICAL: PetAgent start failed; backing off ${BACKOFF_SECONDS}s"
                        sleep "$BACKOFF_SECONDS"
                    fi
                fi
                ;;
            2)
                http_fail_count=0
                if petagent_within_startup_grace; then
                    age="$(petagent_pid_age)"
                    log "PetAgent process is still within startup grace (${age}s); waiting for port"
                elif petagent_process_alive; then
                    pid="$(petagent_pid)"
                    log "PetAgent process $pid is alive but port $PETAGENT_PORT is not listening after grace; restarting"
                    runtime_snapshot "port_down_restart"
                    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
                    sleep 2
                    [ -n "$pid" ] && process_exists "$pid" && kill -9 "$pid" 2>/dev/null || true
                    start_petagent || log "CRITICAL: PetAgent restart failed while port was down"
                else
                    log "PetAgent port $PETAGENT_PORT is down and process is missing; starting runtime"
                    start_petagent || log "CRITICAL: PetAgent start failed while port was down"
                fi
                petagent_fail_count=0
                ;;
            3)
                http_fail_count=$((http_fail_count + 1))
                log "PetAgent HTTP health failed while process and port are alive ($http_fail_count/$HTTP_FAIL_MAX)"
                if [ "$http_fail_count" -ge "$HTTP_FAIL_MAX" ]; then
                    http_fail_count=0
                    pid="$(petagent_pid)"
                    if petagent_health_confirm; then
                        log "PetAgent HTTP health recovered during confirm; not restarting pid ${pid:-unknown}"
                    else
                        log "CRITICAL: PetAgent HTTP half-alive state persisted after confirm; restarting pid ${pid:-unknown}"
                        runtime_snapshot "http_half_alive_restart"
                        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
                        sleep 2
                        [ -n "$pid" ] && process_exists "$pid" && kill -9 "$pid" 2>/dev/null || true
                        start_petagent || log "CRITICAL: PetAgent restart failed while HTTP was half-alive"
                    fi
                fi
                petagent_fail_count=0
                ;;
            *)
                petagent_fail_count=$((petagent_fail_count + 1))
                log "PetAgent unknown health state $petagent_rc: $petagent_fail_count/$MAX_FAILS"
                if [ "$petagent_fail_count" -ge "$MAX_FAILS" ]; then
                    petagent_fail_count=0
                    log "WARNING: PetAgent unknown health state persisted; leaving runtime untouched"
                fi
                ;;
        esac

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

        if [ $((now - last_wake_lock_check)) -ge "$WAKE_LOCK_REFRESH_INTERVAL" ]; then
            last_wake_lock_check="$now"
            wake_state="$(wake_lock_status)"
            if [ "$wake_state" != "held" ]; then
                log "wake_lock status=$wake_state; refreshing Termux wake lock"
                refresh_wake_lock
            fi
        fi

        if [ $((now - last_heartbeat)) -ge "$HEARTBEAT_INTERVAL" ]; then
            last_heartbeat="$now"
            manager_heartbeat
        fi

        sleep "$CHECK_INTERVAL"
    done
}

main "$@"
