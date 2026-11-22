import Link from "next/link";
import { list, fileUrl } from "@/lib/store";
import Badge from "@/components/Badge";
import AutoRefresh from "@/components/AutoRefresh";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [series, episodes, jobs, ledger, chars] = await Promise.all([list("series"), list("episodes"), list("jobs"),
    list("cost_ledger"), list("characters")]);
  const recent = [...episodes].sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0)).slice(0, 6);
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const month = ledger.filter((e) => Date.now() / 1000 - (e.ts || 0) < 30 * 86400).reduce((a, e) => a + (e.usd || 0), 0);
  const thumbs = await Promise.all(recent.map((e) => fileUrl(e.outputs?.thumbnail_key)));
  return (
    <>
      <AutoRefresh active={active.length > 0} ms={8000} />
      <div className="grid">
        <Link href="/episodes/new" className="tile"><div className="big">🎬</div><b>Yeni bölüm</b><div className="muted">Konu yaz, gerisi bulutta</div></Link>
        <Link href="/queue" className="tile"><div className="big">{active.length}</div><b>Aktif iş</b><div className="muted">Render kuyruğu</div></Link>
        <Link href="/characters" className="tile"><div className="big">{chars.length}</div><b>Karakter</b><div className="muted">Kalıcı Character ID</div></Link>
        <Link href="/costs" className="tile"><div className="big">${month.toFixed(2)}</div><b>Bu ay</b><div className="muted">Maliyet kontrolü</div></Link>
      </div>
      <h2>Diziler</h2>
      {series.length === 0 && <p className="muted">Henüz dizi yok. <Link href="/series/new">Dizi oluştur →</Link></p>}
      {series.map((s) => (
        <Link key={s.id} href={`/series/${s.id}`} className="card" style={{ display: "block" }}>
          <div className="row between"><b>{s.title}</b><span className="muted">{(s.episodes || []).length} bölüm</span></div>
          <div className="muted">{s.logline}</div>
        </Link>
      ))}
      <h2>Son bölümler</h2>
      <div className="grid">
        {recent.map((e, i) => (
          <Link key={e.id} href={`/episodes/${e.id}`} className="tile">
            {thumbs[i] ? <img className="media" src={thumbs[i]!} alt="" /> : <div className="muted">🎞️</div>}
            <div style={{ marginTop: 6 }}><b>{e.episode_number}. {e.title}</b></div>
            <Badge s={e.status} /> {e.pipeline?.percent != null && e.status !== "ready" && <span className="muted">%{e.pipeline.percent}</span>}
          </Link>
        ))}
      </div>
    </>
  );
}
