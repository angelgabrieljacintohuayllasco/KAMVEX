# Agente A y Agente B

KAMVEX responde en tres pasos. **Agente A recupera** con un conjunto de predictores que
votan, una **capa de decisión** elige cuál de los candidatos responde, y **Agente B
redacta** con el elegido. Recuperar y redactar es el contrato de DASA; la capa de decisión
va en medio.

Hasta la versión 0.3.0 el paso de redactar no llegaba a ejecutarse en los expertos de Lengua
y Leyes: su modo por defecto era *Exacto*, que no llama al modelo. El usuario veía el
registro del corpus en crudo y con razón pensaba que faltaba el LLM.

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

## La capa de decisión: quién elige entre los candidatos

Agente A ordena los candidatos por recuperación, que no es lo mismo que «cuál contesta la
pregunta». Un modelo pequeño se queda con el primero aunque el bueno sea el tercero. Elegir
es una tarea aparte, y tiene su propia familia de modelos.

Laya, Kev, Von, SemIf y NanoJev son modelos de decisión abiertos: no generan texto, responden
una pregunta tipada. La que nos interesa es *Choice* — dado un estado y un conjunto de
opciones, devuelven una probabilidad por opción en una sola pasada. jevlike no es un modelo
sino un entrenador para construir esa cabeza de atención sobre opciones.

| Proyecto | Qué es | Dónde está |
| --- | --- | --- |
| Laya | ModernBERT-large 421M / mmBERT 322M multilingüe, Apache-2.0 | `convaiinnovations/laya` · [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) |
| SemIf | Lee los logits de las opciones de un modelo congelado (Qwen3.5-4B) | [TheoLeeCJ/SemIf-OpenJev](https://github.com/TheoLeeCJ/SemIf-OpenJev) |
| NanoJev | Qwen3-0.6B con cabezas de decisión tipadas; exige CUDA | [TianyuCodings/NanoJev](https://github.com/TianyuCodings/NanoJev) |
| Kev | Adaptadores LoRA sobre Qwen3.5 (0.8B/4B/9B) sirviendo `/v1/systemone` | — |
| Von | Arquitectura de codificador compacta | — |
| jevlike | Entrenador de una cabeza de atención sobre opciones, no un modelo | — |

### El elector que ya funciona aquí

`LogitChooser` implementa **la técnica de SemIf con el llama-server que ya está cargado**.
Las opciones van numeradas y se le pide solo el número; en vez de dejar que el modelo
escriba «la opción 2» y parsearlo, se lee qué probabilidad le da a los tokens «1», «2»,
«3»… en la siguiente posición. Una sola pasada, sin generar, determinista, en CPU y sin
dependencias nuevas.

**Viene apagado, y es una decisión medida.** Con un LLM general haciendo de elector no
cambia el resultado: Gemma 3 4B responde 8 de 8 turnos con y sin él, Gemma 2 2B responde 5
de 8 en ambos casos, y cuesta entre 3 y 8,5 segundos por pregunta. Con la regla de autoridad
casi nunca tiene algo que decidir. `KAMVEX_CHOOSER=logit` lo enciende.

La cuenta cambia con un modelo de decisión de verdad. Laya son 421M y responde en
milisegundos; ahí sí compensa, y para eso está el contrato de abajo.

### Enchufar los modelos de decisión propios

```
KAMVEX_CHOOSERS=laya=http://127.0.0.1:9101/decide,von=http://127.0.0.1:9102/decide
```

```
POST <url>   {"state": "<la pregunta>", "question": "¿Cuál responde?", "type": "choice",
              "options": [{"id": "1", "text": "…", "key": "Artículo 2"}, …]}
200          {"scores": {"1": 0.19, "2": 0.81}}
```

Se aceptan tres formas de respuesta: una distribución (`scores`, `probs`, `distribution`),
solo la elegida (`choice`), o la forma anidada de Laya (`answers.<pregunta>.choice/probs`).
Varios electores se promedian, porque una distribución dice *cuánto* prefiere cada uno y un
elector inseguro no debe pesar igual que uno convencido. Uno caído sale del promedio y se
anota el error; los demás deciden.

Si nadie destaca —el mejor no saca al segundo más de 0,05— no se toca nada y manda el orden
del Agente A. Un empate no es una decisión.

## Agente B: el LLM

Agente B hace tres cosas que un recuperador no puede hacer.

**1. Resolver la pregunta contra la conversación.** «dame más explicación» no es una
consulta nueva. Antes de buscar se reescribe contra el último tema con sujeto propio, o el
recuperador acaba devolviendo la entrada del diccionario para *explicación*. La reescritura
no usa el LLM: es barata y predecible.

Una pregunta que trae su propio tema no se reescribe, aunque suene a continuación. «y el
artículo 35?» nombra el artículo 35; es un tema nuevo.

**2. Confirmar la elección.** La capa de decisión ya puso delante el candidato que
responde, pero el prompt los numera todos y pide que use el que conteste e ignore el resto.
La respuesta registra cuál acabó usando, que no siempre es el que se le puso primero.

**3. Redactar.** Parafrasear, resumir o ampliar con lo que dicen los candidatos, en el
nivel de detalle que pidió el usuario. Si piden más detalle y las fuentes no dan para más,
la instrucción es decirlo, no rellenar.

La conversación entra en el prompt solo cuando la pregunta la necesita. Para una pregunta
con tema propio es ruido, y un modelo pequeño se engancha al turno anterior y lo repite:
preguntando por el Artículo 2 llegó a contestar sobre el 35 porque era lo último que había
dicho.

## Limpiar lo que el modelo añade de más

Un modelo pequeño no siempre devuelve solo la respuesta. Medido sobre la pila real:

- **Gemma 3 4B** contestó a «explícame mis derechos» con *las instrucciones del prompt*
  seguidas del bloque de fuentes, tal cual.
- **Qwen2.5 3B** empezó con «ÚNICAMENTE EL CANDIDATO [1] Dice lo siguiente sobre el
  Artículo 2:» antes de la respuesta.
- **Gemma 3 4B** respondió correctamente y luego **añadió la frase de negativa al final**,
  por obedecer la regla al pie de la letra.

Los tres se limpian antes de medir nada, y el tercero era el peligroso: una negativa pegada
al final hacía que el guardarraíl diera la respuesta por negativa y **se saltara la
comprobación entera**. La respuesta salía sin verificar.

El recorte del preámbulo se compara con las **instrucciones**, no con las fuentes. Citar la
fuente al pie de la letra es justo lo que debe hacer una respuesta anclada; borrarla por
parecerse al prompt dejaría al usuario sin respuesta. De las líneas iniciales se quita el
marcador `[2] (clave)` y se conserva lo que venga detrás, que puede ser del modelo.

La negativa se borra por **oraciones completas**: cortar en «no cubre este tema» dejaba
colgando «La información disponible».

### El orden de las reglas pesa tanto como su contenido

Al reescribir el prompt dejé la regla de rendirse —«si ninguna fuente responde la pregunta,
di que no la cubre»— en último lugar. Qwen2.5 3B pasó a negarse en tres de ocho turnos,
incluidos «¿Qué dice el Artículo 2?» y «y el artículo 35?», que contestaba bien antes. Lo
último que lee un modelo pequeño pesa de más.

Ahora la regla de rendirse va en medio y empieza por «solo si», y lo último que lee es cómo
escribir. La primera regla está en positivo: *busca la fuente que responde y contesta con lo
que dice*, en vez de *responde usando solo las fuentes*. Decirle qué hacer funciona mejor que
decirle qué no hacer.

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
