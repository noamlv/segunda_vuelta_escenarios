# Continuidad tecnica: modelos y panel electoral ONPE

## Proposito de este documento

Este archivo permite continuar el trabajo con otro agente de programacion
(Qwen, OpenCode, Codex u otro) sin reconstruir ni rediseñar lo que ya funciona.

La prioridad es:

1. conservar el panel actual;
2. incorporar nuevos CSV automaticamente;
3. agregar funciones de forma incremental;
4. mantener separadas las cifras oficiales y las proyecciones;
5. validar siempre el universo completo de mesas.

## Instruccion principal para el siguiente agente

> No rediseñar, reemplazar ni simplificar el panel existente. Trabajar sobre
> `modelos/dashboard_onpe.py` mediante cambios pequeños y localizados. Preservar
> la estructura visual, los colores, las tarjetas, los gráficos, la tabla, los
> filtros, el comportamiento responsive y el archivo HTML único. Las nuevas
> funciones deben agregarse como extensiones del diseño actual.

No crear un panel alternativo salvo pedido expreso. No migrar a React,
Streamlit, Dash, Power BI u otro framework sin autorización. El panel actual
ya usa SVG nativo para los gráficos superiores y Plotly para backtesting,
incertidumbre y contribución territorial; conservar esa combinación.

## Ubicacion del proyecto

Raiz:

```text
/Users/noam/Library/CloudStorage/Dropbox/2 MOE/ONPE/resultados/Análisis de la fusión/Segunda vuelta ODPE
```

Trabajar desde esa carpeta.

## Fuentes de datos

### Cortes ONPE

```text
insumos/descargas_modulo/*.csv
```

Cada CSV contiene una fila por mesa que ya aparece en el modulo. Columnas
principales:

- `NÚMERO DE MESA`
- `ESTADO DEL ACTA`
- `ELECTORES HÁBILES`
- `FUERZA POPULAR`
- `JUNTOS POR EL PERÚ`
- `VOTOS EN BLANCO`
- `VOTOS NULOS`
- `VOTOS IMPUGNADOS`
- geografia, local y ambito

El script detecta el corte mas reciente usando la fecha y hora incluidas en el
nombre del archivo, no solamente la fecha de modificacion.

### Universo electoral

Fuente canonica para el denominador:

```text
insumos/maestras/Mesa por Mesa SEP2026 25.05.26.xlsx
```

Hoja:

```text
Sheet 1
```

Encabezado:

```text
skiprows=10
```

La maestra contiene **92,766 mesas unicas** y aporta:

- mesa;
- electores;
- departamento o continente;
- provincia o pais;
- distrito o ciudad;
- local;
- ODPE.

No reemplazar este denominador por la cantidad de filas del CSV. El CSV puede
no contener todavia todas las mesas.

## Definiciones obligatorias

La unidad es la mesa de sufragio.

### Estados

1. **Contabilizada**
   - `ESTADO DEL ACTA = Contabilizada`.
   - Sus votos integran el resultado oficial.

2. **Enviada al JEE**
   - `ESTADO DEL ACTA = Para envío al JEE`.
   - Puede tener votos digitados, pero aun no integra el resultado oficial.
   - Esos votos pueden cambiar por resolucion, correccion o anulacion.

3. **No ingresada**
   - Mesa presente en la maestra de 92,766 mesas pero ausente del CSV del corte.
   - No debe confundirse con una mesa enviada al JEE.

### Votos y margenes

```text
votos_validos = FUERZA POPULAR + JUNTOS POR EL PERÚ
margen_fp = votos_fuerza_popular - votos_juntos_por_el_peru
```

- Margen positivo: favorece a Keiko/Fuerza Popular.
- Margen negativo: favorece a Sanchez/Juntos por el Peru.
- Porcentajes de candidatos: siempre sobre votos validos.

### Resultado oficial versus proyeccion

El resultado oficial actual usa exclusivamente actas contabilizadas.

Nunca presentar la proyeccion como si fuera el resultado oficial. El panel debe
mostrar simultaneamente:

- lider oficial;
- proyeccion del ensamble;
- intervalo de incertidumbre;
- advertencia metodologica.

## Estado validado del ultimo corte

Corte usado:

```text
PR-ESP_Presidencial_2026-06-09_09-32-PM_96.512_1781058741805.csv
```

Fecha y hora:

```text
9 de junio de 2026, 21:32
```

Reconciliacion sobre 92,766 mesas:

| Estado | Mesas | Porcentaje |
| --- | ---: | ---: |
| Contabilizadas | 89,530 | 96.512% |
| Enviadas al JEE | 1,546 | 1.667% |
| No ingresadas | 1,690 | 1.822% |
| Total | 92,766 | 100.000% |

Electores asociados a mesas pendientes:

```text
1,245,899
```

Resultado oficial contabilizado:

| Candidato | Votos |
| --- | ---: |
| Keiko / Fuerza Popular | 8,915,051 |
| Sanchez / Juntos por el Peru | 8,955,656 |

Sanchez lidera oficialmente por:

```text
40,605 votos
```

## Donde estan las mesas pendientes

Principales territorios del ultimo corte:

| Territorio | Pendientes | JEE | No ingresadas | Electores pendientes |
| --- | ---: | ---: | ---: | ---: |
| Lima | 915 | 915 | 0 | 270,766 |
| America | 905 | 31 | 874 | 442,936 |
| Europa | 573 | 19 | 554 | 280,274 |
| Loreto | 151 | 33 | 118 | 40,585 |
| Cusco | 93 | 52 | 41 | 25,844 |
| Asia | 92 | 0 | 92 | 39,977 |
| Callao | 69 | 69 | 0 | 20,227 |
| Piura | 57 | 57 | 0 | 16,788 |
| Ancash | 45 | 45 | 0 | 12,729 |
| Ucayali | 43 | 36 | 7 | 12,158 |

Hallazgo importante:

- gran parte de las mesas no ingresadas corresponde al extranjero;
- las actas JEE se concentran especialmente en Lima;
- esto explica por que una extrapolacion nacional simple es debil.

## Arquitectura actual

### Motor de modelos

```text
modelos/oraculo_onpe.py
```

Responsabilidades:

- carga y normalizacion de la maestra;
- lectura y ordenamiento de los cortes;
- union de cada corte con las 92,766 mesas;
- clasificacion de contabilizadas y pendientes;
- ejecucion de modelos;
- backtesting;
- pesos del ensamble;
- simulacion de incertidumbre;
- tablas, graficos e informe HTML.

Funciones centrales:

```text
load_master()
load_snapshot()
attach_snapshot()
estimate_pending_by_hierarchy()
run_models()
backtest_models()
model_weights()
add_ensemble()
simulate_uncertainty()
```

### Generador del panel

```text
modelos/dashboard_onpe.py
```

Responsabilidades:

- reutilizar las funciones de `oraculo_onpe.py`;
- construir series historicas;
- clasificar los tres estados de mesa;
- agregar geografia y ODPE;
- preparar el JSON compacto;
- generar un solo archivo HTML para el panel.

La plantilla se encuentra en:

```python
DASHBOARD_HTML = r"""..."""
```

El archivo final es:

```text
modelos/panel/panel_electoral_onpe.html
```

### Caché y apertura del panel

```text
modelos/cache/modelos_cache.json
modelos/abrir_dashboard.sh
modelos/Abrir Dashboard.command
```

El `.command` delega en `abrir_dashboard.sh`. El lanzador tiene tres estados:

1. si hay un CSV electoral más reciente, recalcula modelos y panel;
2. si cambió `dashboard_onpe.py`, regenera solo el HTML;
3. si no cambió la data ni el generador, abre el HTML existente sin ejecutar
   los modelos ni reconstruir el panel.

`oraculo_onpe.py --needs-refresh` retorna código `0` cuando hay data nueva y
`1` cuando el caché está vigente. La comparación usa la fecha del corte
incluida en el nombre, el nombre del archivo y, para cachés nuevos, tamaño y
fecha de modificación.

## Modelos implementados

1. **Resultado observado**
   - Solo actas contabilizadas.
   - No es predictivo.

2. **Arrastre nacional**
   - Mantiene participacion y reparto nacional observado.
   - Supuesto fuerte: las mesas pendientes se parecen al promedio nacional.

3. **Jerarquico territorial**
   - Usa ambito, departamento/continente, provincia/pais y distrito/ciudad.
   - Aplica contraccion hacia niveles superiores para grupos pequenos.

4. **ODPE ponderado**
   - Proyecta dentro de la ODPE.
   - Aplica contraccion hacia el ambito.

5. **JEE reportado + faltantes territoriales**
   - Para actas JEE usa votos ya digitados.
   - Para mesas no ingresadas usa proyeccion territorial.
   - No predice la decision juridica del JEE.

6. **Ensamble**
   - Combina arrastre nacional, jerarquico territorial y ODPE.
   - Pesos inversamente proporcionales al error de backtesting.

7. **Simulacion**
   - Mezcla modelos segun sus pesos.
   - Agrega dispersion beta y error de calibracion.

## Resultados actuales de los modelos

| Modelo | Margen final de Keiko | Lectura |
| --- | ---: | --- |
| Resultado observado | -40,605 | Gana Sanchez oficialmente |
| Arrastre nacional | -42,545 | Proyecta Sanchez |
| Jerarquico territorial | +45,076 | Proyecta Keiko |
| ODPE ponderado | +46,348 | Proyecta Keiko |
| JEE + faltantes territoriales | +43,274 | Proyecta Keiko |
| Ensamble | +32,333 | Proyecta Keiko |

Pesos actuales del ensamble:

| Modelo | Peso |
| --- | ---: |
| Arrastre nacional | 14.981% |
| Jerarquico territorial | 54.881% |
| ODPE ponderado | 30.138% |

Simulacion:

```text
Probabilidad condicional de Keiko: 85.004%
Intervalo 95% del margen de Keiko: -55,230 a +61,996 votos
```

Interpretacion obligatoria:

- el ensamble favorece a Keiko;
- el intervalo permite que gane Sanchez;
- no es una prediccion juridica;
- no debe ocultarse que Sanchez lidera el resultado oficial.

## Contrato de diseño del panel

### No modificar sin autorizacion

- fondo gris muy claro;
- paneles blancos;
- tarjetas con bordes suaves y sombra discreta;
- tipografia de sistema;
- jerarquia visual actual;
- ancho maximo del panel;
- seis tarjetas superiores en escritorio;
- dos tarjetas por fila en movil;
- barra horizontal de estados;
- distribucion de graficos en grilla de 12 columnas;
- tabla territorial inferior;
- controles de region, estado y busqueda;
- un único HTML de salida; Plotly se carga actualmente desde CDN;
- comportamiento responsive.

### Paleta vigente

```text
Fondo:              #f6f7fb
Panel:              #ffffff
Texto principal:    #1f2430
Texto secundario:   #6f768a
Lineas y bordes:    #e6e8f0
Azul contabilizado: #5477c4
Azul claro:         #cedffe
Naranja Keiko:      #f0986e
Verde Sánchez:      #71b436
Rosa JEE:           #bd569b
Amarillo faltante:  #e7c85a
Morado métrica:     #8a5aa8
```

Regla semántica: naranja significa que un resultado favorece a Keiko y verde
que favorece a Sánchez. No usar esos dos colores para MAE, RMSE, estado JEE o
identidad de modelos. Las métricas usan azul, morado, amarillo y rosa.

### Componentes actuales

1. Encabezado con el título en una línea, fecha de actualización y nota sobre
   el procesamiento de datos publicados por la ONPE.
2. Tres etiquetas dinámicas:
   - votos oficiales de Sánchez;
   - votos oficiales de Keiko;
   - diferencia absoluta entre ambos.
3. Primera tarjeta `Estado de las 92,766 mesas`, que integra:
   - actas totales;
   - actas contabilizadas;
   - avance contabilizado;
   - actas enviadas al JEE;
   - porcentaje enviado al JEE sobre las 92,766 actas;
   - barra de composición de contabilizadas, JEE y no ingresadas.
4. Subtítulo `Escenarios posibles` y cinco tarjetas de pronóstico:
   - cuatro modelos individuales;
   - ensamble.
5. Serie temporal del avance.
6. Serie temporal de márgenes desde 90% de avance.
7. Ranking territorial de pendientes.
8. Comparación de modelos.
9. Fichas técnicas de modelos.
10. Pesos del ensamble con explicación.
11. Backtesting: MAE, RMSE, error máximo y evolución.
12. Distribución de incertidumbre.
13. Contribución territorial al margen.
14. Tabla ODPE con filtros.
15. Definiciones y cautelas.

### Actualización automática en GitHub

El workflow `.github/workflows/pages.yml` se ejecuta con cada cambio en
`main`. Solo recalcula cuando detecta cambios en:

- `insumos/descargas_modulo/*.csv`;
- `insumos/maestras/*.xlsx`;
- `modelos/oraculo_onpe.py`;
- `modelos/dashboard_onpe.py`;
- `modelos/requirements.txt`.

Cuando hay nueva data, ejecuta `oraculo_onpe.py --force`, regenera el dashboard,
crea un commit automático con `modelos/cache`, `modelos/salidas` y
`modelos/panel`, y despliega esa misma versión en GitHub Pages. No separar el
recalculo y el despliegue en workflows dependientes: los commits creados con
`GITHUB_TOKEN` no disparan normalmente otro workflow de `push`.

Las nuevas visualizaciones deben agregarse debajo o dentro de una nueva seccion
compatible con la grilla existente. No borrar ni reemplazar componentes.

## Protocolo para incorporar una funcionalidad

1. Leer este documento y `modelos/METODOLOGIA_MODELOS.md`.
2. Identificar si el cambio afecta:
   - fuente;
   - calculo;
   - modelo;
   - dataset del panel;
   - visualizacion;
   - filtro.
3. Modificar primero la capa Python.
4. Guardar nuevos datos en el objeto `payload`.
5. Agregar el componente HTML/JavaScript de forma localizada.
6. No reescribir toda la constante `DASHBOARD_HTML`.
7. Regenerar modelos y panel.
8. Verificar cifras.
9. Abrir el panel mediante servidor local.
10. Probar escritorio, movil, filtros y consola.

## Comandos operativos

### Recalcular modelos

```bash
python3 modelos/oraculo_onpe.py
```

### Regenerar panel

```bash
python3 modelos/dashboard_onpe.py
```

### Servir localmente para pruebas

```bash
python3 -m http.server 8877 --bind 127.0.0.1
```

Abrir:

```text
http://127.0.0.1:8877/modelos/panel/panel_electoral_onpe.html
```

### Validar sintaxis

```bash
python3 -m py_compile modelos/oraculo_onpe.py modelos/dashboard_onpe.py
```

### Flujo recomendado tras agregar un CSV

```bash
./modelos/abrir_dashboard.sh
```

Para abrir sin recalcular cuando no hay cambios:

```bash
./modelos/abrir_dashboard.sh
```

Para forzar una reconstrucción completa:

```bash
./modelos/abrir_dashboard.sh --force
```

## Productos generados

### Modelos e informe

```text
modelos/salidas/proyecciones_modelos.csv
modelos/salidas/backtesting_modelos.csv
modelos/salidas/evolucion_cortes.csv
modelos/salidas/pendientes_por_odpe.csv
modelos/salidas/detalle_actas_pendientes_territorial.csv
modelos/salidas/resumen_modelo.json
modelos/salidas/reporte_oraculo_onpe.html
```

### Panel

```text
modelos/panel/panel_electoral_onpe.html
modelos/panel/serie_avance.csv
modelos/panel/serie_modelos.csv
modelos/panel/pendientes_territorio.csv
modelos/panel/pendientes_odpe.csv
modelos/panel/modelos_actuales.csv
```

Los CSV de `modelos/panel/` son utiles para auditar los numeros visibles sin
tener que extraerlos del HTML.

## Controles de calidad obligatorios

Antes de entregar cualquier cambio deben cumplirse estas identidades:

```text
contabilizadas + JEE + no_ingresadas = 92,766
89,530 + 1,546 + 1,690 = 92,766  # ultimo corte documentado
```

Tambien verificar:

- una fila por mesa en la maestra;
- ninguna duplicacion por cruces;
- porcentajes sobre el denominador correcto;
- suma territorial igual al total nacional;
- margen oficial igual a votos FP menos votos JP contabilizados;
- todas las series ordenadas por fecha del nombre del archivo;
- sin valores `NaN` en las tarjetas;
- filtros funcionales;
- consola del navegador sin errores;
- legibilidad en 1280 x 720;
- legibilidad en aproximadamente 390 x 844.

## Errores ya encontrados y corregidos

### Error 1: confundir resultado oficial con proyeccion

Sanchez lideraba oficialmente, mientras algunos modelos proyectaban a Keiko.
El panel ahora muestra ambos conceptos por separado.

No volver a usar un titular de “ganador” sin indicar si es:

- oficial observado;
- escenario;
- proyeccion.

### Error 2: usar solo las filas del CSV como universo

El CSV tenia 91,076 filas, pero el universo era 92,766 mesas. Eso omitio 1,690
mesas no ingresadas y sesgo temporalmente la proyeccion.

Regla:

```text
universo = maestra completa
corte = informacion parcial que se une al universo
```

### Error 3: tratar JEE y no ingresadas como una sola cosa

Ahora se muestran y modelan por separado.

### Error 4: serie temporal dominada por los cortes iniciales

La serie de margenes del panel se limita a cortes desde 90% de avance para que
la fase decisiva sea legible. La serie de procesamiento conserva todos los
cortes.

### Error 5: el lanzador recalculaba en cada doble clic

El `.command` ya no ejecuta siempre los dos scripts. Primero consulta
`--needs-refresh`; si el caché y el HTML están vigentes, abre el archivo
existente directamente.

### Error 6: solapamiento y colores ambiguos

El gráfico de resultado por modelo tiene márgenes separados para nombres y
valores en escritorio, y una composición compacta en móvil. Naranja y verde
quedan reservados para Keiko y Sánchez. MAE, RMSE, JEE e identidad de modelos
usan colores no electorales.

## Ideas para siguientes incrementos

Estas mejoras son compatibles con el diseño actual:

1. selector para alternar mesas, electores y votos pendientes;
2. tabla o grafico por tipo de observacion JEE;
3. mapa geografico si se valida el cruce de coordenadas;
4. comparacion Peru versus extranjero;
5. alertas de cambios entre el ultimo corte y el anterior;
6. contribucion territorial esperada al margen final;
7. intervalos por modelo;
8. historial de pesos del ensamble;
9. boton para descargar la tabla filtrada;
10. selector de corte historico;
11. marcas verticales para hitos de procesamiento;
12. panel de calidad de datos y cobertura del cruce ODPE.

Agregar estas funciones una por una, preservando el panel existente.

## Regla para trabajo futuro

Al terminar una modificacion, actualizar este documento si cambia:

- una definicion;
- un denominador;
- una fuente;
- un modelo;
- una cifra documentada;
- un archivo generado;
- una regla del diseño;
- el procedimiento de ejecucion.

Este documento es el punto de entrada recomendado para cualquier agente nuevo.
