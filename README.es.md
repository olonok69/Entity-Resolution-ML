# Demo de resolución de entidades de clientes

English version: [README.md](README.md)

Una demo de resolución de identidad de clientes que cabe en un portátil, con registros sintéticos de clientes del Reino Unido cuya verdad se conoce. Compara reglas fuzzy hechas a mano, Splink sin supervisión y un clasificador supervisado de pares; repara los clusters con técnicas de grafos, y después construye un mini MDM, un *customer spine* gobernado, ids estables entre ejecuciones y el MLOps que rodea al matcher de ML (*feature store*, registro de modelos y monitorización).

## Por dónde empezar

- [Visión general del proyecto y resultados](er-demo/README.md) (en inglés)
- [La guía: ejecutarla, aprender cada técnica paso a paso y preguntas frecuentes](er-demo/DEMO_GUIDE.es.md)
- [Guion del vídeo](er-demo/VIDEO_SCRIPT.es.md) y [diapositivas](er-demo/slides/customer-identity-resolution.pptx) (en inglés)

## Inicio rápido

Desde la raíz del repositorio, en Windows PowerShell:

```powershell
cd er-demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe data/generate_data.py
.\.venv\Scripts\python.exe 01_rules_rapidfuzz.py
.\.venv\Scripts\python.exe 02_splink.py
.\.venv\Scripts\python.exe 03_ml_recordlinkage.py
.\.venv\Scripts\python.exe 04_graph_resolution.py
.\.venv\Scripts\python.exe 05_mdm.py
.\.venv\Scripts\python.exe 06_customer_spine.py
.\.venv\Scripts\python.exe 07_identity_drift.py
.\.venv\Scripts\python.exe 08_mlops_feature_store.py
.\.venv\Scripts\python.exe 09_compare.py
```

En macOS o Linux, crea y activa `.venv`, instala `requirements.txt` y ejecuta `bash run_all.sh` desde `er-demo/`.

Los CSV de entrada generados y los resultados de `results/` se excluyen de Git a propósito. Ejecuta el generador y el pipeline para volver a crearlos. `05_mdm.py` reinicia su base de datos local de DuckDB en cada ejecución, y `08_mlops_feature_store.py` reinicia el feature store y el registro de modelos.

## Estructura del proyecto

```text
er-demo/
  common/       estandarización y evaluación compartidas
  data/         generador de datos sintéticos
  databricks/   ejemplo de Databricks/SparkAPI (no ejecutado)
  zingg/        ejemplo de active learning con Zingg (no ejecutado)
  slides/       diapositivas del vídeo
  results/      resultados generados (ignorados por git)
  01_*.py ...   enfoques de matching, reparación por grafos, MDM, spine, deriva, MLOps, informe
```

Todos los registros son sintéticos. `true_entity_id` y `true_household_id` son etiquetas de referencia que solo se usan para evaluar y para el entrenamiento supervisado; no son campos de matching de producción. Los ejemplos de Databricks y Zingg necesitan sus propios entornos y el pipeline local no los verifica.
