# Nombres y descripciones

Normas de `data-models/specs/guidelines.md` y formato que exige `test_schema_descriptions` (`test_data_model`). Todo el contenido del modelo va en **inglés** (preferiblemente americano).

## Nombres

| Elemento | Regla | Ejemplo |
|---|---|---|
| Tipo de entidad | PascalCase, en singular | `WasteContainer`, `SoilProbeObserved` |
| Atributo | camelCase, ASCII, sin guiones ni subrayados | `soilTemperature` |
| Property | Sustantivo (no verbo), cualificado si hace falta | `totalSpotNumber`, `dateCreated` |
| Fecha | Prefijo `date` | `dateObserved`, `dateLastEmptying` |
| Relationship (nueva) | Verbo + objeto (recomendado en NGSI-LD) | `hasAgriParcel`, `isPartOf`, `operatedBy` |
| Relationship (heredada) | Prefijo `ref` + tipo destino (en cierto modo obsoleto; reutilízalo si ya existe) | `refDevice` |
| Lista | Sin plural; la descripción aclara que es una lista | `category` |
| Variante de idioma | `<atributo>_<etiqueta RFC 5646>` | `description_es` |

Antes de proponer un nombre:
1. Búscalo con `search.py attributes --exact <nombre>` y con términos sueltos. Si existe un atributo con el mismo significado, **usa ese nombre exacto**, aunque prefieras otro.
2. Si existen variantes incoherentes (por ejemplo, `temperature` con unidades distintas), elige la más extendida y avisa al usuario.
3. Explica la elección en una frase: «`soilMoistureVwc` y no `soilHumidity`, porque ya existe en AgriParcelRecord con el mismo significado».

Evita nombres ligados a un fabricante o a un proyecto (principio 4 del manifiesto).

## Formato de las descripciones

La prueba oficial parte la descripción por `". "` (punto y espacio) y exige:

- Que una de las partes sea **exactamente** el tipo NGSI: `Property`, `GeoProperty`, `Relationship`, `LanguageProperty` o `ListProperty`.
- Que las partes opcionales tengan la forma `Clave:'valor'` (con comillas simples y nada después): `Model:'…'`, `Units:'…'`, `Enum:'…'`, `Privacy:'…'`.
- Al menos 15 caracteres.
- Descripción también en los subatributos de los objects y en los `items` de los arrays.

Formato que produce `generate.py`:

```
Property. Model:'https://schema.org/Number'. Units:'degree Celsius (CEL)'. The observed soil temperature
Property. Model:'https://schema.org/Text'. Enum:'ok, lowBattery, fault'. Operational status of the probe
Relationship. Reference to the Device entity representing the soil probe
GeoProperty. Location of the rural reference weather station
```

En la especificación escribe **solo el texto** (`description: The observed soil temperature`). El script añade el tipo, el modelo, las unidades y la enumeración.

### Errores típicos que detecta el validador

| Incorrecto | Problema |
|---|---|
| `The observed soil temperature` | Falta el tipo NGSI |
| `Property . The observed…` | Tipo NGSI con caracteres de más |
| `Property. Units:CEL. …` | Falta la comilla simple |
| `Property. Model:'https://schema.org/Number. …` | Falta la comilla de cierre |

## Model (schema.org)

`Model:'…'` apunta al tipo o propiedad de schema.org que mejor describe el valor. Por defecto:

| Tipo JSON / formato | Model |
|---|---|
| string | `https://schema.org/Text` |
| string + `date-time` | `https://schema.org/DateTime` |
| string + `date` | `https://schema.org/Date` |
| string + `uri` | `https://schema.org/URL` |
| number | `https://schema.org/Number` |
| integer | `https://schema.org/Integer` |
| boolean | `https://schema.org/Boolean` |
| object | `https://schema.org/StructuredValue` |

Si schema.org tiene una propiedad con la misma semántica (por ejemplo `https://schema.org/address`), indícala en `model`.

## Textos del modelo

- `title`: «Smart Data Models - <Nombre legible>», al menos 15 caracteres.
- `description` de la entidad: al menos 50 caracteres. Explica qué representa y en qué contexto, sin mencionar al proyecto concreto.
- Descripción de un atributo: una frase que diga qué es y, si hace falta, cómo se mide. Sin punto final, porque el generador lo quita.
