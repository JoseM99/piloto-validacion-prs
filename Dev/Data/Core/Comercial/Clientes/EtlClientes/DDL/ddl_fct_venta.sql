CREATE TABLE mb_gold_prod.comercial.fct_venta (
    cod_venta STRING COMMENT 'codigo',
    mto_venta DECIMAL(18,2) COMMENT 'monto'
) USING DELTA COMMENT 'ventas';