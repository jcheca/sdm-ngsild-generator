# Unidades UN/CEFACT

Referencia de consulta para la fase 4 (atributos). Fuentes: `data-models/specs/guidelines.md` y `specs/howto.md` del repositorio smart-data-models, y la Recomendación 20 de UNECE, incluida en `scripts/data/uncefact_units.json`.

## Reglas SDM

- Cada magnitud tiene una **unidad por defecto**, normalmente la del Sistema Internacional. Se documenta en la descripción del atributo (`Units:'…'`).
- Si un dato llega en otra unidad, se indica con `unitCode`:
  - NGSI v2: metadato `"metadata": {"unitCode": {"type": "Text", "value": "CEL"}}`.
  - NGSI-LD: subpropiedad `"unitCode": "CEL"` dentro de la Property.
- Los códigos son los de **UN/CEFACT Rec. 20**, no los símbolos (`CEL`, no `°C`).
- Las cantidades relativas (humedad relativa, probabilidad, fracción) van de `0` a `1`, con `minimum: 0` y `maximum: 1`. Su unidad es `C62` (*one*), no `P1` (*percent*).

En la propuesta, cada atributo lleva `units: <código>` y, opcionalmente, `unitsText: <nombre en inglés>`. El generador compone `Units:'degree Celsius (CEL)'` y añade `unitCode` a los ejemplos normalizados. El validador comprueba que el código existe y que coincide en el schema y en los ejemplos.

## Cómo buscar un código

No escribas códigos de memoria: hay trampas. Compruébalos siempre:

```bash
python scripts/search.py units litre per second    # por nombre en inglés
python scripts/search.py units --code A97          # comprobar un código
```

Trampas verificadas en la Rec. 20:

| Parece… | Pero es | Correcto |
|---|---|---|
| `HPA` = hectopascal | hectolitre of pure alcohol | `A97` |
| `KJ` = kilojoule | kilosegment | `KJO` |
| `HAR` = hectare | obsoleto en la Rec. 20 | `HAR` sigue existiendo, pero el validador avisa; valora usar `MTK` (m²) |
| `P1` para humedad relativa 0–1 | percent (0–100) | `C62` si el valor va de 0 a 1 |

## Códigos frecuentes (todos vigentes)

### Temperatura

| Código | Unidad | Símbolo |
|---|---|---|
| `CEL` | degree Celsius | °C |
| `KEL` | kelvin | K |
| `FAH` | degree Fahrenheit | °F |

### Longitud, superficie y volumen

| Código | Unidad | Símbolo |
|---|---|---|
| `MMT` | millimetre | mm |
| `CMT` | centimetre | cm |
| `MTR` | metre | m |
| `KMT` | kilometre | km |
| `4H` | micrometre (micron) | µm |
| `MTK` | square metre | m² |
| `MTQ` | cubic metre | m³ |
| `LTR` | litre | l |
| `MLT` | millilitre | ml |

### Masa y concentración

| Código | Unidad | Símbolo |
|---|---|---|
| `GRM` | gram | g |
| `KGM` | kilogram | kg |
| `TNE` | tonne (metric ton) | t |
| `MGM` | milligram | mg |
| `GQ` | microgram per cubic metre | µg/m³ |
| `GP` | milligram per cubic metre | mg/m³ |
| `A93` | gram per cubic metre | g/m³ |
| `M1` | milligram per litre | mg/l |
| `GL` | gram per litre | g/l |
| `KMQ` | kilogram per cubic metre | kg/m³ |
| `59` | part per million | ppm |
| `61` | part per billion (US) | ppb |
| `M33` | millimole per litre | mmol/l |

### Tiempo y frecuencia

| Código | Unidad | Símbolo |
|---|---|---|
| `SEC` | second [unit of time] | s |
| `MIN` | minute [unit of time] | min |
| `HUR` | hour | h |
| `DAY` | day | d |
| `WEE` | week | wk |
| `MON` | month | mo |
| `ANN` | year | y |
| `HTZ` | hertz | Hz |
| `KHZ` | kilohertz | kHz |
| `RPM` | revolutions per minute | r/min |

### Velocidad, caudal y aceleración

| Código | Unidad | Símbolo |
|---|---|---|
| `MTS` | metre per second | m/s |
| `KMH` | kilometre per hour | km/h |
| `KNT` | knot | kn |
| `C16` | millimetre per second | mm/s |
| `H67` | millimetre per hour | mm/h |
| `MSK` | metre per second squared | m/s² |
| `G51` | litre per second | l/s |
| `L2` | litre per minute | l/min |
| `E32` | litre per hour | l/h |
| `MQH` | cubic metre per hour | m³/h |
| `MQS` | cubic metre per second | m³/s |
| `G52` | cubic metre per day | m³/d |

### Presión

| Código | Unidad | Símbolo |
|---|---|---|
| `PAL` | pascal | Pa |
| `A97` | hectopascal | hPa |
| `KPA` | kilopascal | kPa |
| `BAR` | bar [unit of pressure] | bar |
| `MBR` | millibar | mbar |

### Energía y electricidad

| Código | Unidad | Símbolo |
|---|---|---|
| `WTT` | watt | W |
| `KWT` | kilowatt | kW |
| `MAW` | megawatt | MW |
| `C31` | milliwatt | mW |
| `JOU` | joule | J |
| `KJO` | kilojoule | kJ |
| `3B` | megajoule | MJ |
| `KWH` | kilowatt hour | kW·h |
| `MWH` | megawatt hour (1000 kW.h) | MW·h |
| `VLT` | volt | V |
| `AMP` | ampere | A |
| `4K` | milliampere | mA |
| `OHM` | ohm | Ω |
| `D46` | volt - ampere | V·A |
| `KVA` | kilovolt - ampere | kV·A |
| `KVR` | kilovar | kvar |
| `D10` | siemens per metre | S/m |
| `H61` | millisiemens per centimetre | mS/cm |
| `G42` | microsiemens per centimetre | µS/cm |
| `E46` | kilowatt hour per cubic metre | kW·h/m³ |

### Luz, sonido, ángulo y radiación

| Código | Unidad | Símbolo |
|---|---|---|
| `LUX` | lux | lx |
| `CDL` | candela | cd |
| `2N` | decibel | dB |
| `DD` | degree [unit of angle] | ° |
| `C81` | radian | rad |
| `D54` | watt per square metre | W/m² |

### Adimensionales y recuentos

| Código | Unidad | Símbolo |
|---|---|---|
| `P1` | percent | % or pct |
| `C62` | one | 1 |
| `H87` | piece |  |
| `NTU` | Nephelometric turbidity unit | NTU |

### Datos

| Código | Unidad | Símbolo |
|---|---|---|
| `AD` | byte | byte |
| `4L` | megabyte | Mbyte |
| `C74` | kilobit per second | kbit/s |
| `E20` | megabit per second | Mbit/s |
