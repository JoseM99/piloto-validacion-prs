"""Nodo 1 - Desarrollo Lakehouse.

Reglas deterministas del Checklist v2 del CoE (tecnologia Azure Databricks).
Corre en el runner de GitHub Actions. No usa Databricks ni LLM.
"""
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"

# Reglas sin definicion cerrada. No se reportan mientras siga el conflicto.
REGLAS_EN_CONFLICTO = set()

# Carpetas de infraestructura del propio validador: no son codigo de datos.
EXCLUIDOS = {"validators", "tests", ".github", "skills", "experimentos", "docs"}

FUENTES = {"data", "core", "satelites", "apps", "dataentrys"}
TIPOS = {"process", "config", "ddl", "dml", "metadata", "utils"}

SQL_KEYWORDS = ["select", "from", "where", "join", "group by", "order by",
                "having", "insert", "update", "delete", "create", "alter"]

PREFIJOS_FUNC = ("get", "add", "group", "list", "select", "calculate", "read",
                 "write", "join", "validate", "sort", "drop", "append", "main")

# Fila 58 · prefijos de campo en español
PREFIJOS_CAMPO = ("cod", "des", "fec", "hor", "flg", "nom", "ape", "nro",
                  "ctd", "est", "tip", "txt", "val", "mto")

# Filas 9, 12 y 17 · catalogos y prefijos de tabla por capa
CATALOGOS = ("mb_bronze_", "mb_silver_", "mb_gold_")
PREFIJOS_TABLA = {
    "bronze": ("gt_", "et_", "de_"),
    "silver": ("m_", "h_", "p_"),
    "gold": ("fct_", "dim_", "tmp_", "t"),
}

# Fila 15 y 19 · tags obligatorios por capa
TAGS_TABLA = ("frecuencia", "naturaleza", "tipo_tabla", "owner", "dac")

# Fila 84 y 85 · tags obligatorios del workflow
TAGS_WORKFLOW = ("area", "project", "solution", "product_owner",
                 "business_impact", "cost_center", "schedule")
IMPACTO_VALIDO = {"critical", "high", "medium", "low"}

LONG_LINEA = 120        # fila 32
LONG_TABLA = 60         # fila 51
LONG_CAMPO = 40         # fila 57
LONG_WORKFLOW = 70      # fila 82

ACENTOS = "áéíóúÁÉÍÓÚñÑ"


# ---------------------------------------------------------------- extraccion
def extraer_codigo_ipynb(texto):
    """Devuelve el codigo y el markdown de un notebook en formato JSON."""
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
    """Quita comentarios y docstrings para evitar falsos positivos."""
    s = re.sub(r'"""[\s\S]*?"""', '""', codigo)
    s = re.sub(r"'''[\s\S]*?'''", "''", s)
    s = re.sub(r"^\s*#.*$", "", s, flags=re.M)
    return s


def h(rid, nro, archivo, evidencia, explicacion, crit="OBL"):
    """Construye un hallazgo con el formato estandar del veredicto."""
    return {"regla_id": rid, "checklist_nro": nro, "archivo": archivo,
            "evidencia": " ".join((evidencia or "").split())[:180],
            "explicacion": explicacion, "criticidad": crit}


# ------------------------------------------------- taxonomia (filas 20 a 22)
def reglas_taxonomia(path):
    out = []
    partes = [p for p in path.split("/") if p]
    if "Data" not in partes:
        out.append(h("TAX-01", 20, path, path,
                     "El notebook no esta bajo la ruta taxonomica /Data/..."))
        return out

    resto = partes[partes.index("Data") + 1:]

    if len(resto) < 5:
        out.append(h("TAX-01", 20, path, path,
                     "Ruta incompleta: falta Fuente/Origen/Concepto/Proceso/Tipo."))
    if resto and resto[0].lower() not in FUENTES:
        out.append(h("TAX-02", 21, path, resto[0],
                     "Fuente invalida. Validas: Data, Core, Satelites, Apps, Dataentrys."))
    if len(resto) >= 2 and resto[-2].lower() not in TIPOS:
        out.append(h("TAX-03", 22, path, resto[-2],
                     "Tipo invalido. Validos: Process, Config, DDL, DML, Metadata, Utils."))
    return out


# --------------------------------------------------- notebook (filas 23 a 29)
def reglas_notebook(path, codigo, markdown):
    out = []
    limpio = sin_comentarios(codigo)
    en_process = "/process/" in path.lower()

    # 23 · cabecera estandar
    bloque = re.search(r"(?:^[ \t]*#.*\n){3,}", codigo[:1500], re.M)
    cabecera = (markdown or "") + "\n" + (bloque.group(0) if bloque else "")
    faltan = [k for k, pat in [
        ("objetivo", r"^\s*#?\s*(objetivo|proyecto)\b"),
        ("version", r"^\s*#?\s*versi[oó]n?\b"),
        ("desarrollador", r"^\s*#?\s*(desarrollador|autor)\b"),
        ("fecha", r"^\s*#?\s*fecha\b"),
        ("tabla fuente", r"^\s*#?\s*(tabla\s+fuente|fuente|origen)\b"),
        ("tabla destino", r"^\s*#?\s*(tabla\s+destino|destino)\b"),
    ] if not re.search(pat, cabecera, re.I | re.M)]
    if faltan:
        out.append(h("NBK-01", 23, path, cabecera[:120],
                     "Cabecera incompleta, faltan: " + ", ".join(faltan)))

    # 24 · seccion de importaciones y orden
    m_def = re.search(r"^\s*def\s+\w+", limpio, re.M)
    if m_def:
        m_imp = re.search(r"^\s*(import|from)\s+\S+", limpio[m_def.start():], re.M)
        if m_imp:
            out.append(h("NBK-02", 24, path, m_imp.group(0),
                         "Hay importaciones despues de la seccion de funciones.", "OPC"))
    grupos = []
    for m in re.finditer(r"^\s*(?:from\s+(\S+)|import\s+(\S+))", limpio, re.M):
        mod = (m.group(1) or m.group(2)).split(".")[0]
        if mod in ("os", "sys", "re", "json", "time", "logging", "datetime",
                   "math", "typing", "collections", "functools", "itertools"):
            g = 1
        elif mod in ("pyspark", "delta", "pandas", "numpy", "requests", "databricks"):
            g = 2
        else:
            g = 3
        grupos.append((g, m.group(0).strip()))
    for i in range(1, len(grupos)):
        if grupos[i][0] < grupos[i - 1][0]:
            out.append(h("NBK-02", 24, path, grupos[i][1],
                         "Importaciones fuera de orden: primero estandar, "
                         "luego terceros, luego locales.", "OPC"))
            break

    # 25 · importaciones explicitas
    for m in re.finditer(r"^\s*from\s+\S+\s+import\s+\*", limpio, re.M):
        out.append(h("NBK-05", 25, path, m.group(0).strip(),
                     "No se permite importar con asterisco."))

    # 26 · docstrings y sustento de UDF
    lineas = codigo.split("\n")
    for i, ln in enumerate(lineas):
        m_def = re.match(r"\s*def\s+(\w+)\s*\(", ln)
        if not m_def:
            continue
        j = i
        while j < len(lineas) and not lineas[j].rstrip().endswith(":"):
            j += 1
        siguiente = ""
        for k in range(j + 1, min(j + 4, len(lineas))):
            if lineas[k].strip():
                siguiente = lineas[k].strip()
                break
        if siguiente[:3] not in ('"""', "'''"):
            out.append(h("NBK-03", 26, path, "def " + m_def.group(1) + "(...)",
                         "La funcion no tiene docstring."))

    for m in re.finditer(r"(@(?:pandas_)?udf|\budf\s*\()", limpio):
        ctx = codigo[max(0, codigo.find(m.group(0)) - 400):
                     codigo.find(m.group(0)) + 400].lower()
        if not re.search(r"nativ|sustent|justific|no existe", ctx):
            out.append(h("NBK-06", 26, path, m.group(0),
                         "Uso de UDF sin sustento documentado de por que no "
                         "aplica una funcion nativa."))
            break

    # 27 · parametros por widgets
    if en_process:
        if not re.search(r"dbutils\.widgets\.(get|text|dropdown)", limpio):
            out.append(h("NBK-04", 27, path, "(no se encontro dbutils.widgets)",
                         "Los parametros deben recibirse por dbutils.widgets."))
        m_cat = re.search(r"=\s*[\"']mb_(bronze|silver|gold)_(dev|qa|prod)[\"']", limpio)
        if m_cat:
            out.append(h("NBK-04", 27, path, m_cat.group(0),
                         "Catalogo fijo en el codigo; debe venir de un widget."))

    # 32 · longitud de linea
    for n, ln in enumerate(codigo.split("\n"), 1):
        if len(ln) > LONG_LINEA:
            out.append(h("PY-04", 32, path, ln[:70],
                         f"Linea {n} supera los {LONG_LINEA} caracteres.", "OPC"))
            break

    # 30 · naming de variables y funciones
    for m in re.finditer(r"^([A-Za-z_]\w*)\s*=(?!=)", limpio, re.M):
        nom = m.group(1)
        if nom.isupper():
            continue
        if not re.match(r"^[a-z][a-z0-9_]*$", nom):
            out.append(h("PY-01", 30, path, nom, "Variable fuera de snake_case."))
    for m in re.finditer(r"^\s*def\s+(\w+)", limpio, re.M):
        nom = m.group(1)
        if nom.startswith("_"):
            continue
        if nom.split("_")[0].lower() not in PREFIJOS_FUNC:
            out.append(h("PY-01", 30, path, f"def {nom}",
                         "La funcion no usa un prefijo valido "
                         "(get/read/write/validate...)."))
    for m in re.finditer(r"^(df\d*|aux|tmp|temp|x|data)\s*=(?!=)", limpio, re.M):
        out.append(h("PY-02", 30, path, m.group(1),
                     "Nombre de DataFrame poco descriptivo.", "OPC"))

    # 33 y 36 · PySpark
    for m in re.finditer(r"(mergeSchema|overwriteSchema)", limpio):
        out.append(h("PYS-04", 36, path, m.group(0),
                     "Prohibido; los cambios de estructura van por DDL."))

    # 70 · formatos de escritura permitidos
    for m in re.finditer(r"\.write[\s\S]{0,80}?format\s*\(\s*[\"'](csv|json)[\"']",
                         limpio):
        out.append(h("BP-01", 70, path, m.group(0)[:80],
                     "La escritura debe ser Delta (preferido) o Parquet."))

    # 71 · campos de fecha con tipo nativo
    for m in re.finditer(r"[\"'](fec\w*|fecha\w*)[\"']\s*,\s*StringType\(\)", limpio):
        out.append(h("BP-03", 71, path, m.group(0),
                     "Los campos de fecha deben ser DATE o TIMESTAMP, no texto."))

    # 40 · operaciones que trasladan datos al driver
    for m in re.finditer(r"\.(collect|toPandas|take)\s*\(", limpio):
        out.append(h("PERF-01", 40, path, m.group(0),
                     "Traslada datos al driver; revisar si esta justificado.", "OPC"))
        break

    return out


# ---------------------------------------------------- logging (filas 42 a 48)
def reglas_logging(path, codigo):
    out = []
    limpio = sin_comentarios(codigo)

    if not re.search(r"\blogger\s*\.", limpio):
        out.append(h("LOG-01", 42, path, "(no se encontro logger)",
                     "No hay logging; se requiere registro de inicio de proceso."))
        return out

    if not re.search(r"logger\.(info|debug)\s*\(.*(inicio|start)", limpio, re.I):
        out.append(h("LOG-01", 42, path, "(sin log de inicio)",
                     "Falta el registro de inicio de proceso."))
    if not re.search(r"logger\.(info|debug)\s*\(.*(fin|end|termin)", limpio, re.I):
        out.append(h("LOG-02", 43, path, "(sin log de fin)",
                     "Falta el registro de fin de proceso."))
    if not re.search(r"logger\.(info|debug)\s*\(.*(param|widget)", limpio, re.I):
        out.append(h("LOG-03", 44, path, "(sin log de parametros)",
                     "Falta el registro de los parametros de entrada."))

    tiempo = re.search(r"(perf_counter|process_time|monotonic|time\.time\s*\()", limpio) \
        or re.search(r"logger\.\w+\s*\(.*(tiempo|duracion|segundos|elapsed)", limpio, re.I)
    if not tiempo:
        out.append(h("LOG-04", 42, path, "(sin medicion de tiempos)",
                     "Falta el registro de tiempos por etapa del proceso.", "OPC"))

    m_exc = re.search(r"^\s*except\b", limpio, re.M)
    if not m_exc:
        out.append(h("LOG-05", 46, path, "(sin bloque try/except)",
                     "No se capturan excepciones en el proceso.", "OPC"))
    else:
        if not re.search(r"logger\.(error|exception|critical)\s*\(", limpio):
            out.append(h("LOG-05", 46, path, m_exc.group(0).strip(),
                         "Las excepciones no se registran con logger.error."))
        m_pass = re.search(r"except[^\n]*:\s*\n\s*pass\b", limpio)
        if m_pass:
            out.append(h("LOG-05", 46, path, m_pass.group(0),
                         "No se permite silenciar errores con pass."))

    for m in re.finditer(r"^\s*print\s*\(", limpio, re.M):
        out.append(h("LOG-06", 47, path, m.group(0).strip(),
                     "Evite print(); toda salida debe ir por el logger."))
    return out


# --------------------------------------------------------- SQL (filas 61, 63)
def reglas_sql(path, codigo):
    out = []
    for m in re.finditer(
            r"""spark\.sql\s*\(\s*(?:f?["']{1,3})([\s\S]{0,600}?)["']{1,3}\s*\)""",
            codigo):
        q = m.group(1)
        out.append(h("PYS-01", 33, path, "spark.sql(" + " ".join(q.split())[:60],
                     "Spark SQL embebido en cadena; priorizar la API de PySpark."))
        for kw in SQL_KEYWORDS:
            if re.search(rf"\b{kw}\b", q) and not re.search(rf"\b{kw.upper()}\b", q):
                out.append(h("SQL-01", 61, path, q[:80],
                             f"La palabra reservada '{kw}' debe ir en mayusculas.",
                             "OPC"))
                break
        if re.search(r"select\s+\*", q, re.I):
            out.append(h("SQL-03", 63, path, q[:80],
                         "No se permite SELECT *; proyecte las columnas."))
    return out


# --------------------------------------------------------- DDL (filas 9 a 19,
#                                                            49 a 59)
def _capa(catalogo):
    for capa in ("bronze", "silver", "gold"):
        if f"mb_{capa}_" in catalogo.lower():
            return capa
    return None


def reglas_ddl(path, codigo):
    """Valida las sentencias CREATE TABLE presentes en el archivo."""
    out = []
    for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"([`\w.]+)\s*\(([\s\S]*?)\)\s*(?:USING|COMMENT|PARTITIONED|"
            r"CLUSTER|TBLPROPERTIES|;|$)", codigo, re.I):
        objeto = m.group(1).replace("`", "")
        cuerpo = m.group(2)
        bloque = codigo[m.start():m.start() + 3000]
        tabla = objeto.split(".")[-1]

        if not any(c in objeto.lower() for c in CATALOGOS):
            out.append(h("CAT-01", 9, path, objeto,
                         "No usa un catalogo oficial "
                         "(mb_bronze_/mb_silver_/mb_gold_<entorno>)."))
        if objeto.count(".") != 2:
            out.append(h("JER-01", 9, path, objeto,
                         "No sigue la jerarquia catalogo.esquema.tabla."))

        capa = _capa(objeto)
        if capa and not tabla.lower().startswith(PREFIJOS_TABLA[capa]):
            out.append(h("PREF-01", 9, path, tabla,
                         f"La tabla no usa un prefijo valido para la capa {capa}: "
                         + ", ".join(PREFIJOS_TABLA[capa])))

        if tabla != tabla.lower() or not re.match(r"^[a-z][a-z0-9_]*$", tabla):
            out.append(h("DDL-01", 49, path, tabla,
                         "El nombre de la tabla debe ir en snake_case y minusculas."))
        if any(ch in tabla for ch in ACENTOS):
            out.append(h("DDL-02", 50, path, tabla,
                         "El nombre de la tabla no debe llevar acentos ni la letra Ñ."))
        if len(tabla) > LONG_TABLA:
            out.append(h("DDL-03", 51, path, tabla,
                         f"El nombre de la tabla supera los {LONG_TABLA} caracteres.",
                         "OPC"))
        if not re.search(r"USING\s+DELTA", bloque, re.I):
            out.append(h("DDL-05", 53, path, objeto,
                         "Falta declarar USING DELTA en la creacion de la tabla."))
        if not re.search(r"\bCOMMENT\b", bloque, re.I):
            out.append(h("DDL-04", 52, path, objeto,
                         "Faltan comentarios (COMMENT) en la tabla y sus columnas."))

        # 10, 14 y 18 · campos tecnicos de auditoria
        low = bloque.lower()
        for campo in ("_ingestion_time", "_processing_time"):
            if campo not in low:
                out.append(h("AUD-01", 10, path, objeto,
                             f"Falta el campo tecnico de auditoria {campo}."))

        # 15 y 19 · tags obligatorios
        m_tags = re.search(r"TBLPROPERTIES\s*\(([\s\S]*?)\)", bloque, re.I)
        if not m_tags:
            out.append(h("TAG-01", 15, path, objeto,
                         "Faltan los tags obligatorios de la tabla."))
        else:
            props = m_tags.group(1).lower()
            faltan = [t for t in TAGS_TABLA if t not in props]
            if faltan:
                out.append(h("TAG-01", 15, path, objeto,
                             "Faltan tags obligatorios: " + ", ".join(faltan)))

        # 55 a 59 · campos
        dac = False
        for lc in cuerpo.split(","):
            mc = re.match(r"\s*`?([A-Za-z_][\w]*)`?\s+([A-Za-z]+)", lc.strip())
            if not mc:
                continue
            campo, tipo = mc.group(1), mc.group(2).upper()
            if campo.startswith("_"):
                continue
            if campo != campo.lower() or not re.match(r"^[a-z][a-z0-9_]*$", campo):
                out.append(h("CMP-01", 55, path, campo,
                             "El campo debe ir en snake_case y minusculas."))
            if any(ch in campo for ch in ACENTOS):
                out.append(h("CMP-02", 56, path, campo,
                             "El campo no debe llevar acentos ni la letra Ñ."))
            if len(campo) > LONG_CAMPO:
                out.append(h("CMP-03", 57, path, campo,
                             f"El campo supera los {LONG_CAMPO} caracteres."))
            if campo.split("_")[0] not in PREFIJOS_CAMPO:
                out.append(h("CMP-04", 58, path, campo,
                             "El campo no usa un prefijo valido "
                             "(cod, des, fec, nom, mto, val...).", "OPC"))
            if campo.split("_")[0] in ("mto", "val") and tipo in ("FLOAT", "DOUBLE"):
                out.append(h("CMP-04", 58, path, f"{campo} {tipo}",
                             "Los campos mto y val deben ser DECIMAL.", "OPC"))
            if campo.endswith("_dac"):
                dac = True
        if dac and not re.search(r"dac\s*['\"]?\s*[=:]\s*['\"]?\s*si", bloque, re.I):
            out.append(h("CMP-05", 59, path, objeto,
                         "Hay campos con sufijo _dac pero falta el tag Dac=SI."))
    return out


# ----------------------------------------------- workflows (filas 82 a 87)
def reglas_workflow(path, texto):
    """Valida el JSON de definicion de un workflow de Databricks."""
    out = []
    try:
        wf = json.loads(texto)
    except json.JSONDecodeError:
        out.append(h("FMT-01", 86, path, texto[:120],
                     "El JSON del workflow no es valido y no pudo analizarse."))
        return out

    nombre = wf.get("name", "") or os.path.splitext(os.path.basename(path))[0]

    if not re.match(r"^wf_[a-z0-9]+_[a-z0-9_]+$", nombre):
        out.append(h("WF-01", 82, path, nombre,
                     "Nombre invalido. Formato: wf_{proyecto}_{descripcion} "
                     "en minusculas y guion bajo."))
    if len(nombre) > LONG_WORKFLOW:
        out.append(h("WF-01", 82, path, nombre,
                     f"El nombre supera los {LONG_WORKFLOW} caracteres."))

    tags = {k.lower(): str(v).lower() for k, v in (wf.get("tags") or {}).items()}
    faltan = [t for t in TAGS_WORKFLOW if t not in tags]
    if faltan:
        out.append(h("WF-02", 84, path, ", ".join(sorted(tags)) or "(sin tags)",
                     "Faltan tags obligatorios: " + ", ".join(faltan)))

    if "business_impact" in tags and tags["business_impact"] not in IMPACTO_VALIDO:
        out.append(h("WF-03", 85, path, tags["business_impact"],
                     "business_impact debe ser critical, high, medium o low."))
    if "schedule" in tags and not tags["schedule"].strip():
        out.append(h("WF-03", 85, path, "schedule",
                     "El tag schedule debe declarar la frecuencia esperada."))

    if "deploy/workflows/" not in path.replace("\\", "/").lower():
        out.append(h("WF-04", 86, path, path,
                     "El JSON del workflow debe residir en deploy/workflows/."))
    return out


# ------------------------------------------------------------- ADF (3 a 6)
def reglas_adf(path, texto):
    out = []
    nombre = os.path.splitext(os.path.basename(path))[0]
    bajo = path.lower()

    if "/pipeline" in bajo:
        if not re.match(r"^pipeline_(master|load)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$",
                        nombre):
            out.append(h("ADF-01", 4, path, nombre,
                         "Nombre invalido. Formato: "
                         "pipeline_[funcionalidad]_[aplicacion]_[tipo]."))
        if not re.search(r"/(Master|Load Batch|Load Stream)/", path, re.I):
            out.append(h("ADF-02", 3, path, path,
                         "El pipeline no esta en la ruta estandar."))
    elif "/dataset" in bajo:
        if not re.match(r"^ds_(parquet|delta|oracle|csv|bin)_[a-z0-9]+_[a-z0-9]+$",
                        nombre, re.I):
            out.append(h("ADF-03", 6, path, nombre,
                         "Nombre invalido. Formato: ds_[tipo]_[aplicacion]_[conexion]."))
        elif not re.search(r"_(in|out)$", nombre, re.I):
            out.append(h("ADF-03", 6, path, nombre,
                         "El dataset debe indicar conexion de entrada o salida."))
    return out


# -------------------------------------------------------------------- main
def archivos_del_pr(repo, pr, token):
    """Devuelve los archivos modificados en el Pull Request."""
    req = urllib.request.Request(
        f"{API}/repos/{repo}/pulls/{pr}/files?per_page=100",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def evaluar(path, texto):
    """Aplica el conjunto de reglas que corresponde al tipo de archivo."""
    bajo = path.lower()

    if bajo.endswith(".json"):
        segmentos = {p for p in bajo.replace("\\", "/").split("/")}
        if "workflows" in segmentos:
            return reglas_workflow(path, texto)
        return reglas_adf(path, texto)

    if bajo.endswith(".sql"):
        return reglas_ddl(path, texto) + reglas_sql(path, texto)

    if bajo.endswith(".ipynb"):
        codigo, markdown = extraer_codigo_ipynb(texto)
        if codigo is None:
            return [h("FMT-01", 0, path, texto[:120],
                      "El notebook no es un JSON valido y no pudo analizarse. "
                      "Revise comas colgantes o comillas sin cerrar.")]
    else:
        codigo, markdown = texto, ""

    out = reglas_taxonomia(path)
    out += reglas_notebook(path, codigo, markdown)
    out += reglas_logging(path, codigo)
    out += reglas_sql(path, codigo)
    out += reglas_ddl(path, codigo)

    if "/process/" in bajo:
        m_ddl = re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b",
                          sin_comentarios(codigo), re.I)
        if m_ddl:
            out.append(h("TAX-03", 22, path, m_ddl.group(0),
                         "Hay DDL en un notebook de /Process/; debe ir en /DDL/."))
    return out


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
        if not path.lower().endswith((".ipynb", ".py", ".sql", ".json")):
            continue
        if EXCLUIDOS & {p.lower() for p in path.split("/")}:
            continue
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8", errors="replace") as f:
            texto = f.read()

        evaluados.append(path)
        hallazgos += evaluar(path, texto)

    hallazgos = [x for x in hallazgos if x["regla_id"] not in REGLAS_EN_CONFLICTO]
    bloqueantes = [x for x in hallazgos if x["criticidad"] == "OBL"]

    veredicto = {
        "skill": "lakehouse-desarrollo v2.0.0",
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