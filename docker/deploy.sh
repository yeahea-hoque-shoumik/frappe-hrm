#!/bin/bash
# Deploy Frappe HR with Docker: start the stack, wait for the site, finish the
# setup wizard, load sample data, then follow the logs.
#
#   ./deploy.sh
#
# Override any setting below with an environment variable, for example:
#   COMPANY_NAME="Northwind" COUNTRY="Bangladesh" CURRENCY="BDT" TIMEZONE="Asia/Dhaka" ./deploy.sh
#
# Safe to run again: steps that are already done are skipped.
set -euo pipefail
cd "$(dirname "$0")"

# ---- Settings ----
COMPANY_NAME="${COMPANY_NAME:-Acme Demo}"
COMPANY_ABBR="${COMPANY_ABBR:-}" # defaults to the company's initials
COUNTRY="${COUNTRY:-United States}"
CURRENCY="${CURRENCY:-USD}"
TIMEZONE="${TIMEZONE:-America/New_York}"
ADMIN_EMAIL="${ADMIN_EMAIL:-yeaheahoqueshoumik@gmail.com}" # email on the Administrator account
LOAD_SAMPLE_DATA="${LOAD_SAMPLE_DATA:-1}" # 0 = leave the setup wizard and data to you
WEB_PORT=2000                             # must match docker-compose.yml
SETUP_TIMEOUT_MINUTES="${SETUP_TIMEOUT_MINUTES:-60}"

SETUP_MARKER=/home/frappe/benches/.setup-complete

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ---- Checks ----
command -v docker >/dev/null || fail "Docker is not installed. See https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is missing (the 'docker compose' command)."
docker info >/dev/null 2>&1 || fail "Can't reach the Docker daemon. Is it running, and can this user use it?"

# ---- Start ----
step "Starting containers"
docker compose up -d

step "Waiting for the site (the first run installs everything and takes 10-30 minutes)"
deadline=$(( $(date +%s) + SETUP_TIMEOUT_MINUTES * 60 ))
last_report=0
until docker compose exec -T frappe test -f "$SETUP_MARKER" 2>/dev/null \
	&& curl -sf -o /dev/null "http://localhost:${WEB_PORT}/login"; do
	if [ -z "$(docker compose ps -q --status running frappe)" ]; then
		docker compose logs --tail 40 frappe
		fail "The frappe container stopped. See the log above."
	fi
	now=$(date +%s)
	[ "$now" -gt "$deadline" ] && fail "Site not ready after ${SETUP_TIMEOUT_MINUTES} minutes. Check: docker compose logs frappe"
	if [ $(( now - last_report )) -ge 60 ]; then
		echo "   still working: $(docker compose logs --tail 1 --no-log-prefix frappe 2>/dev/null | cut -c1-100)"
		last_report=$now
	fi
	sleep 5
done
echo "   site is up"

step "Setting Administrator email to ${ADMIN_EMAIL}"
docker compose exec -T -e ADMIN_EMAIL="$ADMIN_EMAIL" frappe bash /workspace/seed.sh set_admin_email \
	|| echo "WARNING: could not set the Administrator email." >&2

# ---- Setup wizard and sample data ----
if [ "$LOAD_SAMPLE_DATA" = "1" ]; then
	step "Finishing the setup wizard for ${COMPANY_NAME} (${COUNTRY}, ${CURRENCY})"
	docker compose exec -T \
		-e DEMO_COMPANY="$COMPANY_NAME" \
		-e DEMO_COMPANY_ABBR="$COMPANY_ABBR" \
		-e DEMO_COUNTRY="$COUNTRY" \
		-e DEMO_CURRENCY="$CURRENCY" \
		-e DEMO_TIMEZONE="$TIMEZONE" \
		frappe bash /workspace/seed.sh complete_setup \
		|| fail "The setup wizard failed. Check COUNTRY, CURRENCY and TIMEZONE, then run ./deploy.sh again."

	step "Loading sample data"
	if ! docker compose exec -T frappe bash /workspace/seed.sh; then
		echo "WARNING: loading sample data failed. The app still works; see the error above." >&2
	fi
else
	step "Skipping setup wizard and sample data (LOAD_SAMPLE_DATA=0)"
fi

cat <<EOF

==> Frappe HR is running
   URL:       http://localhost:${WEB_PORT}
   Username:  Administrator
   Password:  admin

   Stop:      docker compose stop       (from $(pwd))
   Remove:    docker compose down       (data is kept)
   Wipe all:  docker compose down -v

==> Following logs (Ctrl+C stops following; the app keeps running)
EOF

exec docker compose logs -f --tail 50
