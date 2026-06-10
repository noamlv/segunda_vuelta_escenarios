#!/bin/bash

# Doble clic para abrir el dashboard en macOS.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/abrir_dashboard.sh" "$@"
STATUS=$?
echo ""
echo "Presiona cualquier tecla para cerrar esta ventana..."
read -n 1
exit "$STATUS"
