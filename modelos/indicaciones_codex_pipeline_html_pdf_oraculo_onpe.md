# Indicaciones para Codex: pipeline reproducible para pronóstico electoral ONPE 2026

> Estado al 9 de junio de 2026: la primera version operativa esta implementada
> en `modelos/oraculo_onpe.py`. La metodologia vigente se resume en
> `modelos/METODOLOGIA_MODELOS.md` y el informe se genera en
> `modelos/salidas/reporte_oraculo_onpe.html`.

## 1. Objetivo general

Construir un proyecto reproducible en Python que permita cargar periódicamente los datos descargados de ONPE, procesarlos, estimar múltiples modelos de proyección electoral para segunda vuelta, comparar sus resultados y exportar un reporte sencillo en HTML y PDF.

El sistema debe funcionar como un pipeline que el usuario pueda ejecutar cada vez que tenga una nueva descarga de datos ONPE. El resultado esperado es un reporte actualizado, navegable y publicable, donde se pueda hacer clic en cada modelo para revisar su lógica, resultados, gráficos, supuestos y advertencias.

## 2. Principios metodológicos

El problema no debe tratarse como una simple extrapolación lineal del porcentaje nacional contabilizado. En elecciones reales, las actas no ingresan de manera aleatoria. El orden de llegada puede estar sesgado por territorio, accesibilidad, tamaño de local, zona urbana/rural, voto extranjero, conectividad o velocidad de procesamiento. Por eso, el pipeline debe distinguir entre:

1. Resultado oficial parcial observado.
2. Resultado proyectado nacional.
3. Incertidumbre de la proyección.
4. Sesgo potencial por actas faltantes.
5. Sensibilidad del resultado según modelo.

Cada modelo debe reportar tanto el ganador proyectado como la diferencia estimada, intervalos de incertidumbre y supuestos principales.

## 3. Lenguaje recomendado

Usar Python como lenguaje principal. La razón es que facilita automatización, integración con datos descargados, generación de HTML, modelos de machine learning, simulación bayesiana, exportación a archivos y posterior integración con un panel web.

R puede usarse de manera complementaria si se desea producir un informe académico en Quarto o validar modelos estadísticos específicos, pero el pipeline operativo debe quedar en Python.

## 4. Estructura sugerida del repositorio

Crear un repositorio con esta estructura:

```text
oraculo-onpe-2026/
│
├── data/
│   ├── raw/                    # Archivos originales descargados de ONPE
│   ├── processed/              # Datos limpios y normalizados
│   └── snapshots/              # Cortes históricos por hora/minuto
│
├── outputs/
│   ├── html/                   # Reportes HTML exportados
│   ├── pdf/                    # Reportes PDF exportados
│   ├── figures/                # Gráficos generados
│   └── tables/                 # Tablas finales en CSV/Excel
│
├── src/
│   ├── config.py               # Parámetros generales
│   ├── ingest.py               # Carga de datos ONPE
│   ├── clean.py                # Limpieza y normalización
│   ├── features.py             # Construcción de variables
│   ├── models_baseline.py      # Modelos simples y de tendencia
│   ├── models_bayes.py         # Modelos bayesianos / Dirichlet
│   ├── models_kalman.py        # Filtro de Kalman
│   ├── models_ml.py            # XGBoost, modelos supervisados
│   ├── ensemble.py             # Ensamble de modelos
│   ├── diagnostics.py          # Validaciones y métricas
│   ├── plots.py                # Visualizaciones
│   └── report.py               # Exportación HTML/PDF
│
├── reports/
│   ├── template.html           # Plantilla principal HTML
│   ├── template_model.html     # Plantilla por modelo
│   └── styles.css              # Estilos simples del reporte
│
├── notebooks/
│   └── exploracion_inicial.ipynb
│
├── run_pipeline.py             # Script principal
├── requirements.txt
├── README.md
└── .gitignore
```

## 5. Flujo de trabajo esperado

El usuario debe poder ejecutar algo como:

```bash
python run_pipeline.py --input data/raw/onpe_2026_06_08_1700.csv --output outputs/html/reporte_2026_06_08_1700.html
```

También debe poder ejecutar:

```bash
python run_pipeline.py --input data/raw/onpe_2026_06_08_1700.csv --pdf true
```

El pipeline debe hacer lo siguiente:

1. Leer el archivo de ONPE.
2. Detectar automáticamente el porcentaje de actas contabilizadas.
3. Normalizar nombres de candidatos, departamentos, provincias, distritos, locales y mesas.
4. Construir variables agregadas nacionales y territoriales.
5. Guardar un snapshot del corte actual.
6. Ejecutar todos los modelos disponibles.
7. Comparar resultados entre modelos.
8. Generar gráficos.
9. Exportar un HTML navegable.
10. Exportar opcionalmente un PDF.

## 6. Tipos de datos esperados

El pipeline debe ser flexible porque ONPE puede entregar datos en distintos formatos. Aceptar al menos:

- CSV.
- Excel.
- JSON si se identifica una API.
- Carpeta con múltiples archivos descargados.

Codex debe crear funciones que detecten columnas equivalentes aunque cambien ligeramente los nombres.

Columnas deseables:

- Fecha y hora del corte.
- Departamento.
- Provincia.
- Distrito.
- Local de votación.
- Mesa.
- Actas contabilizadas.
- Actas procesadas.
- Actas observadas.
- Votos por candidato.
- Votos blancos.
- Votos nulos.
- Votos impugnados, si existieran.
- Electores hábiles.
- Votos emitidos.
- Porcentaje de avance.

## 7. Modelos que debe implementar el sistema

### 7.1 Modelo 0: resultado observado ONPE

No es un modelo predictivo. Presenta el resultado oficial parcial observado.

Debe reportar:

- Porcentaje de actas contabilizadas.
- Votos absolutos por candidato.
- Porcentaje por candidato sobre votos válidos.
- Diferencia absoluta y porcentual.
- Última actualización.

### 7.2 Modelo 1: tendencia nacional simple

Extrapola el resultado nacional actual al 100%.

Uso: referencia básica.

Advertencia: es metodológicamente débil si las actas faltantes no son aleatorias.

### 7.3 Modelo 2: tendencia territorial ponderada

Proyecta resultados pendientes por departamento, provincia o distrito usando el comportamiento observado en cada unidad territorial.

Debe permitir tres niveles:

- Departamento.
- Provincia.
- Distrito.

Si una unidad territorial tiene pocos datos observados, aplicar pooling hacia el nivel superior.

### 7.4 Modelo 3: swing territorial respecto a primera vuelta o elección previa

Si se cuenta con datos históricos o de primera vuelta, estimar el cambio territorial observado y proyectarlo sobre zonas pendientes.

Ejemplo:

- Voto esperado en distrito = voto histórico del distrito + swing observado en unidades similares.

Este modelo puede ser más sólido que la tendencia nacional si existe información territorial histórica confiable.

### 7.5 Modelo 4: Bayes Dirichlet / multinomial

Implementar una simulación bayesiana para estimar el reparto final de votos entre candidatos bajo un modelo Dirichlet-multinomial.

Debe permitir priors:

- Prior no informativo.
- Prior basado en resultados observados nacionales.
- Prior territorial basado en departamentos/provincias/distritos.
- Prior histórico si hay elección previa comparable.

Salida esperada:

- Media posterior por candidato.
- Intervalo creíble.
- Probabilidad de victoria de cada candidato.
- Distribución simulada de la diferencia.

### 7.6 Modelo 5: filtro de Kalman sobre margen electoral

Aplicar un modelo de actualización secuencial sobre el margen entre candidatos conforme ingresan nuevos cortes.

Este modelo requiere snapshots históricos. Si solo existe un corte, debe desactivarse automáticamente.

Salida esperada:

- Margen observado por corte.
- Margen suavizado.
- Margen proyectado.
- Incertidumbre temporal.

### 7.7 Modelo 6: XGBoost territorial

Modelo supervisado para predecir el resultado pendiente por unidad territorial o mesa/local, usando variables disponibles.

Variables posibles:

- Departamento.
- Provincia.
- Distrito.
- Avance territorial.
- Electores hábiles.
- Votos emitidos.
- Resultado observado parcial.
- Historial electoral si existe.
- Rural/urbano si se puede construir.
- Velocidad de ingreso de actas.

Este modelo solo debe activarse si hay suficientes observaciones. Si no hay datos suficientes, debe reportar que no corresponde usarlo.

### 7.8 Modelo 7: ensamble ponderado

Combinar varios modelos en un resultado final.

La ponderación debe basarse en:

- Desempeño retrospectivo sobre snapshots anteriores.
- Estabilidad del modelo.
- Cobertura territorial de datos.
- Coherencia con el avance observado.

Si no hay historial suficiente para calibrar pesos, usar pesos iguales pero advertir la limitación.

### 7.9 Modelo 8: escenarios de sensibilidad

Generar escenarios alternativos:

- Escenario conservador.
- Escenario favorable al candidato A.
- Escenario favorable al candidato B.
- Escenario de reversión en actas faltantes.
- Escenario de voto extranjero.

Esto es clave para comunicar incertidumbre sin vender una falsa precisión.

## 8. Reporte HTML esperado

El reporte debe ser sencillo, estático y publicable. No requiere un dashboard complejo en la primera versión.

Debe incluir:

### 8.1 Encabezado

- Título: Oráculo Electoral ONPE 2026.
- Fecha y hora del corte.
- Fuente de datos.
- Porcentaje de avance.
- Advertencia metodológica breve.

### 8.2 Resumen ejecutivo

Tarjetas principales:

- Resultado oficial parcial.
- Proyección del ensamble.
- Diferencia estimada.
- Probabilidad de victoria por candidato, si existe modelo bayesiano.
- Nivel de incertidumbre: bajo, medio o alto.

### 8.3 Navegación por modelos

Crear pestañas o botones clicables:

- Resultado ONPE observado.
- Tendencia nacional.
- Territorial ponderado.
- Swing territorial.
- Bayes Dirichlet.
- Kalman.
- XGBoost.
- Ensamble.
- Escenarios.
- Diagnóstico de datos.

Cada pestaña debe mostrar:

- Explicación breve del modelo.
- Supuestos.
- Resultado proyectado.
- Gráfico principal.
- Tabla de resultados.
- Limitaciones.

### 8.4 Gráficos mínimos

Incluir al menos:

1. Barra comparativa del resultado ONPE observado.
2. Barra comparativa de la proyección final por modelo.
3. Evolución del margen por corte si hay snapshots.
4. Distribución simulada del margen para modelos bayesianos.
5. Mapa o tabla territorial si hay datos subnacionales.
6. Tabla de comparación entre modelos.

### 8.5 Diagnóstico de calidad de datos

Debe mostrar:

- Filas leídas.
- Filas válidas.
- Filas excluidas.
- Columnas detectadas.
- Valores faltantes relevantes.
- Duplicados por mesa/local, si aplica.
- Inconsistencias de votos.
- Diferencia entre votos emitidos y suma de votos por tipo.

## 9. Exportación PDF

El PDF puede generarse de dos formas:

1. Desde el mismo HTML usando WeasyPrint o Playwright.
2. Con un reporte Quarto si se decide incorporar R o Python en Quarto.

Para la primera versión, usar HTML + Playwright o WeasyPrint.

El PDF debe ser una versión resumida:

- Portada.
- Resumen ejecutivo.
- Comparación de modelos.
- Modelo recomendado.
- Anexos metodológicos breves.

## 10. Interactividad mínima

No construir todavía una aplicación compleja tipo Streamlit o Dash salvo que sea muy simple. Priorizar HTML estático con tabs o secciones colapsables.

Opciones recomendadas:

- HTML + Jinja2 + CSS + JavaScript mínimo.
- Plotly para gráficos interactivos.
- DataTables o tablas HTML simples.

El reporte debe poder abrirse localmente en el navegador sin servidor.

## 11. Librerías sugeridas

Usar Python 3.11 o superior.

Librerías:

```text
pandas
numpy
scipy
statsmodels
scikit-learn
xgboost
plotly
jinja2
pydantic
pyyaml
openpyxl
pyarrow
matplotlib
weasyprint
playwright
```

Opcionales:

```text
pymc
cmdstanpy
geopandas
folium
quarto
```

Evitar dependencias pesadas al inicio si no son necesarias.

## 12. Configuración central

Crear un archivo `config.yaml` con:

```yaml
election:
  name: "Segunda vuelta Perú 2026"
  candidates:
    - "Keiko Fujimori"
    - "Roberto Sánchez"
  valid_vote_columns:
    - "votos_keiko"
    - "votos_roberto"

input:
  raw_folder: "data/raw"
  processed_folder: "data/processed"
  snapshot_folder: "data/snapshots"

report:
  html_output: "outputs/html/reporte_actual.html"
  pdf_output: "outputs/pdf/reporte_actual.pdf"
  title: "Oráculo Electoral ONPE 2026"

models:
  run_baseline: true
  run_territorial: true
  run_bayes: true
  run_kalman: true
  run_xgboost: true
  run_ensemble: true
```

## 13. Script principal esperado

`run_pipeline.py` debe aceptar argumentos:

```bash
python run_pipeline.py \
  --input data/raw/onpe.csv \
  --config config.yaml \
  --html true \
  --pdf false \
  --save-snapshot true
```

Debe producir mensajes claros en consola:

```text
[1/8] Leyendo datos ONPE...
[2/8] Limpiando columnas...
[3/8] Construyendo agregados...
[4/8] Guardando snapshot...
[5/8] Ejecutando modelos...
[6/8] Generando gráficos...
[7/8] Exportando HTML...
[8/8] Finalizado.
```

## 14. Validación retrospectiva

Si existen varios snapshots, el sistema debe poder simular qué habría proyectado cada modelo en cortes anteriores.

Ejemplo:

- Corte al 50%.
- Corte al 60%.
- Corte al 70%.
- Corte al 80%.
- Corte al 90%.

Comparar cada proyección contra el resultado final disponible o contra el corte más reciente si aún no hay resultado final.

Métricas:

- Error absoluto de margen.
- Error absoluto por candidato.
- Brier score para probabilidad de victoria.
- Estabilidad de proyección entre cortes.
- Cambio de ganador proyectado.

## 15. Modelo recomendado para comunicar públicamente

El reporte debe evitar presentar un único resultado sin contexto. El resultado principal recomendado debe ser el ensamble, pero acompañado de:

- Resultado oficial parcial ONPE.
- Intervalo de incertidumbre.
- Comparación con modelos alternativos.
- Advertencia sobre actas pendientes y sesgo territorial.

La frase sugerida para el reporte es:

> La proyección no reemplaza el conteo oficial. Estima el resultado probable bajo supuestos explícitos sobre el comportamiento de las actas pendientes. La incertidumbre depende del porcentaje de avance, la distribución territorial de las actas faltantes y la estabilidad de los modelos.

## 16. Criterios para activar/desactivar modelos

Cada modelo debe tener condiciones mínimas.

- Tendencia nacional: siempre disponible.
- Territorial ponderado: requiere variable territorial y avance por territorio.
- Swing histórico: requiere datos históricos comparables.
- Bayes Dirichlet: disponible con votos por candidato.
- Kalman: requiere al menos tres snapshots temporales.
- XGBoost: requiere suficientes unidades observadas y variables predictoras.
- Ensamble: requiere al menos dos modelos válidos.

Si un modelo no cumple condiciones, el HTML debe mostrarlo como “No disponible para este corte” y explicar la razón.

## 17. Manejo de incertidumbre

No usar más decimales de los necesarios. Reportar:

- Porcentajes con dos decimales.
- Diferencias de votos como enteros.
- Probabilidades con una o dos cifras decimales.
- Intervalos con límites claros.

Ejemplo:

```text
Roberto Sánchez: 50.08% [49.96%, 50.20%]
Keiko Fujimori: 49.92% [49.80%, 50.04%]
Diferencia estimada: 29,147 votos
Probabilidad de victoria: 87.4%
```

## 18. Diseño visual

El diseño debe ser sobrio y legible. No copiar marcas ni estilos oficiales de ONPE. Se puede usar un estilo oscuro o claro, pero debe priorizar lectura.

Recomendación:

- Fondo claro para PDF.
- Fondo claro o modo oscuro opcional para HTML.
- Colores consistentes por candidato.
- Tablas limpias.
- Gráficos interactivos en HTML.
- Gráficos estáticos o simplificados en PDF.

## 19. Archivos de salida esperados

Cada ejecución debe producir:

```text
outputs/html/reporte_actual.html
outputs/pdf/reporte_actual.pdf              # opcional
outputs/tables/resultados_modelos.csv
outputs/tables/diagnostico_datos.csv
outputs/figures/*.html
outputs/figures/*.png
```

También debe guardar un JSON con resultados estructurados:

```text
outputs/resultados_actuales.json
```

Ese JSON servirá para alimentar un panel posterior.

## 20. README esperado

Crear un README con:

- Objetivo del proyecto.
- Cómo instalar dependencias.
- Cómo colocar los datos ONPE.
- Cómo ejecutar el pipeline.
- Cómo interpretar el HTML.
- Qué modelos están implementados.
- Limitaciones metodológicas.
- Cómo publicar el reporte.

## 21. MVP recomendado

Primera versión funcional:

1. Carga CSV/Excel.
2. Limpieza y validación.
3. Resultado ONPE observado.
4. Tendencia nacional simple.
5. Territorial ponderado por departamento.
6. Bayes Dirichlet básico.
7. Comparación de modelos.
8. HTML con pestañas.
9. Exportación PDF opcional.
10. Guardado de snapshots.

Segunda versión:

1. Kalman con snapshots.
2. Swing territorial histórico.
3. XGBoost.
4. Ensamble calibrado.
5. Diagnóstico territorial más avanzado.
6. Mapa subnacional.

Tercera versión:

1. Panel web actualizado.
2. Automatización de descarga de datos.
3. API propia de resultados.
4. Publicación continua.
5. Versión metodológica extendida.

## 22. Advertencias importantes para Codex

No asumir que el orden de llegada de actas es aleatorio.
No presentar el resultado proyectado como resultado oficial.
No ocultar modelos que fallan: reportar por qué no se ejecutaron.
No usar redes neuronales si no hay suficientes datos.
No sobreajustar con pocos cortes temporales.
No usar demasiados decimales.
No borrar snapshots anteriores.
No modificar archivos raw originales.

## 23. Resultado final esperado

Al terminar, el usuario debe poder descargar datos ONPE, copiarlos en `data/raw/`, ejecutar un comando y obtener un HTML publicable con análisis modelo por modelo.

El producto final debe servir para:

- Monitoreo interno.
- Publicación rápida.
- Comparación metodológica.
- Transparencia sobre supuestos.
- Actualización continua durante el conteo electoral.
