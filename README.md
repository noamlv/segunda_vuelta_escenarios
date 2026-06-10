# Segunda vuelta ODPE

Carpeta autocontenida para el cruce ONPE-ODPE de segunda vuelta.

## Dashboard publicado

El panel más reciente se publica automáticamente en GitHub Pages después de
cada actualización de la rama `main`:

https://noamlv.github.io/segunda_vuelta_escenarios/

## Carpetas

- `scripts/`: código R y Python.
- `insumos/descargas_modulo/`: CSV descargados del módulo especializado.
- `insumos/maestras/`: Excel maestros.
- `salidas/`: CSV generados.
- `modelos/`: modelos, documentación, caché y panel generado.
- `docs/`: notas de reanudación.

## Ejecutar

Desde esta carpeta:

```r
source("scripts/01_onpe_odpe_cruce_segunda_vuelta.R")
```

El script toma automáticamente el CSV presidencial más reciente y escribe los productos en `salidas/`.

## Ranking ODPE

Para generar el Word con el ranking de ODPE:

```bash
python scripts/03_ranking_odpe_word.py
```

Salida:

```text
salidas/ranking_odpe_por_eleccion.docx
```

Para recalcular el cruce y generar el Excel rápidamente después de agregar un nuevo CSV:

```text
actualizar_ranking_odpe.bat
```

Salida:

```text
salidas/Ranking de procesamiento por ODPE.xlsx
```

## Modelos de proyección

Para recalcular el pronostico con todos los cortes disponibles:

```bash
python3 modelos/oraculo_onpe.py
```

Informe principal:

```text
modelos/salidas/reporte_oraculo_onpe.html
```

Panel de seguimiento:

```bash
python3 modelos/dashboard_onpe.py
```

```text
modelos/panel/panel_electoral_onpe.html
```

Metodología:

```text
modelos/METODOLOGIA_MODELOS.md
```

Documento de continuidad para otros agentes:

```text
modelos/CONTINUIDAD_PARA_OTRO_AGENTE.md
```
