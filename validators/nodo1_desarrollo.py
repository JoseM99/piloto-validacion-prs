"""Nodo 1 - Desarrollo Lakehouse.

Reglas deterministas [N1] de la skill mibanco.lakehouse-desarrollo.
Corre en el runner de GitHub Actions. No usa Databricks ni LLM.
"""
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"

# Reglas en conflicto entre el Checklist v2 y el ltsdev.docx.
# Mientras no se resuelvan, no se reportan (ver hoja "Mapeo Skills").
REGLAS_EN_CONFLICTO = {"PY-04"}

FUENTES = {"data", "core", "satelites", "apps", "dataentrys"}
TIPOS = {"process", "config", "ddl", "metadata", "utils"}

SQL_KEYWORDS = ["select", "from", "where", "join", "group by", "order by",
                "having", "insert", "update", "delete", "create", "alter"]

PREFIJOS_FUNC = ("get", "add", "group", "list", "select", "calculate", "read",
                 "write", "join", "validate", "sort", "drop", "append", "main")


# ---------------------------------------------------------------- extracción
def extraer_codigo_ipynb(texto):
    """Devuelve solo el codigo de las celdas 'code' de un notebook."""
    try:
        nb = json.loads(texto)
    except json.JSONDecodeError:
        return None, None

    codigo, markdown = [], []
    for celda in nb.get("cells", []):
        fuente = celda.get("source", [])
        if isinstance(fuente, list):
            fuente = "".join(fuente)
        if celda.get("cell_type") == "code":
            codigo.append(fuente)
        else:
            markdown.append(fuente)
    return "\n".join(codigo), "\n".join(markdown)


def sin_comentarios(codigo):
    """Quita comentarios y literales de cadena para evitar falsos positivos."""
    s = re.sub(r'"""[\s\S]*?"""', '""', codigo)
    s = re.sub(r"'''[\s\S]*?'''", "''", s)
    s = re.sub(r"^\s*#.*$", "", s, flags=re.M)
    return s


def h(rid, nro, archivo, evidencia, explicacion, crit="OBL"):
    return {"regla_id": rid, "checklist_nro": nro, "archivo": archivo,
            "evidencia": (evidencia or "")[:180].strip(),
            "explicacion": explicacion, "criticidad": crit}


# ------------------------------------------------------------------ reglas
def reglas_taxonomia(path):
    out = []
    partes = [p for p in path.split("/") if p]
    if "Data" not in partes:
        out.append(h("TAX-01", 24, path, path,
                     "El notebook no esta bajo la ruta taxonomica /Data/..."))
        return out

    i = partes.index("Data")
    resto = partes[i + 1:]

    if len(resto) < 5:
        out.append(h("TAX-01", 24, path, path,
                     "Ruta incompleta: falta Fuente/Origen/Concepto/Proceso/Tipo."))

    if resto and resto[0].lower() not in FUENTES:
        out.append(h("TAX-02", 25, path, resto[0],
                     "Fuente invalida. Validas: Data, Core, Satelites, Apps, Dataentrys."))

    if len(resto) >= 2:
        tipo = resto[-2]
        if tipo.lower() not in TIPOS:
            out.append(h("TAX-03", 26, path, tipo,
                         "Tipo invalido. Validos: Process, Config, DDL, Metadata, Utils."))
    return out


def reglas_notebook(path, codigo, markdown):
    out = []
    limpio = sin_comentarios(codigo)
    en_process = "/process/" in path.lower()

    # NBK-01 cabecera
    cabecera = (markdown or "") + "\n" + codigo[:1500]
    faltan = [k for k, pat in [
        ("objetivo", r"objetivo|proyecto"),
        ("version", r"versi[oó]n|version"),
        ("desarrollador", r"desarrollador|autor"),
        ("fecha", r"fecha"),
    ] if not re.search(pat, cabecera, re.I)]
    if faltan:
        out.append(h("NBK-01", 27, path, cabecera[:120],
                     "Cabecera incompleta, faltan: " + ", ".join(faltan)))

    # NBK-02 imports antes de la primera funcion
    m_def = re.search(r"^\s*def\s+\w+", limpio, re.M)
    if m_def:
        despues = limpio[m_def.start():]
        m_imp = re.search(r"^\s*(import|from)\s+\S+", despues, re.M)
        if m_imp:
            out.append(h("NBK-02", 28, path, m_imp.group(0),
                         "Hay imports despues de la seccion de funciones."))

    # NBK-03 docstrings
    for m in re.finditer(r"^(\s*)def\s+(\w+)\s*\([^)]*\)\s*(->[^:]+)?:\s*\n((?:\1\s+.*\n)?)",
                         codigo, re.M):
        if not re.match(r"\s*(\"\"\"|''')", m.group(4) or ""):
            out.append(h("NBK-03", 29, path, f"def {m.group(2)}(...)",
                         "La funcion no tiene docstring."))

    # NBK-04 widgets
    if en_process:
        if not re.search(r"dbutils\.widgets\.(get|text|dropdown)", limpio):
            out.append(h("NBK-04", 30, path, "(no se encontro dbutils.widgets)",
                         "Los parametros deben recibirse por dbutils.widgets."))
        m_cat = re.search(r"=\s*[\"']mb_(bronze|silver|gold)_(dev|qa|prod)[\"']", limpio)
        if m_cat:
            out.append(h("NBK-04", 30, path, m_cat.group(0),
                         "Catalogo hardcodeado; debe venir de un widget."))

    # PY-01 naming de variables y funciones
    for m in re.finditer(r"^([A-Za-z_]\w*)\s*=(?!=)", limpio, re.M):
        nom = m.group(1)
        if nom.isupper():
            continue
        if not re.match(r"^[a-z][a-z0-9_]*$", nom):
            out.append(h("PY-01", 32, path, nom,
                         "Variable fuera de snake_case."))
    for m in re.finditer(r"^\s*def\s+(\w+)", limpio, re.M):
        nom = m.group(1)
        if nom.startswith("_"):
            continue
        if not nom.split("_")[0].lower() in PREFIJOS_FUNC:
            out.append(h("PY-01", 32, path, f"def {nom}",
                         "La funcion no usa un prefijo valido (get/read/write/validate...).",
                         "OPC"))

    # PYS-04 esquemas
    for m in re.finditer(r"(mergeSchema|overwriteSchema)", limpio):
        out.append(h("PYS-04", 39, path, m.group(0),
                     "Prohibido; los cambios de estructura van por ALTER TABLE."))

    # LOG-01/02/03/06
    if not re.search(r"\blogger\s*\.", limpio):
        out.append(h("LOG-01", 45, path, "(no se encontro logger)",
                     "No hay logging; se requiere registro de inicio de proceso."))
    else:
        if not re.search(r"logger\.(info|debug)\s*\(.*(inicio|start)", limpio, re.I):
            out.append(h("LOG-01", 45, path, "(sin log de inicio)",
                         "Falta el registro de inicio de proceso."))
        if not re.search(r"logger\.(info|debug)\s*\(.*(fin|end|termin)", limpio, re.I):
            out.append(h("LOG-02", 46, path, "(sin log de fin)",
                         "Falta el registro de fin de proceso."))
        if not re.search(r"logger\.(info|debug)\s*\(.*(param|widget)", limpio, re.I):
            out.append(h("LOG-03", 47, path, "(sin log de parametros)",
                         "Falta el registro de los parametros de entrada."))

    for m in re.finditer(r"^\s*print\s*\(", limpio, re.M):
        out.append(h("LOG-06", 50, path, m.group(0).strip(),
                     "No se permite print(); usar el logger."))

    # SQL-01 / SQL-03
    for m in re.finditer(r"""spark\.sql\s*\(\s*(?:f?["']{1,3})([\s\S]{0,400}?)["']{1,3}\s*\)""",
                         codigo):
        q = m.group(1)
        for kw in SQL_KEYWORDS:
            if re.search(rf"\b{kw}\b", q) and not re.search(rf"\b{kw.upper()}\b", q):
                out.append(h("SQL-01", 64, path, q[:80],
                             f"Keyword '{kw}' debe ir en mayusculas.", "OPC"))
                break
        if re.search(r"select\s+\*", q, re.I):
            crit = "OPC" if re.search(r"\blimit\b", q, re.I) else "OBL"
            out.append(h("SQL-03", 66, path, q[:80],
                         "No se permite SELECT *; proyectar columnas explicitamente.",
                         crit))

    # BP-01 formatos
    for m in re.finditer(r"\.write[\s\S]{0,60}?format\s*\(\s*[\"'](csv|json)[\"']", limpio):
        out.append(h("BP-01", 72, path, m.group(0)[:80],
                     "La escritura debe ser Delta (preferido) o Parquet."))

    # BP-03 fechas como texto
    for m in re.finditer(r"[\"'](fec\w*|fecha\w*)[\"']\s*,\s*StringType\(\)", limpio):
        out.append(h("BP-03", 74, path, m.group(0),
                     "Los campos de fecha deben ser DATE o TIMESTAMP, no texto."))

    # TAX-03 derivada: DDL dentro de /Process/
    if en_process:
        m_ddl = re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", limpio, re.I)
        if m_ddl:
            out.append(h("TAX-03", 26, path, m_ddl.group(0),
                         "Hay DDL en un notebook de /Process/; debe ir en /DDL/."))
    return out


def reglas_adf(path, texto):
    out = []
    nombre = os.path.splitext(os.path.basename(path))[0]
    bajo = path.lower()

    if "/pipeline" in bajo:
        if not re.match(r"^pipeline_(master|load)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$", nombre):
            out.append(h("ADF-01", 4, path, nombre,
                         "Nombre invalido. Formato: pipeline_[funcionalidad]_[aplicacion]_[tipo]."))
        if not re.search(r"/(Master|Load Batch|Load Stream)/", path, re.I):
            out.append(h("ADF-02", 5, path, path,
                         "El pipeline no esta en la ruta estandar segun su funcionalidad."))
    elif "/dataset" in bajo:
        if not re.match(r"^ds_(parquet|delta|oracle|csv|bin)_[a-z0-9]+_[a-z0-9]+$",
                        nombre, re.I):
            out.append(h("ADF-03", 6, path, nombre,
                         "Nombre invalido. Formato: ds_[tipo]_[aplicacion]_[conexion]."))
        elif not re.search(r"_(in|out)$", nombre, re.I):
            out.append(h("ADF-03", 6, path, nombre,
                         "El dataset debe indicar conexion de entrada (in) o salida (out)."))
    return out


# -------------------------------------------------------------------- main
def archivos_del_pr(repo, pr, token):
    req = urllib.request.Request(
        f"{API}/repos/{repo}/pulls/{pr}/files?per_page=100",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        ev = json.load(f)

    repo = os.environ["GITHUB_REPOSITORY"]
    pr = ev["pull_request"]["number"]
    token = os.environ["GITHUB_TOKEN"]

    hallazgos, evaluados = [], []

    for a in archivos_del_pr(repo, pr, token):
        path = a["filename"]
        if a["status"] == "removed":
            continue
        if not path.lower().endswith((".ipynb", ".py", ".json")):
            continue
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8", errors="replace") as f:
            texto = f.read()

        if path.lower().endswith(".json"):
            hallazgos += reglas_adf(path, texto)
            evaluados.append(path)
            continue

        if path.lower().endswith(".ipynb"):
            codigo, markdown = extraer_codigo_ipynb(texto)
            if codigo is None:
                continue
        else:
            codigo, markdown = texto, ""

        evaluados.append(path)
        hallazgos += reglas_taxonomia(path)
        hallazgos += reglas_notebook(path, codigo, markdown)

    hallazgos = [x for x in hallazgos if x["regla_id"] not in REGLAS_EN_CONFLICTO]
    bloqueantes = [x for x in hallazgos if x["criticidad"] == "OBL"]

    veredicto = {
        "skill": "mibanco.lakehouse-desarrollo v1.0.0",
        "nodo": "1-determinista",
        "estado_global": "RECHAZADO" if bloqueantes else "APROBADO",
        "archivos_evaluados": evaluados,
        "hallazgos": hallazgos,
    }
    with open("veredicto_desarrollo.json", "w", encoding="utf-8") as f:
        json.dump(veredicto, f, ensure_ascii=False, indent=2)

    print(f"ESTADO: {veredicto['estado_global']} | "
          f"archivos: {len(evaluados)} | hallazgos: {len(hallazgos)}")
    for x in hallazgos:
        print(f"  [{x['criticidad']}] {x['regla_id']} {x['archivo']}: {x['explicacion']}")

    sys.exit(1 if bloqueantes else 0)


if __name__ == "__main__":
    main()
