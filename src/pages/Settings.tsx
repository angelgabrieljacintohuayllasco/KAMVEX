import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { detectHardware, HwInfo } from "../api/client";

export default function Settings() {
  const [hw, setHw] = useState<HwInfo | null>(null);
  const [port, setPort] = useState<number | null>(null);
  const [ready, setReady] = useState<boolean>(false);

  useEffect(() => {
    detectHardware().then(setHw).catch(() => {});
    invoke<number>("sidecar_port").then(setPort).catch(() => {});
    invoke<boolean>("sidecar_ready").then(setReady).catch(() => {});
  }, []);

  const Row = ({ k, v }: { k: string; v: string }) => (
    <div className="flex justify-between border-b border-white/5 py-2 text-sm">
      <span className="text-white/50">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-semibold mb-4">Settings</h1>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <h2 className="font-medium mb-2">Backend (sidecar)</h2>
        <Row k="Puerto" v={port ? String(port) : "…"} />
        <Row k="Estado" v={ready ? "activo ✓" : "iniciando…"} />
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h2 className="font-medium mb-2">Hardware</h2>
        {hw ? (
          <>
            <Row k="CPU" v={hw.cpu_brand || "—"} />
            <Row k="Núcleos físicos" v={String(hw.physical_cores)} />
            <Row k="Hilos lógicos" v={String(hw.logical_cores)} />
            <Row k="RAM total" v={`${hw.total_ram_gb.toFixed(1)} GB`} />
            <Row k="RAM disponible" v={`${hw.available_ram_gb.toFixed(1)} GB`} />
          </>
        ) : (
          <p className="text-white/40 text-sm">Detectando…</p>
        )}
        <p className="text-xs text-white/30 mt-3">
          La auto-configuración por hardware (recomendar modelo + perfil + flags)
          llega en el siguiente slice.
        </p>
      </section>
    </div>
  );
}
