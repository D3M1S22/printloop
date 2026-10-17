#!/usr/bin/env bash
# Wrapper per OrcaSlicer via Flatpak per PrintLoop.
# Assicura i permessi per /tmp e home, e inietta --allow-newer-file per compatibilità con i 3MF BambuStudio.
set -euo pipefail

ARGS=()
HAS_ALLOW_NEWER=0
IS_HELP=0

for arg in "$@"; do
    if [[ "$arg" == "--allow-newer-file" ]]; then
        HAS_ALLOW_NEWER=1
    elif [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
        IS_HELP=1
    fi
    ARGS+=("$arg")
done

if [[ $IS_HELP -eq 0 && $HAS_ALLOW_NEWER -eq 0 ]]; then
    exec /usr/bin/flatpak run --filesystem=/tmp --filesystem=home com.orcaslicer.OrcaSlicer --allow-newer-file "${ARGS[@]}"
else
    exec /usr/bin/flatpak run --filesystem=/tmp --filesystem=home com.orcaslicer.OrcaSlicer "${ARGS[@]}"
fi

