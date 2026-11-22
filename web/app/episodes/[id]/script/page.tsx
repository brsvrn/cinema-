import { notFound } from "next/navigation";
import { get, list } from "@/lib/store";
import { POSES, EMOTIONS, CAMERAS } from "@/lib/types";
import { saveScript } from "../../../actions";
export const dynamic = "force-dynamic";

export default async function ScriptEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ep = await get("episodes", id);
  if (!ep) notFound();
  const s = ep.script;
  if (!s) return (<><h1>Senaryo editörü</h1><p className="muted">Senaryo henüz üretilmedi. Bölümü “Senaryo + storyboard önizle” ile başlatın; worker senaryoyu yazınca burada düzenleyebilirsiniz.</p></>);
  const names: Record<string, string> = Object.fromEntries((await list("characters")).map((c) => [c.id, c.name]));
  return (
    <>
      <h1>Senaryo editörü</h1>
      <p className="muted">Replikleri, duyguları, hareketleri ve kamera açılarını düzenleyin. “Kaydet ve render et” yalnızca değişen aşamaları yeniden üretir; karakterler ve mekân onaylı modellerden gelir.</p>
      <form action={saveScript}>
        <input type="hidden" name="id" value={id} />
        <label>Bölüm başlığı</label><input name="title" defaultValue={s.title} />
        <p className="muted">Işık: {s.lighting} · müzik: {s.music_mood} · mekân: {s.location_id}</p>
        {s.beats.map((b: any, i: number) => b.type === "line" ? (
          <div key={i} className="beat">
            <div className="row between"><b>{names[b.speaker] || b.speaker}</b><span className="muted">#{i}</span></div>
            <label>Replik (TR)</label><textarea name={`text_${i}`} defaultValue={b.text} />
            <label>Altyazı (EN)</label><input name={`text_en_${i}`} defaultValue={b.text_en} />
            <div className="two">
              <div><label>Duygu / mimik</label><select name={`emotion_${i}`} defaultValue={b.emotion}>{EMOTIONS.map((e) => <option key={e}>{e}</option>)}</select></div>
              <div><label>Hareket</label><select name={`action_${i}`} defaultValue={b.action || ""}><option value="">otomatik</option>{POSES.map((p) => <option key={p}>{p}</option>)}</select></div>
              <div><label>Kamera</label><select name={`camera_${i}`} defaultValue={b.camera || ""}>{CAMERAS.map((c) => <option key={c} value={c}>{c || "otomatik"}</option>)}</select></div>
              <div><label>&nbsp;</label><span><input type="checkbox" name={`delete_${i}`} /> sil</span></div>
            </div>
          </div>
        ) : (
          <div key={i} className="beat action">
            <div className="row between"><span>🎬 {b.description || "aksiyon"}</span><span className="muted">#{i} · {b.duration}s</span></div>
            <div className="muted">{b.camera ? `kamera: ${b.camera}` : ""} {b.events ? `olay: ${JSON.stringify(b.events)}` : ""}</div>
            <input type="hidden" name={`camera_${i}`} value={b.camera || ""} />
          </div>
        ))}
        <div className="row" style={{ position: "sticky", bottom: 80, background: "var(--bg)", padding: "10px 0" }}>
          <button className="btn secondary" name="action" value="save">Kaydet</button>
          <button className="btn" name="action" value="render">Kaydet ve render et</button>
        </div>
      </form>
    </>
  );
}
