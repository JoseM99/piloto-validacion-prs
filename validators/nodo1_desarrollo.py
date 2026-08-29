"""Nodo 1 - Desarrollo Lakehouse.

Reglas deterministas del Checklist v4. Corre en el runner de GitHub Actions.
Toda la definicion de reglas, listas y limites vive en el catalogo.

Uso local:  python validators/nodo1_desarrollo.py --local <archivo> [...]
"""
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"
RUTA_CATALOGO = "config/catalogo_reglas.json"

ACENTOS = "áéíóúÁÉÍÓÚñÑ"
SQL_KEYWORDS = ["select", "from", "where", "join", "group by", "order by",
                "having", "insert", "update", "delete", "create", "alter"]
ESTANDAR = {"os", "sys", "re", "json", "time", "logging", "datetime",
            "math", "typing", "collections", "functools", "itertools"}
TERCEROS = {"pyspark", "delta", "pandas", "numpy", "requests", "databricks"}

CAT = {}
REGLAS = {}
LISTAS = {}
LIMITES = {}
OPCIONES = {}


# ---------------------------------------------------------------- catalogo
def cargar_catalogo(ruta=RUTA_CATALOGO):
    """Carga el catalogo y expone sus bloques como globales."""
    global CAT, REGLAS, LISTAS, LIMITES, OPCIONES
    with open(ruta, encoding="utf-8") as f:
        CAT = json.load(f)
    REGLAS = CAT["reglas"]
    LISTAS = CAT["listas"]
    LIMITES = CAT["limites"]
    OPCIONES = CAT["opciones"]


def activa(rid):
    """Una regla suspendida no se evalua."""
    r = REGLAS.get(rid)
    return bool(r) and r.get("estado") != "suspendida"


def h(rid, archivo, evidencia, detalle=None, linea=None):
    """Arma el hallazgo tomando codigo, criticidad y textos del catalogo."""
    r = REGLAS[rid]
    return {
        "regla_id": rid,
        "codigo": r["codigo"],
        "criticidad": r["criticidad"],
        "archivo": archivo,
        "linea": linea,
        "evidencia": " ".join((evidencia or "").split())[:180],
        "mensaje": r["mensaje"] + (f" {detalle}" if detalle else ""),
        "correccion": r["correccion"],
    }


# --------------------------------------------------------------- utilidades
def extraer_codigo_ipynb(texto):
    """Devuelve codigo, markdown y las celdas SQL con su posicion en el codigo."""
    try:
        nb = json.loads(texto)
    except json.JSONDecodeError:
        return None, None, None

    codigo, markdown, sql = [], [], []
    pos = 0
    for celda in nb.get("cells", []):
        fuente = celda.get("source", [])
        if isinstance(fuente, list):
            fuente = "".join(fuente)
        if celda.get("cell_type") == "code":
            codigo.append(fuente)
            if re.match(r"\s*%sql\b", fuente):
                sql.append((pos, fuente))
            pos += len(fuente) + 1   # el salto que agrega el join
        else:
            markdown.append(fuente)
    return "\n".join(codigo), "\n".join(markdown), sql


def sin_comentarios(codigo):
    """Quita comentarios y docstrings para evitar falsos positivos."""
    s = re.sub(r'"""[\s\S]*?"""', '""', codigo)
    s = re.sub(r"'''[\s\S]*?'''", "''", s)
    s = re.sub(r"^\s*#.*$", "", s, flags=re.M)
    return s


def normalizar_cabecera(texto):
    """Quita marcas de comentario y separadores para poder buscar las etiquetas.

    Cubre los tres estilos en uso: almohadilla en Python, doble guion en celdas
    SQL y barras verticales como separador de columnas.
    """
    lineas = []
    for ln in texto.split("\n"):
        ln = re.sub(r"^\s*(?:#|-{2,})+", "", ln)
        lineas.append(ln.replace("|", " ").strip())
    return "\n".join(lineas)


def nro_linea(texto, pos):
    return texto.count("\n", 0, pos) + 1


# ----------------------------------------------------- taxonomia · ADB-WS-05
def reglas_taxonomia(path):
    out = []
    partes = [p for p in path.split("/") if p]
    if "Data" not in partes:
        if activa("TAX-01"):
            out.append(h("TAX-01", path, path))
        return out

    resto = partes[partes.index("Data") + 1:]
    if len(resto) < 5 and activa("TAX-01"):
        out.append(h("TAX-01", path, path, "Faltan niveles en la ruta."))
    if resto and resto[0].lower() not in LISTAS["fuentes_taxonomia"] and activa("TAX-02"):
        out.append(h("TAX-02", path, resto[0]))
    if len(resto) >= 2 and resto[-2].lower() not in LISTAS["tipos_taxonomia"] and activa("TAX-03"):
        out.append(h("TAX-03", path, resto[-2]))
    return out


# ------------------------------------------------------- notebook · ADB-NB-*
def reglas_notebook(path, codigo, markdown):
    out = []
    limpio = sin_comentarios(codigo)
    en_process = "/process/" in path.lower()

    # ADB-NB-01 · cabecera. Se aceptan los tres estilos: markdown, comentarios
    # de Python y comentarios de celda SQL.
    if activa("NBK-01"):
        crudo = codigo[:3000]
        bloque_py = re.search(r"(?:^[ \t]*#.*\n){3,}", crudo, re.M)
        bloque_sql = re.search(r"(?:^[ \t]*-{2,}.*\n){3,}", crudo, re.M)
        cabecera = normalizar_cabecera(
            (markdown or "")
            + "\n" + (bloque_py.group(0) if bloque_py else "")
            + "\n" + (bloque_sql.group(0) if bloque_sql else ""))
        faltan = [k for k, pat in [
            ("objetivo", r"^\s*(objetivo|proyecto)\b"),
            ("version", r"^\s*versi[oó]n?\b"),
            ("desarrollador", r"^\s*(desarrollador|autor)\b"),
            ("fecha", r"^\s*fecha\b"),
            ("tabla fuente", r"^\s*(tabla\s+fuente|fuente|origen)\b"),
            ("tabla destino", r"^\s*(tabla\s+destino|destino)\b"),
        ] if not re.search(pat, cabecera, re.I | re.M)]
        if faltan:
            out.append(h("NBK-01", path, cabecera[:120],
                         "Faltan: " + ", ".join(faltan), 1))

    # ADB-NB-02 · orden de importaciones
    if activa("NBK-02"):
        m_def = re.search(r"^\s*def\s+\w+", limpio, re.M)
        if m_def:
            m_imp = re.search(r"^\s*(import|from)\s+\S+", limpio[m_def.start():], re.M)
            if m_imp:
                out.append(h("NBK-02", path, m_imp.group(0),
                             "Hay importaciones despues de la seccion de funciones."))
        grupos = []
        for m in re.finditer(r"^\s*(?:from\s+(\S+)|import\s+(\S+))", limpio, re.M):
            mod = (m.group(1) or m.group(2)).split(".")[0]
            g = 1 if mod in ESTANDAR else (2 if mod in TERCEROS else 3)
            grupos.append((g, m.group(0).strip()))
        for i in range(1, len(grupos)):
            if grupos[i][0] < grupos[i - 1][0]:
                out.append(h("NBK-02", path, grupos[i][1]))
                break

    # ADB-NB-03 · importacion explicita
    if activa("NBK-05"):
        for m in re.finditer(r"^\s*from\s+\S+\s+import\s+\*", limpio, re.M):
            out.append(h("NBK-05", path, m.group(0).strip(),
                         None, nro_linea(limpio, m.start())))

    # ADB-NB-04 · docstring de funcion
    if activa("NBK-03"):
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
                out.append(h("NBK-03", path, "def " + m_def.group(1) + "(...)",
                             None, i + 1))

    # ADB-NB-05 · sustento de UDF
    if activa("NBK-06"):
        for m in re.finditer(r"(@(?:pandas_)?udf|\budf\s*\()", limpio):
            pos = codigo.find(m.group(0))
            ctx = codigo[max(0, pos - 400): pos + 400].lower()
            if not re.search(r"nativ|sustent|justific|no existe", ctx):
                out.append(h("NBK-06", path, m.group(0), None, nro_linea(codigo, pos)))
                break

    # ADB-NB-06 · parametros por widgets
    if en_process and activa("NBK-04"):
        if not re.search(r"dbutils\.widgets\.(get|text|dropdown)", limpio):
            out.append(h("NBK-04", path, "(no se encontraron widgets)"))
        m_cat = re.search(r"=\s*[\"']mb_(bronze|silver|gold)_(dev|qa|prod)[\"']", limpio)
        if m_cat:
            out.append(h("NBK-04", path, m_cat.group(0),
                         "Hay un catalogo fijo en el codigo.",
                         nro_linea(limpio, m_cat.start())))

    # ADB-NB-09 · nombres de DataFrame
    if activa("NBK-09"):
        for m in re.finditer(r"^(df\d*|aux|tmp|temp|x|data)\s*=(?!=)", limpio, re.M):
            out.append(h("NBK-09", path, m.group(1), None, nro_linea(limpio, m.start())))

    # ADB-NB-11 · longitud de linea
    if activa("NBK-11"):
        for n, ln in enumerate(codigo.split("\n"), 1):
            if len(ln) > LIMITES["linea"]:
                out.append(h("NBK-11", path, ln[:70],
                             f"La linea tiene {len(ln)} caracteres.", n))
                break

    # ADB-NB-15 · opciones que alteran la estructura
    if activa("NBK-15"):
        for m in re.finditer(r"(mergeSchema|overwriteSchema)", limpio):
            out.append(h("NBK-15", path, m.group(0), None, nro_linea(limpio, m.start())))

    # ADB-NB-19 · operaciones que trasladan datos
    if activa("NBK-19"):
        m = re.search(r"\.(collect|toPandas|take)\s*\(", limpio)
        if m:
            out.append(h("NBK-19", path, m.group(0), None, nro_linea(limpio, m.start())))

    return out


# -------------------------------------------------------- lakehouse · ADB-LH
def reglas_lakehouse(path, codigo):
    out = []
    limpio = sin_comentarios(codigo)
    permitidos = "|".join(LISTAS["formatos_persistencia"])

    if activa("LH-01"):
        for m in re.finditer(r"\.write[\s\S]{0,80}?format\s*\(\s*[\"'](\w+)[\"']", limpio):
            if m.group(1).lower() not in LISTAS["formatos_persistencia"]:
                out.append(h("LH-01", path, m.group(0)[:80],
                             f"Formatos permitidos: {permitidos}.",
                             nro_linea(limpio, m.start())))

    if activa("LH-02"):
        for m in re.finditer(r"[\"'](fec\w*|fecha\w*)[\"']\s*,\s*StringType\(\)", limpio):
            out.append(h("LH-02", path, m.group(0), None, nro_linea(limpio, m.start())))
    return out


# ---------------------------------------------------------- logging · ADB-NB
def reglas_logging(path, codigo):
    out = []
    limpio = sin_comentarios(codigo)

    hay_logger = bool(re.search(r"\blogger\s*\.", limpio))

    # ADB-NB-24 · se evalua siempre, haya o no logger
    if activa("NBK-24"):
        for m in re.finditer(r"^\s*print\s*\(", limpio, re.M):
            out.append(h("NBK-24", path, m.group(0).strip(),
                         None, nro_linea(limpio, m.start())))

    if not hay_logger:
        if activa("NBK-21"):
            out.append(h("NBK-21", path, "(no se encontro logger)",
                         "No hay registro de ejecucion."))
        return out

    if activa("NBK-21"):
        faltan = []
        if not re.search(r"logger\.(info|debug)\s*\(.*(inicio|start)", limpio, re.I):
            faltan.append("inicio")
        if not re.search(r"logger\.(info|debug)\s*\(.*(fin|end|termin)", limpio, re.I):
            faltan.append("fin")
        tiempo = re.search(r"(perf_counter|process_time|monotonic|time\.time\s*\()", limpio) \
            or re.search(r"logger\.\w+\s*\(.*(tiempo|duracion|segundos|elapsed)", limpio, re.I)
        if not tiempo:
            faltan.append("tiempos por etapa")
        if faltan:
            out.append(h("NBK-21", path, "(registro incompleto)",
                         "Falta: " + ", ".join(faltan)))

    if activa("NBK-22"):
        if not re.search(r"logger\.(info|debug)\s*\(.*(param|widget)", limpio, re.I):
            out.append(h("NBK-22", path, "(sin registro de parametros)"))

    if activa("NBK-23"):
        m_exc = re.search(r"^\s*except\b", limpio, re.M)
        if not m_exc:
            out.append(h("NBK-23", path, "(sin bloque try/except)",
                         "No se capturan excepciones."))
        else:
            if not re.search(r"logger\.(error|exception|critical)\s*\(", limpio):
                out.append(h("NBK-23", path, m_exc.group(0).strip(),
                             "Las excepciones no se registran.",
                             nro_linea(limpio, m_exc.start())))
            m_pass = re.search(r"except[^\n]*:\s*\n\s*pass\b", limpio)
            if m_pass:
                out.append(h("NBK-23", path, m_pass.group(0),
                             "El error se silencia.", nro_linea(limpio, m_pass.start())))

    return out


# ------------------------------------------------- SQL · ADB-NB-12/13, SQL-01
def reglas_sql(path, codigo):
    out = []
    for m in re.finditer(
            r"""spark\.sql\s*\(\s*(?:f?["']{1,3})([\s\S]{0,600}?)["']{1,3}\s*\)""",
            codigo):
        q = m.group(1)
        ln = nro_linea(codigo, m.start())

        if activa("NBK-12"):
            out.append(h("NBK-12", path, "spark.sql(" + " ".join(q.split())[:60], None, ln))

        if activa("SQL-01"):
            for kw in SQL_KEYWORDS:
                if re.search(rf"\b{kw}\b", q) and not re.search(rf"\b{kw.upper()}\b", q):
                    out.append(h("SQL-01", path, q[:80], f"Encontrado: {kw}.", ln))
                    break

        if activa("NBK-13") and re.search(r"select\s+\*", q, re.I):
            out.append(h("NBK-13", path, q[:80], None, ln))
    return out


def reglas_sql_celdas(path, celdas, codigo):
    """SQL-01 y ADB-NB-13 sobre celdas SQL del notebook.

    ADB-NB-12 no aplica: una celda SQL no es una consulta embebida en texto.
    """
    out = []
    for pos, fuente in celdas or []:
        q = re.sub(r"^\s*%sql\b", "", fuente, count=1)
        cuerpo = re.sub(r"^\s*-{2,}.*$", "", q, flags=re.M)   # sin comentarios
        ln = nro_linea(codigo, pos)

        if activa("SQL-01"):
            for kw in SQL_KEYWORDS:
                if re.search(rf"\b{kw}\b", cuerpo) and not re.search(rf"\b{kw.upper()}\b", cuerpo):
                    out.append(h("SQL-01", path, cuerpo[:80],
                                 f"Encontrado: {kw}. En una celda SQL.", ln))
                    break

        if activa("NBK-13") and re.search(r"select\s+\*", cuerpo, re.I):
            out.append(h("NBK-13", path, cuerpo[:80], "En una celda SQL.", ln))
    return out


# ------------------------------------------------------ rutas · ADL-DDL-01..04
def reglas_rutas(path, codigo):
    """Verifica las rutas de almacenamiento declaradas en el codigo."""
    out = []
    rutas = LISTAS.get("rutas_almacenamiento", {})
    if not rutas:
        return out

    mapa = {"bronze": "ADL-02", "silver": "ADL-03", "gold": "ADL-04"}

    for m in re.finditer(r"abfss://([a-z0-9\-]+)@([^\"'\s\)]+)", codigo, re.I):
        contenedor = m.group(1).lower()
        uri = m.group(0)
        ln = nro_linea(codigo, m.start())
        rid = mapa.get(contenedor)
        if not rid:
            continue
        if not activa(rid):
            continue
        patron = rutas.get(contenedor)
        if patron and not re.match(patron, uri, re.I):
            out.append(h(rid, path, uri, None, ln))

    if activa("ADL-01"):
        patron = rutas.get("bridge")
        if patron:
            for m in re.finditer(r"[\"'](/[^\"']*MB_PERU[^\"']*)[\"']", codigo, re.I):
                if not re.match(patron, m.group(1), re.I):
                    out.append(h("ADL-01", path, m.group(1),
                                 None, nro_linea(codigo, m.start())))
    return out


# ------------------------------------------------------------ DDL · ADB-DDL-*
def _capa(objeto):
    for capa in ("bronze", "silver", "gold"):
        if f"mb_{capa}_" in objeto.lower():
            return capa
    return None


def reglas_ddl(path, codigo):
    out = []
    for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"([`\w.]+)\s*\(([\s\S]*?)\)\s*(?:USING|COMMENT|PARTITIONED|"
            r"CLUSTER|TBLPROPERTIES|;|$)", codigo, re.I):
        objeto = m.group(1).replace("`", "")
        cuerpo = m.group(2)
        bloque = codigo[m.start():m.start() + 3000]
        tabla = objeto.split(".")[-1]
        ln = nro_linea(codigo, m.start())

        # ADB-DDL-01 · catalogo y jerarquia
        if activa("DDL-01"):
            if not any(c in objeto.lower() for c in LISTAS["catalogos"]):
                out.append(h("DDL-01", path, objeto, "Catalogo no oficial.", ln))
            elif objeto.count(".") != 2:
                out.append(h("DDL-01", path, objeto,
                             "Se esperaba catalogo.esquema.tabla.", ln))

        # ADB-DDL-01 · prefijo por capa
        capa = _capa(objeto)
        if capa and activa("DDL-02"):
            validos = tuple(LISTAS["prefijos_tabla"][capa])
            if not tabla.lower().startswith(validos):
                out.append(h("DDL-02", path, tabla,
                             f"Prefijos de la capa {capa}: " + ", ".join(validos), ln))

        # ADB-DDL-10 · nombre en snake_case
        if activa("DDL-10") and (tabla != tabla.lower()
                                 or not re.match(r"^[a-z][a-z0-9_]*$", tabla)):
            out.append(h("DDL-10", path, tabla, None, ln))

        # ADB-DDL-11 · caracteres no permitidos
        if activa("DDL-11") and any(ch in tabla for ch in ACENTOS):
            out.append(h("DDL-11", path, tabla, None, ln))

        # ADB-DDL-12 · longitud
        if activa("DDL-12") and len(tabla) > LIMITES["nombre_tabla"]:
            out.append(h("DDL-12", path, tabla,
                         f"Tiene {len(tabla)} caracteres.", ln))

        # ADB-DDL-13 · comentarios
        if activa("DDL-13") and not re.search(r"\bCOMMENT\b", bloque, re.I):
            out.append(h("DDL-13", path, objeto, None, ln))

        # ADB-DDL-14 · formato de almacenamiento
        if activa("DDL-14") and not re.search(r"USING\s+DELTA", bloque, re.I):
            out.append(h("DDL-14", path, objeto, None, ln))

        # ADB-DDL-02 · campos tecnicos de auditoria
        if activa("DDL-05"):
            low = bloque.lower()
            faltan = [c for c in ("_ingestion_time", "_processing_time") if c not in low]
            if faltan:
                out.append(h("DDL-05", path, objeto, "Faltan: " + ", ".join(faltan), ln))

        # ADB-DDL-06 · etiquetas de la tabla
        if activa("DDL-06"):
            m_tags = re.search(r"TBLPROPERTIES\s*\(([\s\S]*?)\)", bloque, re.I)
            if not m_tags:
                out.append(h("DDL-06", path, objeto, "No se declaran etiquetas.", ln))
            else:
                props = m_tags.group(1).lower()
                faltan = [t for t in LISTAS["tags_tabla"] if t not in props]
                if faltan:
                    out.append(h("DDL-06", path, objeto,
                                 "Faltan: " + ", ".join(faltan), ln))

        # ADB-DDL-16 a 20 · campos
        dac = False
        for lc in cuerpo.split(","):
            mc = re.match(r"\s*`?([A-Za-z_][\w]*)`?\s+([A-Za-z]+)", lc.strip())
            if not mc:
                continue
            campo, tipo = mc.group(1), mc.group(2).upper()
            if campo.startswith("_"):
                continue
            if activa("DDL-16") and (campo != campo.lower()
                                     or not re.match(r"^[a-z][a-z0-9_]*$", campo)):
                out.append(h("DDL-16", path, campo, None, ln))
            if activa("DDL-17") and any(ch in campo for ch in ACENTOS):
                out.append(h("DDL-17", path, campo, None, ln))
            if activa("DDL-18") and len(campo) > LIMITES["nombre_campo"]:
                out.append(h("DDL-18", path, campo,
                             f"Tiene {len(campo)} caracteres.", ln))
            if activa("DDL-19"):
                pre = campo.split("_")[0]
                if pre not in LISTAS["prefijos_campo"]:
                    out.append(h("DDL-19", path, campo,
                                 "Prefijo no reconocido.", ln))
                elif pre in ("mto", "val") and tipo in ("FLOAT", "DOUBLE"):
                    out.append(h("DDL-19", path, f"{campo} {tipo}",
                                 "Se espera un tipo decimal.", ln))
            if campo.endswith("_dac"):
                dac = True

        if dac and activa("DDL-20") and \
                not re.search(r"dac\s*['\"]?\s*[=:]\s*['\"]?\s*si", bloque, re.I):
            out.append(h("DDL-20", path, objeto, None, ln))
    return out


# ------------------------------------------------------ workflows · ADB-WF-*
def reglas_workflow(path, texto):
    out = []
    try:
        wf = json.loads(texto)
    except json.JSONDecodeError:
        return [h("FMT-01", path, texto[:120], "No es un JSON valido.")]

    nombre = wf.get("name", "") or os.path.splitext(os.path.basename(path))[0]

    if activa("WF-01"):
        if not re.match(r"^wf_[a-z0-9]+_[a-z0-9_]+$", nombre):
            out.append(h("WF-01", path, nombre))
        elif len(nombre) > LIMITES["nombre_workflow"]:
            out.append(h("WF-01", path, nombre,
                         f"Tiene {len(nombre)} caracteres."))

    # ADB-WF-02 · abreviatura de proyecto
    if activa("WF-02"):
        abrev = LISTAS.get("abreviaturas_proyecto") or []
        partes = nombre.split("_")
        if abrev and len(partes) >= 2 and partes[1] not in abrev:
            out.append(h("WF-02", path, partes[1]))

    if activa("WF-03"):
        tags = {k.lower(): str(v).lower() for k, v in (wf.get("tags") or {}).items()}
        faltan = [t for t in LISTAS["tags_workflow"] if t not in tags]
        if faltan:
            out.append(h("WF-03", path, ", ".join(sorted(tags)) or "(sin etiquetas)",
                         "Faltan: " + ", ".join(faltan)))
        impacto = tags.get("business_impact", "")
        if impacto and impacto not in LISTAS["impacto_valido"]:
            out.append(h("WF-03", path, impacto,
                         "Valores validos: " + ", ".join(LISTAS["impacto_valido"]) + "."))
        if "schedule" in tags and not tags["schedule"].strip():
            out.append(h("WF-03", path, "schedule", "No declara frecuencia."))

    if activa("WF-04") and "deploy/workflows/" not in path.replace("\\", "/").lower():
        out.append(h("WF-04", path, path))

    return out


def reglas_operaciones(path, codigo):
    """ADB-WF-05 · operaciones atomicas fuera del ejecutor centralizado."""
    if not activa("WF-05"):
        return []
    ejecutor = LISTAS.get("ejecutor_centralizado", "")
    if not ejecutor or ejecutor in codigo:
        return []
    out = []
    limpio = sin_comentarios(codigo)
    m = re.search(r"\bALTER\s+TABLE\b[\s\S]{0,120}?\b(ADD|DROP|RENAME)\b", limpio, re.I)
    if m:
        out.append(h("WF-05", path, m.group(0)[:80], None, nro_linea(limpio, m.start())))
    return out


# ------------------------------------------------------- repositorio · ADB-WS
def macroprocesos_tocados(rutas):
    """Carpeta que contiene al tipo de artefacto. Devuelve la ruta relativa."""
    tipos = {c.lower() for c in LISTAS["carpetas_macroproceso"]}
    ignoradas = set(OPCIONES["carpetas_excluidas"]) | {"deploy", "shared"}
    out = set()
    for r in rutas:
        partes = r.replace("\\", "/").split("/")
        for i, p in enumerate(partes):
            if p.lower() in tipos and i > 0:
                if partes[i - 1].lower() in ignoradas:
                    break
                out.add("/".join(partes[:i]))
                break
    return sorted(out)


def reglas_repositorio(raiz, macros):
    """Verifica la estructura del arbol. Requiere el repositorio descargado."""
    out = []

    # ADB-WS-02 · carpetas transversales
    if activa("WS-02"):
        for carpeta, subs in LISTAS["carpetas_transversales"].items():
            base = os.path.join(raiz, carpeta)
            if not os.path.isdir(base):
                out.append(h("WS-02", carpeta + "/", "(no existe)",
                             f"Falta la carpeta {carpeta}."))
                continue
            faltan = [s for s in subs if not os.path.isdir(os.path.join(base, s))]
            if faltan:
                out.append(h("WS-02", carpeta + "/", ", ".join(faltan),
                             "Faltan subcarpetas: " + ", ".join(faltan) + "."))

    for macro in macros:
        base = os.path.join(raiz, macro)
        if not os.path.isdir(base):
            continue

        # ADB-WS-01 · macroproceso autocontenido
        if activa("WS-01"):
            hay = [c for c in LISTAS["carpetas_macroproceso"]
                   if os.path.isdir(os.path.join(base, c))]
            if not hay:
                out.append(h("WS-01", macro + "/", "(sin carpetas del estandar)"))

        # ADB-WS-03 · las seis carpetas
        if activa("WS-03"):
            faltan = [c for c in LISTAS["carpetas_macroproceso"]
                      if not os.path.isdir(os.path.join(base, c))]
            if faltan:
                out.append(h("WS-03", macro + "/", ", ".join(faltan),
                             "Faltan: " + ", ".join(faltan) + "."))
            ddl = os.path.join(base, "ddl")
            if os.path.isdir(ddl) and not os.path.isdir(os.path.join(ddl, "schema_migrations")):
                out.append(h("WS-03", macro + "/ddl/", "(sin schema_migrations)",
                             "Falta la carpeta de migraciones."))

        # ADB-WS-04 · prefijo por tipo de artefacto
        if activa("WS-04"):
            for carpeta, prefijos in LISTAS["prefijos_artefacto"].items():
                dirc = os.path.join(base, carpeta)
                if not os.path.isdir(dirc):
                    continue
                for nombre in sorted(os.listdir(dirc)):
                    if not os.path.isfile(os.path.join(dirc, nombre)):
                        continue
                    if not nombre.endswith(tuple(OPCIONES["extensiones"])):
                        continue
                    if not any(nombre.startswith(p) for p in prefijos):
                        out.append(h("WS-04", f"{macro}/{carpeta}/{nombre}", nombre,
                                     "Se esperaba: " + " o ".join(prefijos) + "."))
    return out


# --------------------------------------------------------------- ADF · ADF-*
def reglas_adf(path, texto):
    out = []
    nombre = os.path.splitext(os.path.basename(path))[0]
    bajo = path.lower()

    try:
        doc = json.loads(texto)
        carpeta = (doc.get("properties", {}).get("folder", {}) or {}).get("name", "")
        nombre = doc.get("name") or nombre
    except (json.JSONDecodeError, AttributeError):
        carpeta = ""

    if "/pipeline" in bajo:
        if activa("ADF-PIP-01"):
            nivel = carpeta.split("/")[0] if carpeta else ""
            if nivel not in LISTAS["carpetas_pipeline"]:
                out.append(h("ADF-PIP-01", path, carpeta or "(sin carpeta)",
                             "Carpetas validas: " + ", ".join(LISTAS["carpetas_pipeline"]) + "."))
        if activa("ADF-PIP-02"):
            if not re.match(r"^pipeline_(master|load)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$", nombre):
                out.append(h("ADF-PIP-02", path, nombre))

    elif "/dataset" in bajo:
        if activa("ADF-DS-01"):
            if carpeta not in LISTAS["rutas_dataset"]:
                out.append(h("ADF-DS-01", path, carpeta or "(sin carpeta)",
                             "Rutas registradas: " + ", ".join(LISTAS["rutas_dataset"]) + "."))
        if activa("ADF-DS-02"):
            if not re.match(r"^ds_(parquet|delta|oracle|csv|sql|bin)_[a-z0-9]+_(in|out)$",
                            nombre, re.I):
                out.append(h("ADF-DS-02", path, nombre))
    return out


# ----------------------------------------------------------------- despacho
def evaluar(path, texto):
    """Aplica el conjunto de reglas que corresponde al tipo de archivo."""
    bajo = path.lower()

    if bajo.endswith(".json"):
        if "workflows" in bajo.replace("\\", "/").split("/"):
            return reglas_workflow(path, texto)
        return reglas_adf(path, texto)

    if bajo.endswith(".sql"):
        return (reglas_ddl(path, texto) + reglas_sql(path, texto)
                + reglas_rutas(path, texto) + reglas_operaciones(path, texto))

    celdas_sql = []
    if bajo.endswith(".ipynb"):
        codigo, markdown, celdas_sql = extraer_codigo_ipynb(texto)
        if codigo is None:
            return [h("FMT-01", path, texto[:120], "No es un JSON valido.")]
    else:
        codigo, markdown = texto, ""

    out = reglas_taxonomia(path)
    out += reglas_notebook(path, codigo, markdown)
    out += reglas_logging(path, codigo)
    out += reglas_lakehouse(path, codigo)
    out += reglas_sql(path, codigo)
    out += reglas_sql_celdas(path, celdas_sql, codigo)
    out += reglas_ddl(path, codigo)
    out += reglas_rutas(path, codigo)
    out += reglas_operaciones(path, codigo)

    if "/process/" in bajo and activa("TAX-03"):
        m_ddl = re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", sin_comentarios(codigo), re.I)
        if m_ddl:
            out.append(h("TAX-03", path, m_ddl.group(0),
                         "Hay definicion de tablas en una carpeta de proceso."))
    return out


def aplicable(path):
    """Las carpetas excluidas son las de la raiz del repositorio.

    Se compara el primer segmento y no cualquier nivel: de lo contrario la
    carpeta config de un macroproceso quedaria fuera de la evaluacion.
    """
    p = path.replace("\\", "/").lstrip("./")
    if not p.lower().endswith(tuple(OPCIONES["extensiones"])):
        return False
    raiz = p.split("/")[0].lower()
    return raiz not in {c.lower() for c in OPCIONES["carpetas_excluidas"]}


# -------------------------------------------------------------------- salida
def escribir_veredicto(hallazgos, evaluados):
    bloqueantes = [x for x in hallazgos if x["criticidad"] == "OBL"]
    veredicto = {
        "catalogo": CAT["version"],
        "checklist": CAT["checklist"],
        "nodo": "1-determinista",
        "estado_global": "RECHAZADO" if bloqueantes else "APROBADO",
        "archivos_evaluados": evaluados,
        "hallazgos": hallazgos,
    }
    with open("veredicto_desarrollo.json", "w", encoding="utf-8") as f:
        json.dump(veredicto, f, ensure_ascii=False, indent=2)

    print(f"ESTADO: {veredicto['estado_global']} | catalogo: {CAT['version']} | "
          f"archivos: {len(evaluados)} | hallazgos: {len(hallazgos)} "
          f"({len(bloqueantes)} obligatorios)")
    for x in hallazgos:
        ubic = f":{x['linea']}" if x["linea"] else ""
        print(f"  [{x['criticidad']}] {x['codigo']} {x['archivo']}{ubic}")
        print(f"        {x['mensaje']}")
        print(f"        -> {x['correccion']}")
    return bloqueantes


# ---------------------------------------------------------------------- main
def archivos_del_pr(repo, pr, token):
    req = urllib.request.Request(
        f"{API}/repos/{repo}/pulls/{pr}/files?per_page=100",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def modo_local(rutas):
    """Ejecuta el validador sobre archivos sueltos, sin abrir un Pull Request."""
    hallazgos, evaluados = [], []
    for path in rutas:
        if not os.path.isfile(path):
            print(f"No existe: {path}")
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            texto = f.read()
        evaluados.append(path)
        hallazgos += evaluar(path, texto)

    macros = macroprocesos_tocados(evaluados)
    if macros:
        hallazgos += reglas_repositorio(".", macros)

    bloqueantes = escribir_veredicto(hallazgos, evaluados)
    return 1 if bloqueantes else 0


def main():
    if "--local" in sys.argv:
        i = sys.argv.index("--local")
        cargar_catalogo()
        return modo_local(sys.argv[i + 1:])

    cargar_catalogo()

    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        ev = json.load(f)

    repo = os.environ["GITHUB_REPOSITORY"]
    pr = ev["pull_request"]["number"]
    token = os.environ["GITHUB_TOKEN"]

    hallazgos, evaluados = [], []

    for a in archivos_del_pr(repo, pr, token):
        path = a["filename"]
        if a["status"] == "removed" or not aplicable(path) or not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            texto = f.read()
        evaluados.append(path)
        hallazgos += evaluar(path, texto)

    macros = macroprocesos_tocados(evaluados)
    if macros:
        hallazgos += reglas_repositorio(".", macros)

    bloqueantes = escribir_veredicto(hallazgos, evaluados)
    sys.exit(1 if bloqueantes else 0)


if __name__ == "__main__": sys.exit(main() or 0)
