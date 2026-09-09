-- ---------------------------------------------------------------------------
-- PROYECTO  : Data Warehouse Comercial - Ventas
-- OBJETO    : mb_gold_prod.comercial.fct_venta
-- CAPA      : Publicacion
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mb_gold_prod.comercial.fct_venta (
    cod_venta         STRING         COMMENT 'Codigo unico de la venta',
    mto_venta         DECIMAL(18,2)  COMMENT 'Monto total de la venta',
    _ingestion_time   TIMESTAMP      COMMENT 'Marca de ingesta del registro',
    _processing_time  TIMESTAMP      COMMENT 'Marca de procesamiento del registro'
)
USING DELTA
COMMENT 'Hechos de ventas del area comercial'
TBLPROPERTIES (
    'frecuencia' = 'diaria',
    'naturaleza' = 'transaccional',
    'tipo_tabla' = 'hechos',
    'owner'      = 'comercial',
    'dac'        = 'no'
);
