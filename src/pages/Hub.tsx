import { Dataset } from "../api/client";

export default function Hub({ datasets }: { datasets: Dataset[] }) {
  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">Hub</h1>
      <p className="text-sm text-white/40 mb-6">
        Modelos y fuentes que KAMVEX puede usar.
      </p>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-medium">Modelos locales</h2>
          <span className="rounded-full bg-amber-500/10 border border-amber-500/40 px-2 py-0.5 text-xs text-amber-300">
            próximamente
          </span>
        </div>
        <p className="text-sm text-white/50">
          El motor de inferencia llega en el siguiente slice: gestión de modelos
          GGUF (MoE), BitNet ternario y RWKV/Mamba, con Vulkan→iGPU, KV-cache quant
          y speculative decoding — todo configurable por hardware.
        </p>
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h2 className="font-medium mb-3">Fuentes de conocimiento (DASA)</h2>
        {datasets.length === 0 ? (
          <p className="text-sm text-white/40">
            Aún no hay fuentes. Crea una en <b>Knowledge</b>.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {datasets.map((d) => (
              <li
                key={d.name}
                className="rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm flex justify-between"
              >
                <span className="font-medium">{d.name}</span>
                <span className="text-white/50">
                  {d.n_records} registros · {d.profile}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
