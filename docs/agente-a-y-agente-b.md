# Agente A y Agente B

KAMVEX responde en dos pasos, como manda el diseño de DASA. **Agente A recupera** y
**Agente B redacta**. Hasta la versión 0.3.0 el segundo paso no llegaba a ejecutarse en los
expertos de Lengua y Leyes: su modo por defecto era *Exacto*, que no llama al modelo, así
que el usuario veía el registro del corpus en crudo y con razón pensaba que faltaba el LLM.

## Agente A: un conjunto de predictores que votan

Agente A ya no es un solo recuperador. Es un ensemble; cada predictor propone candidatos y
sus listas se funden. Ninguno responde: proponen.

| Predictor | Qué aporta | Peso |
| --- | --- | --- |
| `semantic` | Embeddings MiniLM + IVF-PQ, lo que ya hacía DASA. Encuentra por significado. | 1.0 |
| `key` | El registro que la pregunta nombra entero: «Artículo 2», «efímero». | 3.0 |
| `text` | BM25 sobre el **texto** de los registros. Encuentra lo que no se nombra por su clave. | 1.4 |
| `lexical` | Solapamiento de palabras de contenido con las claves del corpus. | 0.7 |
| externos | Cualquier predictor propio detrás de HTTP. | 1.0 |

### Cómo se funden

Reciprocal Rank Fusion ponderada: cada predictor suma `peso / (60 + posición + 1)` a los
candidatos de su lista. No hace falta que sus scores estén en la misma escala, que es
justo el problema al mezclar un coseno de 0,55 con un acierto exacto de 1,0. Después, un
candidato propuesto por varios predictores recibe un extra de 0,15 por cada apoyo, porque
el acuerdo es la señal más fiable que hay.

Hay una excepción deliberada. Si el índice de claves encuentra la clave **entera** dentro
de la pregunta, ese candidato es **autoritativo**: va primero y con score 1.0. Sin esa
regla, dos predictores flojos coincidiendo en otra cosa lo tapan, y «explicame que es
Pene» terminaba contestando la definición de *pendiente*.

### BM25 y los registros largos

BM25 castiga los documentos largos porque asume que son palabrería. Un artículo que
enumera treinta y dos derechos no es palabrería: es exactamente el que responde «explícame
mis derechos». El castigo se topa al doble de la longitud media (`LENGTH_CLAMP = 2.0`), y
con eso el Artículo 2 entra en los primeros puestos en vez de quedar enterrado.

### Enchufar predictores propios

Un predictor externo es un servicio HTTP:

```
POST <url>   {"query": "...", "top_k": 5, "dataset": "diccionario-es"}
200          {"candidates": [{"key": "...", "text": "...", "score": 0.93}, …]}
```

`key` o `text`, al menos uno. Si solo llega la clave, el texto se lee del corpus. Se
registran por variable de entorno, separados por comas:

```
KAMVEX_PREDICTORS=laya=http://127.0.0.1:9001/predict,kev=http://127.0.0.1:9002/predict
```

Solo se aceptan `http://127.0.0.1`, `http://localhost` y `https://`. Un predictor caído o
que devuelve basura no tumba el ensemble: se anota el error en el diagnóstico y los demás
siguen votando.

## Agente B: el LLM

Agente B hace tres cosas que un recuperador no puede hacer.

**1. Resolver la pregunta contra la conversación.** «dame más explicación» no es una
consulta nueva. Antes de buscar se reescribe contra el último tema con sujeto propio, o el
recuperador acaba devolviendo la entrada del diccionario para *explicación*. La reescritura
no usa el LLM: es barata y predecible.

Una pregunta que trae su propio tema no se reescribe, aunque suene a continuación. «y el
artículo 35?» nombra el artículo 35; es un tema nuevo.

**2. Elegir entre los candidatos.** El prompt numera los candidatos y pide que use el que
responde la pregunta e ignore el resto. La respuesta registra cuál acabó usando.

**3. Redactar.** Parafrasear, resumir o ampliar con lo que dicen los candidatos, en el
nivel de detalle que pidió el usuario. Si piden más detalle y las fuentes no dan para más,
la instrucción es decirlo, no rellenar.

La conversación entra en el prompt solo cuando la pregunta la necesita. Para una pregunta
con tema propio es ruido, y un modelo pequeño se engancha al turno anterior y lo repite:
preguntando por el Artículo 2 llegó a contestar sobre el 35 porque era lo último que había
dicho.

## El guardarraíl

Todo lo que escribe Agente B pasa por una comprobación léxica: qué fracción de las palabras
de contenido de la respuesta aparece en los candidatos. Por debajo de 0,85 la respuesta se
descarta y se devuelve la fuente.

Esto no es un plan B, es la función. Medido con Gemma 2 2B sobre el diccionario, las
respuestas descartadas decían «glándula cavernosa» (la anatomía correcta es *cuerpo*
cavernoso) y «permitir la inserción de una varita». Un modelo de dos mil millones de
parámetros inventa anatomía en cuanto le pides una explicación larga de una definición de
cuatro palabras. La respuesta honesta es la que da el sistema: *no hay más detalle en las
fuentes disponibles*.

## Modo Exacto: ni una palabra ajena al corpus

El reescritor estadístico de DASA encadena oraciones con conectores propios («Además,»,
«Asimismo,»). No aportan datos, pero en una cita legal falsean el texto: el Artículo 2 no
dice «1. Además, a la vida». KAMVEX los quita cuando la oración sin el conector sí está
literal en las fuentes, que es la prueba de que fue inyectado. Y si hay un candidato
autoritativo, se cita su texto tal cual sin pasar por el reescritor.

DASA y SHARD no se tocan: todo esto vive en KAMVEX.

## Medirlo

`scripts/qa/prove_agent_b.py` levanta la pila real, instala los corpus y replica las
conversaciones que fallaban, pidiendo cada turno dos veces (Exacto y Anclado) con el mismo
historial. Resultados en [`benchmarks/2026-09-26-agente-a-mas-b.md`](benchmarks/2026-09-26-agente-a-mas-b.md).
