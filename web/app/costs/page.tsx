import { get, list } from "@/lib/store";
import { estimate } from "@/lib/cost";
import { saveBudget } from "../actions";
export const dynamic = "force-dynamic";
export default async function Costs() {
  const b = (await get("settings", "budget")) || { daily_usd: 1, monthly_usd: 10, allow_paid: false };
  const ledger = (await list("cost_ledger")).sort((x, y) => (y.ts || 0) - (x.ts || 0));
  const now = Date.now() / 1000;
  const day = ledger.filter((e) => now - (e.ts || 0) < 86400).reduce((a, e) => a + (e.usd || 0), 0);
  const month = ledger.filter((e) => now - (e.ts || 0) < 30 * 86400).reduce((a, e) => a + (e.usd || 0), 0);
  const modes = ["economic", "advanced", "cinematic"].map((m) => estimate(m, { llm: !!process.env.ANTHROPIC_API_KEY }));
  return (
    <>
      <h1>Maliyet kontrolü</h1>
      <div className="grid">
        <div className="tile"><div className="big">${day.toFixed(2)}</div><div className="muted">Bugün / ${b.daily_usd}</div></div>
        <div className="tile"><div className="big">${month.toFixed(2)}</div><div className="muted">Bu ay / ${b.monthly_usd}</div></div>
      </div>
      <form action={saveBudget} className="card">
        <h3>Limitler</h3>
        <div className="two">
          <div><label>Günlük limit ($)</label><input name="daily" type="number" step="0.5" defaultValue={b.daily_usd} /></div>
          <div><label>Aylık limit ($)</label><input name="monthly" type="number" step="1" defaultValue={b.monthly_usd} /></div>
        </div>
        <p><input type="checkbox" name="allow_paid" defaultChecked={b.allow_paid} /> Ücretli servislere (Claude API, ElevenLabs, RunPod GPU) izin ver</p>
        <p className="muted">Kapalıyken yalnızca ücretsiz yol kullanılır: GitHub Actions CPU render, Piper TTS, şablon senaryo, prosedürel müzik.</p>
        <button className="btn">Kaydet</button>
      </form>
      <h2>Mod başına tahmin (30 sn)</h2>
      {modes.map((m) => (
        <div key={m.mode} className="card"><div className="row between"><b>{m.mode}</b><b>${m.total}</b></div>
          {m.items.map((i) => <div key={i.item} className="muted">{i.item}: {i.free ? "ücretsiz" : `$${i.usd}`}</div>)}</div>
      ))}
      <h2>Harcama kaydı</h2>
      <table><tbody>{ledger.slice(0, 50).map((e) => <tr key={e.id}><td>{new Date((e.ts || 0) * 1000).toLocaleString("tr-TR")}</td><td>{e.item}</td><td>${e.usd}</td></tr>)}</tbody></table>
      {ledger.length === 0 && <p className="muted">Henüz ücretli harcama yok.</p>}
    </>
  );
}
