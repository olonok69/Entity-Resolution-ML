# Guion del vídeo: resolución de identidad de clientes, del *fuzzy matching* a un *customer spine* gobernado

English version: [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md)

Plan de grabación para el vídeo de YouTube basado en este repositorio. Duración objetivo: unos 22 minutos. Cada capítulo indica qué se ve en pantalla y qué decir; la narración es una guía, no un teleprompter. Las cifras salen de una ejecución limpia con la semilla 42; vuelve a ejecutar `run_all.sh` antes de grabar y compáralas con `results/comparison.md`.

En la narración las cifras van con coma decimal, como se dicen en voz alta; en pantalla el programa las muestra con punto.

Graba a partir de este guion, no de la guía. Las diapositivas [`slides/customer-identity-resolution.pptx`](slides/customer-identity-resolution.pptx) siguen el mismo orden que los capítulos: cada capítulo indica sus diapositivas, así que puedes recorrer la presentación de la 1 a la 29 sin saltos. Las diapositivas están en inglés. Cada capítulo también indica la sección de [DEMO_GUIDE.es.md](DEMO_GUIDE.es.md) que puedes enlazar en la descripción del vídeo para quien quiera los detalles.

## Antes de grabar

- Ejecución limpia: `bash run_all.sh` (o la secuencia de PowerShell de [DEMO_GUIDE.es.md](DEMO_GUIDE.es.md)).
- Abre en pestañas del navegador: `results/comparison.md` (renderizado), `results/splink_waterfall_example.html`, `results/splink_match_weights.html`.
- Abre una consola de DuckDB o DBeaver sobre `results/mdm.duckdb` con las consultas de la sección 3 del [README](README.md) (en inglés) preparadas.
- Tamaño de letra del editor y del terminal 16 o más; oculta las notificaciones.
- Deja `true_entity_id` visible solo en la primera toma de datos, y di una vez que es la clave de respuestas, nunca un campo para emparejar.

## Capítulos (descripción de YouTube)

```text
00:00 Por qué es difícil la identidad de clientes
02:00 Los datos sintéticos y por qué tienen una clave de respuestas
03:30 Estandarización y blocking
05:30 Reglas y fuzzy matching
07:00 Splink: Fellegi-Sunter sin etiquetas
10:00 ML supervisado: variables, etiquetas y por qué las métricas por pares engañan
12:00 ¿Precisión o recall? Ponerle precio a cada error
13:00 Grafos: encadenamiento, reglas cannot-link y reparación con corte mínimo
15:30 MDM: golden record, crosswalk y stewardship
17:00 Customer spine y la jerarquía de identidad
18:00 Deriva de identidad: mantener los ids estables
19:00 MLOps: feature store, registro de modelos y monitorización
20:15 Del portátil a una plataforma de datos
21:30 Resumen y qué hace falta en producción
```

## Orden de las diapositivas de un vistazo

| Capítulo | Diapositivas | Sección de la guía |
|---|---|---|
| 1. Por qué es difícil la identidad de clientes | 1 a 4 | 3.1 |
| 2. Los datos y la clave de respuestas | 5 | 4 (generate_data.py) |
| 3. Estandarización y blocking | 6 a 7 | 3.2, 3.3 |
| 4. Reglas y fuzzy matching | 8 | 3.4 |
| 5. Splink | 9 a 10 | 3.5 |
| 6. ML supervisado | 11 a 12 | 3.6 |
| 7. ¿Precisión o recall? | 13 | 3.9 |
| 8. Grafos | 14 a 17 | 3.7 |
| 9. MDM | 18 a 19 | 3.8 |
| 10. Customer spine | 20 | 3.8 |
| 11. Deriva de identidad | 21 | 3.10 |
| 12. MLOps | 22 a 24 | 3.11 |
| 13. Del portátil a una plataforma de datos | 25 a 26 | 7 |
| 14. Resumen | 27 a 29 | 2 |

## 1. Por qué es difícil la identidad de clientes (00:00, 2 min)

**Diapositivas:** 1 (título), 2 (una persona, tres sistemas), 3 (qué vas a aprender), 4 (el pipeline).

**En pantalla:** diapositivas 1 y 2, con las filas de CRM, WEB y BILLING de la misma persona; después las diapositivas 3 y 4.

**Di:** "Todas las empresas tienen al mismo cliente en varios sistemas, y ninguno comparte una clave. Robert Smith en el CRM es Bob Smith en la web y R. Smyth en facturación. Si te equivocas en un sentido, le mandas tres cartas; si te equivocas en el otro, fusionas a dos personas y le enseñas a un cliente los datos de otro. En este vídeo construyo el pipeline completo en un portátil: fuzzy matching, un modelo probabilístico, machine learning, técnicas de grafos, un pequeño hub de datos maestros, un customer spine gobernado y el MLOps que lo rodea, y mido cada paso.

Este es el mapa del vídeo [diapositiva 3]. Y este es el pipeline [diapositiva 4]: ocho etapas, siempre con la misma forma. Estandarizar, agrupar por claves, puntuar, grafo, maestro, spine, estabilizar y operar. Cada caja es un script del repositorio."

## 2. Los datos y la clave de respuestas (02:00, 1.5 min)

**Diapositivas:** 5.

**En pantalla:** diapositiva 5, después `data/generate_data.py` (`noisy_copy`, `add_households`) y luego `data/customers.csv` en un visor.

**Di:** "Los datos reales nunca te dicen la verdad, así que los genero. 4.000 personas y 8.192 registros repartidos en tres sistemas, con erratas, apodos, nombre y apellido intercambiados, campos vacíos, gente que se ha mudado y 183 hogares donde dos personas comparten dirección y a veces un email familiar. Cada registro guarda un `true_entity_id`. Es la clave de respuestas: solo la uso para medir, nunca para emparejar."

## 3. Estandarización y blocking (03:30, 2 min)

**Diapositivas:** 6 (sección Matching), 7 (embudo de blocking).

**En pantalla:** diapositiva 6, después `common/standardise.py` (apodos, `clean_email`, `clean_phone`), luego `BLOCKING_KEYS` en `01_rules_rapidfuzz.py`, la línea de blocking que imprime el script y la diapositiva 7.

**Di:** "La mitad de la calidad del matching viene de una limpieza aburrida: pasar a minúsculas, quitar tratamientos, convertir Bob en Robert, normalizar teléfonos y códigos postales y añadir códigos fonéticos. Después, el blocking. 8.192 registros dan 33,5 millones de pares. Solo comparo registros que comparten una clave barata: mismo email, mismo teléfono, misma fecha de nacimiento y apellido que suena igual, etcétera. Quedan 6.405 pares, y todavía contienen el 96,5 % de las coincidencias reales. Esa cifra es el techo del recall, así que es lo primero que mido."

## 4. Reglas y fuzzy matching (05:30, 1.5 min)

**Diapositivas:** 8 (tres formas de puntuar un par).

**En pantalla:** diapositiva 8, después `score()` en `01_rules_rapidfuzz.py` y luego la línea de métricas.

**Di:** "El enfoque clásico: una puntuación fuzzy ponderada, dos umbrales, uno para fusionar automáticamente y otro para revisar, y Union-Find para convertir pares en clientes. El F1 es 0,93. Es fácil de explicar, pero elegí cada peso a mano, y cada fuente nueva obliga a reajustarlos. Por eso los dos capítulos siguientes sustituyen esos pesos: Splink los aprende sin etiquetas y un clasificador los aprende con etiquetas."

## 5. Splink: Fellegi-Sunter sin etiquetas (07:00, 3 min)

**Diapositivas:** 9 (campos, niveles, m y u), 10 (sumar los bits de un par).

**En pantalla:** diapositiva 9, después `train()` en `02_splink.py`, luego `splink_m_u_parameters.html` y después la diapositiva 10 junto a `splink_match_weights.html` y `splink_waterfall_example.html`.

**Di:** "Splink aprende los pesos en lugar de que yo los adivine. Compara los dos registros campo a campo: nombre, apellido, fecha de nacimiento, email, etcétera. Para cada campo tiene una pequeña escala de niveles de acuerdo: exacto, una errata pequeña, más lejos, completamente distinto o vacío.

Para cada nivel aprende dos números. m: de todos los pares que de verdad son la misma persona, ¿cuántos caen en este nivel? Para el nombre, el 68 % coincide exactamente. u: de todos los pares que son personas distintas, ¿cuántos caen aquí por pura casualidad? Solo medio por ciento comparte nombre. Divides m entre u, tomas el logaritmo en base 2 y obtienes bits de evidencia: más 7 por un nombre exacto, menos 3 por uno distinto y cero si falta.

Cada par empieza en menos 12 bits, porque solo uno de cada cuatro mil quinientos pares al azar es una coincidencia. Sumas los bits de cada campo, lo conviertes en probabilidad y listo. u sale de pares al azar, que casi nunca coinciden, y m del algoritmo de esperanza-maximización, así que no necesito ninguna etiqueta. Y se explica solo: este gráfico de cascada es exactamente esa suma, barra a barra, para un par.

La precisión es 0,966, más baja de lo que esperaba. Cuando miro las fusiones erróneas, 110 de las 198 son personas del mismo hogar. Misma dirección, mismo apellido, mismo email familiar. El modelo acierta en que es una evidencia fuerte; solo que es evidencia de un hogar, no de una persona. Quedaos con esto."

## 6. ML supervisado: variables, etiquetas y por qué las métricas por pares engañan (10:00, 2 min)

**Diapositivas:** 11 (un par se convierte en una fila de variables), 12 (de dónde salen las etiquetas).

**En pantalla:** diapositiva 11, `features()` en `03_ml_recordlinkage.py`, la AP y las métricas de clusters que imprime el script, y después la diapositiva 12.

**Di:** "Si los data stewards me dan etiquetas, puedo entrenar un clasificador. Cada par candidato se convierte en una fila de números: cuánto se parecen los nombres, los apellidos, si coincide la fecha de nacimiento, el teléfono, el código postal, y una similitud TF-IDF del nombre completo. Para Thomsa Datson y Thomas Dawson eso es 0,97 para el nombre, 0,91 para el apellido y unos para fecha de nacimiento, teléfono y código postal. La etiqueta es uno si son la misma persona. Gradient boosting aprende de esas filas y, a diferencia de Fellegi-Sunter, puede aprender combinaciones, por ejemplo que un teléfono compartido vale menos cuando el apellido es distinto.

Dos trampas. Separa entrenamiento y test por persona, no por par, o el mismo registro aparece en los dos lados y la puntuación sale demasiado buena. Y comprueba la calibración: cuando el modelo dice 0,9, ¿acierta nueve de cada diez veces? Aquí sí, con un error de 0,4 puntos. La precisión media es 0,9998, prácticamente perfecta. Pero convierte los pares en clusters y siguen quedando 142 pares erróneos, porque una sola arista mala une dos clusters enteros. Por eso siempre evalúo los clusters con B-cubed, no solo los pares.

¿De dónde salen las etiquetas en la vida real? No de datos sintéticos como los míos. Se etiquetan pares: los stewards deciden los pares de la zona gris en la cola de revisión, el negocio ya confía en algunos vínculos, como el mismo pasaporte o la misma tarjeta de fidelización, y las puntuaciones muy altas y muy bajas de Splink sirven para empezar. El active learning manda a las personas solo los pares de los que el modelo está menos seguro. Y todo esto es open source: Splink es MIT, la edición community de Zingg es AGPL; no hay que comprar ninguna licencia."

## 7. ¿Precisión o recall? (12:00, 1 min)

**Diapositivas:** 13.

**En pantalla:** diapositiva 13.

**Di:** "¿Qué error es peor? Con datos de clientes, normalmente la fusión errónea: dos personas se convierten en una, una ve los pedidos de la otra, y eso es un incidente de privacidad difícil de deshacer. Una coincidencia perdida es una carta duplicada que una ejecución posterior puede arreglar. Pero no siempre: en fraude, control de sanciones o una solicitud de acceso del RGPD, perder un vínculo es el error caro. Así que no eliges un umbral, eliges dos: por encima del alto fusionas automáticamente, en medio lo mandas a una persona y por debajo del bajo los mantienes separados."

## 8. Grafos: encadenamiento, cannot-link y reparación con corte mínimo (13:00, 2.5 min)

**Diapositivas:** 14 (sección Grafos), 15 (una arista mala fusiona a dos personas), 16 (cannot-link y corte mínimo), 17 (corte mínimo en el componente Jones).

**En pantalla:** diapositivas 14 y 15, después 16 y 17, `repair()` y `cannot_link()` en `04_graph_resolution.py`, las líneas de antes y después, y luego `shared_identifiers.csv`.

**Di:** "Piensa en los registros como nodos y en las coincidencias como aristas, y dale a cada arista su evidencia en bits, el mismo match weight que calculó Splink. Un cliente es un componente conexo: todo lo que puedes alcanzar siguiendo aristas. Ahí está también el peligro. Si A coincide con B y B con C, A y C acaban juntos aunque no compartan nada. Aquí hay un caso real: dos Thomas Jones y tres Stanley Jones, unidos por una única arista débil de 6,6 bits que viene de un email familiar compartido.

Ahora añado conocimiento de negocio como reglas cannot-link: dos registros con fechas de nacimiento distintas no pueden ser la misma persona. 42 de los 2.712 componentes incumplen una regla. Para cada uno ejecuto un corte mínimo: el conjunto de aristas con menos bits en total que separa los registros en conflicto. El puente de 6,6 bits desaparece; la arista de 59,5 bits entre los dos registros idénticos de Thomas nunca se corta. Usar bits importa: las probabilidades se saturan todas cerca de 1, así que el corte no podría distinguir una arista fuerte de una débil. Se cortan 80 aristas, los pares fusionados por error bajan de 198 a 12 y el recall solo pasa de 0,965 a 0,962.

El mismo grafo me da otra cosa: emails conectados a más de una persona. Aquí 31 son buzones familiares. Esa lista va a los stewards y a la lista de exclusiones del blocking."

## 9. MDM: golden record, crosswalk y stewardship (15:30, 1.5 min)

**Diapositivas:** 18 (sección Mastering), 19 (el mini MDM).

**En pantalla:** diapositivas 18 y 19, después consultas de DuckDB sobre `golden_record` (enseña `provenance`), `xref`, `golden_history` y `review_queue`.

**Di:** "Los clusters todavía no son un producto. El hub de datos maestros le da a cada cliente un id estable, elige el mejor valor de cada campo con reglas de survivorship y anota de dónde salió, mantiene un crosswalk desde cada id de origen y guarda el historial. Los registros nuevos se puntúan contra el maestro con el modelo guardado: 197 de 200 clientes que vuelven se asignan correctamente. Los dudosos van a una cola de revisión, y cada acción de un steward queda auditada. Un borrado por el RGPD elimina a la persona de todas las tablas."

## 10. Customer spine y jerarquía (17:00, 1 min)

**Diapositivas:** 20.

**En pantalla:** diapositiva 20, después `SELECT * FROM customer_spine WHERE household_size > 1`, la consulta de la jerarquía y `spine_contracts.csv`.

**Di:** "El customer spine es la tabla a la que todo el mundo se une. Cada fila es un cliente con su hogar, sus claves de origen, la versión del modelo y su vínculo más débil. Por encima, una jerarquía gobernada: hogar, cliente y registro de origen, cada arista con su regla y su confianza. Y la gobernanza es código: siete contratos de datos se ejecutan en cada build, y si uno falla, no se publica nada."

## 11. Deriva de identidad (18:00, 1 min)

**Diapositivas:** 21.

**En pantalla:** diapositiva 21 (gráfico de barras), `carry_forward()` en `07_identity_drift.py`.

**Di:** "Vuelve a ejecutar el matching la semana que viene y mira qué pasa con los ids. Si renumeras los clusters, el 56 % de los clientes recibe un id nuevo: se rompen todas las tablas que dependen de ellos. Si arrastras los ids por solapamiento, mantienes el id para la parte más grande cuando un cliente se divide y guardas un alias cuando dos clientes se fusionan, solo cambia el 0,2 %."

## 12. MLOps: feature store, registro y monitorización (19:00, 1.25 min)

**Diapositivas:** 22 (sección MLOps), 23 (feature store, registro y puerta de promoción), 24 (monitorización sin etiquetas).

**En pantalla:** diapositivas 22 y 23, después la clase `FeatureStore`, las líneas del registro y de la promoción, y luego la diapositiva 24 y `monitoring_report.csv`.

**Di:** "Para operar el matcher de ML como un producto, las variables viven en un feature store versionado que leen tanto el entrenamiento como la puntuación, así que no hay desfase entre los dos. Los modelos van a un registro; un aspirante solo pasa a campeón si supera una puerta de calidad de clusters y de calibración. Después, monitorización sin etiquetas: en un lote normal la distribución de puntuaciones es estable. En una fuente rota, donde han desaparecido los teléfonos y los nombres se han quedado en iniciales, saltan cuatro alertas de deriva, mientras que la tasa de coincidencias, por sí sola, parece mejor. Vigila más de un KPI."

## 13. Del portátil a una plataforma de datos (20:15, 1.25 min)

**Diapositivas:** 25 (cómo encaja en un lakehouse), 26 (un framework reutilizable a escala).

**En pantalla:** diapositiva 25 y después la 26. Opcionalmente `databricks/splink_on_databricks.py`.

**Di:** "Todo lo que hemos visto corre en un portátil con DuckDB. En una plataforma de datos la forma es la misma; solo cambia el motor. Bronze es una tabla por fuente, silver es la tabla de clientes estandarizada, después viene Splink sobre Spark con la reparación por grafos y la cola de revisión, y gold es la capa publicada: golden record, crosswalk, spine y jerarquía, con contratos y enmascarado de los datos personales. Los registros nuevos llegan por los change feeds y se emparejan de forma incremental. El notebook de Databricks del repositorio es un ejemplo de diseño; no lo he ejecutado para este vídeo.

Si tuviera que construir esto para una empresa real, estos son los ocho pasos [diapositiva 26]. Empieza preguntando cuántos registros hay, qué fuentes, si es por lotes o en tiempo real y cuánto cuesta una fusión errónea. La última línea es la importante: el matcher es configuración, así que una fuente nueva es un cambio de configuración, no un proyecto nuevo."

## 14. Resumen (21:30, 1 min)

**Diapositivas:** 27 (resultados por método), 28 (lecciones), 29 (descarga el código).

**En pantalla:** diapositiva 27, después la 28 y luego la 29 con la URL del repositorio.

**Di:** "Aquí están todas las cifras en un solo gráfico. Las reglas son explicables, Splink te da pesos aprendidos sin etiquetas, el ML te da recall cuando tienes etiquetas y los grafos arreglan lo que los pares no ven. Alrededor necesitas un maestro, un spine gobernado, ids estables y MLOps. Todo está en el repositorio, con una guía que explica cada paso. En producción, espera datos más sucios y cifras más bajas; lo que se mantiene es el método. El enlace está en la descripción: clónalo, ejecútalo en menos de un minuto y cuéntame en los comentarios cuál es tu problema de matching más difícil."

## Planos de recurso y gráficos

- Animación de los registros de una persona en tres sistemas (capítulo 1).
- Embudo de blocking: 33,5 M → 6.405 pares (capítulo 3).
- Pesos de Fellegi-Sunter sumándose (capítulo 5).
- Fila de variables de un par y la barra con los dos umbrales (capítulos 6 y 7).
- Cluster encadenado con una arista de corte mínimo en rojo, y después el componente Jones corte a corte (capítulo 8).
- Árbol hogar → cliente → origen (capítulo 10).
- Gráfico de barras de la deriva: 56 % / 0,87 % / 0,20 % (capítulo 11).
- Capas bronze, silver y gold (capítulo 13).
- Tabla de resultados de `results/comparison.md` (capítulo 14).
