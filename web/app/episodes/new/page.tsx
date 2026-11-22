import { list } from "@/lib/store";
import { estimate } from "@/lib/cost";
import { createEpisode } from "../../actions";
export const dynamic = "force-dynamic";
export default async function NewEpisode({ searchParams }: { searchParams: Promise<{ series?: string; mode?: string }> }) {
  const sp = await searchParams;
  const series = await list("series");
  const mode = sp.mode || "economic";
  const llm = !!process.env.ANTHROPIC_API_KEY;
  const est = estimate(mode, { llm });
  return (
    <>
      <h1>Bölüm üretimi</h1>
      <form action={createEpisode} className="card">
        <label>Dizi</label>
        <select name="series_id" defaultValue={sp.series || series[0]?.id}>{series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}</select>
        <label>Bölüm konusu</label>
        <textarea name="topic" required placeholder="ör. Ada fenerin bodrumunda eski bir harita bulur" />
        <label>Üretim modu</label>
        <div className="row">
          {[["economic", "1 · Ekonomik 2D"], ["advanced", "2 · Gelişmiş 2D"], ["cinematic", "3 · Sinematik GPU"]].map(([m, l]) => (
            <a key={m} className={`btn small ${m === mode ? "" : "secondary"}`} href={`?mode=${m}${sp.series ? `&series=${sp.series}` : ""}`}>{l}</a>
          ))}
        </div>
        <input type="hidden" name="mode" value={mode} />
        <h3>Tahmini maliyet</h3>
        <table><tbody>{est.items.map((i) => <tr key={i.item}><td>{i.item}</td><td className="muted">{i.qty}</td><td>{i.free ? "ücretsiz" : `$${i.usd}`}</td></tr>)}
          <tr><td><b>Toplam</b></td><td /><td><b>${est.total}</b></td></tr></tbody></table>
        {!llm && <p className="muted">ANTHROPIC_API_KEY tanımlı değil: senaryo ücretsiz şablon yazarıyla üretilir (basit). Claude bağlanınca dizi hafızasını okuyan tam senaryo yazımı açılır.</p>}
        {mode === "cinematic" && <p className="muted">⚠ Sinematik mod RunPod GPU kullanır ve ücretlidir; Maliyet Kontrolü’nde ücretli işlemlere izin verilmeden başlamaz.</p>}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn secondary" name="action" value="preview">📝 Senaryo + storyboard önizle</button>
          <button className="btn" name="action" value="full">🎬 Tam üret</button>
        </div>
        <p className="muted">Üretim bulut worker’ında yapılır; telefonu kapatsanız da devam eder.</p>
      </form>
    </>
  );
}
