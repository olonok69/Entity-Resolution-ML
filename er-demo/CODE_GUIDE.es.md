# Guía del código: cada script, línea a línea

English version: [CODE_GUIDE.md](CODE_GUIDE.md)

Esta guía explica en detalle cada script de Python de la demo. Cada bloque de código enlaza con las líneas exactas que describe, indica la diapositiva de la presentación ([slides/customer-identity-resolution.pptx](slides/customer-identity-resolution.pptx)) donde se muestra la idea y remite a la sección correspondiente de la [DEMO_GUIDE](DEMO_GUIDE.es.md) para la teoría. El propio código está comentado en inglés, instrucción a instrucción, así que puedes leer el script y esta guía en paralelo.

Cómo usarla:
- Si un término es nuevo, lee primero los conceptos de la [DEMO_GUIDE](DEMO_GUIDE.es.md) y después vuelve aquí para ver cómo lo hace el código.
- Abre el script junto a esta página. Enlaces como [01_rules_rapidfuzz.py#L73-L92](01_rules_rapidfuzz.py#L73-L92) saltan a esas líneas en GitHub.
- Los bloques "Qué deberías ver" son las líneas exactas que imprime el script con la semilla fija (42) y las versiones de `requirements.txt`, así que tu ejecución debería coincidir cifra a cifra.
- Los números de línea corresponden a la versión actual de cada archivo. Si editas un script, los enlaces posteriores a tu cambio se desplazarán.

## Contenido

1. [Orden de ejecución](#orden-de-ejecución)
2. [Mapa de diapositivas al código](#mapa-de-diapositivas-al-código)
3. Código compartido: [data/generate_data.py](#datagenerate_datapy), [common/standardise.py](#commonstandardisepy), [common/evaluate.py](#commonevaluatepy)
4. Emparejamiento: [01_rules_rapidfuzz.py](#01_rules_rapidfuzzpy), [02_splink.py](#02_splinkpy), [03_ml_recordlinkage.py](#03_ml_recordlinkagepy)
5. Grafos: [04_graph_resolution.py](#04_graph_resolutionpy)
6. Gestión de maestros: [05_mdm.py](#05_mdmpy), [06_customer_spine.py](#06_customer_spinepy), [07_identity_drift.py](#07_identity_driftpy)
7. MLOps: [08_mlops_feature_store.py](#08_mlops_feature_storepy)
8. Informe y lanzador: [09_compare.py](#09_comparepy), [run_all.sh](#run_allsh)
9. No se ejecutan en local: [databricks/splink_on_databricks.py](#databrickssplink_on_databrickspy), [zingg/zingg_customers.py](#zinggzingg_customerspy)

## Orden de ejecución

```text
data/generate_data.py      -> data/customers.csv, data/new_batch.csv
01_rules_rapidfuzz.py      -> results/clusters_rapidfuzz.csv, review_queue_rapidfuzz.csv, metrics_rapidfuzz.csv
02_splink.py               -> results/clusters_splink.csv, pairs_splink.csv, splink_model.json, review_queue_splink.csv, splink_threshold_sweep.csv, metrics_splink.csv
03_ml_recordlinkage.py     -> results/pairs_ml_features.csv, metrics_ml.csv
04_graph_resolution.py     -> results/clusters_graph.csv, shared_identifiers.csv, metrics_graph.csv
05_mdm.py                  -> results/mdm.duckdb, mdm_golden_record.csv, mdm_xref.csv, mdm_review_queue.csv
06_customer_spine.py       -> results/customer_spine.csv, identity_hierarchy.csv, spine_contracts.csv, metrics_households.csv
07_identity_drift.py       -> results/id_alias.csv, id_events.csv, identity_drift.csv
08_mlops_feature_store.py  -> results/feature_store.duckdb, model_registry/, model_versions.csv, monitoring_report.csv
09_compare.py              -> results/comparison.md (the table behind slide 27)
```

Todos los scripts usan la limpieza compartida de [common/standardise.py](common/standardise.py) y las métricas compartidas de [common/evaluate.py](common/evaluate.py), así que todos los comparadores se puntúan de la misma forma.

## Mapa de diapositivas al código

| Diapositiva | Tema | Dónde está en el código |
|---|---|---|
| 2, 5 | Una persona, tres sistemas; datos sintéticos | [data/generate_data.py](#datagenerate_datapy) |
| 4 | Pipeline | [Orden de ejecución](#orden-de-ejecución), [run_all.sh](#run_allsh) |
| 7 | *Blocking* | [01_rules_rapidfuzz.py](#01_rules_rapidfuzzpy) `candidate_pairs()`, reglas de *blocking* de [02_splink.py](#02_splinkpy) |
| 8 | Tres formas de puntuar un par | [01](#01_rules_rapidfuzzpy) `score()`, [02](#02_splinkpy), [03](#03_ml_recordlinkagepy) |
| 9, 10 | Fellegi-Sunter, m/u, sumar bits | [02_splink.py](#02_splinkpy) |
| 11, 12 | Características y etiquetas supervisadas | [03_ml_recordlinkage.py](#03_ml_recordlinkagepy) |
| 13 | Precisión o recall | umbrales en [01](#01_rules_rapidfuzzpy), [02](#02_splinkpy), [03](#03_ml_recordlinkagepy); métricas en [common/evaluate.py](#commonevaluatepy) |
| 15, 16, 17 | Por qué engañan las puntuaciones de pares, cannot-link, corte mínimo | [04_graph_resolution.py](#04_graph_resolutionpy) |
| 19 | Mini MDM | [05_mdm.py](#05_mdmpy) |
| 20 | *Customer spine* y jerarquía | [06_customer_spine.py](#06_customer_spinepy) |
| 21 | Deriva de identidad | [07_identity_drift.py](#07_identity_driftpy) |
| 23, 24 | *Feature store*, registro, puerta, monitorización | [08_mlops_feature_store.py](#08_mlops_feature_storepy) |
| 25, 26 | *Lakehouse* y framework a escala | [databricks/splink_on_databricks.py](#databrickssplink_on_databrickspy), [zingg/zingg_customers.py](#zinggzingg_customerspy) |
| 27 | Gráfico de resultados | [09_compare.py](#09_comparepy) |

---

## data/generate_data.py

**Qué hace:** construye el experimento. Inventa con Faker 4,400 personas "verdaderas" y limpias, agrupa a algunas en hogares de dos y después escribe varias copias deliberadamente sucias de las primeras 4,000 personas repartidas en tres sistemas de origen (CRM, WEB, BILLING). También escribe un lote posterior de 400 registros, la mitad de personas que vuelven y la otra mitad de personas totalmente nuevas. Como las personas existen antes que sus copias, cada registro lleva el id de la persona a la que pertenece de verdad, y eso es lo que permite que todos los pasos posteriores cuenten fusiones erróneas y enlaces perdidos.

**Ejecución:** `python data/generate_data.py` (primera línea de [run_all.sh](run_all.sh)). Tarda un par de segundos.

**Lee / Escribe:** no lee nada. Escribe `data/customers.csv` (población inicial) y `data/new_batch.csv` (carga incremental que leen `05_mdm.py`, `06_customer_spine.py`, `07_identity_drift.py` y `08_mlops_feature_store.py`). Las columnas `true_entity_id` y `true_household_id` son claves de respuesta solo para evaluar; ningún comparador las usa como característica ni como clave de *blocking*.

**Diapositivas:** 2 (Una persona, tres sistemas), 5 (Datos sintéticos), 20 (los hogares alimentan el *customer spine*).

**Guía:** [3.1 El problema](DEMO_GUIDE.es.md#31-el-problema), [0. Generar el experimento](DEMO_GUIDE.es.md#0-generar-el-experimento-datagenerate_datapy), [1. Ejecutar la demo](DEMO_GUIDE.es.md#1-ejecutar-la-demo).

**Recorrido**

1. [data/generate_data.py#L1-L22](data/generate_data.py#L1-L22) Docstring del módulo: qué ruido se inyecta, por qué hacen falta datos sintéticos (solo puedes medir la ER cuando conoces la respuesta), las salidas y las diapositivas relacionadas.
2. [data/generate_data.py#L24-L37](data/generate_data.py#L24-L37) Importaciones. `random` decide cada tirada de moneda del ruido, `Faker` genera nombres y direcciones con aspecto británico, y el proveedor `date_time` de Faker se importa dos veces porque se parchea más abajo.
3. [data/generate_data.py#L39-L49](data/generate_data.py#L39-L49) Parámetros del experimento y semillas. `SEED`, `N_ENTITIES`, `N_NEW_BATCH` y `HOUSEHOLD_RATE` controlan todo lo posterior; fijar la semilla de `random` y de Faker hace que cada ejecución produzca datos idénticos, y por eso las cifras de la demo son reproducibles (diapositiva 5).
4. [data/generate_data.py#L52-L63](data/generate_data.py#L52-L63) Parche `_rand_seconds`. Faker elige marcas de tiempo aleatorias con `randint` en Windows y con `uniform` en el resto de sistemas, así que la misma semilla producía personas distintas según el sistema operativo. Forzar `uniform` da el mismo conjunto de datos en todas partes.
5. [data/generate_data.py#L66-L76](data/generate_data.py#L66-L76) `_FixedNow` congela "hoy" en 2026-10-19 para que las edades y las marcas de tiempo de "los últimos 3 años" no se muevan con el calendario. Sin esto, repetir la ejecución el mes que viene cambiaría las fechas de nacimiento y los valores de `updated_at`.
6. [data/generate_data.py#L78-L105](data/generate_data.py#L78-L105) `NICKNAMES` (de nombre formal a apodo, para inyectar ruido; [common/standardise.py](common/standardise.py) tiene el mapa inverso), los tres `SOURCES` de la diapositiva 2 y la carpeta de salida `OUT`.
7. [data/generate_data.py#L108-L127](data/generate_data.py#L108-L127) `typo()`: un error de teclado por llamada (transposición, borrado, inserción o sustitución) en una posición interior. Son justo las ediciones que las comparaciones por distancia de edición y Jaro-Winkler están pensadas para perdonar (diapositiva 8).
8. [data/generate_data.py#L130-L146](data/generate_data.py#L130-L146) `phone_format()`: el mismo número escrito en bruto, con espacios, en formato internacional `+44` o con guiones. Es ruido puramente de formato, que `clean_phone()` elimina; muestra por qué la estandarización va antes del emparejamiento (diapositiva 4).
9. [data/generate_data.py#L149-L178](data/generate_data.py#L149-L178) `make_entity()`: una persona limpia de referencia. Al 25% se le fuerza un nombre de pila que tiene apodo, para que el problema de los apodos aparezca de verdad; el email es `first.last[nn]@provider`.
10. [data/generate_data.py#L181-L252](data/generate_data.py#L181-L252) `noisy_copy()`: el corazón del generador. Copia una persona en un registro de origen y aplica ruido independiente: apodos, erratas, nombre y apellido intercambiados, mayúsculas ([L194-L209](data/generate_data.py#L194-L209)); día y mes de la DOB intercambiados o DOB ausente ([L211-L216](data/generate_data.py#L211-L216)); email ausente, con errata o en mayúsculas, como mucho una de las tres ([L218-L227](data/generate_data.py#L218-L227)); teléfono ausente o con otro formato ([L229-L230](data/generate_data.py#L229-L230)); mudanza o dirección abreviada y formato del código postal ([L232-L246](data/generate_data.py#L232-L246)); y huecos propios de cada fuente, WEB sin dirección y BILLING sin DOB ([L247-L251](data/generate_data.py#L247-L251)). La rama de "mudanza" es importante: crea coincidencias verdaderas sin ninguna evidencia de dirección, y por eso ningún campo por sí solo puede decidir una coincidencia (diapositiva 9).
11. [data/generate_data.py#L255-L283](data/generate_data.py#L255-L283) `add_households()`: agrupa a 220 personas (el 10% de 4,400) en hogares de dos personas que comparten dirección; el 60% comparte además apellido y el 25%, un buzón familiar como `thesmiths@gmail.com`. Usa su propio `random.Random(SEED + 1)` para que añadir hogares no desplace el ruido a nivel de persona. Estos hogares crean el riesgo de fusión errónea de "personas distintas, misma dirección y mismo apellido" (diapositivas 15 a 17) y el problema de los identificadores compartidos en `04_graph_resolution.py`.
12. [data/generate_data.py#L286-L301](data/generate_data.py#L286-L301) `main()`, población inicial: crea las 4,400 personas, añade los hogares y después asigna a cada una de las primeras 4,000 personas entre 1 y 3 sistemas de origen (35/40/25%) y un 7% de probabilidad de un duplicado dentro del mismo sistema.
13. [data/generate_data.py#L303-L315](data/generate_data.py#L303-L315) Lote nuevo: las posiciones pares son una persona existente al azar (debería asociarse a un cliente existente) y las impares, una de las personas extra reservadas (debería convertirse en un cliente nuevo). Este reparto 50/50 es lo que hace medible el "197/200 clientes recurrentes asociados correctamente" de `05_mdm.py`.
14. [data/generate_data.py#L317-L341](data/generate_data.py#L317-L341) Fija el orden de las columnas, baraja las filas con `sample(frac=1)` para que los duplicados no queden contiguos y escribe los dos CSV.
15. [data/generate_data.py#L342-L349](data/generate_data.py#L342-L349) Imprime las tres líneas de resumen, incluido cuántos hogares de los datos iniciales tienen realmente dos personas.

**Qué deberías ver**

```text
customers.csv: 8192 records for 4000 people
new_batch.csv: 400 records
households with 2 people: 183
```

8,192 registros para 4,000 personas son unos 2.05 registros por persona, así que la mayoría de las personas tiene al menos un duplicado que encontrar. 183 es menos que los 220 hogares creados porque las parejas se sacaron de las 4,400 personas y algunos convivientes están entre las 400 reservadas para el lote nuevo.

**Prueba esto**

1. Pon `HOUSEHOLD_RATE = 0.30` y vuelve a ejecutar todo el pipeline: más personas comparten dirección y apellido, así que suben las fusiones erróneas en `01_rules_rapidfuzz.py` y `02_splink.py`, y la reparación con grafos de `04_graph_resolution.py` tiene más que cortar.
2. Sube la probabilidad de mudanza de [L232](data/generate_data.py#L232) de 0.15 a 0.40: coincidir en la dirección pasa a ser una evidencia más débil, el recall baja y Splink aprende una `m` menor para la dirección.
3. Cambia `SEED` a 7: todas las cifras se mueven un poco, lo que muestra cuánto de la diferencia entre comparadores es ruido y cuánto es un efecto real.

---

## common/standardise.py

**Qué hace:** el paso de limpieza compartido que todos los comparadores ejecutan antes del *blocking* y la puntuación. Unas funciones `clean_*` pequeñas eliminan las diferencias puramente de formato (mayúsculas, acentos, tratamientos, formatos de teléfono, espacios del código postal, puntos y etiquetas con `+` de Gmail), y `standardise()` las aplica a un DataFrame completo y añade claves derivadas: un nombre de pila canónico para los apodos, códigos fonéticos, la parte de usuario del email y el área del código postal. Ejecutar una única función en todas partes hace que los comparadores de reglas, Splink y ML vean exactamente las mismas entradas, así que sus resultados son comparables.

**Ejecución:** no se ejecuta directamente. Lo importan con `from common.standardise import standardise` los pasos `01` a `05`, `07` y `08` (`05_mdm.py` también lo usa para el lote incremental).

**Lee / Escribe:** ningún archivo. La entrada es el DataFrame en bruto de `data/customers.csv` o `data/new_batch.csv`; la salida es una copia limpia con las columnas extra `unique_id`, `first_name_canon`, `email_user`, `postcode_area`, `surname_metaphone` y `first_metaphone`.

**Diapositivas:** 4 (Pipeline, fase de estandarización), 7 (*Blocking*: las claves derivadas son claves de *blocking*), 8 (Tres formas de puntuar un par: las tres puntúan estos campos limpios), 10 (Robert Smith vs Bob Smyth: el mapa de apodos y metaphone son lo que hace que ese par se parezca).

**Guía:** [3.2 Estandarización](DEMO_GUIDE.es.md#32-estandarización), [3.3 Agrupación por claves (*blocking*, indexación)](DEMO_GUIDE.es.md#33-agrupación-por-claves-blocking-indexación), [Base compartida](DEMO_GUIDE.es.md#base-compartida-commonstandardisepy).

**Recorrido**

1. [common/standardise.py#L1-L16](common/standardise.py#L1-L16) Docstring del módulo: por qué estandarizar primero (las diferencias de formato no deberían costar evidencia de coincidencia), la entrada, las columnas de salida y las diapositivas.
2. [common/standardise.py#L18-L25](common/standardise.py#L18-L25) Importaciones: `re` para expresiones regulares, `unicodedata` para quitar acentos y `jellyfish` para el código fonético Metaphone.
3. [common/standardise.py#L27-L55](common/standardise.py#L27-L55) `NICKNAMES`: de apodo a nombre formal. Es el inverso del mapa del generador más algunas formas extra (`rob`, `will`, `beth`, `jimmy`, `katie`). Es el paso de "Bob" a "robert" de la diapositiva 10.
4. [common/standardise.py#L56-L58](common/standardise.py#L56-L58) `TITLES`: una expresión regular compilada que elimina tratamientos (`mr`, `dr.`, ...) solo como palabras completas.
5. [common/standardise.py#L61-L73](common/standardise.py#L61-L73) `clean_name()`: vacío a `None`, acentos eliminados con NFKD, minúsculas, tratamientos eliminados y después solo se conservan letras, espacios, apóstrofos y guiones. Devolver `None` en lugar de `""` importa: Splink y las características de ML tratan `None` como "sin evidencia" y no como un desacuerdo.
6. [common/standardise.py#L76-L88](common/standardise.py#L76-L88) `clean_email()`: minúsculas, quita la `+etiqueta` y elimina los puntos solo en Gmail, porque solo Gmail los ignora. Aplicar la regla de los puntos a todos los proveedores crearía coincidencias de email falsas.
7. [common/standardise.py#L91-L101](common/standardise.py#L91-L101) `clean_phone()`: conserva los dígitos, convierte un `44` inicial en `0` y rechaza todo lo que tenga menos de 10 dígitos. Después de esto, los cuatro formatos de `phone_format()` del generador se reducen a un único valor, así que coincidir exactamente en el teléfono pasa a ser una evidencia fuerte.
8. [common/standardise.py#L104-L112](common/standardise.py#L104-L112) `clean_postcode()`: mayúsculas, quita los espacios y vuelve a insertar el espacio antes de los 3 últimos caracteres (el *inward code* británico).
9. [common/standardise.py#L115-L153](common/standardise.py#L115-L153) `standardise()`: copia la entrada (los valores en bruto siguen disponibles para los *golden records*), asigna `unique_id` (el nombre de columna que exige Splink), limpia los nombres y construye `first_name_canon` ([L121-L128](common/standardise.py#L121-L128)), limpia el email y añade `email_user` ([L129-L131](common/standardise.py#L129-L131)), limpia el teléfono y el código postal y añade `postcode_area` ([L132-L136](common/standardise.py#L132-L136)), normaliza los espacios de la dirección ([L137-L140](common/standardise.py#L137-L140)), convierte la DOB a `YYYY-MM-DD` y deja como ausentes los valores que no se pueden interpretar ([L141-L143](common/standardise.py#L141-L143)) y, por último, añade los códigos Metaphone del apellido y del nombre canónico ([L144-L152](common/standardise.py#L144-L152)). `smith` y `smyth` se codifican los dos como `SM0`, así que una regla de *blocking* sobre `dob + surname_metaphone` los empareja a pesar de la diferencia de ortografía (diapositiva 7).

**Qué deberías ver:** este módulo no imprime nada. Su efecto aparece en la línea de *blocking* del paso siguiente, `blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}` de `01_rules_rapidfuzz.py`: el 96.5% de los pares verdaderos sobrevive al *blocking* con estas claves limpias, mientras se descarta el 99.98% de los 33.5 millones de pares posibles. También puedes inspeccionarlo directamente:

```python
import pandas as pd
from common.standardise import standardise
standardise(pd.read_csv("data/customers.csv")).head()
```

**Prueba esto**

1. Quita la rama de Gmail ([L85-L87](common/standardise.py#L85-L87)) y vuelve a ejecutar `01_rules_rapidfuzz.py`: no esperes casi ningún cambio, porque el generador nunca añade puntos en Gmail. Es un recordatorio de que una regla solo ayuda si ese ruido existe en tus datos.
2. Vacía el diccionario `NICKNAMES`: `first_name_canon` pasa a ser igual a `first_name`, la regla de *blocking* `first_name_canon + last_name` pierde los pares Bob/Robert y bajan la completitud de pares y el recall.
3. Cambia `clean_phone()` para que devuelva `d` sin comprobar la longitud: los números cortos y rotos empiezan a coincidir exactamente, lo que puede crear fusiones erróneas.

---

## common/evaluate.py

**Qué hace:** el evaluador con clave de respuesta que comparten todos los pasos. `evaluate_clusters()` compara los clústeres predichos con `true_entity_id` y devuelve precisión/recall/F1 por pares, precisión/recall/F1 B-cubed, número de entidades, el clúster más grande, los pares de fusión errónea y los pares perdidos. `blocking_recall()` mide cuántos pares verdaderos sobreviven al *blocking*. `union_find_clusters()` convierte los enlaces de pares aceptados en clústeres (componentes conexas). Como todos los comparadores se puntúan con el mismo código, las cifras de la comparación final son equivalentes.

**Ejecución:** no se ejecuta directamente. Lo importan `01_rules_rapidfuzz.py`, `02_splink.py`, `03_ml_recordlinkage.py`, `04_graph_resolution.py`, `06_customer_spine.py` (hogares) y `08_mlops_feature_store.py`.

**Lee / Escribe:** ningún archivo. Las entradas son ids de registro, etiquetas de clúster predichas y etiquetas verdaderas; la salida es un `dict` normal que cada paso imprime y guarda como una fila de `results/metrics_*.csv`.

**Diapositivas:** 12 (Etiquetas: la verdad hace posible medir), 13 (Precisión o recall), 15 (Por qué engañan las puntuaciones de pares: el encadenamiento de union-find y `largest_cluster`), 27 (Gráfico de resultados, construido con estas métricas).

**Guía:** [3.9 Métricas de calidad del emparejamiento](DEMO_GUIDE.es.md#39-métricas-de-calidad-del-emparejamiento), [Precisión o recall: ¿qué importa más?](DEMO_GUIDE.es.md#precisión-o-recall-qué-importa-más), [3.3 Agrupación por claves (*blocking*, indexación)](DEMO_GUIDE.es.md#33-agrupación-por-claves-blocking-indexación), [Paso 3. Encadenamiento](DEMO_GUIDE.es.md#paso-3-encadenamiento-chaining-por-qué-basta-una-arista-mala), [Evaluación compartida](DEMO_GUIDE.es.md#evaluación-compartida-commonevaluatepy).

**Recorrido**

1. [common/evaluate.py#L1-L16](common/evaluate.py#L1-L16) Docstring del módulo: las dos familias de métricas, las funciones auxiliares y cómo leer `false_merges_pairs`, `missed_pairs` y `largest_cluster`.
2. [common/evaluate.py#L18-L23](common/evaluate.py#L18-L23) Importaciones: `combinations` enumera pares sin orden; `Counter` construye un histograma de tamaños.
3. [common/evaluate.py#L26-L36](common/evaluate.py#L26-L36) `_pairs()`: para cada clúster, todos los pares ordenados de sus registros. Un clúster de tamaño k da k(k-1)/2 pares, y por eso los clústeres grandes dominan las métricas por pares: un solo clúster erróneo de 9 registros cuesta muchos pares.
4. [common/evaluate.py#L39-L52](common/evaluate.py#L39-L52) Métricas por pares en `evaluate_clusters()`: construye los conjuntos de pares predichos y verdaderos; precisión = pares fusionados correctos / pares fusionados, y recall = pares fusionados correctos / pares verdaderos (diapositiva 13).
5. [common/evaluate.py#L54-L70](common/evaluate.py#L54-L70) B-cubed: para cada registro, compara su clúster predicho con su clúster verdadero; la precisión es la parte de mi clúster que de verdad soy yo y el recall, la parte de mis registros reales con la que estoy agrupado. Promediar por registro da a cada registro el mismo peso, así que B-cubed es menos sensible a unos pocos clústeres grandes.
6. [common/evaluate.py#L72-L91](common/evaluate.py#L72-L91) El diccionario de resultados. `false_merges_pairs` y `missed_pairs` son diferencias entre los conjuntos de pares; `largest_cluster` es la alarma de encadenamiento. La línea 73 construye un histograma `sizes` que no se devuelve.
7. [common/evaluate.py#L94-L107](common/evaluate.py#L94-L107) `blocking_recall()`: completitud de pares (*pair completeness*, los pares verdaderos que el *blocking* conservó; es un techo para el recall, porque ningún modelo puede emparejar un par que nunca ve) y ratio de reducción (la proporción de los n(n-1)/2 pares posibles que se descartaron) (diapositiva 7).
8. [common/evaluate.py#L110-L131](common/evaluate.py#L110-L131) `union_find_clusters()`: una estructura de conjuntos disjuntos con *path halving*. Cada par aceptado une dos clústeres; A-B y B-C juntan a A y C aunque A-C tuviera una puntuación baja. Ese cierre transitivo es el efecto de encadenamiento que repara `04_graph_resolution.py` (diapositivas 15 a 17). Siempre gana la raíz más pequeña, así que los ids de clúster son deterministas.

**Qué deberías ver:** este módulo no imprime nada; sus diccionarios aparecen en la salida de otros pasos. Por ejemplo, `01_rules_rapidfuzz.py` imprime:

```text
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
quality: {'pair_precision': 0.9523, 'pair_recall': 0.9127, 'pair_f1': 0.9321, 'bcubed_precision': 0.9882, 'bcubed_recall': 0.9539, 'bcubed_f1': 0.9707, 'n_records': 8192, 'n_pred_entities': 4278, 'n_true_entities': 4000, 'largest_cluster': 9, 'false_merges_pairs': 267, 'missed_pairs': 510}
```

Léelo así: el 95.2% de los pares fusionados es correcto, pero se fusionaron 267 pares de personas distintas y se perdieron 510 pares verdaderos; 4,278 clientes predichos frente a 4,000 personas reales significa que, en conjunto, se fusiona de menos; el F1 B-cubed (0.971) es mayor que el F1 por pares (0.932) porque la puntuación por registro da más peso a los clústeres pequeños y correctos. Splink obtiene 198 fusiones erróneas / 205 pares perdidos, el comparador de ML 142 / 145 y, tras la reparación con grafos, 12 (Splink) y 9 (ML).

**Prueba esto**

1. En una consola de Python, llama a `evaluate_clusters([1, 2, 3, 4], ["a", "a", "a", "a"], [1, 1, 2, 2])`: un clúster fusionado con dos personas da una precisión por pares de 0.3333 (2 de 6 pares correctos), precisión B-cubed 0.5, recall 1.0 y 4 pares de fusión errónea: la fusión errónea de manual.
2. Llama a `union_find_clusters([1, 2, 3], [(1, 2), (2, 3)])`: los tres acaban en el clúster 1 aunque (1, 3) nunca se emparejó. Es el encadenamiento en tres líneas.
3. Compara la precisión por pares con la precisión B-cubed en la fila de rapidfuzz: la diferencia muestra cuánto pesan unos pocos clústeres grandes y erróneos en la puntuación por pares.

---

## 01_rules_rapidfuzz.py

**Qué hace.** El comparador hecho a mano. Limpia los registros, propone pares candidatos con cinco claves de *blocking* baratas, puntúa cada par con pesos elegidos a mano sobre similitudes de RapidFuzz y reparte las puntuaciones en tres franjas: coincidencia automática, revisión y no coincidencia. Las coincidencias automáticas se convierten en aristas de un grafo y las componentes conexas (Union-Find) son los clientes predichos. Es la línea base con la que se comparan los comparadores probabilístico y supervisado, y su `candidate_pairs()` se reutiliza en los pasos 3 y 8.

**Ejecución.** `python 01_rules_rapidfuzz.py` desde `er-demo/` (necesita `data/customers.csv`; `run_all.sh` lo crea antes).

**Lee / Escribe.** Lee `data/customers.csv`. Escribe `results/clusters_rapidfuzz.csv` (de registro a clúster), `results/review_queue_rapidfuzz.csv` (pares de la zona gris) y `results/metrics_rapidfuzz.csv` (una fila de métricas, que recoge `09_compare.py`).

**Diapositivas.** 4 (pipeline), 7 (*blocking*), 8 (tres formas de puntuar un par), 13 (precisión o recall) y 15 (por qué engañan las puntuaciones de pares) para el efecto de encadenamiento de Union-Find.

**Guía.** [3.2 Estandarización](DEMO_GUIDE.es.md#32-estandarización), [3.3 *Blocking*](DEMO_GUIDE.es.md#33-agrupación-por-claves-blocking-indexación), [3.4 Comparar y puntuar](DEMO_GUIDE.es.md#34-comparar-y-puntuar), [3.9 Métricas de calidad del emparejamiento](DEMO_GUIDE.es.md#39-métricas-de-calidad-del-emparejamiento), [Recorrido por el código 1](DEMO_GUIDE.es.md#1-comparador-hecho-a-mano-01_rules_rapidfuzzpy).

### Recorrido

1. [01_rules_rapidfuzz.py#L1-L20](01_rules_rapidfuzz.py#L1-L20) **Docstring del módulo.** Las cinco fases del comparador clásico (estandarizar, *blocking*, puntuar, aplicar umbrales, agrupar), además de entradas, salidas y diapositivas. La diapositiva 4 muestra el mismo pipeline.
2. [01_rules_rapidfuzz.py#L22-L48](01_rules_rapidfuzz.py#L22-L48) **Importaciones.** `itertools.combinations` construye todos los pares dentro de un bloque; `rapidfuzz.fuzz` da similitudes de texto en la escala 0..100. La línea de `sys.path` permite importar los módulos compartidos [common/evaluate.py](common/evaluate.py) (`blocking_recall`, `evaluate_clusters`, `union_find_clusters`) y [common/standardise.py](common/standardise.py) (`standardise`). Todos los comparadores usan la misma limpieza y las mismas métricas, y eso es lo que hace justa la comparación.
3. [01_rules_rapidfuzz.py#L50-L54](01_rules_rapidfuzz.py#L50-L54) **Umbrales.** `AUTO_MATCH = 0.80` y `REVIEW = 0.65` crean tres franjas. Solo la franja superior crea aristas; la intermedia es trabajo para un *data steward*. Mover estas cifras es el compromiso entre precisión y recall de la diapositiva 13.
4. [01_rules_rapidfuzz.py#L56-L70](01_rules_rapidfuzz.py#L56-L70) **`BLOCKING_KEYS`.** Cinco claves alternativas: email, teléfono, DOB + sonido del apellido, código postal + sonido del nombre y nombre canónico + apellido. Una clave de varias columnas exige que todas sean iguales. Las claves se unen, así que un par que se le escapa a una (por ejemplo, por falta de email) lo puede encontrar otra. Es la diapositiva 7.
5. [01_rules_rapidfuzz.py#L73-L92](01_rules_rapidfuzz.py#L73-L92) **`candidate_pairs()`.** Para cada clave: descarta los registros con la clave vacía (si no, todos los vacíos forman un bloque gigante), agrupa por la clave y añade todos los pares de cada bloque. Los bloques de más de 200 registros se saltan, porque un bloque de n registros cuesta n(n-1)/2 comparaciones y los bloques enormes suelen salir de valores genéricos compartidos. Los pares se ordenan para que (a, b) y (b, a) sean la misma tupla, y el conjunto elimina los pares encontrados por varias claves. Resultado: 6,405 pares en lugar de 33.5 millones (diapositiva 7).
6. [01_rules_rapidfuzz.py#L95-L103](01_rules_rapidfuzz.py#L95-L103) **`sim()`.** Devuelve `None` cuando falta alguno de los dos valores (sin evidencia, no desacuerdo); si no, la puntuación de RapidFuzz dividida entre 100. `fuzz.ratio` es una similitud normalizada basada en la distancia de edición; quien llama puede pasar otra función, como `token_set_ratio`.
7. [01_rules_rapidfuzz.py#L106-L155](01_rules_rapidfuzz.py#L106-L155) **`score()`.** Siete campos, cada uno una tupla (similitud, peso) con pesos que suman 1.0. Los nombres, el email y la dirección se comparan de forma difusa; la DOB, el teléfono y el código postal, de forma exacta (1.0 o 0.0), y valen `None` cuando falta alguno de los dos lados. Las líneas [L147-L155](01_rules_rapidfuzz.py#L147-L155) descartan los campos ausentes y dividen por los pesos que siguen en juego, así que un registro WEB sin dirección ni DOB no se penaliza por tener menos datos. Los pesos son conjeturas, y esa es justo la debilidad que corrige Fellegi-Sunter (diapositiva 8, fila "puntuación difusa ponderada").
8. [01_rules_rapidfuzz.py#L158-L172](01_rules_rapidfuzz.py#L158-L172) **Cargar, limpiar, *blocking*.** `standardise()` normaliza nombres, emails, teléfonos y códigos postales y añade las claves derivadas. `by_id` es un índice para buscar registros rápido. `blocking_recall()` usa la verdad sintética solo para medir cuántos pares verdaderos sobrevivieron al *blocking* (el techo del recall).
9. [01_rules_rapidfuzz.py#L174-L182](01_rules_rapidfuzz.py#L174-L182) **Puntuar y repartir en franjas.** Se puntúa cada par candidato, se convierte el resultado en un DataFrame y se separa en `matches` (>= 0.80) y `review` (de 0.65 a 0.80).
10. [01_rules_rapidfuzz.py#L184-L194](01_rules_rapidfuzz.py#L184-L194) **Agrupar y evaluar.** `union_find_clusters()` toma las componentes conexas de las aristas de coincidencia automática, así que A-B más B-C junta a A, B y C aunque A-C nunca se comparara. Esta transitividad es la razón por la que una sola arista mala puede fusionar a dos personas (diapositiva 15). `evaluate_clusters()` devuelve precisión/recall/F1 por pares y B-cubed, el clúster más grande, los pares de fusión errónea y los pares perdidos.
11. [01_rules_rapidfuzz.py#L196-L206](01_rules_rapidfuzz.py#L196-L206) **Guardar.** Clústeres, cola de revisión y una tabla de métricas de una fila etiquetada `rules + rapidfuzz`.
12. [01_rules_rapidfuzz.py#L209-L212](01_rules_rapidfuzz.py#L209-L212) **Punto de entrada.** `main()` solo se ejecuta cuando el archivo se lanza directamente, así que `03_ml_recordlinkage.py` y `08_mlops_feature_store.py` pueden importar `candidate_pairs()` sin ejecutar el comparador.

### Qué deberías ver

```
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
auto-matches: 5300, review queue: 334
quality: {'pair_precision': 0.9523, 'pair_recall': 0.9127, 'pair_f1': 0.9321, 'bcubed_precision': 0.9882, 'bcubed_recall': 0.9539, 'bcubed_f1': 0.9707, 'n_records': 8192, 'n_pred_entities': 4278, 'n_true_entities': 4000, 'largest_cluster': 9, 'false_merges_pairs': 267, 'missed_pairs': 510}
```

Cómo leerlo:
- ***Blocking***: 6,405 pares candidatos de unos 33.5 millones posibles (ratio de reducción del 99.98%). Una completitud de pares de 0.9649 significa que el 96.5% de los pares verdaderos está entre los candidatos, así que ningún comparador de esta demo puede superar ese recall por pares.
- **Franjas**: 5,300 pares se convirtieron en aristas y 334 irían a un *data steward*.
- **Calidad**: precisión por pares 0.952 con **267 pares de fusión errónea** y recall por pares 0.913 con **510 pares perdidos**. 4,278 clientes predichos frente a 4,000 reales significa que el comparador fusiona de menos (divide a las personas), mientras que el clúster más grande, de 9 registros, muestra algo de encadenamiento. Son las cifras más flojas de los tres comparadores, el punto de partida del gráfico de resultados (diapositiva 27).

### Prueba esto

1. **Sube `AUTO_MATCH` a 0.90** ([L54](01_rules_rapidfuzz.py#L54)). Menos aristas: bajan las fusiones erróneas, suben los pares perdidos y crece `n_pred_entities`. Bájalo a 0.70 y pasa lo contrario, con un `largest_cluster` mayor. Es la diapositiva 13 en la práctica.
2. **Quita la clave `["email"]`** de `BLOCKING_KEYS` ([L61](01_rules_rapidfuzz.py#L61)). Bajan los pares candidatos y la completitud de pares; el recall no se recupera por mucho que ajustes la puntuación, porque el *blocking* es un techo.
3. **Cambia un peso**, por ejemplo da 0.20 a `"postcode"` y 0.05 a `"email"` ([L127](01_rules_rapidfuzz.py#L127), [L141](01_rules_rapidfuzz.py#L141)). Los miembros de un mismo hogar (misma dirección y código postal) empiezan a fusionarse, lo que muestra lo sensibles que son los pesos elegidos a mano.

---

## 02_splink.py

**Qué hace.** El comparador probabilístico. Describe a Splink un modelo Fellegi-Sunter (reglas de *blocking* más siete comparaciones de campos, cada una con una escalera de niveles), lo entrena sin ninguna etiqueta (primero el *prior*, después `u` a partir de pares aleatorios y luego `m` con tres sesiones de EM), puntúa los pares candidatos y agrupa con p >= 0.95. También hace un barrido de varios umbrales, guarda el modelo entrenado como JSON para los pasos posteriores y genera tres gráficos que hacen visibles los pesos.

**Ejecución.** `python 02_splink.py` desde `er-demo/` (se ejecuta en local sobre DuckDB; la versión de Databricks cambia a `SparkAPI`, consulta [databricks/splink_on_databricks.py](databricks/splink_on_databricks.py)).

**Lee / Escribe.** Lee `data/customers.csv`. Escribe en `results/`: `splink_model.json` (lo reutilizan `05_mdm.py`, `06_customer_spine.py` y `07_identity_drift.py`), `pairs_splink.csv` (lo lee `04_graph_resolution.py`), `clusters_splink.csv`, `review_queue_splink.csv`, `splink_threshold_sweep.csv`, `splink_match_weights.html`, `splink_m_u_parameters.html`, `splink_waterfall_example.html` y `metrics_splink.csv`.

**Diapositivas.** 7 (*blocking*), 8 (tres formas de puntuar), **9 (campos, niveles, m y u)**, **10 (sumar bits: Robert Smith vs Bob Smyth)**, 13 (precisión o recall).

**Guía.** [3.5 Fellegi-Sunter, paso a paso](DEMO_GUIDE.es.md#35-fellegi-sunter-paso-a-paso), en particular el [Paso 7](DEMO_GUIDE.es.md#paso-7-súmalo-todo-y-conviértelo-en-probabilidad) y el [Paso 8](DEMO_GUIDE.es.md#paso-8-cómo-aprende-el-modelo-m-y-u-sin-etiquetas); [3.3 *Blocking*](DEMO_GUIDE.es.md#33-agrupación-por-claves-blocking-indexación); [Recorrido por el código 2](DEMO_GUIDE.es.md#2-comparador-probabilístico-02_splinkpy).

### El modelo en cinco líneas (diapositivas 9 y 10)

- **Campos y niveles.** Cada uno de los siete campos se compara con una escalera de niveles; por ejemplo, para el apellido: exacto, Jaro-Winkler >= 0.92, >= 0.88, >= 0.70, todo lo demás, más un nivel de "ausente". Un par cae en el primer nivel que se cumple.
- **m** = con qué frecuencia caen en ese nivel las *coincidencias verdaderas* (calidad de los datos). Nombre exacto: m = 0.676.
- **u** = con qué frecuencia caen en él *personas distintas* por casualidad (lo común que es el valor). Nombre exacto: u = 0.0047.
- **Bits.** Cada nivel suma log2(m / u) bits: el nombre exacto es log2(0.676 / 0.0047) = +7.2. Un campo ausente suma 0.
- ***Prior*.** Cada par parte de log2(λ / (1 − λ)) con λ ≈ 0.00022, es decir, −12.1 bits. Peso total w = *prior* + bits de los campos; probabilidad = 2^w / (1 + 2^w). Diapositiva 10: Robert Smith vs Bob Smyth obtiene −12.1 + 7.2 (nombre) + 5.3 (apellido JW >= 0.88) + 12.3 (email) − 1.8 (código postal) = **+10.9 bits, p ≈ 0.9995**.

### Recorrido

1. [02_splink.py#L1-L33](02_splink.py#L1-L33) **Docstring del módulo.** El modelo en resumen, todos los archivos de salida y qué paso posterior lee cada uno, las diapositivas y una explicación de los avisos esperados (consulta "Qué deberías ver").
2. [02_splink.py#L35-L55](02_splink.py#L35-L55) **Importaciones.** `splink.comparison_library` (`cl`) contiene las escaleras de comparación ya preparadas. `DuckDBAPI` es el motor SQL, `Linker` el objeto que entrena, predice, agrupa y dibuja, `SettingsCreator` la especificación del modelo y `block_on` la función auxiliar para reglas de *blocking*. La limpieza y las métricas compartidas son las mismas que en los pasos 1 y 3.
3. [02_splink.py#L57-L60](02_splink.py#L57-L60) **`CLUSTER_THRESHOLD = 0.95`.** La probabilidad de coincidencia que necesita un par para convertirse en arista. Es una decisión de negocio, que explora el barrido de más abajo.
4. [02_splink.py#L62-L81](02_splink.py#L62-L81) **`MODEL_COLUMNS`.** Las columnas que se cargan en DuckDB: id de registro, campos comparados, claves de *blocking* y `true_entity_id`, que se arrastra solo para poder evaluar los clústeres; ninguna regla ni comparación lo usa.
5. [02_splink.py#L83-L97](02_splink.py#L83-L97) **Configuración: tarea y *blocking*.** `dedupe_only` porque todas las fuentes ya están en una sola tabla. Las cinco reglas de *blocking* de predicción usan las mismas claves que el paso 1, así que todos los comparadores comparan el mismo tipo de candidatos (diapositiva 7).
6. [02_splink.py#L98-L123](02_splink.py#L98-L123) **Configuración: comparaciones (diapositiva 9).** Los siete campos y sus escaleras de niveles: `NameComparison` para nombre y apellido con ajuste por frecuencia de términos (coincidir en un nombre raro vale más bits que coincidir en "smith"), `DateOfBirthComparison` (exacta, Levenshtein <= 1, a menos de 1 mes / 1 año / 10 años), `EmailComparison` (exacto, mismo usuario, difuso), teléfono exacto, `PostcodeComparison` (completo, sector, distrito, área) y dirección con Jaro-Winkler. Cada nivel de cada escalera tendrá su propio m, u y peso. `retain_intermediate_calculation_columns=True` conserva los niveles de cada campo en las predicciones para que el gráfico de cascada pueda mostrarlos.
7. [02_splink.py#L126-L134](02_splink.py#L126-L134) **`build_linker()`.** Crea una base de datos DuckDB en memoria, registra las columnas seleccionadas como la tabla `customers` y construye el `Linker`. `log_level=logging.WARNING` oculta los mensajes informativos rutinarios de Splink, pero sigue mostrando los avisos.
8. [02_splink.py#L137-L176](02_splink.py#L137-L176) **`train()`: tres fases, sin etiquetas.**
   - [L139-L152](02_splink.py#L139-L152) ***Prior*.** `estimate_probability_two_random_records_match` cuenta los pares que cumplen tres reglas estrictas (mismo email, mismo teléfono, mismo nombre completo y DOB), supone que esas reglas encuentran el 70% de las coincidencias verdaderas (`recall=0.7`) y divide por el número de pares posibles. Resultado: λ ≈ 0.00022, los −12.1 bits de los que parte cada par (diapositiva 10).
   - [L153-L157](02_splink.py#L153-L157) **u.** `estimate_u_using_random_sampling` toma una muestra de hasta 2 millones de pares aleatorios. Los pares aleatorios casi nunca son la misma persona, así que la proporción que cae en cada nivel *es* u.
   - [L158-L176](02_splink.py#L158-L176) **m con EM, tres sesiones.** EM supone un valor de m, puntúa los pares de un bloque de entrenamiento, vuelve a estimar m a partir de esas probabilidades y repite hasta que se estabiliza. Dentro de un bloque por DOB todos los pares coinciden en la DOB, así que esa sesión no puede aprender la m de la DOB (Splink la deja fija). De ahí las tres sesiones: con bloque por DOB (aprende todo menos la DOB), por código postal (aprende la DOB, no el código postal) y por nombre + apellido (aprende DOB, código postal, email, teléfono y dirección). Splink promedia la m de cada campo entre las sesiones que pudieron aprenderla, así que cada campo queda cubierto al menos una vez. Es el "cómo aprende sin etiquetas" del [Paso 8](DEMO_GUIDE.es.md#paso-8-cómo-aprende-el-modelo-m-y-u-sin-etiquetas).
9. [02_splink.py#L179-L188](02_splink.py#L179-L188) **Cargar, construir, entrenar.** La misma entrada y la misma limpieza que en el paso 1; la columna de verdad no se toca nunca durante el entrenamiento.
10. [02_splink.py#L190-L195](02_splink.py#L190-L195) **Predecir.** Puntúa cada par candidato (*prior* + bits, convertido en probabilidad) y conserva los pares con p >= 0.2, para que la franja de revisión y el barrido puedan reutilizar un único conjunto puntuado. Aquí se imprime el aviso "m values not fully trained".
11. [02_splink.py#L196-L205](02_splink.py#L196-L205) **Agrupar con 0.95 y evaluar.** `cluster_pairwise_predictions_at_threshold` conserva las aristas con p >= 0.95 y toma las componentes conexas; `as_pandas_dataframe()` trae el resultado de vuelta desde DuckDB. Las métricas usan el mismo `evaluate_clusters()` que el paso 1.
12. [02_splink.py#L207-L235](02_splink.py#L207-L235) **Barrido de umbrales (diapositiva 13).** Vuelve a agrupar las mismas predicciones con umbrales de 0.5 a 0.999 sin reentrenar e imprime para cada uno la precisión, el recall, el F1, el F1 B-cubed y el número de clientes predichos.
13. [02_splink.py#L237-L248](02_splink.py#L237-L248) **Guardar el modelo y los gráficos de pesos.** `save_model_to_json` escribe la configuración, el *prior* y todos los m y u, para que los pasos posteriores puntúen datos nuevos sin reentrenar. `match_weights_chart` muestra log2(m / u) por nivel (los bits de las diapositivas 9 y 10); `m_u_parameters_chart` muestra m y u en bruto, uno al lado del otro.
14. [02_splink.py#L249-L260](02_splink.py#L249-L260) **Pares y cola de revisión.** Todos los pares puntuados, con `match_weight` y `match_probability`, van a `pairs_splink.csv` (las aristas ponderadas del paso 4). Los pares con 0.5 <= p < 0.95 forman la cola de revisión.
15. [02_splink.py#L261-L269](02_splink.py#L261-L269) **Gráfico de cascada (diapositiva 10).** Elige el par que está a un tercio de la clasificación por probabilidad y dibuja la barra del *prior*, una barra por campo (los campos ausentes aparecen como 0 porque `filter_nulls=False`) y el peso final. Es la diapositiva 10 con un par real.
16. [02_splink.py#L270-L276](02_splink.py#L270-L276) **Guardar clústeres, barrido y métricas** (etiqueta de método `splink (EM, p>=0.95)`, que recoge `09_compare.py`).

### Qué deberías ver

Primero, los avisos del entrenamiento:

```
WARNING:
Level Exact match on sector on comparison postcode not observed in dataset, unable to train m value
WARNING:
Level Exact match on district on comparison postcode not observed in dataset, unable to train m value
WARNING:
Level Levenshtein distance <= 1 on comparison dob not observed in dataset, unable to train m value
...
 -- WARNING --
You have called predict(), but there are some parameter estimates which have neither been estimated or specified ...
Comparison: 'dob':
    m values not fully trained
Comparison: 'postcode':
    m values not fully trained
```

**Son esperables.** EM solo puede estimar la m de un nivel si algunas coincidencias probables caen en él. En los datos sintéticos, un error de DOB es un intercambio de día y mes (dos o más ediciones de carácter, nunca una), y una persona que se muda recibe un código postal aleatorio completamente nuevo, así que ninguna coincidencia verdadera coincide solo en el sector o el distrito del código postal. Cada sesión de EM que podía aprender la DOB o el código postal informa del nivel que falta (la DOB en las sesiones 2 y 3, el código postal en las sesiones 1 y 3), y después `predict()` te recuerda que esos niveles usan valores de m por defecto. En `results/splink_model.json` estos tres niveles tienen u pero no m. También son raros entre las no coincidencias, así que el efecto sobre las puntuaciones es despreciable. Con datos reales, donde estos patrones sí aparecen, los avisos desaparecerían.

Después, los resultados:

```
quality @ 0.95 {'pair_precision': 0.9661, 'pair_recall': 0.9649, 'pair_f1': 0.9655, 'bcubed_precision': 0.9902, 'bcubed_recall': 0.9804, 'bcubed_f1': 0.9853, 'n_records': 8192, 'n_pred_entities': 4102, 'n_true_entities': 4000, 'largest_cluster': 7, 'false_merges_pairs': 198, 'missed_pairs': 205}
 threshold  pair_precision  pair_recall  pair_f1  bcubed_f1  n_pred_entities
     0.500          0.9429       0.9752   0.9588     0.9845             4033
     0.800          0.9576       0.9699   0.9637     0.9852             4070
     0.900          0.9611       0.9678   0.9644     0.9851             4084
     0.950          0.9661       0.9649   0.9655     0.9853             4102
     0.990          0.9759       0.9629   0.9693     0.9862             4121
     0.999          0.9813       0.9512   0.9660     0.9840             4172
review queue (0.5 <= p < 0.95): 161 pairs
```

Cómo leerlo:
- Con 0.95, precisión por pares de 0.966 con **198 pares de fusión errónea** y recall de 0.965 con **205 pares perdidos**, frente a 267 / 510 del comparador de reglas, sin una sola etiqueta. El recall casi alcanza el techo del *blocking* (0.9649).
- El barrido es la diapositiva 13: al subir el umbral, la precisión sube (de 0.943 a 0.981), el recall baja (de 0.975 a 0.951) y el número de clientes predichos crece (se divide más).
- Muchas de las fusiones erróneas que quedan son miembros de un mismo hogar: un apellido, una dirección, un código postal y un email familiar compartidos son de verdad una evidencia fuerte (el Ejemplo B del [Paso 7](DEMO_GUIDE.es.md#paso-7-súmalo-todo-y-conviértelo-en-probabilidad)). El paso 4 elimina la mayoría con una regla cannot-link.
- Abre `results/splink_match_weights.html` y `results/splink_waterfall_example.html` para ver los bits de las diapositivas 9 y 10.

### Prueba esto

1. **Cambia `CLUSTER_THRESHOLD` a 0.99** ([L60](02_splink.py#L60)). Las métricas principales pasan a ser las de la fila 0.990 del barrido, y la cola de revisión (0.5 <= p < 0.99) crece.
2. **Quita la sesión de EM por código postal** ([L168-L170](02_splink.py#L168-L170)). Entonces la DOB solo se aprende en la sesión 3; compara las filas de DOB de `splink_m_u_parameters.html` antes y después.
3. **Pon `recall=0.9`** en la estimación del *prior* ([L151](02_splink.py#L151)). λ se hace más pequeño, así que cada par parte con menos bits; las probabilidades bajan un poco y los pares en el límite quedan por debajo de 0.95.

---

## 03_ml_recordlinkage.py

**Qué hace.** El comparador supervisado. Reutiliza el *blocking* del paso 1, convierte cada par candidato en una fila de 14 características numéricas (similitudes de texto, coincidencia exacta y fonética, y un coseno TF-IDF sobre el registro completo), etiqueta cada par con la verdad sintética y entrena un clasificador de *gradient boosting* con validación cruzada en dos particiones (*cross-fitting*), de modo que cada par recibe una probabilidad fuera de partición (*out-of-fold*). Los pares por encima de 0.9 se convierten en aristas y las componentes conexas, en clientes.

**Ejecución.** `python 03_ml_recordlinkage.py` desde `er-demo/`.

**Lee / Escribe.** Lee `data/customers.csv` (e importa `candidate_pairs()` de `01_rules_rapidfuzz.py`). Escribe `results/pairs_ml_features.csv` (características, etiqueta y `ml_probability` por par, que lee `04_graph_resolution.py`) y `results/metrics_ml.csv` (que recoge `09_compare.py`). `08_mlops_feature_store.py` importa `features()` de este archivo.

**Diapositivas.** 8 (tres formas de puntuar), 11 (características supervisadas), 12 (etiquetas), 13 (precisión o recall), 15 (por qué engañan las puntuaciones de pares).

**Guía.** [3.6 Matching supervisado, paso a paso](DEMO_GUIDE.es.md#36-matching-supervisado-paso-a-paso), sobre todo el [Paso 2. Características](DEMO_GUIDE.es.md#paso-2-características-convertir-un-par-en-una-fila-de-números) y el [Paso 5. Evalúa sin engañarte](DEMO_GUIDE.es.md#paso-5-evalúa-sin-engañarte); [Recorrido por el código 3](DEMO_GUIDE.es.md#3-comparador-supervisado-03_ml_recordlinkagepy).

### Recorrido

1. [03_ml_recordlinkage.py#L1-L21](03_ml_recordlinkage.py#L1-L21) **Docstring del módulo.** Indexación, características y modelo en resumen, la advertencia honesta sobre el reparto en particiones, las salidas y las diapositivas.
2. [03_ml_recordlinkage.py#L23-L47](03_ml_recordlinkage.py#L23-L47) **Importaciones.** `recordlinkage.Compare` calcula una columna de similitud por comparación. `HistGradientBoostingClassifier` es un modelo rápido de árboles con *gradient boosting* que acepta NaN, así que los campos ausentes no necesitan imputación. `TfidfVectorizer` construye los vectores de n-gramas de caracteres y `average_precision_score`, la métrica de ordenación independiente del umbral.
3. [03_ml_recordlinkage.py#L49-L55](03_ml_recordlinkage.py#L49-L55) **Reutilizar el *blocking* y fijar el umbral.** Hace falta `__import__("01_rules_rapidfuzz")` porque un nombre de módulo que empieza por un dígito no puede aparecer en una instrucción `import`. Reutilizar `candidate_pairs()` garantiza los mismos 6,405 pares que en el paso 1, así que las diferencias salen solo de la puntuación. `THRESHOLD = 0.9` es el punto de trabajo.
4. [03_ml_recordlinkage.py#L58-L69](03_ml_recordlinkage.py#L58-L69) **`record_text()`.** Une nombre, apellido, usuario del email, código postal y dirección en una sola cadena por registro (los valores ausentes pasan a cadenas vacías). Esta vista del "registro completo" alimenta la característica TF-IDF.
5. [03_ml_recordlinkage.py#L72-L119](03_ml_recordlinkage.py#L72-L119) **`features()`: comparaciones de campos (diapositiva 11).** Trece columnas por par: Jaro-Winkler sobre el nombre, Jaro-Winkler y Levenshtein sobre el apellido, códigos Metaphone exactos para los dos nombres (coincidencia por sonido), DOB exacta y con Levenshtein (la segunda da crédito parcial a un intercambio de día y mes), email por q-gramas, usuario del email con Jaro-Winkler, teléfono exacto, código postal y área del código postal, y dirección por q-gramas. `missing_value=np.nan` mantiene "desconocido" separado de "distinto". Tener varias similitudes solapadas sobre un mismo campo es deliberado: el modelo aprende cuáles importan y cómo interactúan, algo que no pueden hacer los pesos elegidos a mano (paso 1) ni los pesos independientes por campo (paso 2).
6. [03_ml_recordlinkage.py#L121-L139](03_ml_recordlinkage.py#L121-L139) **`features()`: coseno TF-IDF del registro completo.** Ajusta un vectorizador TF-IDF de 2 a 4-gramas de caracteres (solo cuando no se le pasa uno, para que el servicio del paso 8 reutilice el vocabulario del entrenamiento), convierte cada registro en un vector disperso normalizado, asigna los ids de los pares a filas de la matriz y calcula el producto escalar fila a fila, que es igual a la similitud del coseno. Es un "embedding" barato que tolera erratas y campos en la columna equivocada.
7. [03_ml_recordlinkage.py#L142-L151](03_ml_recordlinkage.py#L142-L151) **Cargar, *blocking*, calcular características.** La tabla se indexa por `unique_id` porque `recordlinkage` busca los registros por índice; `reset_index()` devuelve a `candidate_pairs()` la columna que espera. Ordenar hace reproducible el orden de los pares.
8. [03_ml_recordlinkage.py#L152-L158](03_ml_recordlinkage.py#L152-L158) **Etiquetas (diapositiva 12).** Un par vale 1 cuando los dos registros comparten `true_entity_id` y 0 en caso contrario. En producción, estas etiquetas saldrían de las decisiones de los *data stewards* sobre la cola de revisión. La verdad es una etiqueta, nunca una característica.
9. [03_ml_recordlinkage.py#L160-L179](03_ml_recordlinkage.py#L160-L179) ***Cross-fitting* en dos particiones.** Los pares se reparten según la paridad del id de entidad del registro izquierdo; cada partición se puntúa con un modelo entrenado en la otra, así que todas las probabilidades son fuera de partición. No es estrictamente disjunto por entidades (la misma persona puede aparecer en el lado derecho de un par de entrenamiento), y por eso el paso 8 repite la prueba con un reparto estricto. Imprime los pares, los positivos y la precisión media.
10. [03_ml_recordlinkage.py#L181-L191](03_ml_recordlinkage.py#L181-L191) **Umbrales después de agrupar (diapositivas 13 y 15).** Para 0.5, 0.9 y 0.99 el script construye las componentes conexas e imprime la precisión y el recall a nivel de clúster y el clúster más grande. Una ordenación de pares casi perfecta puede seguir produciendo fusiones erróneas en cuanto las aristas se encadenan.
11. [03_ml_recordlinkage.py#L193-L199](03_ml_recordlinkage.py#L193-L199) **Agrupación final con 0.9** y métricas completas con el mismo `evaluate_clusters()` que en los pasos 1 y 2.
12. [03_ml_recordlinkage.py#L201-L215](03_ml_recordlinkage.py#L201-L215) **Guardar.** Características más `label` y `ml_probability` por par (el MultiIndex del par pasa a las columnas `id_l` e `id_r`), y una tabla de métricas de una fila.

### Qué deberías ver

```
pairs: 6405, positives: 5639, average precision (out of fold): 0.9998
  threshold 0.5: pair P=0.9683 R=0.9762 largest cluster=9
  threshold 0.9: pair P=0.9757 R=0.9752 largest cluster=7
  threshold 0.99: pair P=0.9805 R=0.9735 largest cluster=7
quality: {'pair_precision': 0.9757, 'pair_recall': 0.9752, 'pair_f1': 0.9754, 'bcubed_precision': 0.9937, 'bcubed_recall': 0.9858, 'bcubed_f1': 0.9898, 'n_records': 8192, 'n_pred_entities': 4082, 'n_true_entities': 4000, 'largest_cluster': 7, 'false_merges_pairs': 142, 'missed_pairs': 145}
```

Cómo leerlo:
- 5,639 de los 6,405 pares candidatos son coincidencias verdaderas; el resto son negativos difíciles que propuso el *blocking*.
- Una precisión media de 0.9998 dice que la ordenación de los pares es casi perfecta y, aun así, los clústeres contienen **142 pares de fusión errónea**. Las puntuaciones de pares favorecen al modelo; las métricas de clúster son las honestas (diapositiva 15).
- Con 0.9: precisión por pares de 0.976, recall de 0.975 y **145 pares perdidos**, lo mejor de los tres comparadores (reglas 267 / 510, Splink 198 / 205), pero necesitó etiquetas.
- Las líneas de umbral vuelven a mostrar la diapositiva 13: pasar de 0.5 a 0.99 sube la precisión y baja el recall, y el umbral más bajo tiene el clúster más grande (9) porque se encadenan más aristas débiles.

### Prueba esto

1. **Cambia `THRESHOLD` a 0.99** ([L55](03_ml_recordlinkage.py#L55)). Las métricas finales coinciden con la línea `threshold 0.99`: menos fusiones erróneas y algunos pares perdidos más.
2. **Quita la característica TF-IDF** comentando [L138](03_ml_recordlinkage.py#L138). Compara la precisión media y el número de fusiones erróneas con la línea base: en estos datos sintéticos limpios, las características de campo llevan casi toda la señal, mientras que con texto libre más desordenado el coseno del registro completo suele importar más.
3. **Sustituye la regla de particiones** de [L164](03_ml_recordlinkage.py#L164) por un reparto aleatorio (por ejemplo, `np.random.default_rng(0).integers(0, 2, len(X))`). Espera puntuaciones algo más optimistas, porque las mismas personas aparecen en entrenamiento y en prueba: la fuga de información que evita el reparto disjunto por entidades del paso 8.

---

## 04_graph_resolution.py

**Qué hace.** Convierte los pares aceptados por el comparador de Splink (02) y por el supervisado (03) en un grafo de registros, en el que los registros son nodos y las coincidencias aceptadas son aristas ponderadas por la evidencia en bits. Un cliente es una componente conexa. Las componentes que contienen dos registros que, según las reglas de negocio, no pueden ser la misma persona (DOB contradictorias, nombres de pila claramente distintos) se dividen con un corte mínimo ponderado. Por último, lista los emails y teléfonos que apuntan a más de un cliente resuelto.

**Ejecución.** `python 04_graph_resolution.py` (desde `er-demo/`, después de `02_splink.py` y `03_ml_recordlinkage.py`).

**Lee / Escribe.**
- Lee `data/customers.csv`, `results/pairs_splink.csv` y `results/pairs_ml_features.csv`.
- Escribe `results/metrics_graph.csv` (una fila por origen de aristas tras la reparación), `results/clusters_graph.csv` (los clústeres de Splink reparados, la entrada de `05_mdm.py`) y `results/shared_identifiers.csv` (la cola de trabajo de los *data stewards*).

**Diapositivas.** 14, 15, 16, 17, 27.

**Guía.** [3.7 Agrupación y la vista de grafo](DEMO_GUIDE.es.md#37-agrupación-clustering-y-la-vista-de-grafo-paso-a-paso), en particular el [Paso 3. Encadenamiento](DEMO_GUIDE.es.md#paso-3-encadenamiento-chaining-por-qué-basta-una-arista-mala), el [Paso 4. Restricciones cannot-link](DEMO_GUIDE.es.md#paso-4-restricciones-cannot-link-conocimiento-de-negocio-que-el-modelo-no-tiene), el [Paso 5. Corte mínimo](DEMO_GUIDE.es.md#paso-5-corte-mínimo-min-cut-quitar-las-aristas-más-débiles-que-los-separan) y el [Paso 6. El grafo de identificadores](DEMO_GUIDE.es.md#paso-6-el-grafo-de-identificadores-quién-comparte-un-email); el recorrido por el código [4. Resolución con grafos](DEMO_GUIDE.es.md#4-resolución-con-grafos-04_graph_resolutionpy); [3.9 Métricas de calidad del emparejamiento](DEMO_GUIDE.es.md#39-métricas-de-calidad-del-emparejamiento) para P, R y B-cubed.

### Recorrido

1. [04_graph_resolution.py#L1-L37](04_graph_resolution.py#L1-L37) **Docstring del módulo.** Expone la idea (los pares responden a "¿coinciden estos dos?", los clientes son una cuestión de grafos), los cinco pasos, las entradas, las salidas y el orden de ejecución. Diapositiva 14.
2. [04_graph_resolution.py#L40-L58](04_graph_resolution.py#L40-L58) **Importaciones.** `networkx` aporta el grafo, las componentes y el corte mínimo; `rapidfuzz.distance.JaroWinkler.similarity` devuelve una puntuación en [0, 1] que premia un prefijo común, buena para nombres de pila. Los módulos compartidos `standardise()` y `evaluate_clusters()` mantienen este paso comparable con todos los demás comparadores.
3. [04_graph_resolution.py#L61-L66](04_graph_resolution.py#L61-L66) **Constantes.** Las aristas son los pares con p de Splink >= 0.95 o p de ML >= 0.9, los mismos umbrales con los que agrupan 02 y 03, así que "antes de la reparación" reproduce exactamente sus resultados. `FIRST_NAME_CONFLICT = 0.75` es el nivel de Jaro-Winkler por debajo del cual dos nombres canónicos cuentan como personas distintas.
4. [04_graph_resolution.py#L69-L79](04_graph_resolution.py#L69-L79) **`dob_conflict()`.** Un conflicto exige que las dos DOB se conozcan y sean distintas. Un intercambio de día y mes en el mismo año (03/04 frente a 04/03) se trata como una errata, no como otra persona. Por qué: un valor ausente no es evidencia de diferencia, y los intercambios son el error de DOB más habitual. Diapositiva 16 (restricción), diapositiva 17 (Thomas 2008-07-14 vs Stanley 2002-07-12).
5. [04_graph_resolution.py#L82-L97](04_graph_resolution.py#L82-L97) **`name_conflict()`.** Solo salta cuando nada más explica que los nombres de pila sean distintos: no cuando suenan igual (mismo metaphone), no cuando la DOB coincide (una errata en un apodo), no cuando un nombre de pila se parece al apellido del otro registro (campos intercambiados, Jaro-Winkler >= 0.85). En el resto de casos, Jaro-Winkler < 0.75 significa personas distintas. Estas excepciones evitan que la regla divida coincidencias auténticas. Diapositiva 16.
6. [04_graph_resolution.py#L100-L103](04_graph_resolution.py#L100-L103) **`cannot_link()`.** Cualquiera de las dos reglas es una restricción de negocio estricta que se impone a cualquier puntuación del modelo. Diapositiva 16.
7. [04_graph_resolution.py#L106-L117](04_graph_resolution.py#L106-L117) **`evidence_bits()`.** Convierte una probabilidad de ML en log-odds en bits, `log2(p / (1 - p))`, la misma escala que el `match_weight` de Splink. Las probabilidades se saturan cerca de 1.0 y los bits no, así que el corte mínimo puede distinguir una arista de 15 bits de una de 60. Acotar los valores mantiene el logaritmo finito; el mínimo de 0.01 mantiene las capacidades positivas. Diapositiva 17 ("por qué bits").
8. [04_graph_resolution.py#L120-L130](04_graph_resolution.py#L120-L130) **`build_graph()`.** Añade cada registro como nodo (así los registros sin coincidencias son clientes de un solo registro) y cada par aceptado como arista no dirigida con `weight` = bits. Diapositiva 14.
9. [04_graph_resolution.py#L133-L181](04_graph_resolution.py#L133-L181) **`repair()`.** El núcleo del paso. Pone en cola todas las componentes de varios registros ([L141](04_graph_resolution.py#L141)), busca el primer par cannot-link dentro de cada una ([L151-L158](04_graph_resolution.py#L151-L158)) y se salta las que no tienen ninguno. Para una componente con conflicto, copia el subgrafo, asigna a cada arista una `capacity` igual a sus bits ([L163-L167](04_graph_resolution.py#L163-L167)) y llama a `nx.minimum_cut(sub, a, b)`, que devuelve la partición más barata que separa los dos registros en conflicto ([L172](04_graph_resolution.py#L172)). Las aristas que cruzan la partición se eliminan ([L174-L178](04_graph_resolution.py#L174-L178)) y los dos trozos vuelven a la cola ([L180](04_graph_resolution.py#L180)), porque un corte puede dejar otro conflicto pendiente. Por qué importa: elimina los enlaces más débiles (un email familiar, una dirección compartida) y conserva los fuertes. Diapositivas 16 y 17 (el corte 1 elimina las dos aristas de 6.6 bits, el corte 2 las cuatro aristas de 15.3 y 25.3 bits, y la arista de 59.5 bits no se corta nunca).
10. [04_graph_resolution.py#L184-L187](04_graph_resolution.py#L184-L187) **`to_clusters()`.** Convierte las componentes en `{record_id: cluster_id}`, usando como etiqueta determinista el id más pequeño de cada componente.
11. [04_graph_resolution.py#L190-L213](04_graph_resolution.py#L190-L213) **`shared_identifiers()`.** El grafo de identificadores: para cada valor de email y de teléfono, cuenta a cuántos clientes resueltos distintos pertenecen sus registros; si son más de uno, se marca. `truly_shared` usa la verdad sintética solo para evaluar la lista. Por qué: un valor realmente compartido (un buzón familiar) debería excluirse del *blocking*; el resto apunta a coincidencias perdidas. Diapositiva 16 ("Flag").
12. [04_graph_resolution.py#L216-L235](04_graph_resolution.py#L216-L235) **`main()`, carga.** Vuelve a estandarizar los datos en bruto indexados por `unique_id`, conserva los pares de Splink aceptados (renombrando `match_weight` a `bits`) y los pares de ML aceptados (añadiendo `bits` con `evidence_bits`).
13. [04_graph_resolution.py#L238-L257](04_graph_resolution.py#L238-L257) **`main()`, antes y después.** Para cada origen de aristas: construye el grafo, evalúa las componentes conexas sin más ("antes", idéntico a 02 / 03), repara, vuelve a evaluar ("después") e imprime las estadísticas y las dos líneas de métricas. Diapositivas 16 y 27.
14. [04_graph_resolution.py#L260-L265](04_graph_resolution.py#L260-L265) **Resumen de identificadores compartidos.** Se construye sobre los clústeres de Splink reparados, los que usa a continuación el MDM.
15. [04_graph_resolution.py#L269-L274](04_graph_resolution.py#L269-L274) **Salidas.** Métricas para `09_compare.py`, `clusters_graph.csv` para `05_mdm.py` y el CSV de identificadores compartidos.
16. [04_graph_resolution.py#L278-L279](04_graph_resolution.py#L278-L279) Punto de entrada estándar.

### Qué deberías ver

```text
splink: {'components_checked': 2712, 'components_split': 42, 'edges_cut': 80}
  connected components   P=0.9661 R=0.9649 B3-F1=0.9853 false-merge pairs=198
  + graph repair         P=0.9979 R=0.9617 B3-F1=0.9889 false-merge pairs=12
ml: {'components_checked': 2714, 'components_split': 26, 'edges_cut': 36}
  connected components   P=0.9757 R=0.9752 B3-F1=0.9898 false-merge pairs=142
  + graph repair         P=0.9984 R=0.9723 B3-F1=0.9918 false-merge pairs=9
shared identifiers flagged: 73, of which really shared by different people: 31
```

Cómo leerlo:
- `components_checked` cuenta todas las componentes examinadas, incluidos los trozos nuevos que vuelven a la cola tras un corte. Con Splink, 42 componentes tenían un conflicto y se cortaron 80 aristas.
- La línea "connected components" es igual a los resultados de 02 (Splink) y 03 (ML); la línea "+ graph repair" es la mejora. Con Splink, los pares de fusión errónea bajan de 198 a 12 mientras el recall solo baja de 0.965 a 0.962. Con ML bajan de 142 a 9, y su F1 B-cubed de 0.9918 es el mejor de la demo (diapositiva 27: 0.992).
- Tras la reparación, Splink tiene 4,144 clientes y ML 4,108 (en `metrics_graph.csv`); el clúster más grande baja a 6, el máximo real del generador.
- Los 73 identificadores compartidos son 48 emails y 25 teléfonos. 31 emails son buzones familiares reales; los otros 17 emails y los 25 teléfonos pertenecen a una persona dividida en dos clientes, es decir, coincidencias perdidas para un *data steward*.

### Prueba esto

1. Pon `FIRST_NAME_CONFLICT = 0.85` (línea 66). Más pares de nombres cuentan como conflicto, así que se dividen más componentes: las fusiones erróneas bajan un poco más, pero el recall cae, porque se separan nombres de pila auténticos con erratas.
2. Elimina la excepción del intercambio de día y mes: sustituye la línea 79 por `return True`. Cualquier DOB distinta pasa a ser un conflicto, así que se dividen algunas personas reales con la DOB intercambiada. El recall baja un poco a cambio de casi ninguna mejora de precisión.
3. Cambia `SPLINK_THRESHOLD` a 0.8 (línea 65). El grafo recibe más aristas y más débiles, así que la precisión "antes" baja y más componentes contienen conflictos; la reparación recupera gran parte, lo que demuestra que las restricciones y el corte mínimo te permiten trabajar con un umbral más bajo de forma segura.

---

## 05_mdm.py

**Qué hace.** Construye un pequeño hub de gestión de datos maestros (MDM) en un archivo DuckDB. Inicializa el hub con los clústeres por lotes de los comparadores anteriores (un `customer_id` maestro por clúster), construye un *golden record* por cliente con supervivencia y procedencia a nivel de campo y, después, compara un lote nuevo de registros con el maestro usando el modelo Splink guardado: las coincidencias seguras se asocian, las de la zona gris van a una cola de revisión y el resto se convierten en clientes nuevos. Por último, muestra la aprobación de un *data steward* y un borrado RGPD, y exporta las tablas principales.

**Ejecución.** `python 05_mdm.py` desde `er-demo/`, después de `02_splink.py` (escribe `results/splink_model.json` y `results/clusters_splink.csv`) y, preferiblemente, de `04_graph_resolution.py` (escribe `results/clusters_graph.csv`).

**Lee / Escribe.**
- Lee: `data/customers.csv`, `data/new_batch.csv`, `results/clusters_graph.csv` (si no existe, usa `results/clusters_splink.csv`) y `results/splink_model.json`.
- Escribe: `results/mdm.duckdb` (tablas `source_record`, `xref`, `golden_record`, `golden_history`, `review_queue`, `steward_audit` y secuencia `customer_seq`), `results/mdm_golden_record.csv`, `results/mdm_xref.csv` y `results/mdm_review_queue.csv`. El archivo DuckDB se borra y se vuelve a crear en cada ejecución. `06_customer_spine.py` lee el archivo DuckDB, no los CSV.

**Diapositivas.** 18 (sección de gestión de maestros), 19 (Mini MDM), 13 (Precisión o recall: los dos umbrales), 9 (ajustes por frecuencia de términos reutilizados al puntuar), 16 (los clústeres reparados con cannot-link como punto de partida), 20 (el *spine* construido sobre este hub).

**Guía.** [3.8 MDM, golden record y customer spine](DEMO_GUIDE.es.md#38-mdm-golden-record-y-customer-spine), [3.9 Métricas de calidad del emparejamiento](DEMO_GUIDE.es.md#39-métricas-de-calidad-del-emparejamiento), [Recorrido por el código, paso 5](DEMO_GUIDE.es.md#5-flujo-de-datos-maestros-05_mdmpy), [6. Opcional: demostrar cómo deshacer una fusión](DEMO_GUIDE.es.md#6-opcional-demostrar-cómo-deshacer-una-fusión).

### Recorrido

1. [05_mdm.py#L1-L32](05_mdm.py#L1-L32) Docstring del módulo: la lista de capacidades del MDM, las entradas, las salidas y el orden de ejecución. Léelo primero para ver el hub como un sistema, no como un comparador (diapositiva 19).
2. [05_mdm.py#L34-L53](05_mdm.py#L34-L53) Importaciones. `duckdb` es la base de datos embebida que hace de hub; `DuckDBAPI` y `Linker` de Splink cargan el modelo entrenado; `standardise` es la misma limpieza que usan los comparadores, así que los valores guardados coinciden con lo que vio el modelo.
3. [05_mdm.py#L55-L104](05_mdm.py#L55-L104) Configuración. `AUTO_MATCH, REVIEW = 0.95, 0.50` (L62) reparten los registros entrantes entre asociar, revisar y nuevo (diapositiva 13: un umbral automático más alto compra precisión). `GOLDEN_FIELDS` son los atributos que decide la supervivencia. `SOURCE_PRIORITY` ordena la confianza (CRM por encima de BILLING y este por encima de WEB) y solo sirve para desempatar. `RECENCY_FIELDS` marca los datos de contacto en los que gana el valor más reciente. `MODEL_COLUMNS` es exactamente lo que espera el modelo Splink guardado.
4. [05_mdm.py#L107-L110](05_mdm.py#L107-L110) `now()`: un único formato de marca de tiempo ISO en UTC para enlaces, versiones y filas de auditoría.
5. [05_mdm.py#L116-L155](05_mdm.py#L116-L155) `MiniMDM.__init__()`: crea las seis tablas y la secuencia de ids. La clave del diseño es la separación: las fuentes en bruto pero limpias, el *crosswalk* (`xref`, de id de origen a id maestro) y el *golden record* derivado son tablas distintas, así que cualquier valor del *golden record* se puede rastrear y volver a calcular. `golden_history` copia el esquema del *golden record* y añade `valid_to` para el versionado SCD2 (diapositiva 19).
6. [05_mdm.py#L158-L163](05_mdm.py#L158-L163) `new_customer_id()`: obtiene `nextval('customer_seq')` y le da el formato `C0000001`. Una secuencia nunca reutiliza un valor, así que un id maestro no se recicla nunca tras una fusión o un borrado.
7. [05_mdm.py#L166-L225](05_mdm.py#L166-L225) `survive()`: el motor de supervivencia, campo a campo. Los valores vacíos se excluyen (L179-L187). Los campos de contacto toman el `updated_at` más reciente y los empates se resuelven por la confianza de la fuente (L188-L200). Los nombres y la DOB toman el valor en el que coinciden más registros (`Counter` sin distinguir mayúsculas), después la confianza de la fuente y después la recencia (L201-L216), así que una errata aislada pierde frente a la ortografía que comparten dos fuentes. Cada ganador se guarda con su procedencia: registro de origen, sistema de origen y regla (L217-L224). Es el "*golden record* con procedencia" de la diapositiva 19 y del apartado 3.8 de la guía.
8. [05_mdm.py#L227-L288](05_mdm.py#L227-L288) `rebuild_golden()`: vuelve a calcular solo los clientes afectados. Une `source_record` con `xref` para esos ids (L235-L237), lee las versiones actuales (L239-L242), agrupa los miembros por cliente y ejecuta `survive()` (L246-L266), cierra las filas abiertas del historial asignando `valid_to` (L267-L272), borra y vuelve a insertar las filas actuales del *golden record* y añade las nuevas instantáneas al historial (L273-L288). Un cliente que se queda sin miembros (porque se fusionó en otro) simplemente no recibe fila nueva.
9. [05_mdm.py#L290-L296](05_mdm.py#L290-L296) `_close_history()`: una función auxiliar que cierra la versión abierta de un cliente. No se usa en el flujo de la demo.
10. [05_mdm.py#L299-L330](05_mdm.py#L299-L330) `insert_sources()`: conserva las columnas de origen (sin etiquetas de verdad), sustituye email, teléfono, código postal y DOB por su forma estandarizada, pone los nombres con mayúscula inicial, marca `loaded_at` e inserta en bloque a través de un DataFrame registrado.
11. [05_mdm.py#L332-L339](05_mdm.py#L332-L339) `link()`: `INSERT OR REPLACE` en `xref`, de modo que cada registro de origen tiene exactamente un cliente actual, con la probabilidad y el método que lo pusieron ahí.
12. [05_mdm.py#L341-L372](05_mdm.py#L341-L372) `initial_load()`: guarda las fuentes, asigna a cada `cluster_id` del lote un `customer_id` nuevo (los ids de clúster son etiquetas propias de cada ejecución; los ids de cliente son la clave de negocio), escribe el *crosswalk* con el método `splink_batch_cluster` y construye la versión 1 de cada *golden record*.
13. [05_mdm.py#L374-L435](05_mdm.py#L374-L435) `incremental_load()`: el camino en tiempo real de un MDM. Los pares candidatos se traducen de registro existente a cliente existente (L390), solo se conserva el mejor candidato por registro nuevo (L395-L399) y después cada registro nuevo se enlaza automáticamente con p >= 0.95 (L404-L409) o recibe un cliente nuevo provisional (L410-L417); si el mejor candidato está en la zona gris de 0.50 a 0.95, además se pone en cola para revisión (L418-L430). Una sola llamada a `rebuild_golden()` refresca todo lo afectado (L434). Ten en cuenta que los elementos en revisión también se cuentan dentro de `new_customer`.
14. [05_mdm.py#L438-L462](05_mdm.py#L438-L462) `approve_review()`: un *data steward* está de acuerdo con el candidato. Todos los registros del cliente provisional pasan a apuntar al destino (`steward_approved`), el elemento de la cola se cierra y se reconstruyen los dos clientes: el provisional desaparece y el destino recibe una versión nueva. Las decisiones de los *data stewards* son las etiquetas que, según el apartado 3.8 de la guía, vuelven al entrenamiento.
15. [05_mdm.py#L464-L471](05_mdm.py#L464-L471) `reject_review()`: solo cambia el estado de la cola, porque el registro ya está en su propio cliente.
16. [05_mdm.py#L473-L525](05_mdm.py#L473-L525) `unmerge_record()`: corrige una fusión errónea para un registro. Exige un motivo, un registro conocido y un cliente con al menos dos miembros (L477-L494), asigna un id nuevo y, dentro de una transacción, mueve el registro, marca como `unmerged` cualquier fila de revisión, escribe en `steward_audit` y reconstruye los dos *golden records* (L500-L524). `main()` no la llama; consulta la sección 6 de la guía.
17. [05_mdm.py#L527-L552](05_mdm.py#L527-L552) `erase_customer()`: el derecho de supresión del RGPD. Busca los ids de origen del cliente, borra sus filas de `source_record` y `review_queue` y después borra el cliente de `xref`, `golden_record` y `golden_history`. Devuelve el número de registros de origen eliminados.
18. [05_mdm.py#L555-L580](05_mdm.py#L555-L580) `score_new_records()`: carga `splink_model.json` en un `Linker` sobre los registros existentes, calcula las tablas de frecuencia de términos para `first_name_canon`, `last_name` y `email` (los valores raros pesan más, diapositiva 9) y llama a `predict_between()` para puntuar solo los pares existente-nuevo que cumplen las reglas de *blocking* del modelo, conservando p >= 0.50. Sin reentrenar: los valores de m y u salen del modelo guardado.
19. [05_mdm.py#L589-L609](05_mdm.py#L589-L609) `main()`, carga inicial: vuelve a crear el archivo DuckDB, lee los datos iniciales como texto, da preferencia a los clústeres reparados con grafos (menos fusiones erróneas, diapositiva 16), los carga e imprime `(customers, records)`.
20. [05_mdm.py#L611-L617](05_mdm.py#L611-L617) Lote incremental: estandariza los dos lados, puntúa, aplica los umbrales e imprime los recuentos.
21. [05_mdm.py#L619-L657](05_mdm.py#L619-L657) Evaluación con la verdad sintética (solo después de tomar las decisiones). Cada cliente existente se etiqueta con la persona verdadera más frecuente entre sus registros iniciales; después, `ok_link` cuenta las personas recurrentes asociadas a su propio cliente, `should_link` los registros nuevos cuya persona ya existía y `wrong_link` los registros nuevos asociados al cliente de otra persona (una fusión errónea).
22. [05_mdm.py#L659-L670](05_mdm.py#L659-L670) Demo de *data steward* y gobierno: aprueba el primer elemento abierto de la cola de revisión y después borra el cliente con más registros de origen.
23. [05_mdm.py#L672-L695](05_mdm.py#L672-L695) Exporta a CSV el *golden record*, el *crosswalk* y la cola de revisión, y después imprime un *golden record* con al menos tres fuentes y un teléfono, junto con su JSON de procedencia (cortado a 600 caracteres).

### Qué deberías ver

```
initial clusters from clusters_graph.csv
initial load: (4144, 8192)
incremental batch: {'auto_linked': 198, 'to_review': 4, 'new_customer': 202}
returning customers correctly attached: 197/200, wrong attachments: 1
steward approved review item WEB-008319
GDPR erase C0000321: removed 6 source records
example golden record: C0000001 Gareth Smith ... n_source_records 3, sources BILLING,CRM,WEB, version 1
provenance: first_name/last_name/dob from CRM-005671 (most_frequent_then_source_priority), email/phone from BILLING-005670 (most_recent), ...
```

(Splink también imprime un aviso de que los valores de m de `dob` y `postcode` no están totalmente entrenados; es lo esperable y se usan valores por defecto.)

Cómo leerlo:
- **4,144 clientes para 8,192 registros.** Los datos tienen 4,000 personas reales; los 144 clientes extra son personas que el comparador por lotes más la reparación con grafos dividieron en más de un clúster. El hub prefiere una fusión perdida a una errónea.
- **404 registros nuevos:** 198 se asociaron automáticamente, 202 recibieron un id de cliente nuevo y 4 de esos 202 están en la cola de revisión (la zona gris).
- **197/200, 1 erróneo.** 200 registros nuevos pertenecen a personas que ya estaban en el maestro; 197 se asociaron al cliente correcto. De los 198 enlaces automáticos, 1 fue al cliente equivocado, así que la precisión incremental es de un 99.5% aproximadamente. Las 3 personas recurrentes que no se asociaron esperan como clientes nuevos o en revisión.
- ***Golden record* y procedencia.** Los nombres y la DOB salen de la fila de CRM (frecuencia y después confianza) y los campos de contacto, de la fila de BILLING actualizada más recientemente. Cada valor se puede explicar.
- La marca de tiempo `updated_at` del registro de ejemplo cambia en cada ejecución.

### Prueba esto

1. Baja `AUTO_MATCH` a `0.80` (L62). Se enlazan automáticamente más registros y la cola de revisión se reduce; vigila `wrong attachments` para ver el coste en precisión (diapositiva 13). Súbelo a `0.99` y más coincidencias correctas acaban en revisión o como clientes nuevos.
2. Borra o renombra `results/clusters_graph.csv` y vuelve a ejecutar. El hub parte de `clusters_splink.csv`, que tiene más fusiones erróneas (198 pares de fusión errónea frente a 12 tras la reparación), así que los *golden records* mezclan a más personas y las etiquetas de `cust_truth` tienen más ruido.
3. Cambia `SOURCE_PRIORITY` para que `WEB` sea `1`, o quita `"email"` de `RECENCY_FIELDS`, y compara el bloque de procedencia de `C0000001`: cambian la fuente ganadora y la `rule` de esos campos, pero no las cifras de emparejamiento (la supervivencia nunca cambia la pertenencia).

---

## 06_customer_spine.py

**Qué hace.** Toma los clientes maestros del hub MDM (paso 5) y publica el *customer spine*: la tabla fina y gobernada de la "Golden Layer" con la que se cruzan todos los sistemas posteriores. Agrupa los clientes en hogares con un grafo de direcciones, escribe una única jerarquía de identidad padre-hijo (HOUSEHOLD, CUSTOMER, SOURCE) y ejecuta siete contratos de datos que deben cumplirse todos antes de exportar nada. La verdad del generador solo se usa al final, para medir la calidad de la agrupación en hogares.

**Ejecución.** `python 06_customer_spine.py` (después de `02_splink.py` y `05_mdm.py`, porque necesita `results/splink_model.json` y `results/mdm.duckdb`).

**Lee / Escribe.**
- Lee: `results/mdm.duckdb` (tablas `golden_record`, `xref` y `source_record`), `results/splink_model.json` (solo para calcular su hash) y `data/customers.csv` y `data/new_batch.csv` (la verdad, solo para evaluar).
- Escribe: las tablas DuckDB nuevas `household`, `identity_hierarchy`, `customer_spine` y `column_classification` en `results/mdm.duckdb`, y los CSV `results/customer_spine.csv`, `results/identity_hierarchy.csv`, `results/spine_contracts.csv` y `results/metrics_households.csv`.

**Diapositivas.** 19 (Mini MDM, la entrada), 20 (*Customer spine* y jerarquía), 25 (correspondencia con el *lakehouse*: el *spine* es la capa Gold), 14-15 (la vista de grafo, reutilizada para los hogares).

**Guía.** [3.8 MDM, golden record y customer spine](DEMO_GUIDE.es.md#38-mdm-golden-record-y-customer-spine), [3.7 Paso 7. Las jerarquías también son grafos](DEMO_GUIDE.es.md#paso-7-las-jerarquías-también-son-grafos), [Recorrido por el código 6](DEMO_GUIDE.es.md#6-customer-spine-y-jerarquía-06_customer_spinepy), [Preguntas frecuentes: Spine, MDM y gobierno](DEMO_GUIDE.es.md#spine-mdm-y-gobierno).

**Recorrido.**

1. [06_customer_spine.py#L1-L32](06_customer_spine.py#L1-L32) Docstring del módulo. Define los tres niveles de la jerarquía, los contratos, las entradas, las salidas y el orden de ejecución. Por qué importa: el *spine* es un producto con consumidores, así que su forma y sus garantías se declaran de entrada. Diapositiva 20.
2. [06_customer_spine.py#L34-L53](06_customer_spine.py#L34-L53) Importaciones. `hashlib` calcula la huella del modelo, `duckdb` es la base de datos del MDM, `networkx` encuentra las componentes conexas, `rapidfuzz` compara las cadenas de las calles y `evaluate_clusters` puntúa los hogares frente a la verdad.
3. [06_customer_spine.py#L55-L73](06_customer_spine.py#L55-L73) Constantes. `ADDRESS_SIMILARITY = 85` es el corte de `fuzz.token_set_ratio` (0-100, sin tener en cuenta el orden de las palabras ni las palabras repetidas) para "misma calle". `PII_COLUMNS` clasifica cada columna personal del *spine* (`PII`, `PII_SENSITIVE` para la fecha de nacimiento, `PII_LOW` para la ciudad y el código postal). Por qué: los metadatos de gobierno viven junto al código y un contrato los comprueba. Diapositiva 20.
4. [06_customer_spine.py#L76-L147](06_customer_spine.py#L76-L147) `households()`: los hogares como problema de grafos. Diapositivas 14 y 20.
   - [L83-L88](06_customer_spine.py#L83-L88) Un grafo no dirigido cuyos nodos son ids de cliente (cadenas) y nodos de dirección (tuplas). Primero se añaden todos los clientes, así que las personas sin dirección forman igualmente un hogar de una sola persona.
   - [L89-L114](06_customer_spine.py#L89-L114) Para cada código postal, la calle de cada registro de origen se compara de forma voraz con los representantes ya vistos en ese código postal (gana la primera grafía que puntúa al menos 85; si no, la calle pasa a ser un representante nuevo). Después, el cliente se une al nodo `("ADDR", postcode, street)`. Usar todos los registros de origen, y no solo la dirección del *golden record*, hace que una persona cuya supervivencia eligió una dirección más reciente siga enlazada con la casa que compartió en su día. Comparar solo dentro de un código postal es una forma de *blocking*: limita las uniones falsas y el trabajo.
   - [L115-L147](06_customer_spine.py#L115-L147) Cada componente conexa es un hogar. Se descartan los nodos de dirección para quedarse con los miembros. La regla es `single_person`, `same_address_same_surname` o `same_address`, y el id del hogar reutiliza los dígitos del id de cliente más pequeño (`C0000042` pasa a `H0000042`), así que los mismos miembros dan el mismo id en cada construcción.
5. [06_customer_spine.py#L150-L174](06_customer_spine.py#L150-L174) `build_hierarchy()`: una única tabla padre-hijo para todos los niveles. Los hogares son las raíces, los clientes apuntan a su hogar con la regla del hogar y los registros de origen apuntan a su cliente con el `match_method` y la `match_probability` del MDM como confianza de la arista. `valid_from` marca la construcción. Por qué: cada arista de la jerarquía se puede explicar (regla más confianza). Diapositiva 20.
6. [06_customer_spine.py#L177-L216](06_customer_spine.py#L177-L216) `contracts()`: siete comprobaciones SQL, cada una devuelve un recuento de infracciones. Un cliente por registro de origen, ningún registro de origen ausente del *crosswalk* (*anti-join*), un *golden record* por cada cliente vivo, exactamente un hogar por cliente, el hogar padre existe, la clave del *spine* es única y las ocho columnas PII están clasificadas. Un contrato solo se cumple con cero infracciones. Por qué: el gobierno es código que se ejecuta en cada construcción, no un documento. Diapositiva 20.
7. [06_customer_spine.py#L219-L230](06_customer_spine.py#L219-L230) Preparación de `main()`: abre `results/mdm.duckdb`, toma una única marca de tiempo UTC para la construcción y calcula la versión del modelo de emparejamiento como los 12 primeros caracteres hexadecimales del SHA-256 de `splink_model.json`. Por qué: linaje, para que un consumidor sepa qué modelo produjo cada cliente.
8. [06_customer_spine.py#L232-L243](06_customer_spine.py#L232-L243) Carga `golden_record`, `xref` y la dirección de cada registro de origen con su cliente, y después construye los hogares y la jerarquía.
9. [06_customer_spine.py#L245-L250](06_customer_spine.py#L245-L250) `con.register()` expone los DataFrames de pandas a SQL, y `CREATE OR REPLACE TABLE` materializa `household` e `identity_hierarchy` (se reconstruyen en cada ejecución).
10. [06_customer_spine.py#L251-L271](06_customer_spine.py#L251-L271) La tabla `customer_spine`: una fila por cliente maestro con el hogar, los atributos maestros, `source_keys` (una lista de DuckDB como `['CRM:CRM-000123', 'WEB:WEB-000456']`), `weakest_link_probability` (el registro menos seguro, una señal para los *data stewards*), `golden_version`, `match_model_version` y `published_at`. `GROUP BY ALL` agrupa por todas las columnas no agregadas. Diapositivas 20 y 25.
11. [06_customer_spine.py#L272-L281](06_customer_spine.py#L272-L281) Escribe `column_classification` a partir de `PII_COLUMNS` (en un *lakehouse* serían etiquetas de columna del catálogo).
12. [06_customer_spine.py#L283-L290](06_customer_spine.py#L283-L290) Ejecuta los contratos, los imprime y se detiene con `SystemExit` (código de salida distinto de cero) si alguno falla, antes de exportar nada. Por qué: un *spine* roto nunca llega a los consumidores.
13. [06_customer_spine.py#L292-L311](06_customer_spine.py#L292-L311) Solo evaluación. La verdad de los dos CSV se asigna a cada fila del *crosswalk* y después se reduce a una fila por persona verdadera (el hogar predicho más frecuente si el MDM dividió a la persona). `evaluate_clusters` da la precisión y el recall por pares de "estas dos personas viven juntas". La verdad no se usa nunca para construir los hogares.
14. [06_customer_spine.py#L312-L325](06_customer_spine.py#L312-L325) Imprime el resumen: clientes, hogares de varias personas, precisión y recall por pares de los hogares, número de nodos por nivel de la jerarquía y la versión del modelo.
15. [06_customer_spine.py#L327-L337](06_customer_spine.py#L327-L337) Publica: exporta como CSV el *spine*, la jerarquía, los resultados de los contratos y las métricas de hogares (que lee `09_compare.py`), y después cierra la base de datos.
16. [06_customer_spine.py#L340-L342](06_customer_spine.py#L340-L342) Punto de entrada estándar del script.

**Qué deberías ver.**

```
                                       contract  violations  passed
   every source record has exactly one customer           0    True
     no source record without a crosswalk entry           0    True
        every live customer has a golden record           0    True
every customer belongs to exactly one household           0    True
              every customer's household exists           0    True
                            spine key is unique           0    True
                 every PII column is classified           0    True
customers: 4344, multi-person households: 177, people-in-household pair precision=0.9677 recall=0.7463
hierarchy nodes: {'SOURCE': 8586, 'CUSTOMER': 4344, 'HOUSEHOLD': 4164} | match model version: 4480632c71ba
```

Cómo leerlo: se cumplen los siete contratos, así que el *spine* se publica. El *spine* tiene 4,344 clientes (los 8,192 registros iniciales más el lote nuevo, 8,586 registros de origen en total, tal como los consolidó el paso 5). 177 hogares tienen más de una persona; el resto son de una sola persona, lo que da 4,164 nodos de hogar. Cuando el script pone a dos personas en el mismo hogar acierta el 97% de las veces (precisión 0.9677), y encuentra el 75% de los pares reales de convivientes (recall 0.7463). Los fallos son sobre todo personas cuya dirección compartida no aparece nunca en sus registros (mudanzas, formularios web sin dirección). El hash de la versión del modelo cambia cada vez que cambia `splink_model.json`.

**Prueba esto.**
- Baja `ADDRESS_SIMILARITY` ([L60](06_customer_spine.py#L60)) a 70: más grafías de calle se reducen a un solo nodo, así que el recall sube y la precisión baja (se fusionan vecinos de calles parecidas). Súbelo a 95 y pasa lo contrario.
- Quita `"postcode"` de `PII_COLUMNS` ([L64-L73](06_customer_spine.py#L64-L73)): el contrato "every PII column is classified" informa de 1 infracción, el script termina con "data contract failed: spine not published" y no se reescribe ningún CSV.
- Construye los hogares solo con la dirección del *golden record* (cambia la consulta `members` de [L237-L239](06_customer_spine.py#L237-L239) para que lea `address, postcode` de `golden_record`): el recall baja, porque las personas cuya supervivencia eligió una dirección más reciente pierden el enlace con la casa que compartieron.

---

## 07_identity_drift.py

**Qué hace.** Ejecuta el modelo Splink guardado sobre dos instantáneas de los datos: los registros iniciales y una instantánea posterior en la que el 5% de los registros cambió sus datos de contacto y se añadió el lote nuevo. Las dos se agrupan desde cero. Después compara tres formas de dar un id de cliente a los clústeres de la ejecución 2 (renumerar en cada ejecución, usar el id de un registro miembro y arrastrar el id de la ejecución 1 según el solapamiento) y mide cuántos registros existentes recibieron un id distinto.

**Ejecución.** `python 07_identity_drift.py` (desde `er-demo/`, después de `02_splink.py`, que escribe `results/splink_model.json`).

**Lee / Escribe.**
- Lee `data/customers.csv`, `data/new_batch.csv` y `results/splink_model.json`; importa `MODEL_COLUMNS` de `02_splink.py`.
- Escribe `results/identity_drift.csv` (tasa de deriva por estrategia), `results/id_alias.csv` (de id retirado a id superviviente) y `results/id_events.csv` (todos los eventos new / split / merged_into).

**Diapositivas.** 21 (y la cifra de titular del 56% al 0.2% de la diapositiva 3).

**Guía.** [3.10 Deriva de identidad](DEMO_GUIDE.es.md#310-deriva-de-identidad-identity-drift); el recorrido por el código [7. Deriva de identidad](DEMO_GUIDE.es.md#7-deriva-de-identidad-07_identity_driftpy); las preguntas frecuentes [Deriva, MLOps y feature stores](DEMO_GUIDE.es.md#deriva-mlops-y-feature-stores).

### Recorrido

1. [07_identity_drift.py#L1-L38](07_identity_drift.py#L1-L38) **Docstring del módulo.** Define la deriva de identidad, las dos ejecuciones, las tres estrategias de ids y la tasa de deriva, además de las entradas, las salidas y el orden de ejecución. Diapositiva 21.
2. [07_identity_drift.py#L40-L56](07_identity_drift.py#L40-L56) **Importaciones.** `DuckDBAPI` y `Linker` de Splink puntúan en una base de datos DuckDB dentro del proceso. `02_splink.py` no se puede importar con un `import` normal porque su nombre empieza por un dígito, así que `__import__("02_splink")` lo carga para reutilizar `MODEL_COLUMNS` (su `main()` no se ejecuta al importarlo).
3. [07_identity_drift.py#L58-L63](07_identity_drift.py#L58-L63) **Constantes.** `THRESHOLD = 0.95` coincide con 02, así que la ejecución 1 reproduce sus 4,102 clientes. `UPDATE_RATE = 0.05` es la proporción de registros cuyos datos de contacto cambian.
4. [07_identity_drift.py#L66-L80](07_identity_drift.py#L66-L80) **`cluster()`.** Carga el JSON del modelo entrenado en un `Linker` nuevo (sin reentrenar), puntúa los pares candidatos con p >= 0.5, agrupa con p >= 0.95 y devuelve el `cluster_id` de Splink para cada `unique_id`. Mantener el modelo fijo significa que cualquier deriva sale de los datos, no de un modelo nuevo.
5. [07_identity_drift.py#L83-L89](07_identity_drift.py#L83-L89) **`sequential()`.** El enfoque ingenuo: numerar los clústeres `C0000001...` por orden de primera aparición tras ordenar por id de registro. Cualquier clúster que aparezca o desaparezca al principio del orden desplaza todos los números posteriores. Diapositiva 21 (lo que no hay que hacer).
6. [07_identity_drift.py#L92-L128](07_identity_drift.py#L92-L128) **`carry_forward()`.** El remedio. Construye una tabla de solapamiento de registros entre cada clúster de la ejecución 2 y cada id de la ejecución 1 ([L96-L98](07_identity_drift.py#L96-L98)), la ordena por tamaño del solapamiento resolviendo los empates a favor del id menor en orden lexicográfico (el más antiguo) ([L101](07_identity_drift.py#L101)) y entrega de forma voraz cada id antiguo a un único clúster nuevo como mucho ([L103-L107](07_identity_drift.py#L103-L107)). Esa es la regla de las divisiones: el trozo más grande conserva el id. Los clústeres que se quedan sin id reciben un número nuevo y un evento: `split` si sus registros venían de un clúster antiguo, `new` si solo contienen registros del lote nuevo ([L109-L120](07_identity_drift.py#L109-L120)). Los ids antiguos que ningún clúster conservó se fusionaron; cada uno recibe un evento `merged_into` que apunta al clúster que tiene la mayoría de sus registros ([L122-L126](07_identity_drift.py#L122-L126)). Diapositiva 21 (reglas de arrastre de ids).
7. [07_identity_drift.py#L131-L136](07_identity_drift.py#L131-L136) **`drift()`.** Proporción de los registros presentes en las dos ejecuciones cuyo id es distinto. Los registros del lote nuevo no pueden derivar, así que solo cuenta la intersección.
8. [07_identity_drift.py#L139-L154](07_identity_drift.py#L139-L154) **`membership_changed()`.** La cifra de contexto: la proporción de registros de la ejecución 1 cuyo conjunto de compañeros de clúster de la ejecución 1 es distinto en la ejecución 2. Se ignoran las etiquetas y se comparan conjuntos de registros, así que mide el cambio real de los clústeres, que está cerca del límite inferior que puede alcanzar cualquier estrategia de ids.
9. [07_identity_drift.py#L157-L176](07_identity_drift.py#L157-L176) **`main()`, construcción de la ejecución 2.** Con semillas fijas (7), se elige el 5% de los registros; la mitad recibe un número de móvil `07...` aleatorio nuevo y la otra mitad pierde el email. Esto debilita la evidencia que mantenía unidos algunos clústeres. Se añade el lote nuevo.
10. [07_identity_drift.py#L178-L181](07_identity_drift.py#L178-L181) **Dos agrupaciones.** Las dos instantáneas se estandarizan y se agrupan desde cero con el mismo modelo.
11. [07_identity_drift.py#L183-L193](07_identity_drift.py#L183-L193) **Las tres estrategias.** Los ids de la ejecución 1 son la numeración secuencial (lo que se publicó). La ejecución 2 recibe una numeración secuencial, un id representativo (`R-` más el `cluster_id` de Splink, comparado con la misma forma para la ejecución 1) y un id arrastrado cuyos números nuevos empiezan después del último número de la ejecución 1.
12. [07_identity_drift.py#L195-L207](07_identity_drift.py#L195-L207) **Informe.** Una fila por estrategia más la fila de contexto, impresas como tabla, y después el recuento de eventos de arrastre. Diapositivas 21 y 3.
13. [07_identity_drift.py#L211-L216](07_identity_drift.py#L211-L216) **Salidas.** La tabla de deriva, la tabla de alias (solo fusiones, renombradas a `retired_id` / `surviving_id` para poder traducir las claves antiguas) y el registro completo de eventos.
14. [07_identity_drift.py#L220-L221](07_identity_drift.py#L220-L221) Punto de entrada estándar.

### Qué deberías ver

Splink imprime primero su aviso de "untrained parameters" para `dob` y `postcode` dos veces, una por ejecución (m values not fully trained); es lo esperable con el modelo guardado. Después:

```text
run 1: 4102 customers, run 2: 4309 customers
                              strategy  drift_rate
                            sequential      0.5613
                        representative      0.0087
                         carry_forward      0.0020
context: records whose cluster changed      0.0051
carry-forward events: {'new': 201, 'split': 11, 'merged_into': 5}
```

Cómo leerlo:
- La ejecución 1 da los mismos 4,102 clientes que `02_splink.py`; la ejecución 2 tiene 4,309, unos 200 más por el lote nuevo y unas pocas divisiones.
- La renumeración secuencial cambia el 56% de los ids existentes aunque solo el 0.51% de los registros cambió de verdad de clúster. Eso es deriva pura.
- El id representativo cambia el 0.87%: cuando un clúster cambia, su registro representativo puede cambiar, y entonces todos los miembros reciben un id nuevo.
- El arrastre de ids cambia solo el 0.20%, por debajo de la cifra de contexto del 0.51%: solo se mueven los registros que se separan o se fusionan, y todos los demás de un clúster que cambia conservan su id.
- Eventos: 201 clientes totalmente nuevos, 11 trozos separados con ids nuevos y 5 ids retirados registrados en `id_alias.csv`.

### Prueba esto

1. Pon `UPDATE_RATE = 0.2` (línea 63). Más registros pierden evidencia, así que se dividen más clústeres: suben la cifra de contexto, el número de eventos `split` y todas las tasas de deriva, pero el arrastre de ids sigue muy por debajo del secuencial.
2. Cambia `THRESHOLD` a 0.99 (línea 61). Los clústeres son más pequeños y más frágiles, así que pequeños cambios en los datos los dividen más a menudo; vigila los recuentos de `split` y `merged_into`.
3. Abre `results/id_alias.csv` y compara los ids. En esta ejecución, una de las cinco fusiones conserva el id más alto (más reciente): `C0000208` se retira en favor de `C0002630`, porque el trozo superviviente se elige primero por el mayor solapamiento y la antigüedad solo desempata (línea 101).

---

## 08_mlops_feature_store.py

**Qué hace.** Ejecuta el comparador supervisado del paso 3 como un producto. Las características de los pares van a un pequeño *feature store* versionado en DuckDB, se entrenan dos versiones del modelo con un reparto estrictamente disjunto por entidades, se registran con sus métricas y pasan por una puerta de promoción que mueve el alias `champion`. Después, el *champion* puntúa un lote entrante normal y un feed roto a propósito, y los KPI sin etiquetas con alertas de deriva PSI muestran cuál está sano.

**Ejecución.** `python 08_mlops_feature_store.py` (solo necesita `data/customers.csv` y `data/new_batch.csv` de `data/generate_data.py`; reutiliza el *blocking* de `01_rules_rapidfuzz.py` y las características de `03_ml_recordlinkage.py`). El registro en MLflow solo se hace si `mlflow` está instalado.

**Lee / Escribe.**
- Lee: `data/customers.csv` y `data/new_batch.csv`.
- Escribe: `results/feature_store.duckdb` (tablas `feature_definitions`, `pair_features_train`, `pair_features_new_batch` y `pair_features_broken_feed`), `results/model_registry/matcher_v1.pkl`, `matcher_v2.pkl` y `registry.json`, `results/model_versions.csv`, `results/monitoring_report.csv` y `results/mlruns/` si MLflow está instalado. El registro y el *feature store* se borran al principio de cada ejecución.

**Diapositivas.** 22 (sección de MLOps), 23 (*Feature store*, registro, puerta), 24 (Monitorización), 11 (Características supervisadas), 13 (Precisión o recall), 25 (correspondencia con el *lakehouse*), 27 (Gráfico de resultados).

**Guía.** [3.11 MLOps y feature stores](DEMO_GUIDE.es.md#311-mlops-y-feature-stores), [3.6 Paso 5. Evalúa sin engañarte](DEMO_GUIDE.es.md#paso-5-evalúa-sin-engañarte), [3.6 Paso 6. Confianza: ¿p = 0.9 es de verdad un 90%?](DEMO_GUIDE.es.md#paso-6-confianza-p--09-es-de-verdad-un-90), [3.9 Métricas de calidad del emparejamiento](DEMO_GUIDE.es.md#39-métricas-de-calidad-del-emparejamiento), [Recorrido por el código 8](DEMO_GUIDE.es.md#8-mlops-y-feature-store-08_mlops_feature_storepy), [Preguntas frecuentes: Deriva, MLOps y feature stores](DEMO_GUIDE.es.md#deriva-mlops-y-feature-stores).

**Recorrido.**

1. [08_mlops_feature_store.py#L1-L38](08_mlops_feature_store.py#L1-L38) Docstring del módulo: las cuatro partes (*feature store*, evaluación, registro, monitorización), las entradas, las salidas y el orden de ejecución. Diapositiva 23.
2. [08_mlops_feature_store.py#L40-L77](08_mlops_feature_store.py#L40-L77) Importaciones. Dos familias de modelos (regresión logística dentro de un pipeline y `HistGradientBoostingClassifier`), `average_precision_score` (área bajo la curva de precisión-recall) y `brier_score_loss` (error cuadrático medio de las probabilidades). Los pasos 1 y 3 se cargan con `__import__` porque sus nombres de archivo empiezan por un dígito; reutilizarlos mantiene el *blocking* y las características idénticos a los de los pasos anteriores.
3. [08_mlops_feature_store.py#L79-L89](08_mlops_feature_store.py#L79-L89) Constantes y `now()`. `THRESHOLD = 0.9` es la decisión de coincidencia (la misma que en el paso 3). `PSI_ALERT = 0.2` sigue la regla práctica habitual (por debajo de 0.1, estable; de 0.1 a 0.2, vigilar; por encima de 0.2, actuar). Diapositiva 24.
4. [08_mlops_feature_store.py#L93-L163](08_mlops_feature_store.py#L93-L163) `FeatureStore`, un *feature store* offline diminuto. Diapositiva 23.
   - [L96-L103](08_mlops_feature_store.py#L96-L103) Abre el archivo DuckDB y crea el catálogo `feature_definitions`.
   - [L105-L115](08_mlops_feature_store.py#L105-L115) `version()`: SHA-256 de los nombres de las características ordenados más el vocabulario TF-IDF ajustado, acortado a `fs_` más 10 caracteres hexadecimales. Reajustar el TF-IDF sobre otros datos cambia el vocabulario y, por tanto, la versión.
   - [L117-L137](08_mlops_feature_store.py#L117-L137) `register()`: escribe una fila de catálogo por característica, solo una vez por versión (idempotente).
   - [L139-L150](08_mlops_feature_store.py#L139-L150) `write()`: convierte el MultiIndex del par en las columnas `id_l` e `id_r`, marca `feature_set_version` y `computed_at` y sustituye la tabla.
   - [L152-L163](08_mlops_feature_store.py#L152-L163) `read()`: rechaza una tabla cuya versión sea distinta de la que espera el modelo (`ValueError`). Por qué: es la protección contra el desajuste entre entrenamiento y servicio.
5. [08_mlops_feature_store.py#L167-L183](08_mlops_feature_store.py#L167-L183) `ece()`: el error de calibración esperado. Las probabilidades se reparten en 10 intervalos de la misma anchura; la diferencia de cada intervalo entre la tasa de coincidencia observada y la p media predicha se pondera por su proporción de pares. Un ECE bajo significa que "p = 0.9" acierta de verdad un 90% de las veces, lo que importa porque los pasos 2 y 5 encaminan los pares según su probabilidad. Diapositiva 23.
6. [08_mlops_feature_store.py#L186-L208](08_mlops_feature_store.py#L186-L208) `psi()`: el índice de estabilidad de la población, la suma de `(actual% - expected%) * ln(actual% / expected%)` sobre los intervalos. Los límites de los intervalos son los deciles de referencia (sin duplicados en las características binarias), los valores ausentes tienen su propio intervalo para que un salto en los nulos sea visible, y los intervalos vacíos se recortan a 0.0001 para evitar el logaritmo de cero. Diapositiva 24.
7. [08_mlops_feature_store.py#L211-L231](08_mlops_feature_store.py#L211-L231) `evaluate()`: puntúa los pares de prueba, conserva los pares con p de al menos 0.9, los agrupa con union-find y devuelve las métricas de pares (precisión media, Brier, ECE) y de clúster (F1 B-cubed, precisión y recall por pares y el clúster más grande como detector de encadenamiento). Por qué: la tabla de clientes trabaja con clústeres, no con pares. Diapositivas 13 y 15.
8. [08_mlops_feature_store.py#L235-L266](08_mlops_feature_store.py#L235-L266) El registro: `load_registry()` y `save_registry()` leen y escriben `registry.json` (una lista `versions` y un mapa `aliases`); `register()` serializa el modelo con pickle como `matcher_v{n}.pkl` y guarda su tipo de modelo, la versión del conjunto de características, el umbral, las métricas y la marca de tiempo. Diapositiva 23.
9. [08_mlops_feature_store.py#L269-L287](08_mlops_feature_store.py#L269-L287) `promotion_gate()`: tres comprobaciones en orden. El ECE debe ser como mucho 0.05; el primer modelo aceptable pasa a ser *champion*; a partir de ahí, el F1 B-cubed debe ser al menos el del *champion* y el clúster más grande no debe crecer en más de 2 (ningún encadenamiento nuevo). Diapositiva 23.
10. [08_mlops_feature_store.py#L290-L307](08_mlops_feature_store.py#L290-L307) `log_to_mlflow()`: copia opcional de cada entrada del registro en un almacén local de MLflow (parámetros, métricas, etiqueta `promoted` y el artefacto pickle). Se omite sin avisar si no hay MLflow.
11. [08_mlops_feature_store.py#L311-L326](08_mlops_feature_store.py#L311-L326) `batch_pairs()`: aplica el *blocking* a los registros antiguos y nuevos juntos con las claves del paso 1, conserva solo los pares con exactamente un registro nuevo y pone el id antiguo a la izquierda. Diapositiva 7.
12. [08_mlops_feature_store.py#L329-L348](08_mlops_feature_store.py#L329-L348) `monitor()`: KPI sin etiquetas para un lote puntuado: pares candidatos, tasa de coincidencia (p de al menos 0.9), proporción en la zona gris (de 0.5 a 0.9, la carga de revisión), PSI de la puntuación frente a las puntuaciones del entrenamiento y PSI de cada característica, cada una marcada cuando supera 0.2. Diapositiva 24.
13. [08_mlops_feature_store.py#L353-L359](08_mlops_feature_store.py#L353-L359) `main()` empieza con un registro y un archivo de *feature store* nuevos para que la demo sea repetible.
14. [08_mlops_feature_store.py#L361-L378](08_mlops_feature_store.py#L361-L378) Carga y estandariza la instantánea de entrenamiento, le aplica el *blocking* (6,405 pares), ajusta el TF-IDF una vez, calcula las 14 características de los pares con `features()` del paso 3, las versiona, registra las definiciones y escribe `pair_features_train`. Diapositivas 7, 11 y 23.
15. [08_mlops_feature_store.py#L380-L384](08_mlops_feature_store.py#L380-L384) El entrenamiento vuelve a leer las características del almacén, como lo haría un trabajo programado, y construye las etiquetas: 1 cuando los dos registros comparten id de persona verdadera.
16. [08_mlops_feature_store.py#L386-L398](08_mlops_feature_store.py#L386-L398) Reparto estrictamente disjunto por entidades: un tercio de las personas (semilla 0) son personas de prueba. Los pares de entrenamiento tienen los dos registros de personas de entrenamiento y los de prueba, los dos de personas de prueba; los pares que cruzan la frontera se descartan. Por qué: un reparto aleatorio de pares filtra a la misma persona en entrenamiento y prueba e infla las métricas. Diapositiva 12.
17. [08_mlops_feature_store.py#L400-L425](08_mlops_feature_store.py#L400-L425) Entrena, evalúa, registra y pasa por la puerta a cada candidato en orden (v1, regresión logística con imputación y escalado; v2, *gradient boosting*). La promoción solo mueve el alias; las versiones antiguas se quedan en el registro. Diapositiva 23.
18. [08_mlops_feature_store.py#L427-L431](08_mlops_feature_store.py#L427-L431) El servicio carga el *champion* por su alias desde el archivo del registro y calcula la distribución de puntuaciones de referencia sobre los pares de entrenamiento.
19. [08_mlops_feature_store.py#L433-L439](08_mlops_feature_store.py#L433-L439) Dos lotes: el `new_batch.csv` real y un feed roto en el que faltan los teléfonos y los nombres de pila se reducen a iniciales. Diapositiva 24.
20. [08_mlops_feature_store.py#L440-L457](08_mlops_feature_store.py#L440-L457) Para cada lote: estandariza, aplica el *blocking* frente a los registros existentes, calcula las características con el vectorizador del entrenamiento, las escribe a través del almacén y las vuelve a leer con la versión del conjunto de características del *champion* (la comprobación de desajuste), ejecuta `monitor()` e imprime los cuatro KPI principales y las alertas que haya.
21. [08_mlops_feature_store.py#L458-L464](08_mlops_feature_store.py#L458-L464) Exporta `monitoring_report.csv` (formato largo: batch, kpi, value, alert) y `model_versions.csv` (una fila por versión), que lee `09_compare.py`.
22. [08_mlops_feature_store.py#L467-L469](08_mlops_feature_store.py#L467-L469) Punto de entrada estándar del script.

**Qué deberías ver.**

```
feature store: 6405 pair rows, 14 features, version fs_dc5909e646
entity-disjoint split: 4197 train pairs, 1857 test pairs
v1 logistic_regression: {'average_precision': 0.9999, 'brier': 0.0093, 'ece': 0.0122, 'bcubed_f1': 0.9874, 'pair_precision': 1.0, 'pair_recall': 0.9538, 'largest_cluster': 5} -> PROMOTED (no champion yet)
v2 gradient_boosting: {'average_precision': 1.0, 'brier': 0.0032, 'ece': 0.0038, 'bcubed_f1': 0.993, 'pair_precision': 0.9935, 'pair_recall': 0.9777, 'largest_cluster': 5} -> PROMOTED (B-cubed F1 0.993 >= champion 0.9874)
monitoring new_batch: {'candidate_pairs': 439, 'match_rate': 0.8929, 'grey_zone_share': 0.0, 'psi_score': 0.027} alerts: none
monitoring broken_feed: {'candidate_pairs': 303, 'match_rate': 0.9835, 'grey_zone_share': 0.0066, 'psi_score': 2.7695} alerts: ['psi_score', 'psi_first_jw', 'psi_phone_exact', 'psi_record_tfidf_cos']
```

Cómo leerlo:
- El *feature store* contiene los mismos 6,405 pares del *blocking* que los pasos 1 a 3, con 14 características. El hash de la versión no cambia mientras no cambien las características ni los datos.
- El reparto conserva 4,197 + 1,857 = 6,054 pares; los otros 351 cruzan la frontera entre entrenamiento y prueba y se descartan.
- La v1 se promociona porque todavía no hay *champion*. La v2 tiene mejor ordenación, Brier y calibración (ECE 0.004 frente a 0.012) y un F1 B-cubed más alto (0.993 frente a 0.987) sin encadenamiento extra (clúster más grande de 5 en las dos), así que pasa a ser *champion*. Fíjate en la precisión por pares de 1.0 de la v1 con un recall más bajo: el modelo lineal es más prudente.
- El lote normal tiene un PSI de puntuación de 0.027 (estable) y ninguna alerta. El feed roto tiene un PSI de puntuación de 2.77 y alertas en la puntuación, `first_jw`, `phone_exact` y `record_tfidf_cos`, que señalan directamente las entradas rotas. Su tasa de coincidencia parece mejor (0.98 frente a 0.89) solo porque desapareció cerca de un tercio de los pares candidatos (el teléfono era una clave de *blocking*). Un solo KPI escondería el incidente.

**Prueba esto.**
- Endurece la puerta de calibración: cambia `0.05` por `0.01` en [L275](08_mlops_feature_store.py#L275). La v1 (ECE 0.0122) se rechaza ahora con "calibration too poor", así que la v2 se promociona con "no champion yet".
- Invierte el orden de `candidates` ([L402-L409](08_mlops_feature_store.py#L402-L409)) para que el *gradient boosting* sea la v1. Entonces la regresión logística no pasa la puerta (F1 B-cubed 0.9874, por debajo de 0.993) y se queda como *challenger* ("kept as challenger").
- Haz el feed roto más suave, por ejemplo quitando solo la línea `phone=None` ([L437](08_mlops_feature_store.py#L437)). Espera menos alertas (sobre todo `psi_phone_exact` y la puntuación), lo que muestra que el PSI por característica te dice qué fuente se rompió.

---

## 09_compare.py

**Qué hace:** el paso del informe. Lee los CSV de métricas que los pasos 1 a 8 dejaron en `results/`, los convierte en tablas Markdown y escribe un único archivo, `results/comparison.md`. No calcula nada nuevo, así que es rápido y se puede volver a ejecutar sin riesgo; cualquier entrada que falte se omite, de modo que un pipeline parcial produce un informe parcial (tiene que existir al menos un archivo de comparador).

**Ejecución:** `python 09_compare.py` (última línea de [run_all.sh](run_all.sh)).

**Lee / Escribe:** lee `results/metrics_rapidfuzz.csv`, `metrics_splink.csv`, `metrics_ml.csv` y `metrics_graph.csv` y, opcionalmente, `metrics_households.csv`, `spine_contracts.csv`, `identity_drift.csv`, `model_versions.csv` y `monitoring_report.csv`. Escribe `results/comparison.md` e imprime el mismo texto.

**Diapositivas:** 27 (Gráfico de resultados: la tabla de comparadores), 28 (Lecciones), además de las tablas que hay detrás de la 20 (contratos del *spine*, hogares), la 21 (deriva), y la 23 y la 24 (registro y monitorización).

**Guía:** [9. Informe](DEMO_GUIDE.es.md#9-informe-09_comparepy), [5. Recorrido de diez minutos](DEMO_GUIDE.es.md#5-recorrido-de-diez-minutos), [1. Ejecutar la demo](DEMO_GUIDE.es.md#1-ejecutar-la-demo) (ten `comparison.md` abierto en una pestaña).

**Recorrido**

1. [09_compare.py#L1-L12](09_compare.py#L1-L12) Docstring: entradas, salida, cómo ejecutarlo y diapositivas.
2. [09_compare.py#L14-L19](09_compare.py#L14-L19) Importaciones y `RES`, la carpeta `results/` junto al script.
3. [09_compare.py#L20-L30](09_compare.py#L20-L30) Los cuatro archivos de métricas de comparadores (reglas, Splink, ML y las dos filas de reparación con grafos), apilados con `pd.concat` para los que existan. Una fila por método da la comparación equivalente de la diapositiva 27.
4. [09_compare.py#L31-L43](09_compare.py#L31-L43) `cols`: las columnas que se muestran. Incluyen `false_merges_pairs`, `missed_pairs` y `largest_cluster`, no solo la precisión y el recall, porque la historia de la demo va de recuentos de errores y de encadenamiento (diapositivas 13 y 15).
5. [09_compare.py#L44-L49](09_compare.py#L44-L49) Empieza el informe: el título y la tabla de comparadores con `DataFrame.to_markdown()` (que necesita el paquete `tabulate`).
6. [09_compare.py#L50-L62](09_compare.py#L50-L62) Secciones opcionales de los pasos 6 a 8: hogares (solo se conservan cinco columnas), contratos de datos del *spine*, deriva de identidad y registro de modelos, cada una añadida solo si existe su CSV.
7. [09_compare.py#L63-L76](09_compare.py#L63-L76) Monitorización: el CSV está en formato largo (batch, kpi, value, alert), así que los cuatro KPI principales se pivotan a una fila por KPI y una columna por lote, seguidos de una línea con cada comprobación PSI que superó el umbral de alerta de 0.2 (diapositiva 24).
8. [09_compare.py#L77-L80](09_compare.py#L77-L80) Une los bloques, escribe `results/comparison.md` y lo imprime.

**Qué deberías ver:** la tabla de comparadores (semilla 42):

| method | pair P | pair R | B3-F1 | entities | largest | false merges | missed |
|:--|--:|--:|--:|--:|--:|--:|--:|
| rules + rapidfuzz | 0.9523 | 0.9127 | 0.9707 | 4278 | 9 | 267 | 510 |
| splink (EM, p>=0.95) | 0.9661 | 0.9649 | 0.9853 | 4102 | 7 | 198 | 205 |
| recordlinkage + gradient boosting (p>=0.9) | 0.9757 | 0.9752 | 0.9898 | 4082 | 7 | 142 | 145 |
| splink + graph repair | 0.9979 | 0.9617 | 0.9889 | 4144 | 6 | 12 | 224 |
| ml + graph repair | 0.9984 | 0.9723 | 0.9918 | 4108 | 6 | 9 | 162 |

Cómo leerlo: cada comparador es mejor que el anterior, pero el gran salto de precisión viene del paso de grafos, que reduce las fusiones erróneas de 198 a 12 (Splink) y de 142 a 9 (ML) a cambio de una pequeña pérdida de recall. Las secciones posteriores muestran los hogares (precisión por pares 0.9677, recall 0.7463), los siete contratos del *spine* cumplidos con 0 infracciones, las tasas de deriva 0.5613 (secuencial), 0.0087 (representativo) y 0.0020 (arrastre de ids), el registro (v1 regresión logística con ECE 0.0122, v2 *gradient boosting* con ECE 0.0038 y F1 B-cubed 0.993) y la monitorización (lote nuevo con PSI 0.027 y sin alertas; feed roto con PSI 2.7695 y alertas en `psi_score`, `psi_first_jw`, `psi_phone_exact` y `psi_record_tfidf_cos`).

**Prueba esto**

1. Borra `results/identity_drift.csv` y vuelve a ejecutar `09_compare.py`: la sección de deriva desaparece y el resto del informe no cambia, lo que muestra la lógica de omitir lo que falta en [L58-L62](09_compare.py#L58-L62).
2. Añade `"bcubed_precision"` y `"bcubed_recall"` a `cols`: la tabla muestra que la precisión B-cubed se mantiene alta incluso para el comparador de reglas, porque la mayoría de sus errores está en unos pocos clústeres.
3. Vuelve a ejecutar solo `02_splink.py` con otro umbral y después `09_compare.py`: solo se mueve la fila de Splink, porque el informe se limita a leer lo último que escribió cada paso (la fila "splink + graph repair" solo cambia si vuelves a ejecutar también `04_graph_resolution.py`).

---

## run_all.sh

**Qué hace:** ejecuta toda la demo de principio a fin en el orden del pipeline (diapositiva 4): generar los datos, los tres comparadores, la reparación con grafos, el MDM, el *customer spine*, la deriva de identidad, MLOps y, por último, el informe. Se detiene en el primer paso que falle (`set -e`), así que un paso posterior nunca se ejecuta con entradas obsoletas o ausentes. Cada paso lee los archivos que escribieron los anteriores, así que el orden forma parte del diseño, no es una comodidad.

**Ejecución:** `./run_all.sh` (o `bash run_all.sh`) desde cualquier sitio; primero cambia a su propia carpeta. Para elegir el intérprete: `PYTHON=.venv/bin/python ./run_all.sh`. En PowerShell de Windows, usa la secuencia explícita de [1. Ejecutar la demo](DEMO_GUIDE.es.md#1-ejecutar-la-demo). Una ejecución completa tarda unos 45 segundos en un portátil.

**Lee / Escribe:** todo lo que leen y escriben los pasos: `data/customers.csv`, `data/new_batch.csv` y la carpeta `results/` (CSV de métricas, clústeres, `mdm.duckdb`, `feature_store.duckdb`, `model_registry/`, gráficos de Splink y, por último, `comparison.md`).

**Diapositivas:** 4 (Pipeline), 29 (Consigue el código). El comentario de cada línea indica las diapositivas de ese paso.

**Guía:** [1. Ejecutar la demo](DEMO_GUIDE.es.md#1-ejecutar-la-demo), [Flujo de extremo a extremo](DEMO_GUIDE.es.md#flujo-de-extremo-a-extremo), [10. Solución de problemas](DEMO_GUIDE.es.md#10-solución-de-problemas).

**Recorrido**

1. [run_all.sh#L1-L5](run_all.sh#L1-L5) *Shebang* (`bash` a través de `env`, para que funcione allí donde bash esté en el PATH) y una cabecera de uso.
2. [run_all.sh#L7-L8](run_all.sh#L7-L8) `set -e`: aborta con el primer código de salida distinto de cero.
3. [run_all.sh#L9-L10](run_all.sh#L9-L10) `cd "$(dirname "$0")"`: se ejecuta desde la carpeta del script para que las rutas relativas como `data/` y `results/` se resuelvan, sea cual sea el directorio actual de quien lo llama.
4. [run_all.sh#L11-L13](run_all.sh#L11-L13) `${PYTHON:-python3}` usa `$PYTHON` si está definida y, si no, `python3`. El paso 0 crea los datos con la verdad conocida (diapositiva 5).
5. [run_all.sh#L14-L19](run_all.sh#L14-L19) Los tres comparadores: reglas hechas a mano con rapidfuzz (diapositivas 7 y 8), Fellegi-Sunter de Splink con EM (diapositivas 9 y 10) y *gradient boosting* supervisado sobre características de recordlinkage (diapositivas 11 a 13).
6. [run_all.sh#L20-L21](run_all.sh#L20-L21) Reparación con grafos con restricciones cannot-link y corte mínimo (diapositivas 15 a 17). Necesita las puntuaciones de pares de Splink y de ML de los pasos 2 y 3.
7. [run_all.sh#L22-L25](run_all.sh#L22-L25) Gestión de maestros: mini MDM con *golden records* y el lote incremental (diapositiva 19) y, después, *customer spine*, hogares y jerarquía (diapositiva 20).
8. [run_all.sh#L26-L29](run_all.sh#L26-L29) Deriva de identidad entre dos ejecuciones (diapositiva 21) y el *feature store*, el registro, la puerta de promoción y la monitorización (diapositivas 23 y 24). `05_mdm.py` y `08_mlops_feature_store.py` reinician sus bases de datos, así que las repeticiones parten del mismo estado.
9. [run_all.sh#L30-L31](run_all.sh#L30-L31) Reúne todo en `results/comparison.md` (diapositiva 27).

**Qué deberías ver:** las primeras líneas son

```text
customers.csv: 8192 records for 4000 people
new_batch.csv: 400 records
households with 2 people: 183
blocking: {'candidate_pairs': 6405, 'pair_completeness': 0.9649, 'reduction_ratio': 0.999809}
```

seguidas del resumen de cada paso: reglas, 267 fusiones erróneas / 510 pares perdidos; Splink, 198 / 205 y `review queue (0.5 <= p < 0.95): 161 pairs`; ML, 142 / 145; reparación con grafos, 12 (Splink: 42 componentes divididas, 80 aristas cortadas) y 9 (ML); MDM, `incremental batch: {'auto_linked': 198, 'to_review': 4, 'new_customer': 202}` y `returning customers correctly attached: 197/200`; *spine*, `customers: 4344, multi-person households: 177`; deriva, 0.5613 / 0.0087 / 0.0020; MLOps, v1 y después v2 promocionadas, PSI del feed roto de 2.7695 con cuatro alertas; y, por último, las tablas de `comparison.md`. Splink imprime varios bloques `WARNING` sobre niveles "not observed in dataset" y valores de `m` sin entrenar para `dob` y `postcode`; son esperables (algunos niveles de comparación no aparecen nunca en estos datos sintéticos) y no detienen la ejecución.

**Prueba esto**

1. Ejecuta `PYTHON=.venv/bin/python ./run_all.sh` para usar el entorno virtual del proyecto sin activarlo.
2. Comenta la línea de `04_graph_resolution.py` y vuelve a ejecutar: `09_compare.py` sigue generando un informe, pero las filas de grafos salen del `metrics_graph.csv` de la ejecución anterior (o faltan en una copia limpia del repositorio), lo que muestra por qué hay que ejecutar la secuencia completa. En una copia limpia, `05_mdm.py` usa entonces `clusters_splink.csv`, así que el MDM parte de clústeres sin reparar.
3. Mide el tiempo con `time ./run_all.sh` y compáralo con los 45 segundos aproximados que cita la guía; después mide pasos sueltos para ver cuáles dominan.

---

## databricks/splink_on_databricks.py

> **No se ejecuta en local.** Es un notebook de Databricks (exportado como código fuente). Necesita un *workspace* de Databricks, la sesión `spark` que proporciona Databricks, una tabla Silver de Unity Catalog `customer_std` y un volumen para *checkpoints*. Es un ejemplo de diseño y no forma parte del pipeline verificado en el portátil ni de `run_all.sh`; ninguna cifra de esta sección sale de ejecutarlo.

**Qué hace.** Ejecuta el mismo modelo Fellegi-Sunter que `02_splink.py` (mismas reglas de *blocking*, comparaciones y pasos de entrenamiento) sobre Spark a través de `SparkAPI` de Splink en lugar de `DuckDBAPI`. Los pares, los clústeres y la cola de revisión de los *data stewards* se escriben como tablas Delta en Unity Catalog, y el JSON del modelo, los parámetros y los KPI sin etiquetas se registran en una única ejecución de MLflow. Muestra cómo cada archivo local corresponde a una capa del *lakehouse*.

**Ejecución.** Importa el archivo en un *workspace* de Databricks (se abre como un notebook con celdas de Markdown y de código), asocia un clúster con Spark 3.4+ y `%pip install splink`, y ejecuta todas las celdas. En local solo puedes comprobar que compila: `python -m py_compile databricks/splink_on_databricks.py`.

**Lee / Escribe.**
- Lee la tabla de Unity Catalog `main.customer_mdm.customer_std` (una fila estandarizada por registro de origen, con las columnas que crea `common/standardise.py`).
- Escribe las tablas Delta `pairs`, `clusters` y `review_queue` en `main.customer_mdm`; los *checkpoints* en `/Volumes/main/customer_mdm/checkpoints`; `/tmp/splink_model.json` registrado como artefacto de MLflow, además de los parámetros y las métricas de MLflow.

**Diapositivas.** 25 (correspondencia con el *lakehouse*), 26 (framework a escala), 23 (MLflow, alias *champion*).

**Guía.** Recorrido por el código: [Integraciones opcionales](DEMO_GUIDE.es.md#integraciones-opcionales-databrickssplink_on_databrickspy-y-zinggzingg_customerspy); [7. Diseño del sistema: el framework a escala](DEMO_GUIDE.es.md#7-diseño-del-sistema-el-framework-a-escala); [3.5 Fellegi-Sunter](DEMO_GUIDE.es.md#35-fellegi-sunter-paso-a-paso) y el [Paso 8. Cómo aprende el modelo m y u](DEMO_GUIDE.es.md#paso-8-cómo-aprende-el-modelo-m-y-u-sin-etiquetas) para las llamadas de entrenamiento; [3.11 MLOps y feature stores](DEMO_GUIDE.es.md#311-mlops-y-feature-stores).

### Recorrido

1. [databricks/splink_on_databricks.py#L1-L17](databricks/splink_on_databricks.py#L1-L17) **Celda de Markdown.** `# Databricks notebook source` marca el archivo como notebook; las líneas `# MAGIC %md` se muestran como Markdown. La tabla relaciona las piezas locales con Databricks: los CSV con tablas Delta Bronze, `common/standardise.py` con la tabla Silver, `DuckDBAPI` con `SparkAPI`, `results/*.csv` con tablas de Unity Catalog y `splink_model.json` con un artefacto de MLflow con alias `champion`. Diapositiva 25.
2. [databricks/splink_on_databricks.py#L19-L48](databricks/splink_on_databricks.py#L19-L48) **Separador de celdas y docstring.** `# COMMAND ----------` empieza una celda nueva. El docstring indica las entradas, las salidas, cómo ejecutarlo y que el archivo no se ejecuta en la demo.
3. [databricks/splink_on_databricks.py#L50-L56](databricks/splink_on_databricks.py#L50-L56) **Importaciones.** `mlflow` para el seguimiento de ejecuciones, la librería de comparaciones de Splink, las funciones de columna de Spark `F` y `SparkAPI` como motor.
4. [databricks/splink_on_databricks.py#L58-L67](databricks/splink_on_databricks.py#L58-L67) **Preparación del *workspace*.** Fija el catálogo y el esquema por defecto, define un directorio de *checkpoints* en un volumen de Unity Catalog (los trabajos iterativos de Spark de Splink construyen planes de consulta largos que los *checkpoints* cortan) y carga la tabla Silver. `spark` es una variable global que proporciona Databricks, de ahí el `noqa: F821`.
5. [databricks/splink_on_databricks.py#L70-L92](databricks/splink_on_databricks.py#L70-L92) **Configuración.** Idéntica a la de `02_splink.py`: deduplicación dentro de una tabla combinada, cinco reglas de *blocking* (email, teléfono, DOB + metaphone del apellido, código postal + metaphone del nombre, nombre canónico + apellido) y siete comparaciones con ajuste por frecuencia de términos en los nombres. Solo falta el `retain_intermediate_calculation_columns=True` local. La diapositiva 7 (*blocking*) y la 9 (campos y niveles) explican el contenido.
6. [databricks/splink_on_databricks.py#L96-L98](databricks/splink_on_databricks.py#L96-L98) **Motor y *linker*.** `break_lineage_method="delta_lake_table"` hace que Splink materialice los resultados intermedios como tablas Delta. El *linker* se construye exactamente igual que en local, solo que sobre el DataFrame de Spark.
7. [databricks/splink_on_databricks.py#L102-L114](databricks/splink_on_databricks.py#L102-L114) **Entrenamiento dentro de una ejecución de MLflow.** El *prior* a partir de reglas deterministas con un recall supuesto de 0.7, `estimate_u_using_random_sampling` (u = con qué frecuencia coinciden personas distintas por casualidad, a partir de pares aleatorios; aquí 5e7 pares frente a 2e6 en local, porque Spark se lo puede permitir) y después *expectation maximisation* para m sobre tres bloques, de modo que cada campo se aprende al menos una vez. No se usa ninguna etiqueta. Diapositiva 9.
8. [databricks/splink_on_databricks.py#L118-L128](databricks/splink_on_databricks.py#L118-L128) **Predecir, agrupar, guardar.** Puntúa los pares con p >= 0.2, agrupa con p >= 0.95, escribe `pairs` y `clusters` como tablas Delta y la zona gris 0.5 <= p < 0.95 como `review_queue` para los *data stewards*. Los mismos umbrales que en la ejecución local. Diapositiva 13 (dos umbrales).
9. [databricks/splink_on_databricks.py#L132-L134](databricks/splink_on_databricks.py#L132-L134) **Linaje del modelo.** Guarda el JSON del modelo entrenado y lo registra en MLflow junto con los umbrales, para que cada tabla se pueda rastrear hasta el modelo exacto. Diapositiva 23.
10. [databricks/splink_on_databricks.py#L136-L146](databricks/splink_on_databricks.py#L136-L146) **KPI sin etiquetas.** Número de registros, número de entidades, clúster más grande y tamaño de la cola de revisión, registrados en cada ejecución. Un salto en `max_cluster_size` es la alarma de encadenamiento. Con un *golden set* de los *data stewards* registrarías también la precisión y el recall con `common/evaluate.py` y los compararías con el *champion*. Diapositiva 24.
11. [databricks/splink_on_databricks.py#L148-L155](databricks/splink_on_databricks.py#L148-L155) **Siguientes tareas (Markdown).** *Golden record* y xref en Spark SQL, emparejamiento incremental desde Change Data Feed, una aplicación para los *data stewards*, máscaras de columna para PII y, opcionalmente, *blocking* con búsqueda vectorial. Diapositivas 25 y 26.

### Qué deberías ver

Nada en local: el notebook no se ejecuta en esta demo. En un *workspace* esperarías las tres tablas Delta y una ejecución de MLflow llamada `splink_customer_matching` con el artefacto del modelo, los parámetros `cluster_threshold` y `review_band` y los cuatro KPI. Con los mismos datos sintéticos deberían estar cerca de la ejecución local de Splink (8,192 registros, unas 4,102 entidades, clúster más grande de 7, cola de revisión de unos 161 pares), aunque el muestreo de Spark para u y EM puede producir pequeñas diferencias.

### Prueba esto

1. Cambia la franja de revisión del filtro (línea 127) a 0.8 a 0.95 y compara `review_queue_size` en MLflow: una cola más pequeña para los *data stewards* y más coincidencias perdidas sin revisar.
2. Baja `max_pairs` (línea 110) a 2e6, el valor local, y compara el `n_entities` registrado en dos ejecuciones para ver lo estable que es la estimación de u.
3. Ten en cuenta que `linker.inference.predict_between(...)` en el Markdown (línea 152) es un nombre provisional; consulta la documentación de Splink de tu versión para la API incremental (por ejemplo, `find_matches_to_new_records`) antes de construir esa tarea.

---

## zingg/zingg_customers.py

> **No se ejecuta en local.** Zingg necesita Spark 3.5 y el jar de Zingg (la imagen Docker `zingg/zingg` o una instalación en Databricks), además de una sesión de etiquetado humano. No forma parte de `run_all.sh` y ninguna cifra de la demo sale de él. Comprueba los nombres de los campos y de los tipos de coincidencia con la versión de Zingg que instales.

**Qué hace.** Configura Zingg, una herramienta de resolución de entidades con ML de código abierto sobre Spark que aprende de un pequeño conjunto de etiquetas humanas (aprendizaje activo, *active learning*). El script describe las columnas de entrada y cómo se puede comparar cada una, apunta Zingg a `data/customers.csv` y ejecuta una fase de Zingg elegida en la línea de comandos: buscar pares dudosos, etiquetarlos, entrenar o emparejar.

**Ejecución.** En Docker, desde `er-demo/`:

```bash
docker run -it -v $PWD:/demo zingg/zingg:0.4.0 bash
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py findTrainingData
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py label
# repeat findTrainingData + label until about 30-40 positive pairs
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py train
./scripts/zingg.sh --run /demo/zingg/zingg_customers.py match
```

En local solo puedes comprobar que compila: `python -m py_compile zingg/zingg_customers.py`.

**Lee / Escribe.**
- Lee `/demo/data/customers.csv` (los registros en bruto; Zingg hace su propia normalización y no usa `common/standardise.py`).
- Escribe `/demo/zingg/models/customers_v1/` (pares etiquetados, *blocking* y clasificador aprendidos) y `/demo/results/zingg_output/` (la salida del emparejamiento con `z_cluster`, `z_minScore` y `z_maxScore` por registro).

**Diapositivas.** 8 (nota sobre la licencia: Zingg Community es AGPL-3.0), 12 (de dónde salen las etiquetas: la revisión humana).

**Guía.** Recorrido por el código: [Integraciones opcionales](DEMO_GUIDE.es.md#integraciones-opcionales-databrickssplink_on_databrickspy-y-zinggzingg_customerspy); [3.6 Matching supervisado](DEMO_GUIDE.es.md#36-matching-supervisado-paso-a-paso), en particular el [Paso 7. Dónde falla y de dónde salen las etiquetas](DEMO_GUIDE.es.md#paso-7-dónde-falla-y-de-dónde-salen-las-etiquetas).

### Recorrido

1. [zingg/zingg_customers.py#L1-L32](zingg/zingg_customers.py#L1-L32) **Docstring del módulo.** El flujo de Zingg en seis pasos (findTrainingData, label, repetir, train, match, link / runIncremental), las entradas, las salidas, los comandos de Docker y la nota sobre la licencia. Diapositivas 8 y 12.
2. [zingg/zingg_customers.py#L33-L39](zingg/zingg_customers.py#L33-L39) **Importaciones.** `Arguments` contiene la configuración del trabajo, `FieldDefinition` y `MatchType` describen las columnas, `Zingg` y `ClientOptions` ejecutan una fase y `CsvPipe` es un origen o destino CSV.
3. [zingg/zingg_customers.py#L42-L44](zingg/zingg_customers.py#L42-L44) **Fase y ruta base.** La fase sale del primer argumento de la línea de comandos (por defecto, `findTrainingData`); `/demo` es donde el comando de Docker monta `er-demo/`.
4. [zingg/zingg_customers.py#L50-L64](zingg/zingg_customers.py#L50-L64) **Definiciones de campos.** Una entrada por columna del CSV. Los nombres, la dirección y la ciudad son `FUZZY`; la DOB y el teléfono, `EXACT`; el email, `EMAIL` (compara la parte anterior a la @); el código postal, `PINCODE`. Los ids, el sistema de origen, las marcas de tiempo y el `true_entity_id` sintético son `DONT_USE`: se arrastran a la salida para evaluar, pero nunca se usan para emparejar. Es el equivalente en Zingg de las comparaciones de Splink. Diapositiva 8.
5. [zingg/zingg_customers.py#L67-L76](zingg/zingg_customers.py#L67-L76) **Argumentos del trabajo.** El id de modelo `customers_v1` vincula todas las fases a una misma carpeta de modelo; 4 particiones de Spark; `setLabelDataSampleSize(0.4)` toma una muestra del 40% de los datos al buscar pares dudosos que enseñar a quien etiqueta.
6. [zingg/zingg_customers.py#L79-L87](zingg/zingg_customers.py#L79-L87) **Canales de entrada y salida.** La cadena de esquema de Spark lista las columnas del CSV como texto; el canal de entrada lee `customers.csv` con cabecera; el canal de salida recibe los resultados del emparejamiento. Ten en cuenta que el esquema lista 12 columnas, mientras que el CSV tiene también una 13.ª, `true_household_id`; Spark ignora la columna final sobrante, pero añádela si la quieres en la salida.
7. [zingg/zingg_customers.py#L90](zingg/zingg_customers.py#L90) **Ejecutar la fase.** Construye el cliente de Zingg para la fase elegida y la ejecuta sobre Spark.
8. [zingg/zingg_customers.py#L92-L94](zingg/zingg_customers.py#L92-L94) **Pista para evaluar.** Después de `match`, carga la salida y puntúala con el `evaluate_clusters()` compartido para que Zingg pueda entrar en la tabla comparativa de `results/comparison.md`.

### Qué deberías ver

Nada en local: el script no se ejecuta en esta demo. En Docker, `findTrainingData` y `label` te muestran pares para marcar como coincidencia / no coincidencia / no seguro; después de `train` y `match`, `results/zingg_output/` contiene una fila por registro con `z_cluster` (el cliente resuelto) y `z_minScore` / `z_maxScore` (la puntuación de coincidencia más baja y más alta entre ese registro y los demás de su clúster). No hay cifras de referencia; evalúa con `evaluate_clusters(out.source_record_id, out.z_cluster, out.true_entity_id)` y compara con las filas de Splink y de ML (precisión por pares de 0.966 y 0.976).

### Prueba esto

1. Etiqueta más rondas antes de `train` (de 40 a 80 pares positivos en lugar de 30) y compara el F1 B-cubed: el aprendizaje activo suele mejorar rápido con las primeras etiquetas y después se estanca.
2. Cambia `dob` de `MatchType.EXACT` a `MatchType.FUZZY` (línea 55) para que los intercambios de día y mes y las erratas sigan contando como coincidencia parcial; espera más recall y alguna fusión errónea extra.
3. Pon `postcode` como `MatchType.DONT_USE` (línea 60) para ver cuánto depende el modelo de la evidencia de ubicación.

