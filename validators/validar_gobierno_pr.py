"""Validador de gobierno del Pull Request. 
"""
import json
import os
import re
import sys

PATRON_RAMA = re.compile(r"^(feature|fix|feat|hotfix)/[a-z0-9._-]+$", re.I)
PATRON_ASUNTO = re.compile(r"^\s*\[[^\]]+\]|^[A-Z]{3,5}_[A-Z]{2}_\d{8}_")

SECCIONES = ["Datos generales", "Check list", "Tipo de cambio", "Capa afectada"]
CAMPOS = ["Squad", "Objetivo", "Desarrollador", "PO", "Líder Técnico"]


def validar(rama, titulo, cuerpo):
    h = []
    cuerpo = cuerpo or ""

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

    faltan = [s for s in SECCIONES if s.lower() not in cuerpo.lower()]
    vacios = []
    for c in CAMPOS:
        m = re.search(rf"{re.escape(c)}\s*:\s*(.*)", cuerpo, re.I)
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
            "regla_id": "PR-03", "checklist_nro": 3, "criticidad": "OBL",
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
        "skill": "mibanco.pr-gobierno v1.0.0",
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
