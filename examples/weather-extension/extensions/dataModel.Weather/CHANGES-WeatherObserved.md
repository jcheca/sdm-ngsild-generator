# Proposed extension of WeatherObserved (dataModel.Weather)

- Model: `dataModel.Weather/WeatherObserved`
- Version: `0.3.4` → `0.4.0` (minor: new optional attributes, backwards compatible)
- Reason: Agro-meteorological stations publish reference evapotranspiration and leaf wetness together with the usual weather variables; both are needed for irrigation scheduling and plant disease warnings

## Added attributes

| Attribute | NGSI type | Type | Units | Origin | Description |
|---|---|---|---|---|---|
| `referenceEvapotranspiration` | Property | number | MMT | new | Reference crop evapotranspiration (ET0) accumulated over the observation period, computed with the FAO-56 Penman-Monteith method |
| `leafWetness` | Property | number | C62 | reused from `dataModel.Agrifood/AgriParcelRecord` | Leaf wetness measured by the station sensor, as a ratio between 0 (dry) and 1 (wet) |

All existing attributes, required fields and examples are unchanged; the new attributes have been added to the schema and to the four examples.

## Contributors

- Example Contributor
