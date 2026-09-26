# Agente A + Agente B con Gemma 2 2B

- Modelo: `gemma-2-2b-it-Q4_K_M.gguf` (cpu)
- Fecha: 2026-09-26 02:28
- Pila real: sidecar + llama-server + corpus instalados desde `.kamvex`.
- **Exacto** = solo Agente A (el registro del corpus). **Anclado** = Agente A propone y Agente B (el LLM) elige y redacta.

## Lengua española — diccionario

### Turno 1: «explicame que es Pene»

- Predictores que propusieron: key×1, lexical×0, semantic×5, text×5
- Motor: `llm`, cobertura léxica 1.00, detalle: amplio
- Latencia: Exacto 1711 ms · Anclado 3398 ms

**Exacto (solo Agente A)**

> pene: Órgano sexual masculino.

**Anclado (Agente A + Agente B)**

> Órgano sexual masculino.

<details><summary>Candidatos que recibió el LLM</summary>

1. `pene` (score 1.0; key 1.0) — pene: Órgano sexual masculino.
2. `explicable` (score 0.4667; text 1.0) — explicable: que se puede explicar.
3. `explicablemente` (score 0.4591; text 1.0) — explicablemente: de manera que puede ser explicada.

</details>

### Turno 2: «dame mas explicacion»

- Reescrito para buscar: «explicame que es Pene» (la pregunta sola no tenía tema)
- Predictores que propusieron: key×1, lexical×0, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.25, detalle: amplio
- Latencia: Exacto 116 ms · Anclado 5711 ms

**Exacto (solo Agente A)**

> pene: Órgano sexual masculino.

**Anclado (Agente A + Agente B)**

> No hay más detalle en las fuentes disponibles. Esto es lo que recogen: pene: Órgano sexual masculino.

<details><summary>Candidatos que recibió el LLM</summary>

1. `pene` (score 1.0; key 1.0) — pene: Órgano sexual masculino.
2. `explicable` (score 0.4667; text 1.0) — explicable: que se puede explicar.
3. `explicablemente` (score 0.4591; text 1.0) — explicablemente: de manera que puede ser explicada.

</details>

### Turno 3: «hazme una explicacion muy larga de la palabra pene»

- Predictores que propusieron: key×3, lexical×0, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.50, detalle: amplio
- Latencia: Exacto 194 ms · Anclado 4281 ms

**Exacto (solo Agente A)**

> pene: Órgano sexual masculino.

**Anclado (Agente A + Agente B)**

> No hay más detalle en las fuentes disponibles. Esto es lo que recogen: pene: Órgano sexual masculino.

<details><summary>Candidatos que recibió el LLM</summary>

1. `pene` (score 1.0; key 1.0) — pene: Órgano sexual masculino.
2. `explicación` (score 1.0; key 0.9, text 0.8662) — explicación: Acción de explicar algo.
3. `palabra` (score 0.6963; key 0.95) — palabra: Una palabra es una unidad de lenguaje que se usa para expresar un concepto.

</details>

### Turno 4: «dame una explicacion detallada»

- Reescrito para buscar: «hazme una explicacion muy larga de la palabra pene» (la pregunta sola no tenía tema)
- Predictores que propusieron: key×3, lexical×0, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.08, detalle: amplio
- Latencia: Exacto 189 ms · Anclado 15637 ms

**Exacto (solo Agente A)**

> pene: Órgano sexual masculino.

**Anclado (Agente A + Agente B)**

> No hay más detalle en las fuentes disponibles. Esto es lo que recogen: pene: Órgano sexual masculino.

<details><summary>Candidatos que recibió el LLM</summary>

1. `pene` (score 1.0; key 1.0) — pene: Órgano sexual masculino.
2. `explicación` (score 1.0; key 0.9, text 0.8662) — explicación: Acción de explicar algo.
3. `palabra` (score 0.6963; key 0.95) — palabra: Una palabra es una unidad de lenguaje que se usa para expresar un concepto.

</details>

## Leyes del Perú — Constitución de 1993

### Turno 1: «explicame mis derechos»

- Predictores que propusieron: key×0, lexical×0, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.86, detalle: amplio
- Latencia: Exacto 56 ms · Anclado 18695 ms

**Exacto (solo Agente A)**

> Artículo 139: Son principios y derechos de la función jurisdiccional: 1. Además, el principio de inaplicabilidad por analogía de la ley penal y de las normas que restrinjan derechos.

**Anclado (Agente A + Agente B)**

> Los derechos que te corresponden son los enumerados en el artículo 2, que establece que tienes derecho a la vida, a tu identidad, a tu integridad moral, psíquica y física y a tu libre desarrollo y bienestar. También tienes derecho a la igualdad ante la ley, a la libertad de informar y opinar, a la elección, remoción o revocación de autoridades, a la iniciativa legislativa y a un referéndum. Recuerda que es importante consultar con un abogado para obtener asesoramiento legal específico en tu caso.

<details><summary>Candidatos que recibió el LLM</summary>

1. `Artículo 139` (score 1.0; text 1.0) — Artículo 139: Son principios y derechos de la función jurisdiccional: 1. La unidad y exclusividad de la función jurisdiccional.No existe ni puede establecerse jurisdicción alguna independiente, con excepción de la milita
2. `Artículo 2` (score 0.9839; text 0.9811) — Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la ig
3. `Artículo 107` (score 0.9683; text 0.9421) — Artículo 107: El Presidente de la República y los congresistas tienen derecho de iniciativa en la formación de las leyes. También tienen el mismo derecho en las materias que le son propias los otros poderes del Estado, l
4. `Artículo 31` (score 0.9531; text 0.9123) — Artículo 31: Los ciudadanos tienen derecho a participar en los asuntos públicos mediante referéndum; iniciativa legislativa; remoción o revocación de autoridades y demanda de rendición de cuentas. Tienen también el derec

</details>

### Turno 2: «y el articulo 35?»

- Predictores que propusieron: key×1, lexical×5, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.95, detalle: breve
- Latencia: Exacto 44 ms · Anclado 6143 ms

**Exacto (solo Agente A)**

> Artículo 35: Los ciudadanos pueden ejercer sus derechos individualmente o a través de organizaciones políticas como partidos, movimientos o alianzas, conforme a ley. Tales organizaciones concurren a la formación y manifestación de la voluntad popular. Su inscripción en el registro correspondiente les concede personalidad jurídica. La ley establece normas orientadas a asegurar el funcionamiento democrático de los partidos políticos, y la transparencia en cuanto al origen de sus recursos económicos y el acceso gratuito a los medios de comunicación social de propiedad del Estado en forma proporcional al último resultado electoral general.

**Anclado (Agente A + Agente B)**

> El artículo 35 establece que los ciudadanos pueden ejercer sus derechos individuales o a través de organizaciones políticas como partidos, movimientos o alianzas. Estas organizaciones se inscriben en el registro correspondiente para obtener personalidad jurídica.

<details><summary>Candidatos que recibió el LLM</summary>

1. `Artículo 35` (score 1.0; key 1.0, lexical 0.6455, text 1.0) — Artículo 35: Los ciudadanos pueden ejercer sus derechos individualmente o a través de organizaciones políticas como partidos, movimientos o alianzas, conforme a ley. Tales organizaciones concurren a la formación y manife
2. `Artículo 115` (score 0.2701; text 0.0009) — Artículo 115: Por impedimento temporal o permanente del Presidente de la República, asume sus funciones el Primer Vicepresidente. En defecto de éste, el Segundo Vicepresidente. Por impedimento de ambos, el Presidente del
3. `Artículo 114` (score 0.2658; text 0.0008) — Artículo 114: El ejercicio de la Presidencia de la República se suspende por: 1. Incapacidad temporal del Presidente, declarada por el Congreso, o 2. Hallarse éste sometido a proceso judicial, conforme al artículo 117º d
4. `Artículo 141` (score 0.2616; text 0.0008) — Artículo 141: Corresponde a la Corte Suprema fallar en casación, o en última instancia, cuando la acción se inicia en una Corte Superior o ante la propia Corte Suprema conforme a ley. Asimismo, conoce en casación las res

</details>

### Turno 3: «¿Qué dice el Artículo 2?»

- Predictores que propusieron: key×1, lexical×5, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.92, detalle: breve
- Latencia: Exacto 10 ms · Anclado 8494 ms

**Exacto (solo Agente A)**

> Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la igualdad ante la ley. Nadie debe ser discriminado por motivo de origen, raza, sexo, idioma, religión, opinión, condición económica o de cualquiera otra índole. 3. A la libertad de conciencia y de religión, en forma individual o asociada. No hay persecución por razón de ideas o creencias. No hay delito de opinión. El ejercicio público de todas las confesiones es libre, siempre que no ofenda la moral ni altere el orden público. 4. A las libertades de información, opinión, expresión y difusión del pensamiento mediante la palabra oral o escrita o la imagen, por cualquier medio de comunicación social, sin previa autorización ni censura ni impedimento algunos, bajo las responsabilidades de ley.Los delitos cometidos por medio del libro, la prensa y demás medios de comunicación social se tipifican en el Código Penal y se juzgan en el fuero común.Es delito toda acción que suspende o clausura algún órgano de expresión o le impide circular libremente. Los derechos de informar y opinar comprenden los de fundar medios de comunicación. 5. A solicitar sin expresión de causa la información que requiera y a recibirla de cualquier entidad pública, en el plazo legal, con el costo que suponga el pedido. Se exceptúan las informaciones que afectan la intimidad personal y las que expresamente se excluyan por ley o por razones de seguridad nacional.El secreto bancario y la reserva tributaria pueden levantarse a pedido del juez, del Fiscal de la Nación, o de una comisión investigadora del Congreso con arreglo a ley y siempre que se refieran al caso investigado. 6. A que los servicios informáticos, computarizados o no, públicos o privados, no suministren informaciones que afecten la intimidad personal y familiar. 7. Al honor y a la buena reputación, a la intimidad personal y familiar así como a la voz y a la imagen propias.Toda persona afectada por afirmaciones inexactas o agraviada en cualquier medio de comunicación social tiene derecho a que éste se rectifique en forma gratuita, inmediata y proporcional, sin perjuicio de las responsabilidades de ley. 8. A la libertad de creación intelectual, artística, técnica y científica, así como a la propiedad sobre dichas creaciones y a su producto. El Estado propicia el acceso a la cultura y fomenta su desarrollo y difusión. 9. A la inviolabilidad del domicilio. Nadie puede ingresar en él ni efectuar investigaciones o registros sin autorización de la persona que lo habita o sin mandato judicial, salvo flagrante delito o muy grave peligro de su perpetración. Las excepciones por motivos de sanidad o de grave riesgo son reguladas por la ley. 10. Al secreto y a la inviolabilidad de sus comunicaciones y documentos privados. Las comunicaciones, telecomunicaciones o sus instrumentos sólo pueden ser abiertos, incautados, interceptados o intervenidos por mandamiento motivado del juez, con las garantías previstas en la ley. Se guarda secreto de los asuntos ajenos al hecho que motiva su examen. Los documentos privados obtenidos con violación de este precepto no tienen efecto legal. Los libros, comprobantes y documentos contables y administrativos están sujetos a inspección o fiscalización de la autoridad competente, de conformidad con la ley. Las acciones que al respecto se tomen no pueden incluir su sustracción o incautación, salvo por orden judicial. 11. A elegir su lugar de residencia, a transitar por el territorio nacional y a salir de él y entrar en él, salvo limitaciones por razones de sanidad o por mandato judicial o por aplicación de la ley de extranjería. 12. A reunirse pacíficamente sin armas. Las reuniones en locales privados o abiertos al público no requieren aviso previo. Las que se convocan en plazas y vías públicas exigen anuncio anticipado a la autoridad, la que puede prohibirlas solamente por motivos probados de seguridad o de sanidad públicas. 13. A asociarse y a constituir fundaciones y diversas formas de organización jurídica sin fines de lucro, sin autorización previa y con arreglo a ley. No pueden ser disueltas por resolución administrativa. 14. A contratar con fines lícitos, siempre que no se contravengan leyes de orden público. 15. A trabajar libremente, con sujeción a ley. 16. A la propiedad y a la herencia. 17. A participar, en forma individual o asociada, en la vida política, económica, social y cultural de la Nación. Los ciudadanos tienen, conforme a ley, los derechos de elección, de remoción o revocación de autoridades, de iniciativa legislativa y de referéndum. 18. A mantener reserva sobre sus convicciones políticas, filosóficas, religiosas o de cualquiera otra índole, así como a guardar el secreto profesional. 19. A su identidad étnica y cultural. El Estado reconoce y protege la pluralidad étnica y cultural de la Nación. Todo peruano tiene derecho a usar su propio idioma ante cualquier autoridad mediante un intérprete. Los extranjeros tienen este mismo derecho cuando son citados por cualquier autoridad. 20. A formular peticiones, individual o colectivamente, por escrito ante la autoridad competente, la que está obligada a dar al interesado una respuesta también por escrito dentro del plazo legal, bajo responsabilidad. Los miembros de las Fuerzas Armadas y de la Policía Nacional sólo pueden ejercer individualmente el derecho de petición. 21. A su nacionalidad. Nadie puede ser despojado de ella. Tampoco puede ser privado del derecho de obtener o de renovar su pasaporte dentro o fuera del territorio de la República. 22. A la paz, a la tranquilidad, al disfrute del tiempo libre y al descanso, así como a gozar de un ambiente equilibrado y adecuado al desarrollo de su vida. 23. A la legítima defensa. 24. A la libertad y a la seguridad personales. En consecuencia: 25. Nadie está obligado a hacer lo que la ley no manda, ni impedido de hacer lo que ella no prohibe. 26. No se permite forma alguna de restricción de la libertad personal, salvo en los casos previstos por la ley. Están prohibidas la esclavitud, la servidumbre y la trata de seres humanos en cualquiera de sus formas. 27. No hay prisión por deudas. Este principio no limita el mandato judicial por incumplimiento de deberes alimentarios. 28. Nadie será procesado ni condenado por acto u omisión que al tiempo de cometerse no esté previamente calificado en la ley, de manera expresa e inequívoca, como infracción punible; ni sancionado con pena no prevista en la ley. 29. Toda persona es considerada inocente mientras no se haya declarado judicialmente su responsabilidad. 30. Nadie puede ser detenido sino por mandamiento escrito y motivado del juez o por las autoridades policiales en caso de flagrante delito. El detenido debe ser puesto a disposición del juzgado correspondiente, dentro de las veinticuatro horas o en el término de la distancia. Estos plazos no se aplican a los casos de terrorismo, espionaje y tráfico ilícito de drogas. En tales casos, las autoridades policiales pueden efectuar la detención preventiva de los presuntos implicados por un término no mayor de quince días naturales. Deben dar cuenta al Ministerio Público y al juez, quien puede asumir jurisdicción antes de vencido dicho término. 31. Nadie puede ser incomunicado sino en caso indispensable para el esclarecimiento de un delito, y en la forma y por el tiempo previstos por la ley. La autoridad está obligada bajo responsabilidad a señalar, sin dilación y por escrito, el lugar donde se halla la persona detenida. 32. Nadie debe ser víctima de violencia moral, psíquica o física ni sometido a tortura o a tratos inhumanos o humillantes. Cualquiera puede pedir de inmediato el examen médico de la persona agraviada o de aquélla imposibilitada de recurrir por sí misma a la autoridad. Carecen de valor las declaraciones obtenidas por la violencia. Quien la emplea incurre en responsabilidad.

**Anclado (Agente A + Agente B)**

> El Artículo 2 establece que toda persona tiene derecho a la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar.

<details><summary>Candidatos que recibió el LLM</summary>

1. `Artículo 2` (score 1.0; key 1.0, lexical 0.6455) — Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la ig
2. `Artículo 96` (score 0.5851; semantic 0.5332, lexical 0.3227) — Artículo 96: Cualquier representante a Congreso puede pedir a los Ministros de Estado, al Jurado Nacional de Elecciones, al Contralor General, al Banco Central de Reserva, a la Superintendencia de Banca y Seguros, a los 
3. `Artículo 200` (score 0.3784; text 1.0) — Artículo 200: Son garantías constitucionales: 1. La Acción de Hábeas Corpus, que procede ante el hecho u omisión, por parte de cualquier autoridad, funcionario o persona que vulnera o amenaza la libertad individual o los
4. `Artículo 33` (score 0.3723; text 0.9027) — Artículo 33: El ejercicio de la ciudadanía se suspende: 1. Por resolución judicial de interdicción. 2. Por sentencia con pena privativa de la libertad. 3. Por sentencia con inhabilitación de los derechos políticos.

</details>

### Turno 4: «dame más explicación»

- Reescrito para buscar: «¿Qué dice el Artículo 2?» (la pregunta sola no tenía tema)
- Predictores que propusieron: key×1, lexical×5, semantic×5, text×5
- Motor: `llm`, cobertura léxica 0.76, detalle: amplio
- Latencia: Exacto 11 ms · Anclado 16285 ms

**Exacto (solo Agente A)**

> Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la igualdad ante la ley. Nadie debe ser discriminado por motivo de origen, raza, sexo, idioma, religión, opinión, condición económica o de cualquiera otra índole. 3. A la libertad de conciencia y de religión, en forma individual o asociada. No hay persecución por razón de ideas o creencias. No hay delito de opinión. El ejercicio público de todas las confesiones es libre, siempre que no ofenda la moral ni altere el orden público. 4. A las libertades de información, opinión, expresión y difusión del pensamiento mediante la palabra oral o escrita o la imagen, por cualquier medio de comunicación social, sin previa autorización ni censura ni impedimento algunos, bajo las responsabilidades de ley.Los delitos cometidos por medio del libro, la prensa y demás medios de comunicación social se tipifican en el Código Penal y se juzgan en el fuero común.Es delito toda acción que suspende o clausura algún órgano de expresión o le impide circular libremente. Los derechos de informar y opinar comprenden los de fundar medios de comunicación. 5. A solicitar sin expresión de causa la información que requiera y a recibirla de cualquier entidad pública, en el plazo legal, con el costo que suponga el pedido. Se exceptúan las informaciones que afectan la intimidad personal y las que expresamente se excluyan por ley o por razones de seguridad nacional.El secreto bancario y la reserva tributaria pueden levantarse a pedido del juez, del Fiscal de la Nación, o de una comisión investigadora del Congreso con arreglo a ley y siempre que se refieran al caso investigado. 6. A que los servicios informáticos, computarizados o no, públicos o privados, no suministren informaciones que afecten la intimidad personal y familiar. 7. Al honor y a la buena reputación, a la intimidad personal y familiar así como a la voz y a la imagen propias.Toda persona afectada por afirmaciones inexactas o agraviada en cualquier medio de comunicación social tiene derecho a que éste se rectifique en forma gratuita, inmediata y proporcional, sin perjuicio de las responsabilidades de ley. 8. A la libertad de creación intelectual, artística, técnica y científica, así como a la propiedad sobre dichas creaciones y a su producto. El Estado propicia el acceso a la cultura y fomenta su desarrollo y difusión. 9. A la inviolabilidad del domicilio. Nadie puede ingresar en él ni efectuar investigaciones o registros sin autorización de la persona que lo habita o sin mandato judicial, salvo flagrante delito o muy grave peligro de su perpetración. Las excepciones por motivos de sanidad o de grave riesgo son reguladas por la ley. 10. Al secreto y a la inviolabilidad de sus comunicaciones y documentos privados. Las comunicaciones, telecomunicaciones o sus instrumentos sólo pueden ser abiertos, incautados, interceptados o intervenidos por mandamiento motivado del juez, con las garantías previstas en la ley. Se guarda secreto de los asuntos ajenos al hecho que motiva su examen. Los documentos privados obtenidos con violación de este precepto no tienen efecto legal. Los libros, comprobantes y documentos contables y administrativos están sujetos a inspección o fiscalización de la autoridad competente, de conformidad con la ley. Las acciones que al respecto se tomen no pueden incluir su sustracción o incautación, salvo por orden judicial. 11. A elegir su lugar de residencia, a transitar por el territorio nacional y a salir de él y entrar en él, salvo limitaciones por razones de sanidad o por mandato judicial o por aplicación de la ley de extranjería. 12. A reunirse pacíficamente sin armas. Las reuniones en locales privados o abiertos al público no requieren aviso previo. Las que se convocan en plazas y vías públicas exigen anuncio anticipado a la autoridad, la que puede prohibirlas solamente por motivos probados de seguridad o de sanidad públicas. 13. A asociarse y a constituir fundaciones y diversas formas de organización jurídica sin fines de lucro, sin autorización previa y con arreglo a ley. No pueden ser disueltas por resolución administrativa. 14. A contratar con fines lícitos, siempre que no se contravengan leyes de orden público. 15. A trabajar libremente, con sujeción a ley. 16. A la propiedad y a la herencia. 17. A participar, en forma individual o asociada, en la vida política, económica, social y cultural de la Nación. Los ciudadanos tienen, conforme a ley, los derechos de elección, de remoción o revocación de autoridades, de iniciativa legislativa y de referéndum. 18. A mantener reserva sobre sus convicciones políticas, filosóficas, religiosas o de cualquiera otra índole, así como a guardar el secreto profesional. 19. A su identidad étnica y cultural. El Estado reconoce y protege la pluralidad étnica y cultural de la Nación. Todo peruano tiene derecho a usar su propio idioma ante cualquier autoridad mediante un intérprete. Los extranjeros tienen este mismo derecho cuando son citados por cualquier autoridad. 20. A formular peticiones, individual o colectivamente, por escrito ante la autoridad competente, la que está obligada a dar al interesado una respuesta también por escrito dentro del plazo legal, bajo responsabilidad. Los miembros de las Fuerzas Armadas y de la Policía Nacional sólo pueden ejercer individualmente el derecho de petición. 21. A su nacionalidad. Nadie puede ser despojado de ella. Tampoco puede ser privado del derecho de obtener o de renovar su pasaporte dentro o fuera del territorio de la República. 22. A la paz, a la tranquilidad, al disfrute del tiempo libre y al descanso, así como a gozar de un ambiente equilibrado y adecuado al desarrollo de su vida. 23. A la legítima defensa. 24. A la libertad y a la seguridad personales. En consecuencia: 25. Nadie está obligado a hacer lo que la ley no manda, ni impedido de hacer lo que ella no prohibe. 26. No se permite forma alguna de restricción de la libertad personal, salvo en los casos previstos por la ley. Están prohibidas la esclavitud, la servidumbre y la trata de seres humanos en cualquiera de sus formas. 27. No hay prisión por deudas. Este principio no limita el mandato judicial por incumplimiento de deberes alimentarios. 28. Nadie será procesado ni condenado por acto u omisión que al tiempo de cometerse no esté previamente calificado en la ley, de manera expresa e inequívoca, como infracción punible; ni sancionado con pena no prevista en la ley. 29. Toda persona es considerada inocente mientras no se haya declarado judicialmente su responsabilidad. 30. Nadie puede ser detenido sino por mandamiento escrito y motivado del juez o por las autoridades policiales en caso de flagrante delito. El detenido debe ser puesto a disposición del juzgado correspondiente, dentro de las veinticuatro horas o en el término de la distancia. Estos plazos no se aplican a los casos de terrorismo, espionaje y tráfico ilícito de drogas. En tales casos, las autoridades policiales pueden efectuar la detención preventiva de los presuntos implicados por un término no mayor de quince días naturales. Deben dar cuenta al Ministerio Público y al juez, quien puede asumir jurisdicción antes de vencido dicho término. 31. Nadie puede ser incomunicado sino en caso indispensable para el esclarecimiento de un delito, y en la forma y por el tiempo previstos por la ley. La autoridad está obligada bajo responsabilidad a señalar, sin dilación y por escrito, el lugar donde se halla la persona detenida. 32. Nadie debe ser víctima de violencia moral, psíquica o física ni sometido a tortura o a tratos inhumanos o humillantes. Cualquiera puede pedir de inmediato el examen médico de la persona agraviada o de aquélla imposibilitada de recurrir por sí misma a la autoridad. Carecen de valor las declaraciones obtenidas por la violencia. Quien la emplea incurre en responsabilidad.

**Anclado (Agente A + Agente B)**

> No hay más detalle en las fuentes disponibles. Esto es lo que recogen: Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la igualdad ante la ley. Nadie debe ser discriminado por motivo de origen, raza, sexo, idioma, religión, opinión, condición económica o de cualquiera otra índole. 3. A la libertad de conciencia y de religión, en forma individual o asociada. No hay persecución por razón de ideas o creencias. No hay delito de opinión. El ejercicio público de todas las confesiones es libre, siempre que no ofenda la moral ni altere el orden público. Cualquiera puede pedir de inmediato el examen médico de la persona agraviada o de aquélla imposibilitada de recurrir por sí misma a la autoridad. Carecen de valor las declaraciones obtenidas por la violencia. Quien la emplea incurre en responsabilidad.

<details><summary>Candidatos que recibió el LLM</summary>

1. `Artículo 2` (score 1.0; key 1.0, lexical 0.6455) — Artículo 2: Toda persona tiene derecho: 1. A la vida, a su identidad, a su integridad moral, psíquica y física y a su libre desarrollo y bienestar. El concebido es sujeto de derecho en todo cuanto le favorece. 2. A la ig
2. `Artículo 96` (score 0.5851; semantic 0.5332, lexical 0.3227) — Artículo 96: Cualquier representante a Congreso puede pedir a los Ministros de Estado, al Jurado Nacional de Elecciones, al Contralor General, al Banco Central de Reserva, a la Superintendencia de Banca y Seguros, a los 
3. `Artículo 200` (score 0.3784; text 1.0) — Artículo 200: Son garantías constitucionales: 1. La Acción de Hábeas Corpus, que procede ante el hecho u omisión, por parte de cualquier autoridad, funcionario o persona que vulnera o amenaza la libertad individual o los
4. `Artículo 33` (score 0.3723; text 0.9027) — Artículo 33: El ejercicio de la ciudadanía se suspende: 1. Por resolución judicial de interdicción. 2. Por sentencia con pena privativa de la libertad. 3. Por sentencia con inhabilitación de los derechos políticos.

</details>

