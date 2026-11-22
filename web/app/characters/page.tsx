import Link from "next/link";
import { list, fileUrl } from "@/lib/store";
export const dynamic = "force-dynamic";
export default async function Characters() {
  const chars = await list("characters");
  const imgs = await Promise.all(chars.map((c) => fileUrl(c.reference_images?.model_sheet_key)));
  return (
    <>
      <div className="row between"><h1>Karakter stüdyosu</h1><Link className="btn" href="/characters/new">+ Yeni</Link></div>
      <p className="muted">Her karakter kalıcı bir Character ID taşır. Onaylanan tasarım ve ses profili tüm bölümlerde yeniden kullanılır; sıfırdan üretilmez.</p>
      {chars.map((c, i) => (
        <Link key={c.id} href={`/characters/${c.id}`} className="card" style={{ display: "block" }}>
          <div className="row between"><b>{c.name}</b>
            <span className={`badge ${c.approved ? "ready" : "queued"}`}>{c.approved ? "Onaylı" : "Onay bekliyor"}</span></div>
          <div className="muted">{c.id} · v{c.version} · tasarım #{c.design_hash} · ses #{c.voice_hash}</div>
          {imgs[i] && <img className="media" src={imgs[i]!} alt="" style={{ marginTop: 8, background: "#f4efe6" }} />}
        </Link>
      ))}
    </>
  );
}
