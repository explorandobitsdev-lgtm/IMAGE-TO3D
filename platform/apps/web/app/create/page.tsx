"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Api } from "@/lib/api";

const Viewer = dynamic(() => import("@/components/Viewer"), { ssr: false });

type Mode = "image_to_3d" | "text_to_3d" | "palmilha";

export default function CreatePage() {
  const [mode, setMode] = useState<Mode>("image_to_3d");
  const [token, setToken] = useState<string | null>(null);
  const [credits, setCredits] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<string>("idle");
  const [meshUrl, setMeshUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = localStorage.getItem("token");
    if (t) {
      setToken(t);
      Api.me().then((m) => setCredits(m.credits)).catch(() => {
        localStorage.removeItem("token");
        setToken(null);
      });
    }
  }, []);

  async function quickRegister() {
    const email = prompt("E-mail (será criado se não existir):") || "";
    const password = prompt("Senha:") || "";
    if (!email || !password) return;
    try {
      const r = await Api.register(email, password).catch(() => Api.login(email, password));
      localStorage.setItem("token", r.access_token);
      setToken(r.access_token);
      setCredits(r.credits);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setMeshUrl(null);
    setProgress(0);
    setStatus("uploading");

    const fd = new FormData(e.currentTarget);
    let input: any = {};

    try {
      if (mode === "image_to_3d" || mode === "palmilha") {
        const file = (fileRef.current?.files || [])[0];
        if (!file) throw new Error("selecione uma imagem");
        const presign = await Api.presign(file.type || "image/png");
        await fetch(presign.upload_url, {
          method: "PUT",
          headers: { "Content-Type": file.type || "image/png" },
          body: file,
        });
        input.image_url = presign.public_url;
        if (mode === "palmilha") {
          input.num = Number(fd.get("num"));
          input.lado = fd.get("lado");
        }
      } else if (mode === "text_to_3d") {
        input.prompt = String(fd.get("prompt") || "").trim();
        if (!input.prompt) throw new Error("informe um prompt");
      }

      setStatus("queuing");
      const model = mode === "image_to_3d" ? "triposr" : null;
      const job = await Api.createJob(mode, model, input);
      setJobId(job.id);
      setStatus("running");

      const es = Api.streamJob(job.id, async (ev) => {
        if (typeof ev.progress === "number") setProgress(ev.progress);
        if (ev.done) {
          es.close();
          if (ev.ok) {
            setStatus("succeeded");
            const j = await Api.getJob(job.id);
            const obj = j.assets.find((a: any) => a.kind === "mesh_obj");
            if (obj) setMeshUrl(obj.url);
            const me = await Api.me();
            setCredits(me.credits);
          } else {
            setStatus("failed");
            setError(ev.error || "geração falhou");
          }
        }
      });
    } catch (e: any) {
      setError(e.message);
      setStatus("failed");
    }
  }

  return (
    <main className="container" style={{ paddingTop: "3rem", paddingBottom: "5rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0 }}>Criar 3D</h1>
        <div style={{ color: "var(--muted)", fontSize: 14 }}>
          {token ? `créditos: ${credits ?? "…"}` : (
            <button className="btn btn-ghost" onClick={quickRegister}>Entrar / criar conta</button>
          )}
        </div>
      </header>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {([
          ["image_to_3d", "🖼️ Image → 3D"],
          ["text_to_3d", "💬 Text → 3D"],
          ["palmilha", "👣 Palmilha"],
        ] as [Mode, string][]).map(([m, label]) => (
          <button
            key={m}
            className={mode === m ? "btn" : "btn btn-ghost"}
            onClick={() => setMode(m)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <div className="form-wrap">
        <form className="panel" onSubmit={submit} style={{ display: "grid", gap: "0.9rem" }}>
          {mode === "text_to_3d" && (
            <label>Prompt
              <textarea name="prompt" rows={4} required placeholder="a small cyberpunk owl statue, glossy ceramic, dramatic lighting" />
            </label>
          )}

          {(mode === "image_to_3d" || mode === "palmilha") && (
            <label>Imagem
              <input ref={fileRef} type="file" name="image" accept="image/*" required />
            </label>
          )}

          {mode === "palmilha" && (
            <>
              <label>Numeração (EUR)
                <input type="number" name="num" defaultValue={41} min={28} max={50} required />
              </label>
              <label>Lado
                <select name="lado" defaultValue="auto">
                  <option value="auto">Detectar</option>
                  <option value="direito">Direito</option>
                  <option value="esquerdo">Esquerdo</option>
                </select>
              </label>
            </>
          )}

          <button className="btn" type="submit" disabled={!token || status === "running" || status === "queuing"}>
            {status === "running" ? `Gerando… ${progress}%` : "Gerar"}
          </button>

          {!token && <small style={{ color: "var(--muted)" }}>É preciso entrar antes de gerar.</small>}
          {error && <small style={{ color: "#f87171" }}>{error}</small>}

          {status === "running" && (
            <div className="progress"><span style={{ width: `${progress}%` }} /></div>
          )}
        </form>

        <Viewer url={meshUrl ?? undefined} />
      </div>
    </main>
  );
}
