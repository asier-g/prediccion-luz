# Viabilidad: Previsión del precio de la luz a 7 días

_Investigado: 2026-10-11_

## Competidores y alternativas

| Nombre | Qué hace | Precio | Puntos débiles | Fuente |
|---|---|---|---|---|
| **EpexPredictor** (código abierto) | LightGBM con meteorología de Open-Meteo, previsión de carga y gas. Cubre **España y Portugal**, a 1–3 días, con API pública y MAE publicado | Gratis (BSD-3) | Hasta 3 días. En evcc aún sin España. Sin complemento de Home Assistant. Error publicado con meteorología real (optimista) | [F10][F11] |
| Energy Price Forecast EU | Previsión a 48 h gratis y a 120 h de pago, integrada en Home Assistant (HACS) y evcc | Gratis 48 h; Pro 20 € el primer año | **Sin España** ("resto de la UE en preparación") | [F6][F7] |
| Energyforecast.de | Previsión para Alemania a 2, 6 y 12 días | Gratis 2 días; de pago a 6 y 12 | Solo Alemania; solo cobra a partir de 2 días | [F8][F9] |
| AleaSoft | Previsiones del MIBEL para empresas (240 h, meses y años) | De pago, a empresas (**SIN VERIFICAR**) | No es para particulares | [F12] |
| Integraciones OMIE y PVPC (Home Assistant, evcc), tarifaluzhora, apps | Precios publicados de hoy y mañana | Gratis | Nada más allá de mañana; tarifaluzhora dice que predecirlo "es imposible" | [F3][F4][F5][F14][F27] |
| App Grupo OMI | Futuros de OMIP (mes, trimestre, año) | Gratis | Nivel medio, no la forma horaria ni la semana | [F13] |
| Reglas caseras | "Cargar de madrugada", "el fin de semana es más barato", "las horas de sol" | Gratis | Ver el experimento: a veces aciertan tanto como un modelo | [F5] |

**Búsquedas realizadas:**
- "previsión precio luz PVPC próximos 7 días predicción España web"
- "previsión precio electricidad España próximos días web predicción OMIE semana AleaSoft gratis"
- "Spain electricity price forecast app 7 days ahead OMIE prediction consumers EV charging"
- "Home Assistant Spain electricity price forecast next days integration OMIE prediction"
- "Home Assistant HACS electricity price forecast integration Germany machine learning next days EPEX prediction"
- "energypriceforecast.eu Spain ES bidding zone forecast day-ahead price"
- "community.home-assistant.io PVPC price forecast tomorrow day after Spain prediction"
- "evcc GitHub Spain OMIE price forecast beyond tomorrow feature request planner"
- "EpexPredictor github day-ahead price prediction Open-Meteo countries evcc"

**Conclusión sobre la competencia:** el hueco "nadie prevé el precio en España más allá de mañana" **ya no existe del todo**. EpexPredictor lo cubre gratis a 1–3 días. Lo que queda libre es:
- el horizonte de 4 a 7 días;
- previsiones probabilísticas, con rango de incertidumbre;
- el paso del precio mayorista al precio final que paga cada tarifa (PVPC o indexada);
- un complemento nativo de Home Assistant en español;
- una validación honesta y pública del error.

> **Nota del 2026-10-12:** la API de EpexPredictor sirve para España unos 7 días (hasta D+7), no 1–3. El error que publica sigue siendo solo a 1–3 días, así que el horizonte de 4 a 7 días no está libre, pero no se sabe si su previsión ahí es buena. Lo dirá la comparación de la tarea 3.4.

## Viabilidad técnica

**Experimento propio** (detalle en [experimento/](experimento/README.md)): un año de prueba sin tocar (oct. 2025 – oct. 2026), previendo cada hora de D+2 a D+7 solo con la información disponible el día D.
- **El ML gana a las reglas obvias, pero solo con meteorología prevista:**
  - el gradient boosting o una red neuronal pequeña bajan el error un 15–16 % frente a la mejor regla (media de 7 días): −4 €/MWh, IC 95 % [−5,3, −2,7];
  - sin meteorología, el modelo es *peor* que la regla.
- **La red neuronal y el gradient boosting empatan:** el valor está en los datos (viento, sol), no en un modelo más profundo.
- **En decisiones reales:**
  - elegir las 4 horas más baratas del día ahorra 1,9 €/MWh frente a la regla "de 13 a 17 h";
  - elegir el día más barato de la semana ahorra 2,5 €/MWh frente a "el domingo".

  Las dos diferencias son significativas, pero pequeñas.
- **Potencia de cálculo:**
  - todo el experimento tarda unos 3 minutos en un portátil i5 sin GPU;
  - en producción basta con reentrenar una vez al mes y prever una vez al día;
  - cabe en un servidor gratuito o en GitHub Actions.

**Stack probable:**
- Python con LightGBM o PyTorch (N-HiTS) para aprender deep learning de verdad.
- Datos: OMIE, ESIOS (previsiones de demanda, eólica y solar de Red Eléctrica) y Open-Meteo.
- Previsión diaria en GitHub Actions o un VPS pequeño.
- API (FastAPI) y web con la previsión y el error real acumulado.
- Integración HACS para Home Assistant y plantilla para evcc.

**Partes difíciles:**
- **Superar a EpexPredictor** en sus 1–3 días: ya usa LightGBM con meteorología, carga y gas [F10].
- **Previsión probabilística bien calibrada** (cuantiles 10–90 %).
- **Pasar del precio mayorista al precio final** de cada tarifa: PVPC con su 55 % a plazo [F16], o la fórmula de Octopus o Som Energia [F18][F19].
- **Cambios del mercado:** el paso a cuartos de hora en 2025 ya obliga a adaptar los datos.

**Datos y APIs:**
- OMIE: ficheros públicos y gratuitos [F23]; sus condiciones de reutilización no se pudieron leer (**SIN VERIFICAR**).
- ESIOS: token personal gratuito [F4].
- Open-Meteo: gratis solo sin uso comercial; 29 $/mes en plan comercial [F21][F22].

## Aspectos legales y regulatorios

- **Responsabilidad:** es una previsión orientativa. Hay que avisar de que no es el precio oficial y publicar el error real.
- **Licencias:**
  - Open-Meteo pide atribución (CC BY 4.0) y prohíbe el uso comercial en su API gratuita [F21];
  - condiciones de reutilización de OMIE: **SIN VERIFICAR**.
- **Datos personales:** no hay; la previsión es la misma para todos.

## MVP

- **Qué incluye:**
  - previsión horaria de D+2 a D+7 con cuantiles;
  - web pública con la previsión y su error frente a la realidad, actualizado cada día;
  - API JSON;
  - sensor de Home Assistant (HACS) y plantilla de evcc.
- **Qué queda fuera:**
  - precio final por tarifa (se añade después);
  - optimizador de cargas;
  - cuentas de usuario.
- **Esfuerzo estimado:** 6–8 semanas a 5 h/semana. El modelo base ya existe (este experimento). Lo nuevo es el canal diario, la API, la web y la integración.

## Razones por las que esto podría fallar

1. **Ya existe gratis lo más útil.** EpexPredictor cubre España a 1–3 días con API pública [F10], y el precio de mañana es oficial. Lo que queda (4–7 días) es lo que menos valor práctico tiene.
2. **El ahorro para un hogar es de pocos euros al año** (ver `03-mercado-y-monetizacion.md`). La gran ganancia, cargar a mediodía en lugar de de madrugada, la da una regla gratuita.
3. **El PVPC suaviza la señal:** desde 2026 solo el 45 % de la energía sigue el mercado diario [F16][F17][F29]. El público que más se beneficia, el de tarifa indexada, es pequeño [F20].
4. **Mercado pequeño:** unas 19.000 instalaciones de Home Assistant en España que envían datos, frente a 134.000 en Alemania [F1].
5. **Riesgo de que llegue un competidor mejor:** Energy Price Forecast EU tiene "el resto de la UE en preparación" [F6].
6. **Dependencia de datos de terceros:** cambios de formato (cuartohorario), condiciones de OMIE, licencia comercial de Open-Meteo.

## Cómo validarlo barato

1. **Ya hecho:** el backtest muestra que el ML con meteorología bate a las reglas, con un margen pequeño pero significativo.
2. **Comparar con EpexPredictor (1 semana):** guardar cada día su previsión para España (API pública) junto a la propia y comparar el MAE en D+2 y D+3. Si no se le gana, el producto debe centrarse en lo que no hace: 4–7 días, cuantiles, precio final por tarifa e integración en español.
3. **Demanda (2 semanas):** publicar el experimento como artículo y la previsión diaria en una web sencilla, con enlace en el foro de Home Assistant, en evcc y en foros españoles. Contar visitas, estrellas e instalaciones. Más de 100 usuarios recurrentes sería una buena señal.
