#!/bin/bash
set -e

BRANCH="${FRAPPE_BRANCH:-version-16}"
SOCKETIO_PORT="${SOCKETIO_PORT:-2200}"
BENCHES=/home/frappe/benches
SETUP_DONE="$BENCHES/.setup-complete"

# The named volume is created root-owned on first start
sudo chown frappe:frappe "$BENCHES"
cd "$BENCHES"

if [ -f "$SETUP_DONE" ]; then
    echo "Bench already set up, starting"
    cd frappe-bench
    # Apply on every start, so changing SOCKETIO_PORT needs no reinstall
    bench set-config -g socketio_port "$SOCKETIO_PORT"
    exec bench start
fi

# A previous attempt stopped half way; start over
rm -rf frappe-bench

echo "Creating new bench on $BRANCH..."
bench init --skip-redis-config-generation --frappe-branch "$BRANCH" frappe-bench

cd frappe-bench

# Use containers instead of localhost
bench set-mariadb-host mariadb
bench set-redis-cache-host redis://redis:6379
bench set-redis-queue-host redis://redis:6379
bench set-redis-socketio-host redis://redis:6379

# The browser connects to socket.io on this port, so it must match the host port
bench set-config -g socketio_port "$SOCKETIO_PORT"

# Remove redis, watch from Procfile
sed -i '/redis/d' ./Procfile
sed -i '/watch/d' ./Procfile

bench get-app --branch "$BRANCH" erpnext
bench get-app --branch "$BRANCH" hrms

bench new-site hrms.localhost \
--force \
--mariadb-root-password 123 \
--admin-password admin \
--no-mariadb-socket

bench --site hrms.localhost install-app hrms
bench --site hrms.localhost set-config developer_mode 1
bench --site hrms.localhost enable-scheduler
bench --site hrms.localhost clear-cache
bench use hrms.localhost

touch "$SETUP_DONE"

exec bench start
