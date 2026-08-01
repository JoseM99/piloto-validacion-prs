---
name: mibanco.lakehouse-desarrollo
version: 1.0.0
fuentes:
  - "Checklist CoE Data Engineering v2 — LMDK v4.0 (filas 4-6, 24-51, 64-66, 72-74)"
  - "Documento de Estándares de Desarrollo Lakehouse — Tribu de Datos / COE Data & Analytics (v001, 15/12/2025)"
description: Estándares de DESARROLLO del Lakehouse de MiBanco — nomenclatura de Azure Data Factory, taxonomía de workspace, estructura de notebooks Databricks, Python, PySpark, performance, logging, SQL y buenas prácticas Lakehouse. Úsala siempre que revises un Pull Request que toque notebooks .ipynb, archivos .py, .sql o definiciones de ADF del ecosistema Lakehouse. NO cubre modelamiento de datos (catálogos, DDL, campos, tags, DAC) — para eso usa mibanco.lakehouse-modelamiento; ni el gobierno del PR (rama, asunto, descripción) — para eso usa mibanco.pr-gobierno.
---

# Estándares de Desarrollo Lakehouse — MiBanco

Cubre 37 de las 76 validaciones del Checklist v2 del CoE. Cada regla lleva
el ID compartido con la columna **Regla ID** del Excel y el **Nº** de su
fila, para que un hallazgo del PR se pueda rastrear hasta el checklist.

Marca de verificación:

- **[N1]** la valida el Nodo 1 con regex. **No la reportes**, ya está
  cubierta; si la mencionas, duplicas el hallazgo.
- **[N2]** requiere leer el contexto. Esto es lo tuyo.

Criticidad: **OBL** bloquea el merge · **OPC** es recomendación.

---

## 0. Qué reportar y qué no

Léelo antes de emitir cualquier hallazgo.

**Reporta solo si puedes citar el fragmento exacto del diff que incumple.**
Si no puedes copiar la línea culpable, no es un hallazgo.

**No reportes:**

- Reglas marcadas **[N1]** — ya las cubre el Nodo 1.
- Código que no aparece en el diff. Solo se evalúa lo que cambió.
- Cosas que *podrían* pasar sin evidencia en el código: tamaños de datos,
  volúmenes, longitudes que no están declaradas.
- Nombres que cumplen la regla pero "podrían ser mejores".
- Reglas de otras skills: catálogos, prefijos de tabla, campos, tags y
  DAC son de `mibanco.lakehouse-modelamiento`.

**Ante la duda, no reportes.** Un falso positivo cuesta más que un hallazgo
omitido: entrena al equipo a ignorar al validador.

Si sospechas algo pero no puedes probarlo, va a `requiere_revision_humana`,
no a `hallazgos`.

---

## 1. Azure Data Factory (ADF)

Aplica solo si el PR toca pipelines o datasets.

**Pipelines:** `pipeline_[funcionalidad]_[aplicación]_[tipo]`

- `funcionalidad`: `master` (orquestación) · `load batch` · `load stream`
- `aplicación`: `TPZ` (Topaz) · `DWH` · `TMS` (Temenos) · `SAT` (satélites) ·
  `DET` (data entries) · `SBX` (sandbox)
- `tipo`: tipo de carga — fecha, mes, full o stream

**Datasets:** `ds_[tipo]_[aplicacion]_[conexion]`

- `tipo`: `parquet` · `delta` · `oracle` · `csv` · `bin`
- `conexion`: fuente, indicando si es de entrada (`in`) o salida (`out`)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| ADF-01 | 4 | Nombre de pipeline cumple el patrón y usa valores válidos | [N1] | OBL |
| ADF-02 | 5 | Pipeline guardado en la ruta estándar según funcionalidad | [N1] | OBL |
| ADF-03 | 6 | Dataset cumple `ds_[tipo]_[aplicacion]_[conexion]` con conexión in/out | [N1] | OBL |

Ejemplos válidos: `pipelines/Master/pipeline_master_QUIPU` ·
`pipelines/Load Batch/TPZ/pipeline_load_TPZ_Fecha` ·
`datasets/BaseDatos/Oracle/ds_oracle_dwh_in`

---

## 2. Taxonomía del workspace (TAX)

```
/Workspace/Data/<fuente>/<origen>/<concepto>/<proceso>/<tipo>
```

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| TAX-01 | 24 | El notebook está en la ruta taxonómica completa | [N1] | OBL |
| TAX-02 | 25 | `<fuente>` ∈ Data, Core, Satelites, Apps, Dataentrys | [N1] | OBL |
| TAX-03 | 26 | `<tipo>` ∈ Process, Config, DDL, Metadata, Utils | [N1] | OBL |

**Regla derivada, y de las más útiles:** un notebook en `/Process/` no debe
contener DDL. Si ves `CREATE TABLE`, `ALTER TABLE` o `DROP TABLE` dentro de
un notebook de proceso, repórtalo como TAX-03 — el objeto está en la
carpeta equivocada. Cruza con PYS-04.

---

## 3. Estructura del notebook (NBK)

Seis secciones, en orden: cabecera · librerías · funciones · parámetros ·
variables y constantes · inicio de proceso.

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| NBK-01 | 27 | Cabecera completa: objetivo, versión, desarrollador, fecha | [N1] | OBL |
| NBK-02 | 28 | Librerías en sección propia y ordenadas (Python, terceros, locales) | [N1] | OBL |
| NBK-03 | 29 | Funciones en sección propia con docstrings; UDFs solo si no hay nativa | [N1] | OBL |
| NBK-04 | 30 | Parámetros por `dbutils.widgets`, nunca hardcodeados | [N1] | OBL |
| NBK-05 | 31 | Variables y constantes centralizadas al inicio (catálogos, esquemas, rutas) | [N2] | OBL |

NBK-04 es OBL por una razón práctica: en producción ADF pasa sus parámetros
a los widgets, así que el mismo código corre en prueba y en producción. Un
valor fijo rompe esa portabilidad.

---

## 4. Python (PY)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| PY-01 | 32 | Naming: variables en snake_case con el prefijo/sufijo que corresponde | [N1] | OBL |
| PY-02 | 33 | DataFrames con nombres descriptivos (`df_saldos_filtrado`) | [N2] | OBL |
| PY-03 | 34 | Comentarios que expliquen el porqué de la lógica compleja | [N2] | OPC |
| PY-04 | 35 | Longitud de línea controlada — **ver nota** | [N1] | OPC |

**Sufijos de variable:** `df` · `field` · `col` · `path` · `type` · `id` ·
`file` · `perc` · `desc` · `amount` · `date` · `num` · `len`

**Prefijos de función:** `get` · `add` · `group` · `list` · `select` ·
`calculate` · `read` · `write` · `join` · `validate` · `sort` · `drop` ·
`append`

> **PY-04 está en conflicto.** El Checklist v2 dice ~120 caracteres; el
> documento de estándares dice máximo 80. Mientras no se resuelva, **no
> reportes esta regla**.

---

## 5. PySpark (PYS)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| PYS-01 | 36 | Preferir la API de PySpark sobre Spark SQL embebido en strings | [N2] | OBL |
| PYS-02 | 37 | `select()` obligatorio para proyectar solo las columnas necesarias | [N2] | OBL |
| PYS-03 | 38 | Column pruning desde la lectura y filtros lo más temprano posible | [N2] | OBL |
| PYS-04 | 39 | Prohibido `mergeSchema` y `overwriteSchema`; los cambios de estructura van por `ALTER TABLE` | [N1] | OBL |
| PYS-05 | 40 | Revisar duplicados en las llaves antes de un join | [N2] | OPC |
| PYS-06 | 41 | `broadcast()` solo con tablas pequeñas | [N2] | OPC |
| PYS-07 | 42 | `repartition()` solo con justificación (implica shuffle completo) | [N2] | OPC |
| PYS-08 | 43 | `coalesce()` para reducir particiones antes de escribir | [N2] | OPC |

**Sobre PYS-06:** no afirmes que un DataFrame es grande o pequeño si el
código no lo dice. Sin evidencia en el diff, no hay hallazgo.

**Sobre PYS-03**, el patrón correcto filtra y proyecta desde la lectura:

```python
df = spark.table("mb_silver.rcc.hd_rcc") \
    .select("cod_cliente", "mto_deuda") \
    .filter(F.col("fec_proceso") == var_fecha_proceso)
```

---

## 6. Performance (PERF)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| PERF-01 | 44 | Sin uso **injustificado** de `collect()`, `toPandas()` o `take()` | [N2] | OBL |

Es regla de juicio, no determinista: el estándar permite estas funciones
sobre datasets pequeños y controlados. Reporta solo cuando el contexto
muestre que se aplica sobre un volumen no acotado.

```python
max_mes = df.select(F.max("nro_periodo_mes")).collect()[0][0]   # observable
max_mes = df.select(F.max("nro_periodo_mes")).first()[0]        # correcto
```

---

## 7. Logging (LOG)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| LOG-01 | 45 | Registro de inicio de proceso (`logger.info` con nombre y timestamp) | [N1] | OBL |
| LOG-02 | 46 | Registro de fin de proceso con resultado y registros procesados | [N1] | OBL |
| LOG-03 | 47 | Registro de los parámetros de entrada recibidos | [N1] | OBL |
| LOG-04 | 48 | Registro de tiempos por etapa (lectura, transformación, escritura) | [N2] | OBL |
| LOG-05 | 49 | Errores y excepciones capturados y registrados con `logger.error` | [N2] | OBL |
| LOG-06 | 50 | No existen `print()`: toda salida va por el logger | [N1] | OBL |
| LOG-07 | 51 | Niveles correctos: INFO flujo normal, WARN anomalías, ERROR crítico, DEBUG solo en desarrollo | [N2] | OBL |

Razón de LOG-06: `print()` no respeta niveles, no se registra en ADF/Jobs y
no queda en los logs oficiales, así que rompe la auditoría.

---

## 8. SQL (SQL)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| SQL-01 | 64 | Keywords en mayúsculas: `SELECT`, `FROM`, `WHERE`, `JOIN`, `GROUP BY` | [N1] | OPC |
| SQL-02 | 65 | Alias descriptivos (`FROM ms_saldos AS sal`), no letras sueltas | [N2] | OPC |
| SQL-03 | 66 | No existe `SELECT *` — **ver nota** | [N1] | OBL |

> **SQL-03 está en conflicto.** El Checklist v2 lo prohíbe de plano; el
> documento de estándares lo permite acotado con `LIMIT 5`. Hasta que se
> defina, el Nodo 1 lo emite como observación y no como bloqueo.

---

## 9. Buenas prácticas Lakehouse (BP)

| ID | Nº | Regla | Verif. | Crit. |
|---|---|---|---|---|
| BP-01 | 72 | Formatos Delta (preferido) o Parquet; CSV/JSON solo como insumo | [N1] | OBL |
| BP-02 | 73 | Rutas de lectura/escritura parametrizadas (variables o widgets) | [N2] | OBL |
| BP-03 | 74 | Campos de fecha con tipos nativos DATE o TIMESTAMP, nunca texto | [N1] | OBL |

---

## 10. Formato de salida

Devuelve JSON. Sin texto antes ni después.

```json
{
  "hallazgos": [
    {
      "regla_id": "PERF-01",
      "checklist_nro": 44,
      "archivo": "Dev/Data/Core/Topaz/.../Process/nb_ejemplo.ipynb",
      "evidencia": "max_mes = df.select(F.max(\"nro_periodo_mes\")).collect()[0][0]",
      "explicacion": "Trae datos al driver sobre un dataset no acotado; usar first().",
      "criticidad": "OBL",
      "confianza": "alta"
    }
  ],
  "requiere_revision_humana": [],
  "sin_hallazgos_en": ["archivo_b.ipynb"]
}
```

Obligatorios: `regla_id`, `checklist_nro`, `archivo`, `evidencia`, `criticidad`.

`evidencia` es copia literal del diff. Si no la tienes, el hallazgo va a
`requiere_revision_humana`.

`confianza`: `alta` cuando la evidencia es inequívoca; `media` cuando
depende de contexto que no ves. Nunca declares `alta` sin cita literal.
