# Resolución de identidad de clientes: la guía

English version: [DEMO_GUIDE.md](DEMO_GUIDE.md)

Esta es la guía que acompaña al vídeo de YouTube y a la presentación. Tiene tres objetivos:

1. **Ejecutarlo tú mismo** (secciones 1, 5 y 6): los comandos, qué abrir y un recorrido breve.
2. **Aprender las ideas** (secciones 2, 3, 7 y 8): qué es cada técnica, paso a paso y con los números de la propia demo, cómo escala y respuestas a las preguntas habituales.
3. **Seguir el vídeo.** El guion de grabación es [VIDEO_SCRIPT.es.md](VIDEO_SCRIPT.es.md): tiene los capítulos, los tiempos y la narración, y recorre la presentación en orden, de la diapositiva 1 a la 29. Usa esta guía como referencia detrás de cada capítulo, no como guion.

La demo usa datos sintéticos con identificadores de entidad y de hogar conocidos. Los resultados sirven para comparar enfoques, no como cifras de rendimiento en producción.

## Contenido

1. [Ejecutar la demo](#1-ejecutar-la-demo)
2. [Qué cubre la demo](#2-qué-cubre-la-demo)
3. [Conceptos básicos](#3-conceptos-básicos)
4. [Recorrido por el código](#4-recorrido-por-el-código)
5. [Recorrido de diez minutos](#5-recorrido-de-diez-minutos)
6. [Opcional: demostrar cómo deshacer una fusión](#6-opcional-demostrar-cómo-deshacer-una-fusión)
7. [Diseño del sistema: el framework a escala](#7-diseño-del-sistema-el-framework-a-escala)
8. [Preguntas frecuentes](#8-preguntas-frecuentes)
9. [Glosario](#9-glosario)
10. [Solución de problemas](#10-solución-de-problemas)

## 1. Ejecutar la demo

Ejecuta estos comandos desde PowerShell en el directorio `er-demo/` del repositorio. Llaman directamente al intérprete del entorno virtual, así que no hace falta activarlo.

```powershell
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

La secuencia es la misma que la de `run_all.sh`, escrita paso a paso para que funcione en PowerShell sin Bash. La ejecución completa tarda unos 45 segundos en un portátil, y más en una máquina en frío. `05_mdm.py` borra y vuelve a crear `results/mdm.duckdb`, y `08_mlops_feature_store.py` reinicia el *feature store* (almacén de características) y el *model registry* (registro de modelos). Por eso, si repites la secuencia, siempre partes del mismo estado.

Antes de explorar o grabar, comprueba que existen estos archivos:

- `results/comparison.md`: todas las tablas de métricas en un solo sitio. Tenlo abierto en una pestaña.
- `results/splink_match_weights.html` y `results/splink_waterfall_example.html`: abre los dos en un navegador.
- `results/mdm.duckdb` (*golden record*, *crosswalk*, historial, *spine* y jerarquía) y `results/feature_store.duckdb`.
- `results/shared_identifiers.csv`, `results/identity_drift.csv`, `results/monitoring_report.csv`, `results/model_registry/registry.json`.

Opcional: si ejecutas `pip install mlflow` antes de la ejecución, `08_mlops_feature_store.py` también registra las dos versiones del modelo en `results/mlruns`. Después, `mlflow ui --backend-store-uri results/mlruns` te las muestra. La demo funciona sin MLflow.

La demo es local. Zingg y el ejemplo de Databricks SparkAPI no forman parte de la ejecución en el portátil.

## 2. Qué cubre la demo

Cada capacidad que necesita una plataforma de resolución de identidad de clientes, el archivo que la muestra y la cifra principal.

| Capacidad | Dónde está en la demo | Cifra principal |
|---|---|---|
| Técnicas basadas en grafos y resolución de entidades | `04_graph_resolution.py`, hogares en `06_customer_spine.py` | Pares fusionados por error 198 → 12 tras la reparación por corte mínimo (*min-cut*) |
| Vinculación de registros y coincidencia difusa (*fuzzy matching*) | `01`, `02`, `common/standardise.py` | El *blocking* conserva el 96.5% de los pares verdaderos con el 0.02% de las comparaciones |
| ML donde las reglas deterministas no bastan | `02` (EM, sin etiquetas), `03` (supervisado), Zingg | F1 de las reglas 0.93 → F1 del ML 0.975 |
| Arquitectura de *customer spine* y jerarquía de identidad gobernada | `06_customer_spine.py` | 7 contratos de datos, hogar → cliente → origen |
| Framework reutilizable, menos duplicación, menos deriva de identidad | `common/`, modelo guardado reutilizado 3 veces, `07_identity_drift.py` | Deriva de identificadores 56% → 0.2% |
| Métricas de calidad del *matching*: precisión, confianza, rendimiento | `common/evaluate.py`, barrido de umbrales, calibración en `08` | F1 *B-cubed*, ECE 0.004 |
| Integración en plataformas de datos y en la Golden Layer | `05_mdm.py`, *spine* en `06`, `databricks/` | Tabla `customer_spine`, correspondencia Bronze/Silver/Gold |
| MLOps: despliegue, monitorización, ciclo de vida | `08_mlops_feature_store.py`, MLflow en `databricks/` | La puerta de calidad promociona la v2; un feed roto dispara 4 alertas PSI |
| *Feature stores* | `08_mlops_feature_store.py` | Características versionadas; el servicio rechaza una versión distinta |
| Datos maestros de clientes y *MDM* | `05_mdm.py` | 197/200 clientes recurrentes asociados correctamente |
| Trabajo con *data stewards* (responsables de datos) | Cola de revisión, gráfico de cascada (*waterfall chart*), auditoría de stewards, lista de identificadores compartidos | El gráfico de cascada explica una coincidencia barra a barra |

## 3. Conceptos básicos

Lee esta sección una vez de principio a fin. Cada apartado explica una idea con los números de la propia demo.

### 3.1 El problema

La **resolución de entidades (ER, *entity resolution*)** encuentra los registros que se refieren a la misma cosa del mundo real. Con clientes tiene tres variantes: **deduplicación** (una tabla), **vinculación de registros** (*record linkage*, entre tablas) y **canonicalización** (elegir los mejores valores). Los datos de clientes no tienen una clave compartida entre sistemas, así que deducimos la identidad a partir de atributos con ruido: nombres, fecha de nacimiento (DOB), email, teléfono y dirección.

El pipeline siempre tiene la misma forma:

```text
standardise -> block -> compare -> score -> classify (threshold) -> cluster -> master (golden record) -> publish (spine)
```

Casi toda la calidad sale del primer y del último paso, que es lo que la gente olvida: la estandarización y evaluar clústeres en lugar de pares.

### 3.2 Estandarización

Haz desaparecer las diferencias de formato antes de comparar: mayúsculas, acentos, tratamientos (`Mr`), apodos (`Bob` → `robert`), formatos de teléfono (`+44 7…` → `07…`), espacios en el código postal, puntos y etiquetas con `+` de Gmail. Los códigos fonéticos (Soundex, Metaphone) permiten que `Smith` y `Smyth` compartan bloque. Regla práctica: normaliza lo que es formato y compara de forma difusa lo que es una diferencia real.

### 3.3 Agrupación por claves (*blocking*, indexación)

Comparar todos los pares cuesta `n(n-1)/2`: 33.5 millones de pares para 8,192 registros, y 5 × 10¹⁴ para 30 millones. El *blocking* solo compara registros que comparten una clave barata (mismo email, misma DOB + mismo sonido del apellido, mismo código postal + mismo sonido del nombre). Se unen varias reglas de *blocking*, de modo que un registro que se escapa de una regla lo recoge otra.

- **Completitud de pares (*pair completeness*, recall del *blocking*)** = pares verdaderos que sobreviven al *blocking* / todos los pares verdaderos. Es un techo para el recall: ningún modelo puede emparejar un par que nunca ve. Aquí, 96.5%.
- **Ratio de reducción** = 1 − candidatos / todos los pares. Aquí, 99.98%.
- Los bloques muy grandes (un email genérico compartido) se saltan o se limitan. Si no, un solo valor genera millones de comparaciones.
- Otros métodos: vecindario ordenado (*sorted neighbourhood*), *canopy clustering*, LSH / MinHash y búsqueda de vecinos más cercanos con embeddings para texto desordenado.

### 3.4 Comparar y puntuar

Cada campo recibe una similitud: exacta, Levenshtein (distancia de edición), Jaro-Winkler (buena para nombres cortos, premia un prefijo común), *token-set ratio* (orden de las palabras), coseno sobre q-gramas / TF-IDF (texto largo) y tolerancia en fechas. Después hay tres familias de puntuación:

| Familia | Cómo se construye la puntuación | Etiquetas necesarias | Punto fuerte | Punto débil |
|---|---|---|---|---|
| Reglas deterministas | `same email AND same DOB` | No | Exactas, auditables | Fallan con todo lo que tiene ruido |
| Puntuación difusa ponderada | Pesos elegidos a mano × similitudes | No | Explicable, rápida | Los pesos son conjeturas; hay que reajustarlos para cada origen |
| Probabilística (*Fellegi-Sunter*) | `m` y `u` aprendidos por nivel de cada campo | No (EM) | Pesos con fundamento, explicable | Supone independencia entre campos |
| Clasificador supervisado | Modelo sobre características del par | Sí | El más flexible, aprende interacciones | Necesita etiquetas y MLOps |
| Aprendizaje activo (*active learning*: Zingg, dedupe) | Clasificador entrenado con los pares de los que está menos seguro | Unas pocas docenas | Pocas etiquetas | Sesión de etiquetado, licencias |

### 3.5 Fellegi-Sunter, paso a paso

Fellegi-Sunter es el modelo que hay dentro de Splink. Responde a una pregunta sobre un par de registros: *¿cuánto más probable es lo que veo si los dos registros son la misma persona que si son dos personas distintas?* Construye la respuesta a partir de cuatro ideas: campos, niveles de comparación, `m` y `u`.

#### Paso 1. Campos

Un **campo** es una columna que comparas entre los dos registros. La demo compara siete: nombre canónico, apellido, fecha de nacimiento, email, teléfono, código postal y dirección (la lista `comparisons` de `02_splink.py`). Cada campo se compara por separado y los resultados se suman al final.

#### Paso 2. Niveles de comparación (cuánto coincide el campo)

Para cada campo no te limitas a preguntar "¿igual o distinto?". Defines una escalera corta de **niveles de comparación**, también llamados **niveles de acuerdo**, desde el acuerdo más fuerte hasta el desacuerdo. Para el apellido en esta demo:

| Nivel | Qué significa | Par de ejemplo |
|---|---|---|
| Missing | uno de los dos valores está vacío | `smith` vs (vacío) |
| Exact match | idénticos tras la estandarización | `smith` vs `smith` |
| Jaro-Winkler ≥ 0.92 | una pequeña errata | `griffiths` vs `griffihs` (0.98) |
| Jaro-Winkler ≥ 0.88 | algo más alejados | `smith` vs `smyth` (0.89) |
| Jaro-Winkler ≥ 0.70 | vagamente parecidos | `walker` vs `walsh` (0.79) |
| All other comparisons | claramente distintos | `smith` vs `jones` |

Cada par cae exactamente en un nivel por campo: Splink revisa los niveles de arriba abajo y se queda con el primero que se cumple. Así, un par de registros se convierte en un patrón corto como *nombre exacto, apellido JW ≥ 0.88, DOB vacía, email exacto, teléfono vacío, código postal distinto, dirección vacía*.

#### Paso 3. `m`: con qué frecuencia caen en este nivel las coincidencias verdaderas

`m` se mide **solo entre pares que de verdad son la misma persona**. Para cada nivel, es la proporción de esos pares que cae en él.

Según el modelo entrenado en esta demo (`results/splink_model.json`, semilla 42; `u` se estima con una muestra aleatoria, así que tu ejecución puede variar un poco), para el nombre canónico:

| Nivel | m | Cómo leerlo |
|---|---|---|
| Exact match | 0.676 | El 67.6% de las coincidencias verdaderas tiene exactamente el mismo nombre |
| JW ≥ 0.92 | 0.176 | El 17.6% se diferencia por una pequeña errata |
| JW ≥ 0.88 | 0.025 | El 2.5% se diferencia algo más |
| JW ≥ 0.70 | 0.015 | El 1.5% solo se parece vagamente |
| All other | 0.108 | El 10.8% parece completamente distinto (nombre y apellido intercambiados, un apodo que no está en el diccionario) |

Los valores de `m` de un campo suman 1, porque toda coincidencia verdadera cae en algún nivel. `m` describe la **calidad de los datos**: si tus orígenes fueran perfectos, `m` para "exact match" sería 1.0.

#### Paso 4. `u`: con qué frecuencia caen en este nivel personas distintas por casualidad

`u` es la misma medida **entre pares de personas distintas**. Para el nombre, el nivel exacto tiene `u = 0.0047`: dos clientes aleatorios y sin relación comparten nombre el 0.47% de las veces, porque nombres como *James* y *Sarah* son habituales. "All other" tiene `u = 0.967`: casi todos los pares aleatorios tienen nombres claramente distintos.

`u` describe **lo comunes que son los valores**. Un campo donde cada persona tiene un valor distinto (el teléfono) tiene un `u` diminuto para la coincidencia exacta. Un campo con pocos valores (sexo, ciudad) lo tiene grande.

Una analogía útil es una prueba médica: `m` es la sensibilidad (con qué frecuencia la prueba da positivo cuando hay enfermedad) y `u` es la tasa de falsos positivos (con qué frecuencia da positivo cuando no la hay).

#### Paso 5. El peso de coincidencia (*match weight*) de un campo: log2(m / u)

El cociente `m / u` dice cuántas veces es más probable el nivel observado en una coincidencia que en una no coincidencia. Al aplicar `log2` se convierte en **bits de evidencia**, que se pueden sumar sin más:

| Nivel del nombre | m | u | m / u | Peso log2(m/u) |
|---|---|---|---|---|
| Exact match | 0.676 | 0.0047 | 144 | **+7.2** (evidencia fuerte a favor de coincidencia) |
| JW ≥ 0.70 | 0.015 | 0.025 | 0.6 | **−0.7** (ligera evidencia en contra) |
| All other | 0.108 | 0.967 | 0.11 | **−3.2** (evidencia en contra) |
| Missing | | | | **0** (ninguna evidencia en ningún sentido) |

Un peso positivo significa que la observación es más típica de coincidencias. Uno negativo, que es más típica de no coincidencias. Un valor vacío no suma nada.

#### Paso 6. El *prior*: parte de lo raras que son las coincidencias

Antes de mirar ningún campo, es muy improbable que dos registros aleatorios sean la misma persona. El *prior* del modelo es `λ = 0.00022` (aproximadamente 1 de cada 4,550 pares aleatorios es una coincidencia). En bits: `log2(λ / (1 − λ)) = −12.1`. Cada par empieza en −12.1 y los campos tienen que ganarse la subida.

#### Paso 7. Súmalo todo y conviértelo en probabilidad

Peso de coincidencia total = *prior* + el peso del nivel de cada campo. Para volver a probabilidad: `probability = 2^w / (1 + 2^w)`.

**Ejemplo A: la misma persona en dos sistemas.** El CRM tiene *Robert Smith, 1981-03-14, robert.smith@gmail.com, 07700 900123, SW1A 1AA*. La WEB tiene *Bob Smyth, robert.smith+shop@gmail.com, NW3 2QG* (sin DOB, sin teléfono, sin dirección, y se ha mudado).

| Campo | Valores tras la estandarización | Nivel | m | u | Peso |
|---|---|---|---|---|---|
| Prior | | | | | −12.1 |
| Nombre | robert / robert (Bob → robert) | Exact | 0.676 | 0.0047 | +7.2 |
| Apellido | smith / smyth | JW ≥ 0.88 | 0.036 | 0.00088 | +5.3 |
| DOB | 1981-03-14 / vacía | Missing | | | 0 |
| Email | robert.smith@gmail.com en ambos (sin la etiqueta `+`) | Exact | 0.785 | 0.00016 | +12.3 |
| Teléfono | 07700900123 / vacío | Missing | | | 0 |
| Código postal | SW1A 1AA / NW3 2QG | All other | 0.278 | 0.965 | −1.8 |
| Dirección | / vacía | Missing | | | 0 |
| **Total** | | | | | **+10.9** |

Probabilidad = 2^10.9 / (1 + 2^10.9) ≈ **0.9995**. El modelo los vincula, aun con una errata en el apellido y un código postal distinto, porque el email es casi exclusivo de una persona.

**Ejemplo B: dos personas del mismo hogar.** *Thomas Jones, 2008-07-14* y *Stanley Jones, 2002-07-12*, los dos con el email familiar `thejoness@yahoo.co.uk`, la misma dirección y código postal, y teléfonos distintos.

| Campo | Nivel | Peso |
|---|---|---|
| Prior | | −12.1 |
| Nombre: thomas / stanley | All other | −3.2 |
| Apellido: jones / jones | Exact | +7.4 |
| DOB: 6 años de diferencia | ≤ 10 years | −3.7 |
| Email: el mismo buzón familiar | Exact | +12.3 |
| Teléfono: distinto | All other | −4.3 |
| Código postal: el mismo | Exact | +12.3 |
| Dirección: la misma | Exact | +12.3 |
| **Total** | | **+21.0**, probabilidad ≈ 1.0 |

El modelo no se equivoca con la evidencia: compartir email, dirección y apellido es típico de una sola persona. Lo que no puede saber es que un hogar también los comparte. Esa es justo la fusión errónea que detecta el paso de grafos (sección 3.7, `04_graph_resolution.py`) con una regla *cannot-link* sobre la DOB.

(Los pesos anteriores usan los `m` y `u` entrenados antes del ajuste por frecuencia de términos, así que el gráfico de cascada de un par real puede variar un poco).

#### Paso 8. Cómo aprende el modelo `m` y `u` sin etiquetas

- **`u` a partir de pares aleatorios.** Si eliges dos registros al azar, casi nunca son la misma persona (1 de cada 4,550). Así que si muestreas unos millones de pares aleatorios y cuentas cuántas veces aparece cada nivel, esas proporciones *son* `u`. Es lo que hace `estimate_u_using_random_sampling()`.
- **`m` con maximización de la esperanza (EM, *expectation-maximisation*).** No sabemos qué pares son coincidencias, así que EM adivina y va afinando: (1) empieza con valores de `m` aproximados, (2) puntúa cada par candidato con los `m` y `u` actuales, lo que da a cada uno una probabilidad de coincidencia, (3) recalcula `m` como la proporción de cada nivel entre los pares, ponderando cada par por su probabilidad de coincidencia, y (4) repite hasta que los valores dejan de cambiar.
- **Por qué EM se ejecuta tres veces.** Cada ejecución de EM solo mira pares de una regla de *blocking*, por ejemplo "misma DOB". Dentro de ese bloque todos los pares coinciden en la DOB, así que la ejecución no puede aprender el `m` de la DOB. `02_splink.py` ejecuta EM sobre bloques de DOB, de código postal y de nombre, para que cada campo se aprenda al menos en una ejecución.
- **Ajuste por frecuencia de términos.** Para nombres y email, Splink sustituye el `u` medio del campo por la frecuencia del valor concreto. Coincidir en `smith` (común, `u` alto) da menos bits que coincidir en `featherstonehaugh` (raro, `u` diminuto).

#### Dónde verlo en la demo

- `results/splink_m_u_parameters.html`: los `m` y `u` de cada nivel, uno al lado del otro.
- `results/splink_match_weights.html`: el peso `log2(m/u)` de cada nivel, los mismos números que las tablas anteriores.
- `results/splink_waterfall_example.html`: el Paso 7 para un par real, barra a barra.
- Para imprimir la tabla tú mismo:

```powershell
.\.venv\Scripts\python.exe -c "import json, math; m = json.load(open('results/splink_model.json')); [print(c['output_column_name'], l['label_for_charts'], round(l['m_probability'], 4), round(l['u_probability'], 6), round(math.log2(l['m_probability'] / l['u_probability']), 1)) for c in m['comparisons'] for l in c['comparison_levels'] if l.get('m_probability') and l.get('u_probability')]"
```

El supuesto que debes tener presente: los pesos solo se pueden sumar porque el modelo trata los campos como **independientes** dado el estado de coincidencia. Por eso los campos correlacionados (código postal y dirección, email y nombre) se cuentan dos veces. Es una de las razones por las que los modelos supervisados, o un diseño cuidadoso de las comparaciones, pueden hacerlo mejor.

### 3.6 Matching supervisado, paso a paso

Fellegi-Sunter aprende de los datos sin etiquetas. El *matching* supervisado hace lo contrario: le enseñas a un modelo pares cuya respuesta ya conoces y él aprende la regla por su cuenta. `03_ml_recordlinkage.py` lo construye en siete pasos.

#### Paso 1. La unidad de aprendizaje es un par, no un registro

Un modelo no puede mirar un registro de cliente y decir quién es. Mira **dos registros** y responde a una pregunta: *¿la misma persona o no?* Por eso cada ejemplo de entrenamiento es un par, y su **etiqueta** es 1 (coincidencia) o 0 (no coincidencia).

Los pares salen del mismo *blocking* que usa el *matcher* de reglas (`rules.candidate_pairs`), porque puntuar los 33.5 millones de pares es imposible. Eso da 6,405 pares candidatos. La etiqueta sale de `true_entity_id`: 1 si los dos registros tienen el mismo id. En producción esa columna no existe; las etiquetas vienen de los stewards (Paso 7).

Hay una sorpresa que conviene entender: **el 88% de los pares candidatos son coincidencias** (5,639 de 6,405), mientras que entre todos los pares posibles solo lo es el 0.017%. El *blocking* ya ha descartado casi todas las no coincidencias fáciles. El modelo solo tiene que separar los casos difíciles que sobreviven al *blocking*.

#### Paso 2. Características: convertir un par en una fila de números

Una **característica** (*feature*) es un número que describe cómo se comparan los dos registros en un aspecto. `features()` construye 14. El mismo par, tal como lo ve el modelo:

| Registro | Nombre | Apellido | DOB | Email | Teléfono | Dirección | Código postal |
|---|---|---|---|---|---|---|---|
| BILLING-000003 | Thomsa | Datson | 1984-12-28 | (vacío) | +44 7890838637 | Sudio 89, Kirsty Oval | SE98 3WD |
| CRM-000004 | Thomas | Dawson | 1984-12-28 | thomas.dawson@btinternet.com | +44 7890838637 | Studio 89, Kirsty Oval | SE98 3WD |

| Característica | Qué mide | Valor para este par |
|---|---|---|
| `first_jw` | Similitud Jaro-Winkler de los nombres canónicos (de 0 a 1) | 0.97 (una letra intercambiada) |
| `last_jw` | Jaro-Winkler de los apellidos | 0.91 |
| `last_lev` | Similitud Levenshtein de los apellidos | 0.83 |
| `first_phonetic`, `last_phonetic` | ¿Coinciden los códigos Metaphone? (1/0) | 1 y 0 |
| `dob_exact` | ¿Misma DOB? (1/0, vacío si falta alguna) | 1 |
| `dob_lev` | Similitud de caracteres de las DOB como texto (detecta día y mes intercambiados) | 1.0 |
| `email_qgram`, `email_user_jw` | Similitud del email y de la parte anterior a `@` | 0 (falta un email) |
| `phone_exact` | ¿Mismo teléfono? | 1 |
| `postcode_exact`, `postcode_area_exact` | Mismo código postal completo, misma zona | 1 y 1 |
| `address_qgram` | Similitud por q-gramas de la línea de calle | 0.91 |
| `record_tfidf_cos` | Similitud coseno del registro entero como n-gramas de caracteres | 0.59 |
| **Etiqueta** | ¿Mismo `true_entity_id`? | **1** |

La última característica es un "embedding" barato: el nombre, el usuario del email, el código postal y la dirección de cada registro se unen en una sola cadena, se cortan en n-gramas de 2 a 4 caracteres y se ponderan con TF-IDF (los n-gramas raros cuentan más). Dos registros con las mismas letras en sitios distintos, como un nombre y un apellido intercambiados, siguen puntuando alto.

Fíjate en la decisión de diseño de la fila del email: un email vacío puntúa 0, igual que dos emails completamente distintos. Otras características (DOB, teléfono, código postal) dejan el valor vacío, y el *gradient boosting* puede aprender que vacío no es lo mismo que desacuerdo. Esa diferencia importa con datos reales, donde la ausencia de un valor aporta información.

#### Paso 3. El modelo: *gradient boosting*

`HistGradientBoostingClassifier` es una secuencia de árboles de decisión pequeños. El primer árbol hace una estimación aproximada ("misma DOB y mismo teléfono → probable coincidencia"). Cada árbol siguiente se centra en los pares que fallaron los anteriores ("…salvo que los nombres sean completamente distintos"). Trescientos árboles después, la suma de sus votos se convierte en una probabilidad entre 0 y 1.

Comparado con Fellegi-Sunter:

| | Fellegi-Sunter (Splink) | Gradient boosting |
|---|---|---|
| Necesita etiquetas | No | Sí |
| Cómo se combinan los campos | Suma bits independientes por campo | Aprende interacciones ("coincidir en el apellido importa menos cuando la dirección también coincide") |
| Campos correlacionados | Se cuentan dos veces | Se gestionan bien |
| Entradas | Niveles de acuerdo discretos | Cualquier número: similitudes, embeddings, señales de negocio |
| Explicación | Cascada de bits | Importancia de características, valores SHAP |

#### Paso 4. De la probabilidad a la decisión: el umbral

El modelo devuelve una probabilidad para cada par. Un **umbral** la convierte en una decisión: si es igual o superior, el par se convierte en una arista (una coincidencia); si es inferior, no. Después las aristas se agrupan en clientes mediante componentes conexas (sección 3.7). El umbral es una decisión de negocio, y las métricas de clúster muestran su efecto:

| Umbral | Precisión por pares | Recall por pares | Clúster más grande |
|---|---|---|---|
| 0.5 | 0.968 | 0.976 | 9 |
| 0.9 (el usado) | 0.976 | 0.975 | 7 |
| 0.99 | 0.981 | 0.974 | 7 |

Subir el umbral elimina aristas falsas, pero incluso con 0.99 sigue habiendo fusiones erróneas. Son pares de los que el modelo está *seguro* y en los que se equivoca (Paso 6), y ningún umbral lo arregla.

#### Paso 5. Evalúa sin engañarte

Tres trampas, y lo que hace la demo con cada una:

- **La exactitud (*accuracy*) no significa nada aquí.** Con un 88% de coincidencias, un modelo que siempre dice "coincidencia" acierta el 88%. Informa de la **precisión media** (*average precision*: lo bien que el modelo ordena las coincidencias por encima de las no coincidencias) y, sobre todo, de las métricas de clúster.
- **Fugas entre entrenamiento y test.** Una persona aparece en muchos pares. Si divides los pares al azar, el 74% de los pares de test comparte un registro con un par de entrenamiento, así que el modelo se evalúa en parte con personas que ya ha visto. La solución es dividir **por persona**: `03` puntúa cada par con un modelo entrenado con la otra mitad de las personas (según el registro de la izquierda), y `08` usa una división estricta en la que cada persona está entera en entrenamiento o entera en test. Con estos datos sintéticos las dos divisiones dan una precisión media de aproximadamente 0.9999, porque la tarea es fácil. Con datos reales, la división aleatoria es la que te halaga.
- **Las métricas por pares esconden errores de clúster.** La precisión media fuera de pliegue (*out-of-fold*) es 0.9998, casi perfecta. Sin embargo, tras agrupar, hay 142 pares de registros que acaban por error en el mismo cliente. Por eso cada método de esta demo se compara con *B-cubed* y con pares fusionados por error, no con puntuaciones por pares.

#### Paso 6. Confianza: ¿p = 0.9 es de verdad un 90%?

Una probabilidad solo sirve para umbrales y colas de revisión si está **calibrada**: entre todos los pares puntuados alrededor de 0.9, cerca del 90% deberían ser coincidencias. `08_mlops_feature_store.py` lo comprueba con las personas reservadas: agrupa los pares en diez intervalos de probabilidad y compara la predicción media con la proporción que de verdad coincidía:

| Intervalo de probabilidad predicha | Pares | Predicción media | Proporción que de verdad coincidía |
|---|---|---|---|
| 0.0 a 0.1 | 94 | 0.002 | 0.085 |
| 0.1 a 0.9 | 7 | (mixta) | (demasiado pocos para juzgar) |
| 0.9 a 1.0 | 1,948 | 1.000 | 0.997 |

- El **ECE (error de calibración esperado, *expected calibration error*)** es la diferencia media ponderada entre esas dos columnas: 0.004 para *gradient boosting* y 0.012 para regresión logística. Por debajo de 0.05, más o menos, es bueno.
- El **Brier score** es la media de (predicción − etiqueta)²: 0.003.
- El modelo es extremadamente seguro: casi todos los pares están por debajo de 0.1 o por encima de 0.9. Las 8 coincidencias verdaderas escondidas en el intervalo inferior son coincidencias perdidas, y las 6 no coincidencias del superior son los errores con seguridad del Paso 4.

#### Paso 7. Dónde falla y de dónde salen las etiquetas

Merece la pena enseñar los errores con seguridad, porque son los casos que ningún modelo entrenado con estos campos puede resolver:

| Par | Por qué el modelo dice coincidencia (p = 1.0) | Realidad |
|---|---|---|
| Robert Williams, 1996-12-13 / Ronald Williams, 1996-12-13 | Mismo apellido y DOB, nombre parecido | Dos personas |
| Craig Jones, craig.jones@gmail.com / Craig Jones, craig.jones@gmail.com | Mismo nombre y email | Dos personas (una colisión de emails generados) |

Estos casos necesitan más señales (un email verificado, un id de fidelización) o una persona: su sitio es la cola de revisión.

**De dónde salen las etiquetas en producción.** Lo que etiquetas es un *par*, no un registro ni una característica: las características se calculan automáticamente a partir de los dos registros, y la etiqueta es una persona o una fuente de confianza que dice "la misma persona" (1) o "no es la misma persona" (0). Los proyectos reales combinan tres fuentes:

| Fuente | Qué es | Punto fuerte | Punto débil |
|---|---|---|---|
| **Revisión humana** | Los stewards deciden pares de la cola de revisión; cada decisión se guarda como un par etiquetado. Un **conjunto de referencia** (*golden set*) de unos miles de pares, muestreados en todas las franjas de puntuación, se etiqueta una vez y se conserva para evaluar. | La más fiable; cubre los casos difíciles | Cara: cientos o unos pocos miles de pares, no millones |
| **Etiquetas silver** (*silver labels*) | Vínculos en los que el negocio ya confía: mismo documento nacional de identidad, número fiscal o pasaporte, misma tarjeta de fidelización, un mismo inicio de sesión usado en los dos sistemas, fusiones que los stewards ya aprobaron en el MDM | Gratis y abundantes | Sesgadas hacia los pares fáciles, así que añade encima pares difíciles revisados por personas |
| **Modelo no supervisado como profesor** | Los pares a los que Splink da una puntuación muy alta o muy baja se convierten en etiquetas provisionales; las personas revisan la zona gris | Pone en marcha un clasificador desde el primer día | Hereda los errores del profesor (¡los hogares!) |

El **aprendizaje activo** (*active learning*: Zingg, dedupe) mantiene pequeña la parte humana: el modelo solo envía a las personas los pares de los que está menos seguro (puntuaciones cercanas a 0.5), porque un par que ya acierta no le enseña nada. 50 etiquetas bien elegidas pueden hacer el trabajo de 5,000 aleatorias.

**¿Y los datos sintéticos?** El `true_entity_id` de esta demo es sintético, y eso está bien para construir y probar el pipeline y para mostrar el método. No sustituye a las etiquetas reales: los errores de los datos reales (cómo se equivoca la gente al teclear, cómo truncan los nombres los sistemas, qué campos faltan a la vez) son distintos de los errores que te inventas. Un modelo entrenado solo con pares sintéticos puede puntuar bien aquí y aun así fallar con datos de producción.

**Un camino sensato:** empieza con Splink, que no necesita etiquetas; guarda cada decisión de los stewards como etiqueta desde el primer día; usa aprendizaje activo para dedicar el tiempo de los revisores a los pares difíciles; e incorpora el modelo supervisado cuando un *golden set* de unos miles de pares reales demuestre que supera a Splink en métricas de *clúster*.

### 3.7 Agrupación (*clustering*) y la vista de grafo, paso a paso

Todos los comparadores de las secciones 3.4 a 3.6 responden a una pregunta sobre **dos** registros. Pero un cliente puede tener cinco registros repartidos en tres sistemas. Convertir decisiones sobre pares en clientes es un problema de grafos. Y es ahí donde nacen la mayoría de las fusiones erróneas reales. `04_graph_resolution.py` implementa esta sección.

#### Paso 1. Los registros son nodos; las coincidencias, aristas

Dibuja cada registro como un punto (un **nodo**). Por cada par que el modelo acepta, traza una línea entre los dos puntos (una **arista**). Asigna a cada arista un **peso**: la fuerza de la evidencia. En esta demo, el peso es el *match weight* de Splink en bits de la sección 3.5 (para el modelo de ML, el logaritmo de las probabilidades a favor, los *log-odds*, de su probabilidad en bits).

¿Por qué bits y no la probabilidad? Porque las probabilidades se saturan. Una arista con 15 bits de evidencia tiene p = 0.99997 y una con 60 bits tiene p = 0.999…9. Las dos se muestran como 1.0, pero la segunda es muchísimo más fuerte. Los bits mantienen visible esa diferencia.

#### Paso 2. Un cliente es una componente conexa

Una **componente conexa** es un grupo de nodos que pueden alcanzarse entre sí siguiendo aristas. Si A coincide con B y B coincide con C, entonces A, B y C forman una componente y, por tanto, un solo cliente, aunque A y C nunca se hayan comparado. Este paso se llama **cierre transitivo** (*transitive closure*). Lo hacen tanto `union_find_clusters()` como el *clustering* de Splink.

Con estos datos, las aristas de Splink con p ≥ 0.95 forman componentes de estos tamaños:

| Registros en la componente | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| Número de componentes | 1,452 | 1,463 | 971 | 193 | 12 | 8 | 3 |

En el generador nadie tiene más de 6 registros, así que una componente de 7 es, con toda seguridad, errónea.

#### Paso 3. Encadenamiento (*chaining*): por qué basta una arista mala

En la realidad, el emparejamiento **no es transitivo**: que A se parezca a B y B se parezca a C no demuestra que A sea C. El cierre transitivo da por hecho que sí. Por eso, una sola arista falsa entre dos clientes reales fusiona *todos* sus registros. Esto es el **encadenamiento** (*chaining*). Y explica por qué las métricas por pares pueden parecer perfectas mientras los clientes están mal.

Una componente real de la demo, con todas las aristas aceptadas por Splink:

```text
  Thomas Jones  CRM-000035   2008-07-14  FY15 6JF  thejoness@yahoo.co.uk
  Thomas Jons   BILLING-000036  (sin DOB) FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones WEB-005154   2002-07-12  FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones WEB-005155   2002-07-12  FY15 6JF  thejoness@yahoo.co.uk
  Stanley Jones BILLING-005156 (sin DOB)  WD2P 8EJ  thejoness@yahoo.co.uk

  aristas (bits):  WEB-005154 -- WEB-005155      59.5   (registros idénticos)
                   CRM-000035 -- BILLING-000036  34.1
                   BILLING-000036 -- WEB-005154/5 25.3 cada una
                   CRM-000035 -- WEB-005154/5    15.3 cada una
                   BILLING-005156 -- WEB-005154/5 6.6 cada una
```

Thomas y Stanley son dos personas de un mismo hogar que comparten un buzón familiar. Cada arista, por separado, es plausible. Juntas forman un único "cliente" de 5 registros.

#### Paso 4. Restricciones cannot-link: conocimiento de negocio que el modelo no tiene

Una **restricción *cannot-link*** es una regla que dice que dos registros son, sin duda, personas *distintas*, sea cual sea la puntuación. `cannot_link()` usa dos:

| Regla | Se activa cuando | No se activa cuando |
|---|---|---|
| `dob_conflict()` | se conocen las dos fechas de nacimiento (DOB) y son distintas | falta una de las DOB, o son un intercambio de día y mes (03/04 frente a 04/03) |
| `name_conflict()` | los nombres de pila canónicos difieren claramente (Jaro-Winkler < 0.75 y Metaphone distinto) | la DOB coincide (un apodo con una errata), o los nombres parecen intercambiados entre nombre y apellido |

En la componente anterior, Thomas (2008-07-14) y Stanley (2002-07-12) incumplen la regla de la DOB, y *thomas* frente a *stanley* incumple la regla del nombre. La componente contiene seis pares en conflicto, así que hay que dividirla. De las 2,712 componentes de Splink con varios registros, 42 contienen un conflicto.

#### Paso 5. Corte mínimo (*min cut*): quitar las aristas más débiles que los separan

Si dos registros tienen que acabar separados, ¿qué aristas borras? El **corte mínimo** (*min cut*) da la respuesta: el conjunto de aristas cuya eliminación desconecta los dos registros con el menor peso total. Imagina las aristas como tuberías y el peso como su grosor. El corte mínimo es el conjunto de tuberías más barato de bloquear para que nada fluya de un registro al otro. `nx.minimum_cut` lo calcula usando los pesos de las aristas como **capacidades**.

`repair()` lo ejecuta sobre un par en conflicto, elimina las aristas del corte y vuelve a revisar cada trozo hasta que ninguno contiene un conflicto. Para la componente de los Jones:

1. El corte 1 separa BILLING-005156 del resto eliminando sus dos aristas de 6.6 bits (13.2 bits en total, la salida más barata).
2. El corte 2 separa los dos registros web de Stanley de los dos registros de Thomas eliminando las cuatro aristas de 15.3 y 25.3 bits que los unen.
3. Los registros idénticos de Stanley (59.5 bits) nunca se cortan.

Resultado: {Thomas CRM, Thomas BILLING}, {Stanley WEB, Stanley WEB} y {Stanley BILLING} por separado. El hogar ya no es un solo cliente. El último registro es una sobredivisión: en realidad es Stanley, pero su única evidencia era el email familiar y el apellido. Lo prudente es dejarlo como cliente propio para la cola de revisión. Dividir de más tiene arreglo; fusionar a dos personas, no.

En todo el conjunto de datos se cortan 80 aristas en 42 componentes:

| Clústeres de Splink | Precisión por pares | Recall por pares | F1 B-cubed | Pares de fusión errónea |
|---|---|---|---|---|
| Componentes conexas | 0.966 | 0.965 | 0.985 | 198 |
| + cannot-link y corte mínimo | 0.998 | 0.962 | 0.989 | 12 |

#### Paso 6. El grafo de identificadores: ¿quién comparte un email?

Un segundo grafo usa también los **identificadores** como nodos: cada email y cada teléfono pasa a ser un nodo conectado a los registros que lo contienen. Tras la resolución, un identificador conectado a registros de **más de un cliente** es sospechoso. `shared_identifiers()` los lista: 48 emails y 25 teléfonos.

- 31 de los 48 emails los comparten de verdad personas distintas: buzones familiares como `thejoness@yahoo.co.uk`. Hay que excluirlos del *blocking* y darles menos peso en el emparejamiento (la lista de "identificadores genéricos").
- El resto de emails y los 25 teléfonos pertenecen a una sola persona cuyos registros acabaron como dos clientes: son **coincidencias perdidas**. La lista es una cola de trabajo lista para los *data stewards*.

#### Paso 7. Las jerarquías también son grafos

La misma idea construye los hogares en `06_customer_spine.py`. Los clientes y las direcciones son nodos, "este cliente ha vivido en esta dirección" es una arista, y cada componente conexa es un hogar. Un grafo es el modelo natural para cualquier estructura de pertenencia: persona → hogar, persona → empresa, empresa → grupo.

#### Paso 8. Otras técnicas de grafos que conviene conocer

| Técnica | Qué hace | Cuándo usarla |
|---|---|---|
| Intermediación de aristas (*edge betweenness*), puentes | Encuentra aristas por las que pasan muchos caminos mínimos: probables puentes entre dos clústeres reales | Detectar encadenamiento sin restricciones |
| Detección de comunidades (Louvain, Leiden) | Divide un grafo en grupos densamente conectados | Componentes muy grandes, sin restricciones claras |
| *Correlation clustering* | Elige los clústeres que menos contradicen todas las puntuaciones de pares, positivas y negativas | Cuando también te fías de las puntuaciones negativas |
| Densidad del clúster | Proporción de las aristas posibles dentro de un clúster que existen | Una alarma barata: un clúster de 6 registros con 5 aristas es una cadena, no una clique |
| GraphFrames / Spark | Componentes conexas sobre cientos de millones de aristas | Escala de producción; repara solo las pocas componentes que contienen un conflicto |
| Neo4j, TigerGraph | Base de datos de grafos con recorrido en línea | Cuando las aplicaciones consultan la jerarquía en directo |

### 3.8 MDM, golden record y customer spine

- **Registro maestro (*golden record*):** una única mejor versión de cada cliente, construida con reglas de **supervivencia** (*survivorship*) por campo: el valor más frecuente, el más reciente, el de la fuente más fiable, el más completo. Guarda la **procedencia** (*provenance*): qué registro y qué regla ganaron. Así cada valor se puede explicar.
- **Tabla de correspondencias (*crosswalk*, xref):** sistema de origen + id de origen → id maestro. Los sistemas posteriores la usan para traducir sus propios ids.
- **Estilos de MDM:** registro (*registry*, solo el *crosswalk* es central), consolidación (el *golden record* se construye de forma central para analítica), coexistencia (el *golden record* se sincroniza de vuelta con las fuentes) y centralizado (el hub es el sistema de entrada). Esta demo sigue el estilo de consolidación.
- **Gestión de datos (*data stewardship*):** revisión de la zona gris; aprobar, rechazar o deshacer una fusión con un motivo y un registro de auditoría. Las decisiones de los *data stewards* se convierten en etiquetas.
- **Columna vertebral de clientes (*customer spine*):** la tabla fina y gobernada con la que se cruza cada dominio. Una fila por cliente con la clave estable, su lugar en la jerarquía, las claves de origen y metadatos de calidad (versión del modelo, eslabón más débil). En un *lakehouse* con arquitectura medallón vive en Gold, la "Golden Layer".
- **Jerarquía de identidad:** niveles como registro de origen → cliente → hogar (→ empresa / grupo en B2B). Cada arista guarda la regla y la confianza que la crearon.
- **Gobierno:** clasificación de datos personales (PII), contratos de datos (aserciones que deben cumplirse antes de publicar), linaje, control de acceso y borrado RGPD en todas las tablas.

### 3.9 Métricas de calidad del emparejamiento

Verdad: `T(r)` es el clúster real del registro `r` y `C(r)`, el predicho.

- **Precisión por pares** = pares correctamente agrupados juntos / pares agrupados juntos en la predicción. **Recall** (exhaustividad) = pares correctamente agrupados juntos / pares que de verdad van juntos. Los clústeres grandes dominan, porque los pares crecen de forma cuadrática.
- **B-cubed:** por registro, precisión `|C(r) ∩ T(r)| / |C(r)|` y recall `|C(r) ∩ T(r)| / |T(r)|`, promediadas sobre los registros. Cada registro cuenta una vez.
- **Pares de fusión errónea frente a pares perdidos:** con datos de clientes, una fusión errónea es peor (privacidad, consentimiento de marketing equivocado). Por eso se trabaja con precisión alta y la zona gris se envía a revisión.
- **Confianza y calibración:** Brier score = media de (p − y)². **ECE** = Σ sobre los intervalos de probabilidad de (proporción del intervalo × |tasa de coincidencia observada − p media|).
- **KPI sin etiquetas** (en producción no hay verdad): número de entidades, clúster más grande, distribución de tamaños de clúster, tamaño de la cola de revisión, tasa de coincidencia por fuente, distribución de puntuaciones, deriva de ids.
- **Estadístico de deriva:** índice de estabilidad de la población, `PSI = Σ (a − e) × ln(a / e)` sobre los intervalos de una distribución de referencia (`e`) y la actual (`a`). Por debajo de 0.1, estable; entre 0.1–0.2, vigilar; por encima de 0.2, actuar.
- **Conjunto de referencia (*golden set*):** unos pocos miles de pares etiquetados por los *data stewards*, estratificados por franja de puntuación y renovados cada trimestre. Es la forma de medir la precisión y el recall en producción.

#### Precisión o recall: ¿qué importa más?

En identidad de clientes suele importar más la **precisión**. Pero la respuesta real es que eliges el umbral según el coste de cada tipo de error. Y eso depende de para qué se usan las coincidencias.

| Error | Qué significa | Consecuencia | ¿Se puede deshacer? |
|---|---|---|---|
| Precisión baja: **fusión errónea** | Dos personas distintas pasan a ser un solo cliente | Una persona ve los pedidos, la dirección o la cuenta de otra (un incidente RGPD); el consentimiento de marketing y las decisiones de crédito y fraude se basan en datos mezclados | Difícil: los sistemas posteriores ya han usado el cliente fusionado |
| Recall bajo: **coincidencia perdida** | Una persona tiene dos ids de cliente | Cartas duplicadas, una visión del cliente menos completa, una analítica algo peor | Fácil: una ejecución posterior o un *data steward* los enlaza |

Por eso el paso de grafos sacrifica 0.3 puntos de recall (0.965 → 0.962) a cambio de que la precisión pase de 0.966 a 0.998. Y por eso la sección 3.7 dice que dividir de más tiene arreglo, pero fusionar a dos personas, no.

Casos de uso en los que gana el **recall**:

- **Fraude y prevención del blanqueo (AML):** no detectar que dos solicitudes vienen de la misma persona es el error caro; un analista elimina las coincidencias falsas.
- **Control de sanciones y KYC:** una coincidencia perdida puede suponer un incumplimiento normativo.
- **Solicitudes de acceso o borrado RGPD:** tienes que encontrar todos los registros de la persona.

En la práctica se usan **dos umbrales**, no uno. Por encima del umbral alto, los pares se fusionan automáticamente (protege la precisión). Entre los dos, van a la cola de revisión de los *data stewards* (recupera recall). Por debajo del bajo, se quedan separados. Además, mide sobre **clústeres** (B-cubed), junto con el número de pares de fusión errónea y el clúster más grande, no solo sobre pares: un solo par malo puede fusionar dos clientes enteros. El comparador de ML lo demuestra: precisión media 0.9998 y, aun así, 142 pares de fusión errónea.

### 3.10 Deriva de identidad (*identity drift*)

La deriva de identidad es que la misma persona reciba un id distinto con el tiempo, o que los ids pasen sin avisar de una persona a otra. Causas: reconstruir los clústeres desde cero, una nueva versión del modelo, una nueva fuente, cambios de umbral. Soluciones:

- **No regeneres nunca los ids.** Arrástralos: asigna los clústeres nuevos a los ids antiguos según el solapamiento de registros.
- **Divisiones:** la parte más grande conserva el id; las demás reciben ids nuevos con un evento `split_from`.
- **Fusiones:** sobrevive el id más antiguo; el otro se retira con un **alias** para que las referencias antiguas sigan resolviéndose.
- **Mídela:** tasa de deriva por ejecución, divisiones y fusiones por ejecución, y una alerta cuando se disparan.

### 3.11 MLOps y feature stores

- **Almacén de características (*feature store*):** las características (*features*) se calculan una vez, se versionan, se documentan y las leen tanto el entrenamiento como el servicio. Así se evita el desajuste entre entrenamiento y servicio (por ejemplo, un vocabulario TF-IDF reajustado en el momento de puntuar). Un almacén offline para entrenar y uno online para consultas de baja latencia cuando se empareja en tiempo real.
- **Registro de modelos (*model registry*):** cada versión con sus métricas, la versión del conjunto de características y el artefacto. Alias (`champion`, `challenger`) en lugar de versiones fijadas en el código.
- **Puerta de promoción:** comprobaciones automáticas antes de mover un alias: calidad al menos igual, calibración aceptable, ningún encadenamiento nuevo. Antes de cambiar, puntúa el *challenger* en modo sombra sobre lotes reales.
- **Monitorización:** calidad de los datos de entrada (nulos, formatos), PSI de la distribución de puntuaciones, KPI sin etiquetas, deriva de ids y tasa de revocación de los *data stewards* (con qué frecuencia revierten las coincidencias automáticas).
- **Ciclo de reentrenamiento:** etiquetas de los *data stewards* → *golden set* → reentrenar → puerta → promover, todo registrado en MLflow.

## 4. Recorrido por el código

### Flujo de extremo a extremo

```text
data/generate_data.py
  |  customers.csv + new_batch.csv; true_entity_id / true_household_id son la verdad para evaluar
  v
common/standardise.py
  |  nombres limpios, campos de contacto, códigos fonéticos, unique_id
  +----------------------+----------------------+
  v                      v                      v
01_rules_rapidfuzz.py    02_splink.py         03_ml_recordlinkage.py
 reglas + punt. difusa   probabilidades EM    modelo supervisado de pares
  |                      |                      |
  +-------- pares + clústeres + métricas -------+
             |
             v
       04_graph_resolution.py   reparación cannot-link, identificadores compartidos
             |
             v
       05_mdm.py                maestro de clientes + lote incremental
             |
             v
       06_customer_spine.py     jerarquía, hogares, spine, contratos
             |
       07_identity_drift.py     estabilidad de ids entre ejecuciones (usa el modelo Splink guardado)
       08_mlops_feature_store.py feature store, registro, puerta, monitorización
             |
             v
       09_compare.py            results/comparison.md
```

Los tres comparadores usan *blocking* para no probar todos los pares posibles. Sus puntuaciones no son intercambiables. El script de reglas produce una puntuación de similitud con pesos puestos a mano. Splink produce una probabilidad a partir de parámetros Fellegi-Sunter aprendidos. El script de ML produce la probabilidad de un clasificador entrenado con la verdad sintética. Por tanto, los umbrales de cada script son decisiones operativas independientes, no una calibración compartida.

### 0. Generar el experimento: [data/generate_data.py](data/generate_data.py)

**Propósito:** crear datos con la verdad conocida para medir la calidad del emparejamiento de forma reproducible. `SEED`, `N_ENTITIES`, `N_NEW_BATCH` y `HOUSEHOLD_RATE` definen el experimento. `make_entity()` crea la verdad limpia a nivel de persona. `add_households()` agrupa en parejas a cerca del 10% de las personas en hogares que comparten dirección, a menudo apellido y a veces un email familiar (usa su propio generador aleatorio). `noisy_copy()` genera registros específicos de cada fuente con variaciones realistas. `main()` crea la población multifuente y un lote que llega más tarde.

**Qué se escribe:** `data/customers.csv` es la población inicial y `data/new_batch.csv` es la carga incremental. `true_entity_id` y `true_household_id` son las claves de respuesta que usa la evaluación. En un sistema real no deben tratarse como características de emparejamiento. Los scripts posteriores las arrastran para evaluar o crear etiquetas, pero nunca las usan como clave de *blocking* ni como característica de comparación.

**Por qué importa:** sin una clave de respuesta conocida, una demo puede mostrar coincidencias plausibles, pero no puede calcular fusiones erróneas ni enlaces perdidos. La semilla determinista hace que las ejecuciones sean comparables, aunque los cambios de versión de Faker o de las librerías pueden afectar a los resultados exactos.

### Base compartida: [common/standardise.py](common/standardise.py)

**Propósito:** aplicar la misma limpieza antes de generar candidatos y de comparar. `standardise()` copia la entrada, asigna `source_record_id` al `unique_id` de Splink y añade nombres normalizados, canonicalización de apodos y campos de email, teléfono, código postal, dirección, DOB y metaphone. Las funciones `clean_*`, más pequeñas, implementan la regla de cada campo.

**Conexión con los comparadores:** todos los pasos llaman a `standardise(raw)`, incluido el MDM cuando carga filas de origen y cuando prepara registros para la puntuación incremental. Esta única función compartida es la primera pieza del framework reutilizable.

**Idea de diseño:** la normalización hace que las diferencias de formato pesen menos, y la comparación difusa se encarga de las erratas y variaciones que quedan. La estandarización en producción necesita políticas explícitas de configuración regional, validación y específicas de cada fuente. Estas funciones auxiliares son, a propósito, pequeños ejemplos didácticos.

### Evaluación compartida: [common/evaluate.py](common/evaluate.py)

**Propósito:** puntuar los clústeres predichos frente a la verdad, no limitarse a inspeccionar pares de muestra. `evaluate_clusters()` calcula precisión/recall/F1 por pares, métricas B-cubed, número de entidades, clúster más grande, pares de fusión errónea y pares perdidos. `blocking_recall()` mide la completitud de pares (*pair completeness*) y la tasa de reducción. `union_find_clusters()` convierte las aristas de pares aceptados en componentes conexas.

**Interpretación:** las métricas por pares juzgan los pares agrupados juntos. B-cubed promedia la calidad por registro y evita que dominen los clústeres grandes. `largest_cluster` es un aviso útil de encadenamiento, no una métrica de calidad por sí sola. La misma función evalúa también los hogares en el paso 6.

### 1. Comparador hecho a mano: [01_rules_rapidfuzz.py](01_rules_rapidfuzz.py)

**Entrada:** `data/customers.csv`. **Salida:** `results/clusters_rapidfuzz.csv`, `results/review_queue_rapidfuzz.csv` y `results/metrics_rapidfuzz.csv`.

1. `BLOCKING_KEYS` lista combinaciones alternativas de campos. `candidate_pairs()` agrupa los registros por cada clave y une los pares resultantes. Los bloques de más de 200 registros se omiten para evitar la explosión de comparaciones que provocan valores compartidos, como datos de contacto genéricos.
2. `score()` construye similitudes por campo. `sim()` usa RapidFuzz para las cadenas; los valores exactos, como la DOB y el teléfono, usan coincidencia exacta. Los valores que faltan se omiten y los pesos restantes se renormalizan.
3. `AUTO_MATCH` y `REVIEW` dividen las puntuaciones en aristas automáticas, una lista de revisión y candidatos rechazados.
4. `union_find_clusters()` convierte las aristas de coincidencia automática en componentes conexas; `evaluate_clusters()` compara estos grupos con la verdad.

**Qué explicar:** es transparente porque el equipo eligió los campos, los pesos, las reglas de *blocking* y los umbrales. También es frágil: los cambios en la calidad de las fuentes pueden obligar a reajustarlo a mano, y una sola arista errónea puede unir componentes que, si no, estarían separadas.

### 2. Comparador probabilístico: [02_splink.py](02_splink.py)

**Entrada:** `data/customers.csv`. **Salidas:** `results/splink_model.json`, `pairs_splink.csv`, `clusters_splink.csv`, `review_queue_splink.csv`, `splink_threshold_sweep.csv`, tres gráficos HTML y `metrics_splink.csv`.

1. `settings` declara la tarea de deduplicación, el ID único del registro, los bloques de generación de candidatos y las comparaciones por campo. Los ajustes por frecuencia de término reducen el peso de los nombres comunes frente a los raros.
2. `build_linker()` registra los datos estandarizados en DuckDB y crea el `Linker` de Splink.
3. `train()` estima la probabilidad a priori, estima `u` con pares aleatorios y usa EM sobre tres bloques para estimar `m` (sección 3.5). El entrenamiento no recibe ninguna etiqueta.
4. `predict()` puntúa los pares candidatos; el umbral de predicción bajo conserva candidatos para decidir los umbrales después. Splink agrupa con `CLUSTER_THRESHOLD`, 0.95.
5. El barrido de umbrales muestra el equilibrio entre precisión y recall como una decisión de negocio. El JSON guardado es el modelo entrenado que reutilizan los pasos 5 y 7.

**Qué explicar:** con estos datos, la precisión de Splink es 0.966, inferior a la del modelo de ML, y 110 de sus 198 pares de fusión errónea son miembros de un mismo hogar. EM ha aprendido, con razón, que coincidir en dirección + apellido + email es una evidencia muy fuerte. Y dos personas que comparten casa y buzón producen exactamente eso. Esto prepara el paso 4.

### 3. Comparador supervisado: [03_ml_recordlinkage.py](03_ml_recordlinkage.py)

**Entrada:** `data/customers.csv`. **Salidas:** `results/pairs_ml_features.csv` y `results/metrics_ml.csv`.

1. El script importa la función de *blocking* de `01_rules_rapidfuzz.py`, así que el modelo puntúa los mismos pares candidatos.
2. `features()` calcula similitudes de nombre, igualdad fonética, coincidencia exacta de fecha/contacto/código postal y una similitud coseno TF-IDF de n-gramas de caracteres sobre el texto unido del registro. Acepta un vectorizador ya ajustado, que el paso 8 usa para el servicio.
3. `main()` crea etiquetas a partir de la verdad sintética y entrena *gradient boosting* con validación cruzada de dos particiones (*cross-fitting*), dividida por la entidad del registro izquierdo. Es *out-of-fold*, pero no estrictamente disjunto por entidad; el paso 8 muestra la versión estricta.
4. El script aplica umbrales a las probabilidades de los pares, forma componentes conexas, evalúa los clústeres y escribe las características con las etiquetas y las probabilidades *out-of-fold*.

**Qué explicar:** el enfoque de características y modelo puede aprender combinaciones difíciles de programar a mano, pero estos resultados usan una verdad sintética conocida. La AP por pares ronda 1.0 y los clústeres siguen conteniendo fusiones erróneas, así que las métricas de clúster son las honestas.

### 4. Resolución con grafos: [04_graph_resolution.py](04_graph_resolution.py)

**Entradas:** `data/customers.csv`, `results/pairs_splink.csv`, `results/pairs_ml_features.csv`. **Salidas:** `results/metrics_graph.csv`, `results/clusters_graph.csv` (clústeres de Splink reparados, que usa el MDM), `results/shared_identifiers.csv`.

1. `build_graph()` crea un grafo de networkx: los registros son nodos y los pares aceptados son aristas ponderadas por la evidencia en bits (el *match weight* de Splink).
2. `cannot_link()` combina dos reglas. `dob_conflict()`: las dos DOB se conocen y son distintas, permitiendo un intercambio de día y mes. `name_conflict()`: los nombres de pila canónicos son claramente distintos (Jaro-Winkler < 0.75, metaphone distinto), sin DOB coincidente y sin indicios de nombre y apellido intercambiados.
3. `repair()` revisa cada componente. Cuando encuentra un par en conflicto, ejecuta `nx.minimum_cut` entre ellos con la evidencia en bits como capacidades (`evidence_bits()` convierte una probabilidad de ML en *log-odds*), elimina las aristas del corte y vuelve a revisar ambos lados hasta que no queda ningún conflicto. La sección 3.7 recorre un ejemplo real.
4. `shared_identifiers()` construye la vista de identificadores: cada email o teléfono que apunta a más de una persona resuelta.

**Qué explicar:** con Splink, se dividen 42 componentes cortando 80 aristas. Los pares de fusión errónea bajan de 198 a 12 y el recall solo cae de 0.965 a 0.962. Con ML, las fusiones erróneas bajan de 142 a 9 y el F1 B-cubed sube a 0.992, el mejor de la demo. Las restricciones son reglas de negocio, así que son fáciles de explicar y de auditar. La lista de identificadores compartidos es una cola de trabajo para los *data stewards* y una lista de valores candidatos a excluir del *blocking*.

### 5. Flujo de datos maestros: [05_mdm.py](05_mdm.py)

**Entradas:** los datos iniciales en bruto, `results/clusters_graph.csv` (si no existe, usa `clusters_splink.csv`), `results/splink_model.json` y `data/new_batch.csv`. **Salidas:** `results/mdm.duckdb` más exportaciones CSV del *golden record*, el *crosswalk* y la cola de revisión.

1. `MiniMDM.__init__()` crea en DuckDB las tablas de origen, *crosswalk* (`xref`), *golden record* actual, historial, revisión y auditoría.
2. `initial_load()` escribe las filas de origen, asigna a cada clúster un `customer_id` generado, rellena `xref` y llama a `rebuild_golden()`.
3. `survive()` elige un valor ganador no vacío por campo. Los nombres y la DOB usan la frecuencia, después la prioridad de la fuente y después el valor más reciente; los campos de contacto usan el valor más reciente y después la prioridad de la fuente. El JSON `provenance` registra el registro de origen y la regla que ganó en cada campo.
4. `rebuild_golden()` recalcula solo los clientes afectados, cierra la versión abierta anterior del historial, incrementa la versión e inserta la nueva instantánea.
5. `score_new_records()` construye un *linker* de Splink a partir del modelo guardado y puntúa los registros existentes frente al nuevo lote sin reentrenar. `incremental_load()` asocia el registro con p ≥ 0.95; si no, crea un cliente nuevo, y las puntuaciones ≥ 0.50 entran en revisión.
6. `approve_review()`, `reject_review()` y `unmerge_record()` son las acciones de los *data stewards*. `unmerge_record()` valida un motivo, escribe en `steward_audit` y reconstruye ambos *golden records* dentro de una transacción.
7. `erase_customer()` elimina las filas de origen del cliente, el *crosswalk*, el maestro y el historial.

**Distinción importante:** el script normal no ejecuta `unmerge_record()`; consulta la sección 6. Los IDs de cliente son estables durante el ciclo de vida de esta base de datos, pero `main()` vuelve a crear el fichero DuckDB al arrancar.

### 6. Customer spine y jerarquía: [06_customer_spine.py](06_customer_spine.py)

**Entradas:** `results/mdm.duckdb` tras el paso 5. **Salidas:** tablas nuevas `household`, `identity_hierarchy`, `customer_spine`, `column_classification` en la misma base de datos, más `customer_spine.csv`, `identity_hierarchy.csv`, `spine_contracts.csv`, `metrics_households.csv`.

1. `households()` construye un grafo de clientes y nodos de dirección. Cada registro de origen aporta su dirección (código postal + línea de calle, emparejada de forma difusa con un *token-set ratio* ≥ 85 dentro del código postal). Así, un cliente cuya dirección en el *golden record* es una más reciente sigue enlazado al hogar que comparte. Las componentes conexas son los hogares, y cada uno recibe una regla: `single_person`, `same_address_same_surname` o `same_address`.
2. `build_hierarchy()` escribe una única tabla padre-hijo para todos los niveles: HOUSEHOLD (raíz) → CUSTOMER → SOURCE, cada arista con su regla y su confianza.
3. `main()` crea `customer_spine`: una fila por cliente con el hogar, los atributos del *golden record*, las claves de origen (`CRM:CRM-000123`), la probabilidad del eslabón más débil, la versión del *golden record*, la versión del modelo de emparejamiento (un hash del JSON de Splink) y la hora de publicación.
4. `contracts()` ejecuta siete contratos de datos: un cliente por registro de origen, ningún registro de origen huérfano, un *golden record* por cada cliente vivo, exactamente un hogar por cliente, todos los hogares existen, clave del *spine* única y todas las columnas PII clasificadas. Cualquier incumplimiento detiene la publicación con un código de salida distinto de cero.

**Qué explicar:** esta es la tabla de la Golden Layer que consumen los equipos posteriores. Se detectan hogares para el 75% de los pares reales del mismo hogar con un 97% de precisión. Los fallos son personas cuya dirección compartida no aparece nunca en sus registros (mudanzas, formularios web sin dirección). El gobierno es código: los contratos se ejecutan en cada construcción, no viven en un documento.

### 7. Deriva de identidad: [07_identity_drift.py](07_identity_drift.py)

**Entradas:** `data/customers.csv`, `data/new_batch.csv`, `results/splink_model.json`. **Salidas:** `results/identity_drift.csv`, `id_alias.csv`, `id_events.csv`.

1. `cluster()` puntúa y agrupa una instantánea con el modelo guardado, sin reentrenar.
2. La ejecución 1 agrupa los datos iniciales. La ejecución 2 agrupa una instantánea posterior: el 5% de los registros recibe un teléfono nuevo o pierde su email, y se añade el nuevo lote. Todo se vuelve a agrupar desde cero.
3. Se comparan tres estrategias de ids: `sequential()` (renumerar en cada ejecución), representativo (el id de un registro miembro) y `carry_forward()`, que da a cada clúster de la ejecución 2 el id de la ejecución 1 con el que más se solapa, conserva el id para la parte más grande de una división, retira el id más joven en una fusión y registra un alias.
4. `drift()` informa de la proporción de registros de la ejecución 1 cuyo id cambió; `membership_changed()` aporta contexto: cuántos registros cambiaron de clúster de verdad.

**Qué explicar:** la numeración secuencial cambia el 56% de los ids, el id representativo el 0.87% y el arrastre (*carry-forward*) el 0.20%, mientras que el 0.51% de los registros está en un clúster que cambió de verdad. El *carry-forward* produjo 201 ids nuevos, 11 divisiones y 5 fusiones con alias. Los ids son un producto con consumidores, así que su estabilidad es una métrica.

### 8. MLOps y feature store: [08_mlops_feature_store.py](08_mlops_feature_store.py)

**Entradas:** `data/customers.csv`, `data/new_batch.csv`. **Salidas:** `results/feature_store.duckdb`, `results/model_registry/` (modelos serializados con pickle y `registry.json`), `model_versions.csv`, `monitoring_report.csv` y `results/mlruns` si MLflow está instalado.

1. `FeatureStore` contiene `feature_definitions` y tablas versionadas de características de pares. La versión del conjunto de características es un hash de los nombres de las características y del vocabulario TF-IDF ajustado. `read()` rechaza las características cuya versión no coincide con la del modelo.
2. Los pares de entrenamiento se escriben en el almacén y se vuelven a leer, como haría un trabajo de entrenamiento programado.
3. Una **división estrictamente disjunta por entidad** pone un tercio de las personas en el conjunto de prueba; solo se usan los pares con los dos registros en entrenamiento (o los dos en prueba).
4. Se entrenan dos versiones: regresión logística y *gradient boosting*. `evaluate()` informa de la precisión media, Brier, ECE y B-cubed sobre los clústeres de prueba. `register()` guarda cada versión; `promotion_gate()` mueve el alias `champion` solo si el F1 B-cubed es al menos el del *champion*, ECE ≤ 0.05 y el encadenamiento no empeora.
5. La monitorización puntúa con el *champion* el nuevo lote real y una **carga rota** (teléfonos ausentes, nombres de pila reducidos a iniciales), leyendo las características a través del almacén con el vectorizador del entrenamiento. `monitor()` informa de los pares candidatos, la tasa de coincidencia, la proporción en zona gris y el PSI de la puntuación y de cada característica.

**Qué explicar:** v2 (B-cubed 0.993, ECE 0.004) supera a v1 (0.987, 0.012) y se promueve. El lote normal tiene un PSI de puntuación de 0.03 y ninguna alerta. La carga rota tiene un PSI de puntuación de 2.77 y cuatro alertas, pero su tasa de coincidencia parece mejor (0.98 frente a 0.89) porque desapareció un tercio de sus pares candidatos. Un solo KPI habría ocultado el incidente.

### 9. Informe: [09_compare.py](09_compare.py)

Reúne todos los CSV de métricas en `results/comparison.md`: la tabla de comparadores, hogares, contratos del *spine*, deriva, versiones del modelo y monitorización. No recalcula nada; las entradas que faltan se omiten.

### Integraciones opcionales: [databricks/splink_on_databricks.py](databricks/splink_on_databricks.py) y [zingg/zingg_customers.py](zingg/zingg_customers.py)

`databricks/splink_on_databricks.py` traslada la ruta local de Splink a SparkAPI, tablas Delta en Unity Catalog y registro en MLflow. Espera una sesión `spark` proporcionada por Databricks, una tabla Silver, un volumen de *checkpoint* y una instalación compatible de Splink. Es un ejemplo de diseño, no forma parte del *pipeline* verificado en portátil.

`zingg/zingg_customers.py` describe un flujo independiente de aprendizaje activo (*active learning*) sobre Spark. Su argumento de fase selecciona `findTrainingData`, `label`, `train` o `match`; `FieldDefinition` controla qué campos se ignoran, se comparan de forma exacta o de forma difusa. Comprueba la API de Python con la versión instalada de Zingg antes de ejecutarlo.

## 5. Recorrido de diez minutos

| Tiempo | Mostrar | Decir |
|---|---|---|
| 1 min | `data/customers.csv`, `results/comparison.md` | Tres sistemas, 8,192 registros, 4,000 personas, 183 hogares. El generador guarda la verdad, así que cada error se puede contar. |
| 1 min | Salida de `01_rules_rapidfuzz.py` | *Blocking*, puntuación difusa ponderada, umbrales, Union-Find. Explicable, F1 0.93 y ajustado a mano. |
| 2 min | Métricas de Splink, `splink_waterfall_example.html` | Pesos aprendidos con EM y sin etiquetas; el gráfico de cascada es la explicación para un *data steward*. Precisión 0.966: los hogares que comparten dirección y buzón parecen una sola persona. |
| 1 min | Salida de `03_ml_recordlinkage.py` | Las etiquetas dan el mejor recall. AP ≈ 1.0 y los clústeres siguen encadenándose, así que evalúa clústeres. |
| 2 min | Salida de `04_graph_resolution.py`, `shared_identifiers.csv` | Un cliente es una componente. Las reglas cannot-link y un corte mínimo bajan las fusiones erróneas de 198 a 12. La lista de identificadores compartidos va a los *data stewards* y a la lista de exclusión del *blocking*. |
| 1 min | `customer_spine` e `identity_hierarchy` en DuckDB | *Golden record* con procedencia, *crosswalk*, historial, hogar → cliente → fuente, publicado solo cuando se cumplen siete contratos. |
| 1 min | `identity_drift.csv`, `monitoring_report.csv` | Una reconstrucción ingenua cambia el 56% de los ids; el *carry-forward*, el 0.2%. Registro con puerta de promoción; una carga rota dispara cuatro alertas de PSI mientras la tasa de coincidencia parece mejor. |
| 1 min | Sección 7 del README | Cómo encaja con Bronze/Silver/Gold, SparkAPI, GraphFrames, tablas de características de Unity Catalog, MLflow y Workflows. Deja claro que Databricks y Zingg no se ejecutaron aquí. |

Usa `results/comparison.md` como fuente de las métricas exactas. Los valores documentados dependen de la semilla fija y de las versiones de los paquetes; no des a entender que son las métricas esperables en producción.

## 6. Opcional: demostrar cómo deshacer una fusión

La ejecución normal de `05_mdm.py` no llama a `unmerge_record`; sí ejecuta un ejemplo de aprobación y de borrado. Para demostrar cómo se deshace una fusión, ejecuta este fragmento desde PowerShell después de la demo. Modifica `results/mdm.duckdb` y no actualiza las exportaciones CSV ni el *spine*. Vuelve a ejecutar el *pipeline* para restaurar el estado original de la demo.

```powershell
@'
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mdm_demo", "05_mdm.py")
mdm_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdm_demo)

mdm = mdm_demo.MiniMDM(Path("results/mdm.duckdb"))
source_record_id = mdm.con.execute("""
    SELECT x.source_record_id
    FROM xref x
    JOIN (SELECT customer_id FROM xref GROUP BY customer_id HAVING count(*) > 1) multi
      USING (customer_id)
    LIMIT 1
""").fetchone()[0]
new_customer_id = mdm.unmerge_record(source_record_id, "Demo: correcting a false merge")
print("unmerged", source_record_id, "to", new_customer_id)
print(mdm.con.execute("SELECT * FROM steward_audit ORDER BY acted_at DESC LIMIT 1").df())
mdm.con.close()
'@ | .\.venv\Scripts\python.exe -
```

Explica que la fila de origen recibe un nuevo ID de cliente, que se reconstruyen el *golden record* antiguo y el nuevo, que el historial se versiona y que el motivo del *data steward* se escribe en `steward_audit`. Es una corrección de un solo registro, no una división general de clústeres.

## 7. Diseño del sistema: el framework a escala

¿Cómo construirías un framework de resolución de identidades para una empresa real? En este orden:

1. **Aclarar:** cuántos clientes y fuentes hay, si es por lotes o en tiempo real, B2C o B2B, qué consumidores dependen del id, cuánto cuesta una fusión errónea y quiénes son los *data stewards*.
2. **Ingerir y estandarizar (Bronze → Silver):** una tabla por fuente, una librería de estandarización compartida por todos los trabajos y controles de calidad de datos a la llegada (nulos, formatos, valores basura).
3. **Generación de candidatos:** varias reglas de *blocking*, límites de tamaño de bloque y una lista de exclusión de identificadores genéricos alimentada por el grafo de identificadores; mide la completitud de pares sobre el *golden set*.
4. **Puntuación por niveles:** reglas deterministas para los enlaces seguros (mismo email verificado + DOB), un modelo probabilístico (Splink sobre Spark) para el grueso y un modelo supervisado o de *active learning* solo donde la zona gris es grande. Umbrales según el uso de negocio: marketing puede aceptar más riesgo que finanzas.
5. **Capa de grafos:** componentes conexas, restricciones cannot-link y reparación, jerarquías de hogares y empresas, detección de identificadores compartidos. GraphFrames sobre Spark, o una base de datos de grafos si la jerarquía se consulta en línea.
6. **Gestión de maestros (*mastering*):** ids arrastrados (*carry-forward*), *survivorship* con procedencia, historial SCD2, *crosswalk* y flujo de trabajo de los *data stewards* con auditoría.
7. **Golden Layer:** las tablas del *customer spine* y de la jerarquía en Gold, publicadas solo cuando se cumplen los contratos, con la PII etiquetada y enmascarada y el linaje en el catálogo.
8. **Ruta en tiempo real (si hace falta):** un *feature store* online con atributos estandarizados y claves de *blocking*. Un registro nuevo busca candidatos por clave, lo puntúa el mismo modelo y recibe un id en milisegundos; el lote nocturno concilia.
9. **MLOps:** *feature store*, registro con *champion/challenger*, puerta de promoción, puntuación en sombra, monitorización del PSI, KPI sin etiquetas, deriva de ids y tasa de revocación de los *data stewards*; reentrenamiento a partir de las etiquetas de los *data stewards*.
10. **Reutilización:** el comparador es configuración (reglas de *blocking*, comparaciones, umbrales, reglas de *survivorship* por campo), así que una fuente nueva o un tipo de entidad nuevo (proveedor, producto) es un cambio de configuración, no un proyecto nuevo.

## 8. Preguntas frecuentes

### Fundamentos

- **¿Por qué no comparar todos los pares?** Aquí hay 33.5 millones de pares posibles; el *blocking* conserva el 96.5% de los pares reales evaluando 6,405. Con 30 millones de registros, comparar todos los pares es imposible.
- **¿Determinista o probabilístico?** Ambos, por niveles. Determinista para los enlaces seguros y para la explicabilidad; probabilístico o ML donde los datos tienen ruido y las reglas se quedan cortas o emparejan de más.
- **Explica Fellegi-Sunter en un minuto.** "Para cada campo defino niveles de coincidencia: exacto, errata pequeña, distinto, ausente. `m` es la frecuencia con la que las coincidencias reales caen en un nivel; `u`, la frecuencia con la que personas distintas caen en él por casualidad. El peso es log2(m/u), en bits. Parto de la probabilidad a priori, unos −12 bits porque las coincidencias son raras, sumo los bits de cada campo y lo convierto en una probabilidad. `u` sale de pares aleatorios y `m` de EM, así que no hacen falta etiquetas." La sección 3.5 tiene los ejemplos resueltos.
- **¿Qué hace el ajuste por frecuencia de término?** Coincidir en un apellido raro cuenta más que coincidir en `Smith`, usando la frecuencia del valor.
- **¿Splink y Zingg son comerciales? ¿Hace falta licencia?** No. Splink (Ministerio de Justicia del Reino Unido) tiene licencia MIT y es gratuito para cualquier uso, también comercial. Zingg tiene una edición Community gratuita bajo AGPL-3.0 y una edición de pago, Zingg Enterprise, con funciones extra y soporte. La AGPL no plantea problemas para uso interno: sus obligaciones solo se aplican si modificas Zingg y lo distribuyes o lo ofreces como servicio, y por eso algunos equipos legales lo evitan. Todo lo demás de la demo (rapidfuzz, recordlinkage, networkx, DuckDB, scikit-learn) es MIT o BSD. Los productos comerciales de este ámbito son Senzing, Informatica, Reltio, Tamr y Quantexa.
- **¿Jaro-Winkler o Levenshtein?** Jaro-Winkler para cadenas cortas como los nombres (premia los prefijos comunes); Levenshtein o distancia de edición para códigos y cadenas más largas; ratios basados en tokens cuando cambia el orden de las palabras.

### Grafos

- **¿Dónde ayudan los grafos en la resolución de identidades?** En el *clustering* (componentes), la detección y reparación del encadenamiento, los identificadores compartidos, las jerarquías de hogares y empresas, y la propagación de la identidad entre fuentes que nunca comparten un campo directamente.
- **El emparejamiento no es transitivo. ¿Qué haces?** Evaluar clústeres, limitar o inspeccionar las componentes grandes, añadir restricciones cannot-link, cortar las aristas más débiles (corte mínimo) o usar *correlation clustering* o detección de comunidades.
- **¿Cómo escalarías el paso de grafos?** Componentes conexas con GraphFrames sobre Spark; reparar solo las componentes que contienen un conflicto, que son una fracción pequeña; una base de datos de grafos solo para recorridos en línea.

### ML y confianza

- **¿De dónde salen las etiquetas? ¿Hacen falta datos sintéticos?** Se etiquetan pares, no características. Fuentes: las decisiones de los *data stewards* sobre la cola de revisión y un *golden set* estratificado; etiquetas *silver* a partir de identificadores en los que el negocio ya confía (documento nacional de identidad, tarjeta de fidelización, inicio de sesión compartido); pares de Splink con puntuación muy alta y muy baja como etiquetas provisionales; *active learning* para enviar a las personas solo los pares más dudosos. Los datos sintéticos sirven para construir y probar el *pipeline*, no para entrenar el modelo de producción. Sección 3.6, Paso 7.
- **¿Cómo evitas la fuga de datos (*leakage*)?** Dividiendo por entidad, nunca por par; `08` muestra la división estricta.
- **¿Qué significa "confianza" en una coincidencia?** Una probabilidad calibrada. Comprueba la calibración (Brier, ECE) antes de usar umbrales; recalibra con regresión isotónica o con el escalado de Platt.
- **¿Precisión o recall?** Normalmente precisión: una fusión errónea puede exponer los datos de una persona a otra y corromper las decisiones de consentimiento y crédito, y es difícil de deshacer. Una coincidencia perdida, en cambio, es un duplicado que una ejecución posterior puede arreglar. El recall gana en fraude, AML, control de sanciones y solicitudes de acceso RGPD. Usa dos umbrales (fusión automática, cola de revisión, mantener separados) y mide sobre clústeres. Sección 3.9.

### Spine, MDM y gobierno

- **¿Qué es un customer spine?** La tabla gobernada de ids de cliente resueltos, con jerarquía y claves de origen, con la que se cruza cada dominio; sección 3.8.
- **¿Cómo construyes una jerarquía gobernada?** Niveles explícitos, un solo padre por hijo, una regla y una confianza en cada arista, contratos que comprueban la forma en cada construcción e historial de cambios.
- **¿Reglas de survivorship?** Por campo: fiabilidad, actualidad, frecuencia, completitud; siempre con procedencia.
- **¿Cómo gestionas el borrado RGPD?** Borrando de las copias de origen, el *crosswalk*, el *golden record*, el historial y las características; limpiando (*vacuum*) las versiones antiguas de los ficheros; y conservando solo un registro de borrado que no identifique a nadie.

### Deriva, MLOps y feature stores

- **¿Qué es la deriva de identidad y cómo se reduce?** Sección 3.10; cita el 56% → 0.2%.
- **¿Cómo despliegas un nuevo modelo de emparejamiento de forma segura?** Registrar, evaluar sobre el *golden set*, pasar la puerta, puntuar en sombra sobre lotes reales, comparar los KPI sin etiquetas y la deriva de ids, y después mover el alias; para volver atrás, se mueve de nuevo.
- **¿Qué monitorizas sin etiquetas?** Número de entidades, clúster más grande, tamaño de la cola de revisión, tasa de coincidencia por fuente, PSI de la puntuación, deriva de ids y tasa de revocación de los *data stewards*.
- **¿Por qué un feature store aquí?** Los mismos atributos estandarizados y características de pares para el entrenamiento y para la puntuación por lotes y en tiempo real; versionados para que un modelo nunca lea características con las que no se entrenó; reutilizables entre distintos casos de emparejamiento.

### Lo que no está listo para producción

El MDM, el *spine* y el registro son modelos didácticos: no gestionan escrituras concurrentes y no tienen interfaz para los *data stewards*, control de acceso ni ruta en tiempo real. Los datos sintéticos están más limpios que los datos reales de clientes. Las reglas cannot-link se fían de la DOB. Zingg y Databricks no se ejecutaron.

## 9. Glosario

| Término | Significado |
|---|---|
| Blocking (agrupación por claves) | Limitar las comparaciones a los registros que comparten una clave barata |
| Pair completeness (completitud de pares) | Proporción de pares reales que sobreviven al *blocking* |
| Field (campo) | Una columna que se compara entre dos registros (apellido, DOB, email...) |
| Comparison (agreement) level (nivel de comparación o de coincidencia) | Un peldaño de la escala de similitud de un campo: exacto, errata pequeña, distinto, ausente |
| m probability (probabilidad m) | Proporción de coincidencias reales que caen en un nivel (calidad de los datos) |
| u probability (probabilidad u) | Proporción de pares de personas distintas que caen en un nivel por casualidad (lo común que es el valor) |
| Match weight (peso de coincidencia) | log2(m/u), sumado sobre los campos más la probabilidad a priori |
| EM | *Expectation-maximisation* (maximización de la esperanza): estima `m` sin etiquetas |
| B-cubed | Precisión y recall de clúster por registro |
| Chaining (encadenamiento) | Una arista mala que fusiona dos clústeres a través del cierre transitivo |
| Feature (característica) | Un número que describe cómo se comparan dos registros en un aspecto |
| Label (etiqueta) | La respuesta conocida para un par de entrenamiento: coincidencia (1) o no coincidencia (0) |
| Calibration (calibración) | Si las probabilidades predichas coinciden con las tasas de coincidencia observadas |
| Connected component (componente conexa) | Un grupo de nodos que pueden alcanzarse entre sí a través de aristas |
| Transitive closure (cierre transitivo) | Tratar A=B y B=C como A=C, es decir, tomar las componentes conexas |
| Cannot-link | Una regla que dice que dos registros son entidades distintas |
| Minimum cut (corte mínimo) | El conjunto de aristas más barato cuya eliminación separa dos nodos |
| Golden record (registro maestro) | Los mejores valores supervivientes de una entidad |
| Survivorship (supervivencia) | Reglas que eligen cada valor del *golden record* |
| Provenance (procedencia) | Qué registro de origen y qué regla produjeron cada valor |
| Crosswalk (xref) (tabla de correspondencias) | Mapa de los ids de origen al id maestro |
| Customer spine (columna vertebral de clientes) | Tabla gobernada de ids de cliente resueltos con la que se cruzan los dominios |
| Golden Layer | La capa Gold del *lakehouse*, que publica los datos maestros |
| Identity drift (deriva de identidad) | Que el id de una persona cambie entre ejecuciones, o que los ids pasen de una persona a otra |
| Carry-forward (arrastre de ids) | Asignar a los clústeres nuevos el id antiguo con el que más se solapan |
| Feature store (almacén de características) | Características versionadas y compartidas para entrenamiento y servicio |
| PSI | *Population stability index* (índice de estabilidad de la población), un estadístico de cambio de distribución |
| ECE | *Expected calibration error* (error de calibración esperado) |
| Champion / challenger | Modelo actual en producción / candidato a sustituirlo |

## 10. Solución de problemas

- Si falta una salida, vuelve a ejecutar los pasos en orden; las fases posteriores consumen los CSV anteriores, el modelo Splink guardado y `mdm.duckdb`.
- Si `06_customer_spine.py` termina con "data contract failed", vuelve a ejecutar primero `05_mdm.py`: el *spine* espera una base de datos MDM recién construida.
- Si PowerShell no encuentra `python`, instala Python 3.13 o usa el lanzador de Python para crear el entorno virtual, y después sigue con el intérprete de `.venv`.
- Si un gráfico de Splink no se abre, usa la opción Abrir archivo del navegador y selecciónalo en `results/`.
- Si un fichero DuckDB está bloqueado, cierra cualquier cliente SQL que lo tenga abierto y vuelve a ejecutar.
- Los ejemplos de Databricks y Zingg requieren sus propios entornos de ejecución y la ejecución local no los valida.
