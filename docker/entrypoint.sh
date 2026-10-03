#!/bin/sh
# Install the crontab and stay in the foreground as crond (PID 1).
set -eu

SCHEDULE="${SCHEDULE:-*/7 * * * *}"

if [ "${RUN_ONCE:-1}" != "0" ]; then
    /app/run.sh || echo "smrt-runner: initial run failed; cron will retry" >&2
fi

mkdir -p /etc/crontabs
{
    echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    echo "$SCHEDULE /app/run.sh >> /proc/1/fd/1 2>&1"
} > /etc/crontabs/root
chmod 600 /etc/crontabs/root

exec crond -f -c /etc/crontabs -d 4
