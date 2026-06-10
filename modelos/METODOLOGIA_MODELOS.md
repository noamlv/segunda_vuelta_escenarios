# Modelos de proyeccion electoral

## Pregunta

Estimar el resultado final entre Fuerza Popular (Keiko Fujimori) y Juntos por
el Peru (Sanchez) usando los cortes acumulados de ONPE y el universo de mesas
de la segunda vuelta.

## Unidad y denominador

- Unidad: mesa de sufragio.
- Votos validos: Fuerza Popular + Juntos por el Peru.
- Acta contabilizada: `ESTADO DEL ACTA = Contabilizada`.
- Pendiente: acta ausente del corte, no procesada o enviada al JEE.
- El porcentaje de cada candidato se calcula sobre votos validos, no sobre
  electores habiles ni votos emitidos.

## Modelos activos

1. **Resultado observado.** Solo resume los votos ya contabilizados.
2. **Arrastre nacional.** Imputa a lo pendiente la participacion y el reparto
   nacional observado. Es la referencia mas simple y supone ingreso aleatorio.
3. **Jerarquico territorial.** Estima participacion valida y preferencia por
   mesa usando ambito, departamento/continente, provincia/pais y
   distrito/ciudad. Los grupos pequenos se contraen hacia su nivel superior.
4. **ODPE ponderado.** Repite la logica de contraccion dentro de cada ODPE.
5. **JEE reportado + faltantes territoriales.** Suma los votos ya digitados de
   las actas enviadas al JEE y proyecta las mesas que todavia no aparecen en el
   extracto mediante el modelo jerarquico territorial. Es un escenario de
   admision, no una prediccion sobre la decision juridica.
6. **Ensamble.** Combina los modelos 2 a 4 con pesos inversamente
   proporcionales a su error absoluto en cortes historicos desde 60% de avance.
7. **Simulacion.** Sortea entre los modelos segun esos pesos, introduce
   dispersion beta en el voto pendiente y agrega un termino de calibracion
   derivado de los errores retrospectivos recientes.

## Backtesting

Para cada corte historico se ocultan las mesas que aun no estaban
contabilizadas y se intenta reconstruir el ultimo corte disponible. El error se
mide en puntos porcentuales de la cuota de Fuerza Popular sobre votos validos.

Este ejercicio permite comparar modelos, pero su objetivo sigue siendo un corte
provisional. Debe repetirse con cada CSV nuevo y, cuando exista, con el resultado
final certificado.

## Interpretacion de probabilidades

La probabilidad de victoria es condicional al conjunto de modelos. No es una
probabilidad juridica de que un acta observada sea validada, anulada o
modificada. El mecanismo de resolucion del JEE puede producir errores mayores
que los observados durante el procesamiento ordinario.

## Ejecucion

Desde la raiz de esta carpeta:

```bash
python3 modelos/oraculo_onpe.py
```

Los productos se escriben en `modelos/salidas/`, incluido
`reporte_oraculo_onpe.html`.
