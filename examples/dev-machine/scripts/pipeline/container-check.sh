#!/usr/bin/env bash
# container-check.sh — Refuse to run outside Docker.
#
# Checks for /.dockerenv or /run/.containerenv.
# If neither is found, prints an error banner and exits 1 unless
# DEV_MACHINE_ALLOW_HOST is set, in which case prints a warning and exits 0.
# If inside a container, prints confirmation and exits 0.

set -euo pipefail

if [ ! -f /.dockerenv ] && [ ! -f /run/.containerenv ]; then
    echo "=========================================="
    echo "ERROR: DEV MACHINE NOT RUNNING IN CONTAINER"
    echo "=========================================="
    echo ""
    echo "Running dev-machine recipes outside a container is DANGEROUS."
    echo "Autonomous agents have unrestricted filesystem access and can"
    echo "damage files outside the project directory."
    echo ""
    echo "Use: ./run-dev-machine.sh"
    echo "Or:  docker compose run --rm dev-machine"
    echo ""
    echo "To bypass this check (NOT RECOMMENDED):"
    echo "  export DEV_MACHINE_ALLOW_HOST=1"
    echo "=========================================="
    if [ -z "${DEV_MACHINE_ALLOW_HOST:-}" ]; then
        exit 1
    fi
    echo "WARNING: DEV_MACHINE_ALLOW_HOST is set. Proceeding on bare host."
    echo "YOU ACCEPT ALL RISKS OF FILESYSTEM DAMAGE."
fi

echo "Container check passed."
