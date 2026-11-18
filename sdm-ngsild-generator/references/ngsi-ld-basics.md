# Fundamentos de NGSI-LD para la entrevista

Basado en `data-models/ngsi-ld_howto.md` y en los ejemplos de los modelos actuales del repositorio. Cada sección termina con una **explicación corta** para dársela al usuario cuando el concepto aparezca por primera vez. Profundiza solo si te lo pide.

## Entidad, Property, Relationship, GeoProperty

- **Entidad**: algo con identidad propia que se consulta y actualiza por sí mismo (una sonda, una parcela, un contenedor). Tiene `id` y `type`.
- **Property**: un dato de la entidad (temperatura, estado, nombre).
- **Relationship**: un enlace a otra entidad. Su valor (`object`) es la URN de la entidad destino.
- **GeoProperty**: posición o geometría en GeoJSON (`location` y otras).

> *Explicación corta:* «En NGSI-LD cada dato de la entidad es una Property, salvo los que apuntan a otra entidad, que son Relationship. La diferencia importa: con una Relationship el broker puede navegar de una entidad a otra; un texto con un identificador no se puede navegar».

**Criterio para decidir:** si el valor identifica a otra cosa que tiene (o podría tener) su propia entidad, es una Relationship. Por ejemplo, `refDevice` o `hasAgriParcel`. Si es un dato descriptivo, es una Property, aunque sea un código: `routeCode`.

## Identificadores

- Formato: `urn:ngsi-ld:<Type>:<identificador>`, por ejemplo `urn:ngsi-ld:SoilProbeObserved:probe-001`. Se usa también en los ejemplos NGSI v2.
- La URN ya indica el tipo de la entidad apuntada. Por eso NGSI-LD prefiere nombrar las relaciones con verbos (`hasStop`, `isPartOf`) en lugar del prefijo `ref` (ver `naming-and-descriptions.md`).

## El `@context`

- Asocia cada nombre corto (`soilTemperature`) a una URI única. Así, dos sistemas que usan el mismo término saben que significa lo mismo.
- En SDM cada subject publica su `context.jsonld`, que el repositorio genera automáticamente:
  `https://raw.githubusercontent.com/smart-data-models/<subject>/master/context.jsonld`.
- Key-values NGSI-LD: `"@context": [<contexto del subject>]`.
- Normalizado NGSI-LD: `"@context": ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld", <contexto del subject>]`.
- En un subject nuevo, la URL del contexto no existe hasta la publicación, y la prueba oficial lo señala. Es esperable.

> *Explicación corta:* «El `@context` es el diccionario que da significado a los nombres. Gracias a él, `temperature` en tu modelo y en otro del mismo subject significan exactamente lo mismo. No lo escribes tú: el repositorio lo genera a partir de tus schemas».

## Cuatro representaciones de la misma entidad

| | Key-values | Normalizado |
|---|---|---|
| **NGSI v2** (`.json`) | `"soilTemperature": 18.4` | `{"type": "Number", "value": 18.4, "metadata": {"unitCode": {...}, "timestamp": {...}}}` |
| **NGSI-LD** (`.jsonld`) | `"soilTemperature": 18.4` + `@context` | `{"type": "Property", "value": 18.4, "unitCode": "CEL", "observedAt": "..."}` |

Equivalencias v2 → LD (`ngsi-ld_howto.md`):
- atributo normal → `Property`;
- atributo `ref…` → `Relationship` con `object`;
- `geo:json` → `GeoProperty`;
- metadato `timestamp` → `observedAt`;
- metadato `unitCode` → subpropiedad `unitCode`;
- `DateTime` → valor `{"@type": "DateTime", "@value": "..."}`.

En NGSI v2 normalizado **no** se pueden usar los tipos `Property`, `Relationship` ni `GeoProperty` (lo comprueba la prueba oficial). Las relaciones van como `Text` y la geometría como `geo:json`.

> *Explicación corta:* «SDM pide los cuatro ejemplos para que el modelo sirva tanto en brokers NGSI v2 como NGSI-LD. Los genero yo a partir del mismo valor, así que siempre son coherentes».

## Propiedades de propiedades

En NGSI-LD no hay metadatos, sino propiedades anidadas dentro de una Property: `unitCode`, `observedAt`, o una propia como `measurementDepth`. Úsalas para datos que cualifican una medida concreta, no para datos de la entidad. En la práctica no se pasa de uno o dos niveles.

## Patrón dispositivo / observación

Cuando hay un aparato que mide y unas medidas que cambian con el tiempo:
- `Device` (dataModel.Device) describe el aparato: fabricante, batería, estado. Se reutiliza; no se crea uno nuevo.
- `XxxObserved` (como `AirQualityObserved` o `WaterQualityObserved`) contiene las medidas, con `dateObserved` y `refDevice` hacia el `Device`.

Son ciclos de vida distintos: el aparato cambia poco y las observaciones cambian continuamente. Por eso se separan.

> *Explicación corta:* «Separar el dispositivo de sus observaciones permite cambiar o recalibrar el sensor sin tocar el histórico, y reutilizar `Device`, que ya existe en SDM».
