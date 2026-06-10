#!/bin/bash

# Abre el panel existente y solo recalcula cuando cambian la data o el código.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
HTML_FILE="$SCRIPT_DIR/panel/panel_electoral_onpe.html"

echo "=== Pipeline ONPE - Segunda Vuelta ==="
echo "Directorio: $SCRIPT_DIR"
echo ""

FORCE_MODE=false
if [ "$1" = "--force" ]; then
    FORCE_MODE=true
    echo "Modo forzado: se recalcularán los modelos y el panel."
    echo ""
fi

MODEL_REFRESH=false
PANEL_REFRESH=false

if [ "$FORCE_MODE" = true ]; then
    MODEL_REFRESH=true
    PANEL_REFRESH=true
elif python3 oraculo_onpe.py --needs-refresh >/dev/null 2>&1; then
    MODEL_REFRESH=true
    PANEL_REFRESH=true
elif [ ! -f "$HTML_FILE" ] || [ "$SCRIPT_DIR/dashboard_onpe.py" -nt "$HTML_FILE" ]; then
    PANEL_REFRESH=true
fi

if [ "$MODEL_REFRESH" = true ]; then
    echo "[1/2] Nueva data detectada. Recalculando modelos..."
    if [ "$FORCE_MODE" = true ]; then
        python3 oraculo_onpe.py --force
    else
        python3 oraculo_onpe.py
    fi
else
    echo "[1/2] No hay nueva data. Se conserva el caché vigente."
fi

if [ "$PANEL_REFRESH" = true ]; then
    echo ""
    echo "[2/2] Regenerando el panel HTML..."
    python3 dashboard_onpe.py
else
    echo "[2/2] El panel ya está generado; se abrirá sin recalcular."
fi

if [ -f "$HTML_FILE" ]; then
    echo ""
    echo "Abriendo dashboard..."
    open "$HTML_FILE"
    echo "Dashboard abierto en el navegador."
else
    echo "Error: No se encontró el archivo HTML en $HTML_FILE"
    exit 1
fi
