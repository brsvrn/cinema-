import { get, list, fileUrl } from "@/lib/store";
import { saveCharacter, approveCharacter } from "../../actions";
import AutoRefresh from "@/components/AutoRefresh";
export const dynamic = "force-dynamic";

const TEMPLATES: Record<string, any> = {
  child: { height: 0.66, head_ratio: 0.3, build: 0.95, skin: "#f3c9a2", eye_color: "#2f9c63", brow_color: "#8a2f1b",
    hair: { style: "curly_bob", color: "#3b2a20" }, outfit: { top: "raincoat", top_color: "#3a8fd8", bottom: "shorts", bottom_color: "#2f2f3a", shoes: "#c94a3a" } },
  elder: { height: 1.0, head_ratio: 0.21, build: 1.15, skin: "#e4b48e", eye_color: "#4a6fa5", brow_color: "#f2f2f2",
    hair: { style: "short_white", color: "#eeeeee" }, outfit: { top: "sweater", top_color: "#7a3b2e", bottom: "pants", bottom_color: "#3b3631", shoes: "#2a1c14" } },
};

export default async function CharacterPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ t?: string }> }) {
  const { id } = await params;
  const sp = await searchParams;
  const isNew = id === "new";
  const c: any = isNew ? { design: TEMPLATES[sp.t || "child"], voice: { engine: "piper", model: "tr_TR-dfki-medium", pitch_semitones: sp.t === "elder" ? -2 : 4, speed: 1, noise_scale: 0.6 } } : await get("characters", id);
  if (!c) return <p>Karakter bulunamadı.</p>;
  const series = await list("series");
  const d = c.design || {};
  const o = d.outfit || {};
  const v = c.voice || {};
  const [sheet, mouth, sample] = await Promise.all([fileUrl(c.reference_images?.model_sheet_key),
    fileUrl(c.reference_images?.mouth_shapes_key), fileUrl(c.reference_images?.voice_sample_key)]);
  const jobs = isNew ? [] : (await list("jobs")).filter((j) => j.data?.character_id === id && ["queued", "running"].includes(j.status));
  return (
    <>
      <AutoRefresh active={jobs.length > 0} />
      <h1>{isNew ? "Yeni karakter" : c.name}</h1>
      {isNew && <p className="row"><a className="btn secondary small" href="?t=child">Çocuk şablonu</a><a className="btn secondary small" href="?t=elder">Yetişkin şablonu</a></p>}
      {!isNew && (
        <div className="card">
          <div className="row between"><span className="muted">{c.id} · v{c.version}</span>
            <span className={`badge ${c.approved ? "ready" : "queued"}`}>{c.approved ? "Onaylı" : "Onay bekliyor"}</span></div>
          {jobs.length > 0 && <p className="muted">⏳ Model sayfası / ses örneği bulutta hazırlanıyor…</p>}
          {sheet && <><h3>Referans: ön, 3/4, yan, arka + mimik kütüphanesi</h3><img className="media" src={sheet} alt="model sheet" style={{ background: "#f4efe6" }} /></>}
          {mouth && <><h3>Ağız şekilleri (dudak senkronu)</h3><img className="media" src={mouth} alt="mouth shapes" style={{ background: "#f4efe6" }} /></>}
          {sample && <><h3>Sabit ses profili örneği</h3><audio controls src={sample} style={{ width: "100%" }} /></>}
          <h3>Kütüphane</h3>
          <div className="muted">İskelet: {(c.library?.skeleton || []).length} kemik · Mimikler: {(c.library?.expressions || []).join(", ")}</div>
          <div className="muted">Hareketler: {(c.library?.motions || []).join(", ")}</div>
          <div className="muted">LoRA: {c.lora ? c.lora.name : "yok (ekonomik 2D motorunda gerekmez; sinematik modda eğitilebilir)"}</div>
          {!c.approved && <form action={approveCharacter}><input type="hidden" name="id" value={c.id} />
            <p><button className="btn">✅ Bu tasarımı ve sesi onayla</button></p></form>}
        </div>
      )}
      <form action={saveCharacter} className="card">
        <input type="hidden" name="id" value={isNew ? "" : c.id} />
        <h2>Kimlik</h2>
        <label>Ad</label><input name="name" defaultValue={c.name} required />
        <label>Dizi</label>
        <select name="series_id" defaultValue={c.series_id || ""}><option value="">—</option>{series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}</select>
        <label>Rol</label><input name="role" defaultValue={c.role} />
        <label>Kişilik</label><textarea name="personality" defaultValue={c.personality} />
        <label>Geçmiş</label><textarea name="backstory" defaultValue={c.backstory} />
        <h2>Karakter tasarımı</h2>
        <div className="two">
          <div><label>Boy (0.5–1.1)</label><input name="height" type="number" step="0.01" defaultValue={d.height} /></div>
          <div><label>Kafa oranı</label><input name="head_ratio" type="number" step="0.01" defaultValue={d.head_ratio} /></div>
          <div><label>Yapı</label><input name="build" type="number" step="0.01" defaultValue={d.build} /></div>
          <div><label>Saç stili</label><select name="hair_style" defaultValue={d.hair?.style}><option>curly_bob</option><option>short_white</option></select></div>
          <div><label>Ten</label><input name="skin" type="color" defaultValue={d.skin} /></div>
          <div><label>Saç rengi</label><input name="hair_color" type="color" defaultValue={d.hair?.color} /></div>
          <div><label>Göz rengi</label><input name="eye_color" type="color" defaultValue={d.eye_color} /></div>
          <div><label>Kaş rengi</label><input name="brow_color" type="color" defaultValue={d.brow_color} /></div>
          <div><label>Üst giysi</label><select name="top" defaultValue={o.top}><option>raincoat</option><option>sweater</option></select></div>
          <div><label>Üst renk</label><input name="top_color" type="color" defaultValue={o.top_color} /></div>
          <div><label>Alt giysi</label><select name="bottom" defaultValue={o.bottom}><option>shorts</option><option>pants</option></select></div>
          <div><label>Alt renk</label><input name="bottom_color" type="color" defaultValue={o.bottom_color} /></div>
          <div><label>Ayakkabı</label><input name="shoes" type="color" defaultValue={o.shoes} /></div>
          <div><label>Sakal rengi</label><input name="beard_color" type="color" defaultValue={d.beard || "#eeeeee"} /></div>
        </div>
        <p className="row"><span><input type="checkbox" name="freckles" defaultChecked={!!d.freckles} /> Çil</span>
          <span><input type="checkbox" name="glasses" defaultChecked={!!d.glasses} /> Gözlük</span>
          <span><input type="checkbox" name="beard" defaultChecked={!!d.beard} /> Sakal</span></p>
        <h2>Karakter sesi</h2>
        <div className="two">
          <div><label>Motor</label><select name="voice_engine" defaultValue={v.engine}><option value="piper">Piper (ücretsiz)</option><option value="elevenlabs">ElevenLabs (ücretli)</option></select></div>
          <div><label>Piper modeli</label><select name="voice_model" defaultValue={v.model}><option>tr_TR-dfki-medium</option><option>en_US-lessac-medium</option><option>en_US-ryan-medium</option><option>en_US-amy-medium</option></select></div>
          <div><label>Perde (yarım ton)</label><input name="pitch" type="number" step="0.5" defaultValue={v.pitch_semitones} /></div>
          <div><label>Hız</label><input name="speed" type="number" step="0.01" defaultValue={v.speed} /></div>
          <div><label>Doğallık (noise)</label><input name="noise" type="number" step="0.01" defaultValue={v.noise_scale} /></div>
          <div><label>ElevenLabs voice id</label><input name="eleven_id" defaultValue={v.elevenlabs_voice_id || ""} /></div>
        </div>
        <label>Ses tarifi</label><input name="voice_desc" defaultValue={v.description} />
        <p className="muted">Kaydetmek yeni bir sürüm oluşturur ve onay gerektirir; onaylı sürüm değişmeden bölümler üretilemez (devamlılık koruması).</p>
        <p><button className="btn">Kaydet ve önizleme üret</button></p>
      </form>
    </>
  );
}
