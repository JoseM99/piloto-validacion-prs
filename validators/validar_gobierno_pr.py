"""Validador de gobierno del Pull Request.

Reglas PR-01, PR-02 y PR-03 del Checklist v2 CoE. Corre en el runner de
GitHub Actions y no requiere Databricks.

Uso local:  python validators/validar_gobierno_pr.py
"""
import json
import os
import re
import sys
import unicodedata

PATRON_RAMA = re.compile(r"^(feature|fix|feat|hotfix)/[a-z0-9._-]+$", re.I)
PATRON_ASUNTO = re.compile(r"^\s*\[[^\]]+\]|^[A-Z]{3,5}_[A-Z]{2}_\d{8}_")
SECCIONES = ["Datos generales", "Check list", "Tipo de cambio", "Capa afectada"]
CAMPOS = ["Squad", "Objetivo", "Desarrollador", "PO", "Líder Técnico"]


def normalizar(texto):
    """Quita tildes y pasa a minusculas, para comparar sin depender del acento.

    El anexo del checklist escribe algunos nombres de campo sin tilde, asi que
    compararlos de forma exacta marcaba como vacio un campo que si estaba.
    """
    sin_tilde = unicodedata.normalize("NFKD", texto or "")
    sin_tilde = "".join(c for c in sin_tilde if not unicodedata.combining(c))
    return sin_tilde.lower()


def validar(rama, titulo, cuerpo):
    h = []
    cuerpo = cuerpo or ""
    cuerpo_norm = normalizar(cuerpo)

    if not PATRON_RAMA.match(rama or ""):
        h.append({
            "regla_id": "PR-01", "checklist_nro": 1, "criticidad": "OBL",
            "evidencia": rama,
            "explicacion": "La rama debe seguir feature/* o fix/*.",
        })

    if not PATRON_ASUNTO.search(titulo or ""):
        h.append({
            "regla_id": "PR-02", "checklist_nro": 2, "criticidad": "OBL",
            "evidencia": titulo,
            "explicacion": "El asunto debe indicar la categoria del cambio.",
        })

    faltan = [s for s in SECCIONES if normalizar(s) not in cuerpo_norm]

    vacios = []
    for c in CAMPOS:
        # El valor se busca en la misma linea del campo: con \s* los saltos de
        # linea se consumen y un campo vacio toma el texto de la linea siguiente.
        m = re.search(rf"{re.escape(normalizar(c))}[ \t]*:[ \t]*(.*)$",
                      cuerpo_norm, re.M)
        if not m or not m.group(1).strip():
            vacios.append(c)

    marcados = len(re.findall(r"- \[[xX]\]", cuerpo))
    if not marcados:
        marcados = len(re.findall(r"☑|✔", cuerpo))

    if faltan or vacios or marcados == 0:
        detalle = []
        if faltan:
            detalle.append("faltan secciones: " + ", ".join(faltan))
        if vacios:
            detalle.append("campos vacios: " + ", ".join(vacios))
        if marcados == 0:
            detalle.append("no hay items marcados en el Check list")
        h.append({
            # Control propio del validador: el checklist no tiene una fila para
            # el contenido de la descripcion del pase.
            "regla_id": "PR-03", "checklist_nro": None, "criticidad": "OBL",
            "evidencia": (cuerpo[:200] or "(descripcion vacia)"),
            "explicacion": "Descripcion del pase incompleta: " + "; ".join(detalle),
        })

    return h


def main():
    ruta = os.environ["GITHUB_EVENT_PATH"]
    with open(ruta, encoding="utf-8") as f:
        ev = json.load(f)

    pr = ev["pull_request"]
    hallazgos = validar(pr["head"]["ref"], pr["title"], pr.get("body"))

    veredicto = {
        "skill": "mibanco.pr-gobierno v1.1.0",
        "estado_global": "RECHAZADO" if hallazgos else "APROBADO",
        "hallazgos": hallazgos,
    }

    with open("veredicto_gobierno.json", "w", encoding="utf-8") as f:
        json.dump(veredicto, f, ensure_ascii=False, indent=2)

    print(f"ESTADO: {veredicto['estado_global']}")
    for x in hallazgos:
        print(f"  - {x['regla_id']}: {x['explicacion']}")

    sys.exit(1 if hallazgos else 0)


if __name__ == "__main__":
    main()
