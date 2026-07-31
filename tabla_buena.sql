CREATE TABLE mb_silver_prod.mmff.m_party (
    party_id STRING COMMENT 'identificador unico del cliente',
    nom_cliente_dac STRING COMMENT 'nombre del cliente',
    _ingestion_time TIMESTAMP COMMENT 'fecha de ingesta',
    _processing_time TIMESTAMP COMMENT 'fecha de proceso'
)
COMMENT 'tabla maestra de clientes del modelo mmff'
TBLPROPERTIES ('Frecuencia'='Mensual','Naturaleza'='Propia','Tipo_Tabla'='maestra','Data_Owner'='Andrea Vicuna','Dac'='SI')
