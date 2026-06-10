# Reanudar trabajo ONPE - segunda vuelta

Este flujo reutiliza el cruce ONPE-ODPE anterior, pero deja los insumos de segunda vuelta y sus salidas separados.

## Estructura

- `scripts/`: codigo R del cruce.
- `insumos/descargas_modulo/`: CSV descargados del modulo especializado.
- `insumos/maestras/`: tablas maestras de mesas, locales y ODPE.
- `salidas/`: productos CSV generados por el cruce.
- `docs/`: notas para reanudar el trabajo.

## Scripts nuevos

- `scripts/01_onpe_odpe_cruce_reutilizable.R`: contiene las funciones comunes de lectura, cruce y escritura.
- `scripts/01_onpe_odpe_cruce_segunda_vuelta.R`: lanzador para segunda vuelta.
- `scripts/03_ranking_odpe_word.py`: genera el Word `salidas/ranking_odpe_por_eleccion.docx`.
- `scripts/04_ranking_odpe_excel.mjs`: genera el Excel `salidas/Ranking de procesamiento por ODPE.xlsx`.
- `scripts/05_finalizar_ranking_excel.py`: aplica los textos finales con tildes, nota de fuente y panel congelado.
- `actualizar_ranking_odpe.bat`: recalcula cruce y genera el Excel con doble clic.

## Estado probado

El 2026-06-08 se ejecuto el lanzador de segunda vuelta con este corte:

```text
PR-ESP_Presidencial_2026-06-08_01-30-PM_94.102_1780943444464.csv
```

Resultado del diagnostico:

- Mesas ONPE: 88,811
- Mesas cruzadas con ODPE: 88,664
- Tasa de cruce: 99.83%
- Mesas sin ODPE: 147

## Generacion rapida del Excel

Despues de copiar un nuevo CSV en `insumos/descargas_modulo/`, ejecutar:

```text
actualizar_ranking_odpe.bat
```

El flujo toma el CSV presidencial mas reciente, recalcula `resumen_departamento_odpe.csv` y genera:

```text
salidas/Ranking de procesamiento por ODPE.xlsx
```

La linea de actualizacion se infiere del nombre del CSV mas reciente. Si se necesita fijarla manualmente, definir antes `ONPE_SV_UPDATE_LABEL`.

## Carpeta recomendada

Colocar los CSV de segunda vuelta en:

```text
Segunda vuelta ODPE/insumos/descargas_modulo/
```

Las maestras quedan en:

```text
Segunda vuelta ODPE/insumos/maestras/
```

Las salidas se escriben por defecto en:

```text
Segunda vuelta ODPE/salidas/
```

## Ejecucion basica

Desde esta carpeta de analisis:

```r
source("scripts/01_onpe_odpe_cruce_segunda_vuelta.R")
```

## Cuando las maestras nuevas tienen otros nombres

El lanzador queda preparado para estas maestras encontradas:

- `Segunda vuelta ODPE/Mesa por Mesa SEP2026 25.05.26.xlsx`
- `Segunda vuelta ODPE/EG2026_Locales_v15.xlsx`

Para el cruce ODPE usa por defecto `Mesa por Mesa SEP2026 25.05.26.xlsx`, porque ya trae mesa, local, electores y `NOMBRE ODPE`.

Se puede configurar sin tocar el codigo usando variables de entorno antes de ejecutar:

```r
Sys.setenv(ONPE_SV_INSUMOS_DIR = "C:/ruta/a/csv_segunda_vuelta")
Sys.setenv(ONPE_SV_MAESTRAS_DIR = "C:/ruta/a/maestras")
Sys.setenv(ONPE_SV_LOCALES_MESAS_PATTERN = "Mesas|LocalesMesas")
Sys.setenv(ONPE_SV_ODPE_PATTERN = "Locales|ODPE|VOTACION")
source("scripts/01_onpe_odpe_cruce_segunda_vuelta.R")
```

Tambien se pueden pasar rutas exactas:

```r
Sys.setenv(ONPE_SV_LOCALES_MESAS_FILE = "C:/ruta/mesas_locales.xlsx")
Sys.setenv(ONPE_SV_ODPE_FILE = "C:/ruta/locales_odpe.xlsx")
```

## Idea clave

Para segunda vuelta solo se cambia la lista de elecciones a procesar. El cruce conserva la misma logica:

1. CSV ONPE por mesa.
2. Tabla maestra de mesas/locales para obtener `id_local`.
3. Tabla maestra de locales/ODPE para obtener `odpe` y `nombre_odpe`.

Si las nuevas maestras cambian nombres de columnas, revisar primero que existan equivalentes de:

- `departamento` o `departameto`
- `provincia`
- `distrito`
- `nombre_local` o `nombre_del_local`
- `numero_de_mesa`
- `id_local`
- `odpe`
- `nombre_odpe`
