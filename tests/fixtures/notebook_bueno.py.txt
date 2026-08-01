# notebook_bueno.py  (cumple los lineamientos)
df = spark.sql("SELECT id, monto, codmes FROM calidad.gold.ventas")
df = df.withColumn("fecrutina", current_timestamp())
df.write.format("delta").partitionBy("codmes").saveAsTable("calidad.gold.ventas_out")

