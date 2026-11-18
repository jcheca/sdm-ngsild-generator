# Caso de referencia: extensión de WeatherObserved (v0.4.0)

Una red de estaciones agroclimáticas ya publica `WeatherObserved` (`dataModel.Weather`), pero necesita dos variables más:

- `referenceEvapotranspiration` (ET0, FAO-56; mm, `MMT`): **nueva**, no existe en el repositorio.
- `leafWetness` (0–1, `C62`): **reutilizada** de `dataModel.Agrifood/AgriParcelRecord`.

Resultado (`extensions/dataModel.Weather/`):
- `WeatherObserved/`: copia del modelo de GitHub con los dos atributos añadidos al schema y a los cuatro ejemplos. La versión pasa de `0.3.4` a `0.4.0` (minor, según `versioning.md`). Nada del original cambia.
- `CHANGES-WeatherObserved.md`: resumen en inglés para los mantenedores.
- `CONTRIBUTORS.yaml`.

La validación pasa sin errores ni avisos nuevos. El original ya tenía 10 problemas: ids no URN en los ejemplos v2, valores distintos entre ejemplos y un object sin `properties`. Aparecen como «(preexistente en el original)» y no bloquean la extensión.
