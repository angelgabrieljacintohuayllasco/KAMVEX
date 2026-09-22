# Benchmarks

Todo lo de esta carpeta se genera contra la pila real (sidecar + `llama-server` + modelo
GGUF), no con simulaciones. Reproducir:

```bash
# 1. levantar la pila con un modelo y los datasets ya construidos
python scripts/qa/stack.py --home E:/kamvex-bench \
    --model sidecar/models/qwen2.5-1.5b-instruct-q4_k_m.gguf --backend cpu --threads 6 \
    --bundles "datasets-out/*.kamvex"

# 2. calidad de recuperación y de respuesta por dataset y modo
python sidecar/bench.py --sidecar http://127.0.0.1:PUERTO \
    --datasets constitucion-peru-1993,medlineplus-salud-es,wikipedia-es-peru,diccionario-es \
    --modes statistical,grounded --n 20 --out docs/benchmarks/fecha.md

# 3. expertos: perfil completo vs. mismo corpus con prompt genérico vs. modelo solo
python sidecar/bench_experts.py --sidecar http://127.0.0.1:PUERTO --experts programacion
```

## Qué mide cada número

| métrica | qué significa | por qué importa |
|---|---|---|
| hit@1 / hit@5 | el registro sobre el que se pregunta es el primer / está entre los 5 primeros fragmentos | si la recuperación falla, ningún modelo lo arregla |
| exact / recall | cuánto del texto original aparece en la respuesta | mide si el modo Exacto devuelve el dato tal cual |
| groundedness | porcentaje de palabras de contenido de la respuesta que existen en los fragmentos | una respuesta con palabras que el corpus no tiene es una alucinación candidata |
| fallback | veces que el guardarraíl rechazó la respuesta del LLM y devolvió la determinista | cuántas alucinaciones se atajaron |
| no-cubre | veces que el modo Anclado dijo "La información disponible no cubre este tema" | un valor alto con corpus correcto = el modelo es demasiado conservador |
| Oregano | auditoría anti-alucinación de DASA (0-100) | contrato del proyecto: 100 = ningún término prohibido apareció |

## Resultados

| archivo | qué contiene |
|---|---|
| [`2026-09-22-qwen15b-cpu.md`](2026-09-22-qwen15b-cpu.md) | 4 datasets × 2 modos, Qwen2.5-1.5B en CPU |
| [`experts-2026-09-22.md`](experts-2026-09-22.md) | expertos Salud, Leyes, Perú y Lengua (Qwen2.5-1.5B) |
| [`experts-programacion-2026-09-22.md`](experts-programacion-2026-09-22.md) | experto Programación (Qwen2.5-Coder-3B) |

### Resumen 2026-09-22

Equipo: Ryzen 5 5600GT (6 núcleos), 28 GB RAM, sin GPU utilizable (la Radeon integrada
comparte memoria; la GeForce GT 610 tiene un driver de 2018 y queda descartada por
auto-tune). Todo corre en CPU.

**Recuperación y anti-alucinación** (20 preguntas por dataset):

| dataset | hit@1 | Oregano | groundedness (Anclado) | p50 Exacto | p50 Anclado |
|---|---|---|---|---|---|
| Constitución del Perú | 100 % | 100 | 90,3 % | 26 ms | 3,0 s |
| MedlinePlus salud | 100 % | 100 | 93,1 % | 43 ms | 3,2 s |
| Wikipedia Perú | 100 % | 100 | 96,6 % | 59 ms | 2,9 s |
| Diccionario (64 643 lemas) | 100 % | 100 | 89,2 % | 80 ms | 1,2 s |

Cero alucinaciones detectadas por el test Oregano en los cuatro corpus. El guardarraíl
léxico rechazó y sustituyó entre el 10 % y el 20 % de las respuestas del LLM.

**Expertos** (aciertos sobre preguntas con respuesta verificable en la fuente):

| experto | casos | experto | mismo corpus, prompt genérico | modelo solo |
|---|---|---|---|---|
| Programación (Coder-3B) | 12 | **12/12** | 7/12 | 12/12 |
| Leyes del Perú | 3 | **3/3** | 3/3 | 1/3 |
| Perú (cultura) | 3 | **3/3** | 3/3 | 2/3 |
| Lengua española | 2 | **2/2** | 2/2 | 1/2 |
| Salud | 5 | 4/5 | 4/5 | 5/5 |

Lectura honesta de la tabla:

- Donde el conocimiento es **local o normativo** (leyes, geografía peruana, léxico) el
  experto acierta y el modelo por su cuenta falla: 3/3 contra 1/3 en la Constitución.
- En **programación** el modelo ya sabe las respuestas, pero el perfil del experto casi
  duplica los aciertos frente al mismo corpus con un prompt genérico (12/12 contra 7/12),
  y las respuestas citan la documentación oficial en lugar de la memoria del modelo.
- En **salud** el modelo solo acierta más (5/5 contra 4/5) porque las preguntas eran de
  conocimiento general; el valor del experto ahí es que responde desde MedlinePlus y no
  desde lo que el modelo recuerde, que es lo que importa en un tema sensible.
