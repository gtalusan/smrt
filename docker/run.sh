#!/bin/sh
# One tick: discover switches, query per-port stats, publish ports with
# traffic history (rx_good > 0 or tx_good > 0) to MQTT.
# Composes discovery.py / smrt.py / jq / mosquitto_pub. POSIX sh.
set -u

mkdir "${TMPDIR:-/tmp}/smrt-runner.lock" 2>/dev/null || {
    echo "$(date '+%F %T') smrt-runner: tick already running, skipping"
    exit 0
}
trap 'rmdir "${TMPDIR:-/tmp}/smrt-runner.lock" 2>/dev/null' EXIT

log() { echo "$(date '+%F %T') $*"; }

# locate the repo: run.sh may sit in docker/ (native) or flat in /app (container)
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$script_dir/discovery.py" ]; then
    APP=${APP_DIR:-"$script_dir"}
elif [ -f "$script_dir/../discovery.py" ]; then
    APP=${APP_DIR:-"$script_dir/.."}
else
    APP=${APP_DIR:-/app}
fi
PYTHON=${PYTHON:-python3}

MQTT_TOPIC_BASE=${MQTT_TOPIC_BASE:-smrt}
MQTT_PORT=${MQTT_PORT:-1883}
MQTT_QOS=${MQTT_QOS:-1}
MQTT_RETAIN=${MQTT_RETAIN:-0}

# never probe these: VM/container/overlay/tunnel/kernel pseudo-interfaces
DENY='^(docker|veth|br-|virbr|tun|tap|vnet|tailscale|wg|zt|awdl|llw|utun|anpi|bond|erspan|gre|ip6|ip_|sit|ifb|nlmon|teql|gif|stf)'

default_iface() {
    # /proc/net/route: Iface Dest Gateway Flags RefCnt Use Metric Mask ...
    awk '$2 == "00000000" && $3 != "00000000" {print $7 " " $1}' /proc/net/route 2>/dev/null \
        | sort -n | head -1 | cut -d' ' -f2
}

other_ifaces() {
    if [ -d /sys/class/net ]; then
        ls /sys/class/net
    else
        ifconfig -l
    fi | tr ' ' '\n' | grep -Ev "$DENY" | grep -v '^lo' | grep -v '^$'
}

candidates() {
    if [ -n "${INTERFACE:-}" ]; then
        echo "$INTERFACE"
        return
    fi
    def=$(default_iface)
    [ -n "$def" ] && echo "$def"
    for i in $(other_ifaces); do
        [ "$i" != "$def" ] && echo "$i"
    done
}

publish() {
    port=$1
    topic=$2
    payload=$3
    if [ -z "${MQTT_HOST:-}" ]; then
        log "dry-run: $topic $payload"
        return 0
    fi
    set -- mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -q "$MQTT_QOS"
    if [ -n "${MQTT_USERNAME:-}" ]; then
        set -- "$@" -u "$MQTT_USERNAME" -P "${MQTT_PASSWORD:-}"
    fi
    [ "$MQTT_RETAIN" = "1" ] && set -- "$@" -r
    if "$@" -t "$topic" -m "$payload" 2>/dev/null; then
        log "published $topic"
    else
        log "publish failed: $topic"
    fi
}

creds_for() {
    # match TP_CREDENTIALS keys against $1, ignoring case and separators
    n=$(echo "$1" | tr 'A-F' 'a-f' | tr -cd '0-9a-f')
    if [ -n "${TP_CREDENTIALS:-}" ]; then
        printf '%s' "$TP_CREDENTIALS" | jq -c --arg n "$n" \
            'to_entries | map(select((.key | ascii_downcase | gsub("[^0-9a-f]"; "")) == $n))[0].value // empty'
    fi
}

found=0
for iface in $(candidates); do
    log "discovering on $iface..."
    switches=$(cd "$APP" && "$PYTHON" discovery.py -i "$iface" 2>/dev/null) || continue
    if [ "$(printf '%s' "$switches" | jq 'length' 2>/dev/null)" -gt 0 ]; then
        found=1
        break
    fi
done

if [ "$found" -ne 1 ]; then
    log "no switches found on any interface"
    exit 1
fi

printf '%s' "$switches" | jq -c '.[]' | while IFS= read -r sw; do
    host_ip=$(printf '%s' "$sw" | jq -r '.host_ip')
    host_mac=$(printf '%s' "$sw" | jq -r '.host_mac')
    mac=$(printf '%s' "$sw" | jq -r '.switch.mac')
    [ -z "$mac" ] || [ "$mac" = "null" ] && continue

    c=$(creds_for "$mac")
    if [ -n "$c" ] && [ "$c" != "null" ]; then
        user=$(printf '%s' "$c" | jq -r '.username // empty')
        pass=$(printf '%s' "$c" | jq -r '.password // empty')
    fi
    [ -z "${user:-}" ] && user=${DEFAULT_USERNAME:-}
    [ -z "${pass:-}" ] && pass=${DEFAULT_PASSWORD:-}
    if [ -z "$user" ]; then
        log "no credentials for $mac; skipping"
        continue
    fi

    log "querying stats for $mac..."
    stats=$(cd "$APP" && "$PYTHON" smrt.py --username "$user" --password "$pass" \
        --host-mac="$host_mac" --ip-address="$host_ip" --switch-mac "$mac" stats 2>/dev/null) || {
        log "smrt query failed for $mac"
        continue
    }
    if [ "$(printf '%s' "$stats" | jq 'length' 2>/dev/null)" -eq 0 ]; then
        log "no stats for $mac (bad credentials?)"
        continue
    fi

    printf '%s' "$stats" | jq -c '.[] | select(.rx_good > 0 or .tx_good > 0)' | while IFS= read -r row; do
        port=$(printf '%s' "$row" | jq -r '.port')
        publish "$port" "$MQTT_TOPIC_BASE/$mac/stats/$port" "$row"
    done
done

exit 0
