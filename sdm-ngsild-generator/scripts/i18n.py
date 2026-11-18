"""Textos del visor, del informe y de la previsualización en el idioma del usuario.

Incluye español (``es``) e inglés (``en``). Para otro idioma, Claude puede traducir el
catálogo inglés y pasarlo con ``--strings fichero.json``::

    python i18n.py export en > strings-en.json      # plantilla para traducir

Las claves que falten en un catálogo se toman del inglés.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # visor
        "viewer_title": "Smart Data Models proposal",
        "viewer_intro": "Interactive summary of the proposal. Technical names stay in English, as Smart Data Models requires; a translation is shown next to them when available.",
        "diagram": "Entities and relationships",
        "diagram_legend_new": "New entity in this proposal",
        "diagram_legend_ext": "Existing model extended by this proposal",
        "diagram_legend_ref": "Existing model referenced",
        "attributes": "Attributes",
        "attribute": "Attribute",
        "model": "Model",
        "kind": "Kind",
        "translation": "Translation",
        "ngsi_type": "NGSI type",
        "json_type": "Type",
        "units": "Units",
        "origin": "Origin",
        "description": "Description",
        "origin_new": "New",
        "origin_reused": "Reused",
        "origin_commons": "Commons",
        "origin_original": "Original model",
        "origin_added": "Added (extension)",
        "examples": "Examples: NGSI v2 and NGSI-LD side by side",
        "keyvalues": "key-values",
        "normalized": "normalized",
        "concepts": "Concepts used in this proposal",
        "subject": "Subject",
        "new_subject": "new subject",
        "existing_subject": "existing subject",
        "extension": "extension",
        "version": "Version",
        "domains": "Domains",
        "summary_counts": "{entities} new entities, {extensions} extensions, {reused} reused and {new} new attributes",
        "relationship_to": "points to",
        # informe
        "report_title": "Proposal report",
        "report_summary": "Summary",
        "report_validation": "Local validation",
        "report_broker": "Context broker test",
        "report_broker_not_run": "Not run. It is optional and only runs when requested with the URL of an NGSI-LD broker.",
        "report_decisions": "Decision log",
        "report_attributes": "Attributes and their origin",
        "report_contents": "Package contents",
        "report_next": "Next steps",
        "report_next_text": "The package is ready for you to decide whether to contribute it through the usual Smart Data Models process (see the contribution manual: https://bit.ly/contribution_manual). The skill never opens pull requests or writes to GitHub. The `preview/` folder is NOT part of the contribution.",
        "status_pass": "passed",
        "status_warn": "passed with warnings",
        "status_fail": "failed",
        "check": "Check",
        "result": "Result",
        "errors": "Errors",
        "warnings": "Warnings",
        "notes": "Notes",
        "preexisting": "Issues already present in the original model (not caused by the extension)",
        "item": "Item",
        "decision": "Decision",
        "reason": "Reason",
        "source": "Source",
        "dec_reused": "reused",
        "dec_extended": "extended",
        "dec_new": "new",
        "dec_discarded": "discarded",
        "proposal_checks": "Checks on the whole proposal",
        "generated_on": "Generated on",
        "indexes_date": "Repository indexes downloaded on",
        "contents_contribution": "new data models with the official structure (this is what is contributed)",
        "contents_extensions": "proposed new versions of existing models, with a change summary for maintainers",
        "contents_preview": "files that the repository generates automatically (model.yaml, spec.md, @context), for review only",
        "contents_viewer": "interactive summary for people, opens offline with a double click",
        "contents_report": "this report",
        "contents_proposal": "proposal specification used to generate everything (decision record)",
        "contents_broker": "detailed result of the context broker test",
        # previsualización
        "leeme": "PREVIEW ONLY - NOT PART OF THE CONTRIBUTION\n\nThese files approximate what the Smart Data Models repository generates automatically once a data model is published (model.yaml, doc/spec.md and the subject @context). They are included so you can review the result before contributing. Do NOT add them to a pull request: the repository regenerates them.\n\nFidelity: same structure, sections and content as the official generators (data-models/utils), not a byte-for-byte copy.\n",
        # conceptos
        "concept_Property": "Property: a data value of the entity (a measurement, a status, a name).",
        "concept_Relationship": "Relationship: a link to another entity, identified by its URN. A broker can navigate it, unlike a plain text identifier.",
        "concept_GeoProperty": "GeoProperty: a position or geometry in GeoJSON (location and similar).",
        "concept_context": "@context: the dictionary that maps each short name to a unique URI, so the same term means the same thing everywhere. The repository generates it from the schemas.",
        "concept_commons": "Commons: shared attribute sets (GSMA-Commons, Location-Commons...) that models reference instead of redefining.",
        "concept_units": "Units: magnitudes have a default unit; unitCode carries the UN/CEFACT code (e.g. CEL for degree Celsius).",
        "concept_observedAt": "observedAt: the time a value was measured (NGSI-LD); in NGSI v2 it is the timestamp metadata.",
        "concept_formats": "Four examples: NGSI v2 and NGSI-LD, each as key-values (just the values) and normalized (type, value and metadata).",
        "concept_urn": "URN identifiers: urn:ngsi-ld:<Type>:<id> identifies each entity and already conveys its type.",
        "concept_extension": "Extension: a new minor version of an existing model that only adds optional attributes, so existing data stay valid.",
        "concept_new_subject": "New subject: a new group of related models. Its @context URL will exist once published.",
    },
    "es": {
        "viewer_title": "Propuesta de Smart Data Models",
        "viewer_intro": "Resumen interactivo de la propuesta. Los nombres técnicos se mantienen en inglés, como exige Smart Data Models; junto a ellos aparece su traducción cuando está disponible.",
        "diagram": "Entidades y relaciones",
        "diagram_legend_new": "Entidad nueva de esta propuesta",
        "diagram_legend_ext": "Modelo existente que esta propuesta amplía",
        "diagram_legend_ref": "Modelo existente referenciado",
        "attributes": "Atributos",
        "attribute": "Atributo",
        "model": "Modelo",
        "kind": "Clase",
        "translation": "Traducción",
        "ngsi_type": "Tipo NGSI",
        "json_type": "Tipo",
        "units": "Unidades",
        "origin": "Origen",
        "description": "Descripción",
        "origin_new": "Nuevo",
        "origin_reused": "Reutilizado",
        "origin_commons": "Commons",
        "origin_original": "Modelo original",
        "origin_added": "Añadido (extensión)",
        "examples": "Ejemplos: NGSI v2 y NGSI-LD lado a lado",
        "keyvalues": "key-values",
        "normalized": "normalizado",
        "concepts": "Conceptos que aparecen en la propuesta",
        "subject": "Subject",
        "new_subject": "subject nuevo",
        "existing_subject": "subject existente",
        "extension": "extensión",
        "version": "Versión",
        "domains": "Dominios",
        "summary_counts": "{entities} entidades nuevas, {extensions} extensiones, {reused} atributos reutilizados y {new} nuevos",
        "relationship_to": "apunta a",
        "report_title": "Informe de la propuesta",
        "report_summary": "Resumen",
        "report_validation": "Validación local",
        "report_broker": "Prueba contra un context broker",
        "report_broker_not_run": "No ejecutada. Es opcional y solo se ejecuta si se pide indicando la URL de un broker NGSI-LD.",
        "report_decisions": "Registro de decisiones",
        "report_attributes": "Atributos y su origen",
        "report_contents": "Contenido del paquete",
        "report_next": "Siguientes pasos",
        "report_next_text": "El paquete está listo para que decidas si lo contribuyes por el procedimiento habitual de Smart Data Models (ver el manual de contribución: https://bit.ly/contribution_manual). La skill nunca abre pull requests ni escribe en GitHub. La carpeta `preview/` NO forma parte de la contribución.",
        "status_pass": "superada",
        "status_warn": "superada con avisos",
        "status_fail": "fallida",
        "check": "Comprobación",
        "result": "Resultado",
        "errors": "Errores",
        "warnings": "Avisos",
        "notes": "Notas",
        "preexisting": "Problemas que ya tenía el modelo original (no los causa la extensión)",
        "item": "Elemento",
        "decision": "Decisión",
        "reason": "Motivo",
        "source": "Procedencia",
        "dec_reused": "reutilizado",
        "dec_extended": "extendido",
        "dec_new": "nuevo",
        "dec_discarded": "descartado",
        "proposal_checks": "Comprobaciones del conjunto de la propuesta",
        "generated_on": "Generado el",
        "indexes_date": "Índices del repositorio descargados el",
        "contents_contribution": "modelos nuevos con la estructura oficial (es lo que se contribuye)",
        "contents_extensions": "nuevas versiones propuestas de modelos existentes, con un resumen de cambios para los mantenedores",
        "contents_preview": "ficheros que el repositorio genera automáticamente (model.yaml, spec.md, @context), solo para revisión",
        "contents_viewer": "resumen interactivo para personas; se abre sin conexión con doble clic",
        "contents_report": "este informe",
        "contents_proposal": "especificación de la propuesta con la que se ha generado todo (registro de decisiones)",
        "contents_broker": "resultado detallado de la prueba contra el context broker",
        "leeme": "SOLO PREVISUALIZACIÓN: NO FORMA PARTE DE LA CONTRIBUCIÓN\n\nEstos ficheros aproximan lo que el repositorio de Smart Data Models genera automáticamente cuando se publica un modelo (model.yaml, doc/spec.md y el @context del subject). Se incluyen para que puedas revisar el resultado antes de contribuir. NO los añadas a un pull request: el repositorio los regenera.\n\nFidelidad: misma estructura, secciones y contenido que los generadores oficiales (data-models/utils), no una copia byte a byte.\n",
        "concept_Property": "Property: un dato de la entidad (una medida, un estado, un nombre).",
        "concept_Relationship": "Relationship: un enlace a otra entidad, identificada por su URN. El broker puede navegarlo, a diferencia de un identificador en texto.",
        "concept_GeoProperty": "GeoProperty: una posición o geometría en GeoJSON (location y similares).",
        "concept_context": "@context: el diccionario que asocia cada nombre corto a una URI única, para que el mismo término signifique lo mismo en todas partes. Lo genera el repositorio a partir de los schemas.",
        "concept_commons": "Commons: conjuntos de atributos compartidos (GSMA-Commons, Location-Commons...) que los modelos referencian en lugar de redefinir.",
        "concept_units": "Unidades: cada magnitud tiene una unidad por defecto; unitCode lleva el código UN/CEFACT (p. ej. CEL para grados Celsius).",
        "concept_observedAt": "observedAt: el instante en que se midió un valor (NGSI-LD); en NGSI v2 es el metadato timestamp.",
        "concept_formats": "Cuatro ejemplos: NGSI v2 y NGSI-LD, cada uno en key-values (solo los valores) y normalizado (tipo, valor y metadatos).",
        "concept_urn": "Identificadores URN: urn:ngsi-ld:<Tipo>:<id> identifica cada entidad y ya indica su tipo.",
        "concept_extension": "Extensión: una nueva versión minor de un modelo existente que solo añade atributos opcionales, para que los datos existentes sigan siendo válidos.",
        "concept_new_subject": "Subject nuevo: un grupo nuevo de modelos relacionados. La URL de su @context existirá cuando se publique.",
    },
}


def get_strings(lang: str = "en", custom: Path | None = None) -> dict[str, str]:
    """Catálogo de textos para ``lang``, completado con el inglés y, si se indica, con un
    JSON propio (para idiomas no incluidos)."""
    strings = dict(STRINGS["en"])
    strings.update(STRINGS.get(lang, {}))
    if custom:
        data = json.loads(Path(custom).read_text(encoding="utf-8"))
        strings.update({k: str(v) for k, v in data.items() if k in STRINGS["en"]})
    return strings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "export":
        text = json.dumps(STRINGS.get(args[1], STRINGS["en"]), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write(text.encode("utf-8") + b"\n")
        return 0
    sys.stderr.write("Uso: python i18n.py export <es|en>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
