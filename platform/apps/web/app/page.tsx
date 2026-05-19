import Link from "next/link";

export default function Landing() {
  return (
    <main>
      <section className="container hero">
        <h1>Gere modelos 3D com IA</h1>
        <p>
          Text-to-3D, Image-to-3D e geração de palmilhas corretivas em uma
          plataforma única. Modelos open-source (TripoSR, InstantMesh,
          Shap-E), preview WebGL em tempo real, exportação STL/OBJ/GLB.
        </p>
        <Link href="/create" className="btn">Começar agora</Link>
      </section>

      <section className="container">
        <h2 style={{ textAlign: "center", marginBottom: 0 }}>
          O que você pode criar
        </h2>
        <div className="grid-cards">
          <div className="card">
            <h3>🖼️ Image → 3D</h3>
            <p>Foto única vira mesh detalhado via TripoSR / InstantMesh. PBR opcional.</p>
          </div>
          <div className="card">
            <h3>💬 Text → 3D</h3>
            <p>Descreva o que quer; LLM aprimora o prompt e Shap-E / Stable-Fast-3D gera.</p>
          </div>
          <div className="card">
            <h3>👣 Palmilha corretiva</h3>
            <p>Foto da pisada → análise (pronado/normal/cavo) → STL pronto pra impressão.</p>
          </div>
          <div className="card">
            <h3>🎨 Marketplace</h3>
            <p>Publique seus assets, venda com licenças configuráveis. Stripe integrado.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
