# Reporte del panel

Escenario simulado para demo. Agricultores sintéticos de nvidia/Nemotron-Personas-El-Salvador.

- Personas por departamento: 20
- Semilla: 42
- Filas: 280 de 280 pedidas
- Escala inferida por regex en professional_persona y persona (escala_inferida=True; señal en escala_senal).
- nombre_display extraído del texto: 279; generado: 1.

## Cobertura por departamento

| Departamento | n | principal | ampliación | faltantes |
|---|---|---|---|---|
| Ahuachapán | 20 | 20 | 0 | 0 |
| Cabañas | 20 | 20 | 0 | 0 |
| Chalatenango | 20 | 20 | 0 | 0 |
| Cuscatlán | 20 | 20 | 0 | 0 |
| La Libertad | 20 | 20 | 0 | 0 |
| La Paz | 20 | 20 | 0 | 0 |
| La Unión | 20 | 20 | 0 | 0 |
| Morazán | 20 | 20 | 0 | 0 |
| San Miguel | 20 | 20 | 0 | 0 |
| San Salvador | 20 | 20 | 0 | 0 |
| San Vicente | 20 | 20 | 0 | 0 |
| Santa Ana | 20 | 20 | 0 | 0 |
| Sonsonate | 20 | 20 | 0 | 0 |
| Usulután | 20 | 20 | 0 | 0 |

## Trabajadores contratados excluidos

Se excluyen quienes trabajan como asalariados (empleado/a de finca, jornalero, peón, etc.) sin indicar parcela propia. `elegibles` es el universo del regex principal tras la exclusión.

| Departamento | elegibles | excluidos (principal) | excluidos (ampliación) |
|---|---|---|---|
| Ahuachapán | 815 | 61 | 2 |
| Cabañas | 371 | 28 | 5 |
| Chalatenango | 490 | 17 | 3 |
| Cuscatlán | 574 | 39 | 1 |
| La Libertad | 1657 | 218 | 6 |
| La Paz | 711 | 72 | 7 |
| La Unión | 597 | 28 | 5 |
| Morazán | 479 | 32 | 3 |
| San Miguel | 1060 | 77 | 3 |
| San Salvador | 2799 | 465 | 3 |
| San Vicente | 400 | 27 | 6 |
| Santa Ana | 1221 | 119 | 4 |
| Sonsonate | 1084 | 98 | 6 |
| Usulután | 847 | 55 | 6 |
| Total | 13105 | 1336 | 60 |

## Faltantes y ampliaciones

Sin faltantes ni ampliaciones.

## Departamento x banda de edad

| Departamento | 18-34 | 35-54 | 55+ | Total |
|---|---|---|---|---|
| Ahuachapán | 6 | 8 | 6 | 20 |
| Cabañas | 6 | 6 | 8 | 20 |
| Chalatenango | 8 | 4 | 8 | 20 |
| Cuscatlán | 7 | 8 | 5 | 20 |
| La Libertad | 6 | 8 | 6 | 20 |
| La Paz | 7 | 7 | 6 | 20 |
| La Unión | 6 | 6 | 8 | 20 |
| Morazán | 6 | 8 | 6 | 20 |
| San Miguel | 7 | 7 | 6 | 20 |
| San Salvador | 6 | 7 | 7 | 20 |
| San Vicente | 7 | 7 | 6 | 20 |
| Santa Ana | 6 | 9 | 5 | 20 |
| Sonsonate | 7 | 7 | 6 | 20 |
| Usulután | 7 | 7 | 6 | 20 |
| Total | 92 | 99 | 89 | 280 |

## Departamento x escolaridad

| Departamento | basica | media | superior | Total |
|---|---|---|---|---|
| Ahuachapán | 7 | 9 | 4 | 20 |
| Cabañas | 10 | 5 | 5 | 20 |
| Chalatenango | 6 | 8 | 6 | 20 |
| Cuscatlán | 7 | 6 | 7 | 20 |
| La Libertad | 9 | 7 | 4 | 20 |
| La Paz | 7 | 6 | 7 | 20 |
| La Unión | 8 | 8 | 4 | 20 |
| Morazán | 6 | 7 | 7 | 20 |
| San Miguel | 6 | 8 | 6 | 20 |
| San Salvador | 9 | 6 | 5 | 20 |
| San Vicente | 5 | 7 | 8 | 20 |
| Santa Ana | 6 | 5 | 9 | 20 |
| Sonsonate | 4 | 5 | 11 | 20 |
| Usulután | 7 | 6 | 7 | 20 |
| Total | 97 | 93 | 90 | 280 |

## Departamento x cultivo principal

| Departamento | cafe | cana | granos_basicos | hortalizas | mixto | Total |
|---|---|---|---|---|---|---|
| Ahuachapán | 2 | 1 | 14 | 1 | 2 | 20 |
| Cabañas | 1 | 1 | 15 | 1 | 2 | 20 |
| Chalatenango | 2 | 0 | 15 | 1 | 2 | 20 |
| Cuscatlán | 2 | 1 | 14 | 1 | 2 | 20 |
| La Libertad | 4 | 1 | 12 | 1 | 2 | 20 |
| La Paz | 2 | 1 | 13 | 1 | 3 | 20 |
| La Unión | 1 | 1 | 14 | 2 | 2 | 20 |
| Morazán | 1 | 1 | 15 | 1 | 2 | 20 |
| San Miguel | 2 | 1 | 14 | 1 | 2 | 20 |
| San Salvador | 3 | 1 | 12 | 2 | 2 | 20 |
| San Vicente | 1 | 1 | 15 | 1 | 2 | 20 |
| Santa Ana | 3 | 1 | 13 | 1 | 2 | 20 |
| Sonsonate | 2 | 1 | 13 | 1 | 3 | 20 |
| Usulután | 2 | 1 | 14 | 1 | 2 | 20 |
| Total | 28 | 13 | 193 | 16 | 30 | 280 |

## Departamento x escala

| Departamento | mediano | pequeño | subsistencia | Total |
|---|---|---|---|---|
| Ahuachapán | 1 | 9 | 10 | 20 |
| Cabañas | 0 | 11 | 9 | 20 |
| Chalatenango | 1 | 9 | 10 | 20 |
| Cuscatlán | 0 | 10 | 10 | 20 |
| La Libertad | 0 | 8 | 12 | 20 |
| La Paz | 2 | 9 | 9 | 20 |
| La Unión | 2 | 8 | 10 | 20 |
| Morazán | 1 | 7 | 12 | 20 |
| San Miguel | 2 | 9 | 9 | 20 |
| San Salvador | 0 | 10 | 10 | 20 |
| San Vicente | 1 | 9 | 10 | 20 |
| Santa Ana | 0 | 10 | 10 | 20 |
| Sonsonate | 1 | 7 | 12 | 20 |
| Usulután | 3 | 9 | 8 | 20 |
| Total | 14 | 125 | 141 | 280 |
