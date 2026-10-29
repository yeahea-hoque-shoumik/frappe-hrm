#!/bin/bash
# Load sample HR data. Run from the docker folder after finishing the setup wizard:
#   docker compose exec frappe bash /workspace/seed.sh
# `seed.sh complete_setup` finishes the setup wizard instead (used by deploy.sh).
set -e
STEP="${1:-run}"
BENCH=/home/frappe/benches/frappe-bench
cd "$BENCH/sites"
PYTHONPATH=/workspace "$BENCH/env/bin/python" -c "
import frappe
frappe.init(site='hrms.localhost', sites_path='.')
frappe.connect()
try:
    import seed_demo_data
    seed_demo_data.$STEP()
finally:
    frappe.destroy()
"
