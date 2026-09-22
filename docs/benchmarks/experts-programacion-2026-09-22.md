# KAMVEX — expertos vs. modelo solo — Qwen2.5-Coder-3B Q4 · CPU 6 hilos

`experto` = corpus + modo + prompt + samplers del experto · `corpus` = mismo corpus con prompt genérico · `modelo` = el LLM solo.

| experto | casos | experto | corpus | modelo | p50 experto |
|---|---|---|---|---|---|
| Programación | 12 | 12/12 | 7/12 | 12/12 | 6512 ms |

## Programación

**¿Qué hace functools.lru_cache?**
- ✅ experto: functools. Además, lru_cache: lru_cache(user_function)

Decorador para envolver una función con un memorizador invocable que guarda hasta el *maxsize* de las llamadas más recientes.
- ✅ corpus: functools. Además, lru_cache: lru_cache(user_function)

Decorador para envolver una función con un memorizador invocable que guarda hasta el *maxsize* de las llamadas más recientes.
- ✅ modelo solo: `functools.lru_cache` es una función en Python que mejora el rendimiento de las funciones que se ejecutan repetidamente con los mismos argumentos. Al usar `lru_cache`, Python guarda los resultados de las llamadas anterio

**¿Qué hace json.dumps?**
- ✅ experto: json.dumps(obj, *, skipkeys=False, ensure_ascii=True, \ Serializa *obj* en un str con formato JSON usando esta conversion table. Los argumentos tienen el mismo significado que en dump.
- ✅ corpus: dumps: dumps(obj, *, skipkeys=False, ensure_ascii=True, \

Serializa *obj* en un str con formato JSON usando esta conversion table. Además, los argumentos tienen el mismo significado que en dump.
- ✅ modelo solo: `json.dumps()` es una función en Python que se utiliza para convertir un objeto Python en una cadena JSON. JSON (JavaScript Object Notation) es un formato de texto ligero para el intercambio de datos. Aquí tienes algunos

**¿Para qué sirve os.path.join?**
- ✅ experto: os.path.join une uno o más componentes de ruta de forma inteligente.
- ✅ corpus: os.path.join une uno o más componentes de ruta de forma inteligente.
- ✅ modelo solo: `os.path.join` es una función en Python que se utiliza para unir varios componentes de un camino de archivo en una sola cadena. Esto es útil para crear rutas de archivo que funcionen correctamente en diferentes sistemas 

**¿Qué devuelve Array.prototype.reduce?**
- ✅ experto: El método **`reduce()`** ejecuta una función reductora sobre cada elemento de un array, devolviendo como resultado un único valor.
- ❌ corpus: La información disponible no cubre este tema.
- ✅ modelo solo: El método `Array.prototype.reduce` devuelve un único valor que es el resultado de aplicar una función a todos los elementos del array. La función que se pasa a `reduce` toma cuatro argumentos: el valor acumulado, el valo

**¿Qué hace la declaración let en JavaScript?**
- ✅ experto: La declaración **`let`** en JavaScript declara una variable de alcance local con ámbito de bloque(blockscope), permitiendo que las variables sean accesibles solo dentro del bloque en el que se declaran. Además, opcionalm
- ❌ corpus: # Let the base class default method raise the TypeError. Además, py
JSON (JavaScript Object Notation), especificado por 7159 (que hace obsoleto a 4627) y por ECMA-404, es un formato de intercambio de datos ligero inspira
- ✅ modelo solo: La declaración `let` en JavaScript es una forma de declarar variables con un ámbito de bloque. Esto significa que las variables declaradas con `let` solo son accesibles dentro del bloque en el que se declaran, como un bl

**¿Qué hace itertools.chain?**
- ✅ experto: itertools. Además, aproximadamente equivalente a::
def chain(*iterables):
# chain('ABC', 'DEF') → A B C D E F
for iterable in iterables:
yield from iterable.
- ✅ corpus: itertools. Además, aproximadamente equivalente a::
def chain(*iterables):
# chain('ABC', 'DEF') → A B C D E F
for iterable in iterables:
yield from iterable.
- ✅ modelo solo: `itertools.chain` es una función en Python que permite combinar múltiples iterables en uno solo. Esto es útil cuando necesitas procesar datos de múltiples fuentes de manera secuencial. Por ejemplo, si tienes una lista de

**¿Qué hace re.sub?**
- ✅ experto: re.sub retorna la cadena obtenida reemplazando las ocurrencias no superpuestas del patrón en la cadena por el reemplazo de repl. Si el patrón no se encuentra, se retorna la cadena sin cambios.
- ❌ corpus: sub('-{1,2}', dashrepl, 'pro----gram-files')
'pro--gram files'
>>> re. Además, sub(r'\sAND\s', ' & ', 'Baked Beans And Spam', flags=re.
- ✅ modelo solo: `re.sub` es una función en Python que se utiliza para buscar y reemplazar patrones en una cadena de texto. Aquí tienes una breve explicación de cómo funciona:

1. **Patrón**: Es el texto que se busca en la cadena de text

**¿Qué es fetch() en JavaScript?**
- ✅ experto: fetch(miSolicitud). Además, fetch(miSolicitud,miInicializador).
- ❌ corpus: js_output(attrs=None)

Retorna un fragmento de código JavaScript que, si se ejecuta en un navegador que admita JavaScript, actuará de la misma forma que si se hubiera enviado el encabezado HTTP. Además, js_output: Morsel
- ✅ modelo solo: `fetch()` es una función en JavaScript que se utiliza para realizar solicitudes HTTP. Es una forma más moderna y flexible de hacer peticiones a servidores en comparación con métodos como `XMLHttpRequest`. Permite hacer s

**¿Qué parámetros acepta functools.lru_cache?**
- ✅ experto: functools. Además, lru_cache: lru_cache(user_function)

Decorador para envolver una función con un memorizador invocable que guarda hasta el *maxsize* de las llamadas más recientes.
- ✅ corpus: functools. Además, lru_cache: lru_cache(user_function)

Decorador para envolver una función con un memorizador invocable que guarda hasta el *maxsize* de las llamadas más recientes.
- ✅ modelo solo: El parámetro `functools.lru_cache` acepta varios parámetros para controlar el comportamiento de la caché:

1. **maxsize**: Es el número máximo de elementos que la caché puede almacenar. Si se establece en `None`, la cach

**¿Qué hace el parámetro ensure_ascii de json.dumps?**
- ✅ experto: dumps: dumps(obj, *, skipkeys=False, ensure_ascii=True, \

Serializa *obj* en un str con formato JSON usando esta conversion table. Además, los argumentos tienen el mismo significado que en dump.
- ✅ corpus: dumps: dumps(obj, *, skipkeys=False, ensure_ascii=True, \

Serializa *obj* en un str con formato JSON usando esta conversion table. Además, los argumentos tienen el mismo significado que en dump.
- ✅ modelo solo: El parámetro `ensure_ascii` en `json.dumps()` es una opción que controla cómo se manejan los caracteres ASCII en los strings JSON. Aquí hay una explicación detallada:

- **`ensure_ascii=True` (por defecto)**: Los caracte

**¿Qué devuelve os.path.splitext?**
- ✅ experto: Devuelve un par (root, ext) donde root es el nombre de la ruta sin la extensión y ext es la extensión o vacío si no hay ninguna.
- ✅ corpus: Devuelve un par (root, ext) donde root es el nombre de la ruta sin la extensión y ext es la extensión o vacío si no hay ninguna.
- ✅ modelo solo: `os.path.splitext` es una función en Python que divide un archivo en su nombre base y su extensión. Devuelve una tupla con dos elementos: el nombre base del archivo y la extensión. Por ejemplo, si tienes un archivo llama

**¿Qué hace Array.prototype.flatMap?**
- ✅ experto: El método `flatMap()` primero mapea cada elemento usando una función de mapeo, luego aplana el resultado en una nueva matriz. Es idéntico a un map seguido de un flattende profundidad 1, pero `flatMap` es a menudo útil y 
- ❌ corpus: La información disponible no cubre este tema.
- ✅ modelo solo: `Array.prototype.flatMap` es un método en JavaScript que combina el funcionamiento de `map` y `flat` en una sola operación. Aquí te explico cómo funciona:

1. **`map`**: Este método crea un nuevo array aplicando una func
