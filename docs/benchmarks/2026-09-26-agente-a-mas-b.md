# Agente A + Agente B: la prueba

Medido el 2026-09-26 sobre la pila real (sidecar + llama-server + corpus instalados desde `.kamvex`), en CPU con 4 hilos.

Las ocho preguntas son las que el usuario escribió en la app y que solo devolvían el texto crudo del Agente A. Cada turno se hace dos veces con el mismo historial: en **Exacto** (solo Agente A) y en **Anclado** (Agente A propone, Agente B redacta).

## Qué hizo el LLM en cada turno

| modelo | turnos | redactó | guardarraíl | negó | candidato elegido | cobertura media | latencia mediana (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Gemma 2 2B | 8 | 4 | 4 | 0 | 7 | 0.665 | 8494 |
| Gemma 3 1B | 8 | 2 | 5 | 1 | 5 | 0.572 | 6517 |
| Qwen2.5 1.5B | 8 | 3 | 4 | 1 | 4 | 0.583 | 6918 |

- **redactó**: Agente B eligió un candidato y escribió la respuesta. Es lo que faltaba.
- **guardarraíl**: el LLM se salió del corpus y se devolvió la fuente. No es un fallo: es el sistema negándose a que un modelo de 1-2 B invente.
- **negó**: el LLM dijo que los candidatos no responden la pregunta.
- **cobertura media**: fracción del vocabulario de la respuesta que está en el corpus.

## Qué cambió respecto a las capturas

**Gemma 2 2B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): Órgano sexual masculino.

**Gemma 3 1B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): El pene es un órgano sexual masculino.

**Qwen2.5 1.5B** · «explicame que es Pene»

- Exacto (Agente A): pene: Órgano sexual masculino.
- Anclado (A+B): El pene es un órgano sexual masculino.

## Detalle turno a turno

- [Gemma 2 2B](2026-09-26-agente-b-gemma2b.md)
- [Gemma 3 1B](2026-09-26-agente-b-gemma3-1b.md)
- [Qwen2.5 1.5B](2026-09-26-agente-b-qwen15b.md)

## Cómo reproducirlo

```
python scripts/qa/prove_agent_b.py \
    --model sidecar/models/gemma-2-2b-it-Q4_K_M.gguf \
    --label "Gemma 2 2B" --out docs/benchmarks/agente-b-gemma2b.md
```
