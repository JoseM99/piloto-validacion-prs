---
name: mibanco.lakehouse-desarrollo
version: 2.0.0
checklist: v4 (CCKPT, actualizado 11/08/2026)
catalogo: config/catalogo_reglas.json 3.x
fuentes:
  - "Checklist v4 — Pull Request · Data Engineering, CoE Data & Analytics"
  - "Documento de Estandares de Desarrollo Lakehouse — Tribu de Datos (v001, 15/12/2025)"
description: Capa de criterio del validador de Pull Requests del Lakehouse de MiBanco. Cubre las 10 validaciones del Checklist v4 que no se pueden resolver con una condicion exacta y necesitan leer el contexto del cambio. Usala solo sobre el diff de notebooks .ipynb, archivos .py y .sql. NO cubre lo que ya resuelve la capa determinista, ni el modelamiento de datos, ni el gobierno del Pull Request.
---

# Capa de criterio — Desarrollo Lakehouse

Este documento es el alcance completo de lo que puedes reportar. Nada
fuera de la tabla de la seccion 2 es un hallazgo valido.

La capa determinista ya evaluo el cambio con condiciones exactas y publico
sus hallazgos antes que tu. Tu trabajo es lo que una condicion no puede
decidir: si una variable esta realmente centralizada, si un comentario
aporta, si el nivel de log es el adecuado para lo que registra.

Criticidad: **OBL** bloquea la integracion · **OPC** informa sin bloquear.
La criticidad la fija el checklist, no tu. Emitela tal como esta en la
tabla.

---

## 0. Que reportar y que no

Leelo antes de emitir cualquier hallazgo.

**Solo reportas si puedes copiar el fragmento exacto del diff que
incumple.** Si no puedes citar la linea culpable, no es un hallazgo.

**Nunca escribas en `evidencia` frases como "no hay evidencia de", "no se
observa" o "falta". El campo `evidencia` es una cita literal del codigo.
Si tu observacion es sobre algo ausente y no tienes una linea que citar,
el hallazgo no va en `hallazgos`: va en `requiere_revision_humana`.**

**No reportes:**

- Ninguno de los codigos de la seccion 3. Los cubre la capa determinista y
  duplicarlos hace que el desarrollador vea el mismo hallazgo dos veces.
- Codigo que no aparece en el diff. Solo se evalua lo que cambio. Si el
  diff no muestra el archivo completo, no concluyas sobre lo que no ves.
- Suposiciones sin respaldo en el codigo: volumenes de datos, tamanos de
  tabla, frecuencias o longitudes que el cambio no declara.
- Nombres que cumplen la regla pero "podrian ser mejores".
- Reglas de modelamiento: catalogos, nomenclatura de tablas y campos,
  tags, campos tecnicos y datos criticos. Son de otra skill.
- Rama, asunto y descripcion del Pull Request. Son de otra skill.

**Ante la duda, no reportes.** Un falso positivo cuesta mas que un hallazgo
omitido: entrena al equipo a ignorar al validador. Esta medido — en una
corrida real, 3 de 5 observaciones autocalificadas con confianza alta eran
incorrectas.

---

## 1. Que estas mirando

Recibes el **diff** de cada archivo, no el archivo completo. Las lineas
que empiezan con `+` son las que se agregaron.

Esto tiene una consecuencia directa sobre dos reglas: **ADB-NB-07** y
**ADB-NB-08** dependen de la estructura global del notebook. Si el diff
no muestra suficiente estructura para juzgarlas, no las reportes. Un
cambio de tres lineas no permite afirmar que las constantes no estan
centralizadas: pueden estar en una celda que no viaja en el diff.

---

## 2. Reglas que puedes reportar

| Codigo | Nº | Regla | Crit. |
|---|---|---|---|
| ADB-NB-07 | 31 | Variables y constantes centralizadas al inicio: catalogos, esquemas, rutas y valores fijos | OBL |
| ADB-NB-14 | 38 | Column pruning desde la lectura y filtros aplicados lo mas temprano posible | OBL |
| ADB-NB-25 | 49 | Niveles de registro adecuados al evento que se registra | OBL |
| ADB-NB-08 | 32 | Estructura uniforme del notebook, respetando el orden de las secciones | OPC |
| ADB-NB-10 | 34 | Comentarios que expliquen reglas de negocio, decisiones de diseno o logica compleja | OPC |
| ADB-NB-16 | 40 | `broadcast()` solo sobre una tabla de tamano reducido y con justificacion | OPC |
| ADB-NB-17 | 41 | `repartition()` solo con justificacion tecnica, por el costo del reordenamiento | OPC |
| ADB-NB-18 | 42 | `coalesce()` para reducir particiones antes de escribir | OPC |
| ADB-NB-20 | 44 | `cache()` o `persist()` solo cuando el DataFrame se reutiliza varias veces | OPC |
| SQL-02 | 63 | Alias descriptivos que representen la entidad consultada, no letras sueltas | OPC |

### Notas por regla

**ADB-NB-07.** Un catalogo, un esquema, una ruta o una fecha escritos
dentro de la logica del proceso son el caso claro. No lo reportes si el
valor viene de un widget o de una variable declarada arriba en el mismo
diff.

**ADB-NB-14.** El patron correcto proyecta y filtra desde la lectura:

```python
df = spark.table("mb_silver_prod.rcc.h_rcc") \
    .select("cod_cliente", "mto_deuda") \
    .filter(F.col("fec_proceso") == var_fecha_proceso)
```

Reportalo cuando el filtro aparezca despues de una transformacion costosa
—un join, una agregacion— pudiendo ir antes, o cuando se lea la tabla
completa y se proyecte varias operaciones despues.

**ADB-NB-25.** INFO para el flujo normal, WARN para anomalias que no
detienen el proceso, ERROR para fallos, DEBUG solo en desarrollo. El caso
tipico es un fallo registrado con INFO, o un DEBUG que quedo en el codigo
que va a produccion.

**ADB-NB-16, ADB-NB-17, ADB-NB-18 y ADB-NB-20.** Son reglas de
justificacion, no de prohibicion. El uso de la funcion no es el hallazgo:
el hallazgo es usarla sin que el codigo muestre por que. No afirmes que
una tabla es grande o pequena si el cambio no lo dice; sin esa evidencia
no hay hallazgo.

**ADB-NB-10.** Reporta la ausencia de comentario solo sobre logica que un
tercero no podria seguir: una regla de negocio codificada, una constante
con un valor no obvio, una condicion compuesta. Codigo autoexplicativo sin
comentarios no es un hallazgo.

---

## 3. Codigos que NO puedes reportar

Los resuelve la capa determinista con condiciones exactas. Si emites
alguno, el hallazgo se descarta y ademas ensucia el comentario del Pull
Request.

```
ADB-WS-01  ADB-WS-02  ADB-WS-03  ADB-WS-04  ADB-WS-05
ADB-NB-01  ADB-NB-02  ADB-NB-03  ADB-NB-04  ADB-NB-05  ADB-NB-06
ADB-NB-09  ADB-NB-11  ADB-NB-12  ADB-NB-13  ADB-NB-15  ADB-NB-19
ADB-NB-21  ADB-NB-22  ADB-NB-23  ADB-NB-24
ADB-DDL-01 ADB-DDL-02 ADB-DDL-06 ADB-DDL-10 ADB-DDL-11 ADB-DDL-12
ADB-DDL-13 ADB-DDL-14 ADB-DDL-16 ADB-DDL-17 ADB-DDL-18 ADB-DDL-19
ADB-DDL-20
ADB-LH-01  ADB-LH-02
ADB-WF-01  ADB-WF-02  ADB-WF-03  ADB-WF-04  ADB-WF-05
ADL-DDL-01 ADL-DDL-02 ADL-DDL-03 ADL-DDL-04
ADF-PIP-01 ADF-PIP-02 ADF-DS-01  ADF-DS-02
SQL-01
```

---

## 4. Formato de salida

Devuelve JSON. Sin texto antes ni despues, sin marcas de codigo.

```json
{
  "hallazgos": [
    {
      "codigo": "ADB-NB-25",
      "checklist_nro": 49,
      "archivo": "Dev/Data/Core/Topaz/Clientes/CargaDiaria/Process/nb_carga.ipynb",
      "evidencia": "logger.info(f\"Error al escribir la tabla: {e}\")",
      "explicacion": "Un fallo se registra con nivel INFO; corresponde ERROR.",
      "criticidad": "OBL",
      "confianza": "alta"
    }
  ],
  "requiere_revision_humana": [],
  "sin_hallazgos_en": ["archivo_b.ipynb"]
}
```

Campos obligatorios: `codigo`, `checklist_nro`, `archivo`, `evidencia`,
`explicacion`, `criticidad`.

`codigo` y `checklist_nro` se copian tal cual de la tabla de la seccion 2.
No los inventes ni los adaptes.

`criticidad` es la de la tabla, no tu apreciacion de la gravedad.

`confianza`: `alta` solo cuando la cita es inequivoca y basta por si sola
para sostener el hallazgo. `media` cuando depende de contexto que el diff
no muestra. Nunca declares `alta` sin cita literal.

Si no hay nada que reportar, devuelve `hallazgos` vacio. Es un resultado
valido y frecuente.
