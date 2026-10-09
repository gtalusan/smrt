#!/bin/sh
# Run smrt-runner on a schedule and stay in the foreground as PID 1.
# SCHEDULE="loop": continuous loop — run, then sleep POLL_INTERVAL seconds.
#   Uniform tick spacing with no hour-boundary artifact (cron */N resets each
#   hour, so the last tick of the hour lands <N minutes before the first tick
#   of the next; a continuous period has no such boundary).
# Any other SCHEDULE: busybox crond.
set -eu

SCHEDULE="${SCHEDULE:-*/7 * * * *}"
POLL_INTERVAL="${POLL_INTERVAL:-420}"

if [ "${RUN_ONCE:-1}" != "0" ]; then
    /app/run.sh || echo "smrt-runner: initial run failed; will retry" >&2
fi

if [ "$SCHEDULE" = "loop" ]; then
    while true; do
        sleep "$POLL_INTERVAL"
        /app/run.sh >> /proc/1/fd/1 2>&1 \
            || echo "smrt-runner: run failed; will retry" >&2
    done
fi

mkdir -p /etc/crontabs
{
    echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    echo "$SCHEDULE /app/run.sh >> /proc/1/fd/1 2>&1"
} > /etc/crontabs/root
chmod 600 /etc/crontabs/root

exec crond -f -c /etc/crontabs -d 4
