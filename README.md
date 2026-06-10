# Segunda vuelta ODPE

Carpeta autocontenida para el cruce ONPE-ODPE de segunda vuelta.

## Dashboard publicado

El panel más reciente se publica automáticamente en GitHub Pages después de
cada actualización de la rama `main`:

https://noamlv.github.io/segunda_vuelta_escenarios/

## Actualizar con un nuevo CSV

1. En GitHub, abrir `insumos/descargas_modulo/`.
2. Seleccionar **Add file > Upload files**.
3. Subir el nuevo CSV sin borrar los cortes anteriores.
4. Confirmar el cambio directamente en la rama `main`.

La acción `Publicar dashboard en GitHub Pages` detecta el CSV, instala las
dependencias, recalcula los modelos, regenera el panel, guarda los resultados
generados en el repositorio y publica la nueva versión.

También se puede ejecutar manualmente desde **Actions > Publicar dashboard en
GitHub Pages > Run workflow**. Esta opción es útil para forzar un recálculo
cuando se modifica un CSV conservando el mismo nombre.

El nombre del CSV debe conservar el patrón utilizado por las descargas de la
ONPE, por ejemplo:

```text
PR-ESP_Presidencial_2026-06-10_09-58-AM_97.541.csv
```

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
