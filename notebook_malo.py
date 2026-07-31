df = spark.sql("SELECT * FROM ventas")        # rompe SQL-01
password = "1234secreto"                       # rompe SEG-01
df.write.save("/mnt/datos/salida")  
