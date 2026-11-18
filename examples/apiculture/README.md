# Caso de referencia: familia apícola en un subject nuevo (v0.4.0)

Caso de cierre de la v0.4.0: varias entidades relacionadas en un subject nuevo, enlazadas con modelos existentes. Se regenera y valida en `tests/test_v04_proposals.py`.

```
HoneyHarvest ──hasBeehive (1..n)──▶ Beehive ──hasApiary──▶ Apiary ──hasAgriParcel──▶ AgriParcel (Agrifood)
     └────────────hasApiary──────────────────────────────────▲      Beehive ──refDevice──▶ Device (Device)
```

| Entidad | Ciclo de vida | Por qué es una entidad aparte |
|---|---|---|
| `Apiary` | Casi estático (registro, capacidad, flora) | Lo referencian las colmenas y las cosechas |
| `Beehive` | Medidas cada 15 min | Su estado cambia continuamente; se mueve entre colmenares |
| `HoneyHarvest` | Evento puntual | Trazabilidad del lote de miel hasta sus colmenas |

**Subject nuevo `dataModel.Apiculture`** (dominio SmartAgrifood): hay una familia de tres modelos de un ámbito sin sitio natural. El precedente es `dataModel.Aquaculture`, separado de `dataModel.Agrifood`. Los modelos de Agrifood se reutilizan mediante relaciones (`AgriParcel`) y atributos (`legalId`, `weight`, `species`…).

**Reutilización:** 12 de los 23 atributos proceden del repositorio, cada uno con su `reusedFrom`. Los nuevos siguen las normas de nombres (`dateHarvested`, `hasApiary`, `moistureContent` entre 0 y 1).

**Validación** (`validate.py examples/apiculture --spec examples/apiculture/proposal.yaml --check-urls`):
- Sin errores.
- Avisos esperados: `derivedFrom` vacío y el `@context` de `dataModel.Apiculture`, que no existe hasta que se publique.
- Comprobaciones del conjunto: los 5 destinos de las relaciones existen (3 en la propuesta y 2 en el repositorio), y los ejemplos están enlazados entre sí por sus `id`.

`examples/beehive/` es la versión de una sola entidad en `dataModel.Agrifood` (v0.3.0). Este caso la amplía al pasar a una familia de modelos.
