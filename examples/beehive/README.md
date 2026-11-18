# Caso de referencia: Beehive (apicultura de precisión)

Recorrido de las siete fases de la entrevista con los scripts reales del repositorio smart-data-models (índices de noviembre de 2026). Es el caso de cierre de la v0.3.0 y se regenera y valida en `tests/test_e2e_beehive.py`.

- `proposal.yaml`: especificación con el caso de uso, las decisiones y la trazabilidad.
- `contribution/`: salida de `generate.py`. Pasa `validate.py` con un único aviso, `derivedFrom` vacío, normal en un modelo nuevo.

## 1 · Contexto

Una báscula con sensores bajo cada colmena envía cada 15 minutos peso, temperatura y humedad internas, nivel y frecuencia dominante del sonido, y recuento de abejas en la piquera. Los datos los consumen la app del apicultor (alertas de enjambrazón, pérdida de reina, robo) y la plataforma de la cooperativa. Dominio: SmartAgrifood.

## 2 · Búsqueda de lo existente

| Consulta | Resultado |
|---|---|
| `search.py models beehive` · `hive` · `apiary` · `apiculture` · `bee` · `honey` · `pollinator` | Sin modelos de apicultura |
| `search.py subjects --domain SmartAgrifood` | `dataModel.Agrifood` (Animal, AgriParcel…), `dataModel.Aquaculture` |
| `fetch_schema.py Agrifood/Animal FishContainment WasteContainer` | Revisados y descartados (motivos en `decisions`) |

Decisión: **crear** `Beehive` en el subject existente `dataModel.Agrifood`.

## 3 · Estructura

Una sola entidad con los datos estáticos de la colmena y las últimas medidas, como hacen `WasteContainer` o `Streetlight` (manifiesto, principio 5: plano, no profundo). La báscula es un `Device`, que ya existe, y se enlaza con `refDevice`.

## 4 · Atributos (modo lista completa)

`search.py batch` con 18 conceptos. Resultado tras el criterio de Claude:

| Concepto | Atributo | Origen |
|---|---|---|
| hive weight | `weight` (KGM) | reutilizado (Animal y 13 modelos más) |
| internal temperature | `temperature` (CEL) | reutilizado |
| relative humidity | `relativeHumidity` (0–1, C62) | reutilizado |
| hive type | `category` (enum) | reutilizado; la guía lo cita entre los más usados |
| colony status | `status` (enum) | reutilizado |
| species | `species` | reutilizado (Animal) |
| sound level | `soundPressureLevel` (2N) | nuevo; `noiseLevel` describe el sonido emitido por un dispositivo (justificado) |
| dominant frequency | `dominantSoundFrequency` (HTZ) | nuevo |
| bees in/out | `beeEntranceCount`, `beeExitCount` | nuevos (patrón de `vehicleEntranceCount`) |
| frames, queen, inspection | `frameCount`, `queenBirthYear`, `dateLastInspection` | nuevos |
| battery level | — | descartado: pertenece al `Device` |

Obligatorios: solo `id` y `type`.

## 5 · Relaciones

`refDevice` → `Device` (reutilizada; aparece en 33 modelos) y `hasAgriParcel` → `AgriParcel` (reutilizada). `hasAgriFarm` se descarta porque no existe en el repositorio y la granja se alcanza a través de la parcela.

## 6 · Metadatos

CC BY 4.0, un contribuidor de ejemplo y una nota para el README.

## 7 · Generación y validación

```bash
python scripts/generate.py examples/beehive/proposal.yaml --out examples/beehive
python scripts/validate.py examples/beehive --spec examples/beehive/proposal.yaml --check-urls
```

Resultado: 19 comprobaciones superadas y 1 aviso (`derivedFrom`).

La propia validación detectó, durante el recorrido, cuatro atributos marcados como reutilizados sin `reusedFrom`. Se corrigieron en `proposal.yaml` y se añadió esa regla al validador.
