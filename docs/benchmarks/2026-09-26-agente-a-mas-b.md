# Agente A + Agente B: la prueba

Medido el 2026-09-26 sobre la pila real (sidecar + llama-server + corpus instalados desde `.kamvex`), en CPU con 4 hilos.

Las ocho preguntas son las que el usuario escribió en la app y que solo devolvían el texto crudo del Agente A. Cada turno se hace dos veces con el mismo historial: en **Exacto** (solo Agente A) y en **Anclado** (Agente A propone, Agente B redacta).

## Qué hizo el LLM en cada turno

| modelo | turnos | redactó | guardarraíl | negó | candidato usado | elector decidió | elector cambió el orden | elector (ms) | cobertura media | latencia mediana (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gemma 2 2B sin elector | 8 | 5 | 3 | 0 | 7 | 0 | 0 | — | 0.707 | 7596 |
| Gemma 2 2B | 8 | 5 | 3 | 0 | 7 | 1 | 1 | 4947.3 | 0.718 | 7669 |
| Gemma 3 1B | 8 | 2 | 5 | 1 | 5 | 1 | 0 | 3444.1 | 0.553 | 6040 |
| Gemma 3 4B sin elector | 8 | 8 | 0 | 0 | 8 | 0 | 0 | — | 1.0 | 9122 |
| Gemma 3 4B | 8 | 8 | 0 | 0 | 8 | 1 | 1 | 7793.3 | 1.0 | 8828 |
| Qwen2.5 1.5B | 8 | 3 | 3 | 2 | 5 | 1 | 1 | 4578.9 | 0.68 | 6558 |
| Qwen2.5 3B | 8 | 5 | 2 | 1 | 6 | 1 | 1 | 8527.1 | 0.755 | 7424 |

- **redactó**: Agente B eligió un candidato y escribió la respuesta. Es lo que faltaba.
- **guardarraíl**: el LLM se salió del corpus y se devolvió la fuente. No es un fallo: es el sistema negándose a que un modelo de 1-2 B invente.
- **negó**: el LLM dijo que los candidatos no responden la pregunta.
- **candidato usado**: el LLM acabó usando un candidato identificable, no inventando.
- **elector decidió / cambió el orden**: la capa de decisión (SemIf sobre llama-server) eligió con margen, y en cuántos turnos el elegido no era el primero del Agente A. Ahí es donde aporta.
- **cobertura media**: fracción del vocabulario de la respuesta que está en el corpus.

## Qué cambió respecto a las capturas

**Gemma 2 2B sin elector** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): El pene es el órgano sexual masculino.

**Gemma 2 2B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): El pene es el órgano sexual masculino.

**Gemma 3 1B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): No hay más detalle en las fuentes disponibles. Esto es lo que recogen: pene: Órgano sexual masculino.

**Gemma 3 4B sin elector** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): Órgano sexual masculino.

**Gemma 3 4B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): Órgano sexual masculino.

**Qwen2.5 1.5B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): No hay más detalle en las fuentes disponibles. Esto es lo que recogen: pene: Órgano sexual masculino.

**Qwen2.5 3B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): El pene es el órgano sexual masculino.

## ¿Aporta la capa de decisión?

Mismo modelo, mismas preguntas, misma semilla: la única diferencia es el elector.

| modelo | redactó con / sin | cobertura con / sin | coste del elector |
| --- | --- | --- | --- |
| Gemma 2 2B | 5 / 5 | 0.718 / 0.707 | 4947.3 ms |
| Gemma 3 4B | 8 / 8 | 1.0 / 1.0 | 7793.3 ms |

## Detalle turno a turno

- [Gemma 2 2B sin elector](2026-09-26-agente-b-gemma2b-sin-elector.md)
- [Gemma 2 2B](2026-09-26-agente-b-gemma2b.md)
- [Gemma 3 1B](2026-09-26-agente-b-gemma3-1b.md)
- [Gemma 3 4B sin elector](2026-09-26-agente-b-gemma3-4b-sin-elector.md)
- [Gemma 3 4B](2026-09-26-agente-b-gemma3-4b.md)
- [Qwen2.5 1.5B](2026-09-26-agente-b-qwen15b.md)
- [Qwen2.5 3B](2026-09-26-agente-b-qwen3b.md)

## Cómo reproducirlo

```
python scripts/qa/prove_agent_b.py \
    --model sidecar/models/gemma-2-2b-it-Q4_K_M.gguf \
    --label "Gemma 2 2B" --out docs/benchmarks/agente-b-gemma2b.md
```
