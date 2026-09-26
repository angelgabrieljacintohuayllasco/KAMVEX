/**
 * Lo que se le ensena a la persona cuando algo falla.
 *
 * Un "TypeError: Failed to fetch" en rojo no dice nada y hace pensar que la aplicacion
 * esta rota. Un "[object Object]" es peor todavia. El sidecar ya devuelve un mensaje
 * accionable en `detail`; aqui solo se garantiza que llegue entero a la pantalla y que,
 * cuando no lo haya, se diga algo util igualmente.
 */

const GENERICO =
  "Algo fallo y la operacion no se completo. Vuelve a intentarlo; si se repite, mira el registro en Ajustes.";

/** Un texto que la persona pueda leer, siempre. Nunca un objeto ni un error de red crudo. */
export function errorMessage(e: unknown): string {
  if (typeof e === "string") return e.trim() || GENERICO;
  if (e instanceof Error) {
    const m = (e.message ?? "").trim();
    if (!m) return GENERICO;
    // Lo que lanza fetch cuando no hay respuesta: el sidecar aun arranca, o se cayo.
    if (/failed to fetch|networkerror|load failed/i.test(m)) {
      return (
        "El motor local de KAMVEX no responde. Espera unos segundos a que termine de " +
        "arrancar; si sigue igual, cierra y vuelve a abrir la aplicacion."
      );
    }
    return m;
  }
  const texto = String(e ?? "").trim();
  return texto && texto !== "[object Object]" ? texto : GENERICO;
}

/** El mismo mensaje con un prefijo de contexto, para no perder que estaba pasando. */
export function errorMessageWith(prefix: string, e: unknown): string {
  const m = errorMessage(e);
  return prefix.trim() ? `${prefix.trim()} ${m}` : m;
}
