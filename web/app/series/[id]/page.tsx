import Link from "next/link";
import { notFound } from "next/navigation";
import { get, list } from "@/lib/store";
import Badge from "@/components/Badge";
import { updateBible } from "../../actions";
export const dynamic = "force-dynamic";

export default async function SeriesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await get("series", id);
  if (!s) notFound();
  const [eps, chars] = await Promise.all([list("episodes", { series_id: id }), list("characters")]);
  const cast = chars.filter((c) => (s.characters || []).includes(c.id));
  const name = (cid: string) => cast.find((c) => c.id === cid)?.name || cid;
  eps.sort((a, b) => a.episode_number - b.episode_number);
  return (
    <>
      <h1>{s.title}</h1>
      <p className="muted">{s.logline}</p>
      <div className="row"><Link className="btn" href={`/episodes/new?series=${id}`}>+ Yeni bölüm</Link></div>
      <h2>Bölümler</h2>
      {eps.map((e) => (
        <Link key={e.id} href={`/episodes/${e.id}`} className="card row between" style={{ display: "flex" }}>
          <span><b>{e.episode_number}.</b> {e.title}</span><Badge s={e.status} />
        </Link>
      ))}
      <h2>🧠 Dizi hafızası (Series Bible)</h2>
      <div className="card">
        <h3>Kadro</h3>
        {cast.map((c) => <div key={c.id}><Link href={`/characters/${c.id}`}><b>{c.name}</b></Link> <span className="muted">{c.id} · {c.personality}</span></div>)}
        <h3>İlişkiler</h3>
        {(s.relationships || []).map((r: any, i: number) => <div key={i}>{name(r.a)} ↔ {name(r.b)}: <b>{r.type}</b> <span className="muted">{r.notes}</span></div>)}
        <h3>Bölüm özetleri</h3>
        {(s.episodes || []).map((e: any) => <p key={e.number}><b>{e.number}. {e.title}</b> — {e.summary}</p>)}
        <h3>Zaman çizelgesi</h3>
        {(s.timeline || []).map((t: any) => <div key={t.episode} className="muted">Bölüm {t.episode}: gün {t.day}, {t.time}</div>)}
        <h3>Yaşanmış olaylar</h3>
        <ul>{(s.events || []).map((e: any, i: number) => <li key={i}><span className="muted">B{e.episode}</span> {e.text}</li>)}</ul>
        <h3>Çözülmemiş hikâyeler</h3>
        <ul>{(s.threads || []).filter((t: any) => !t.resolved_in).map((t: any) => <li key={t.id}>{t.text} <span className="muted">(B{t.opened_in})</span></li>)}</ul>
        <h3>Çözülen hikâyeler</h3>
        <ul>{(s.threads || []).filter((t: any) => t.resolved_in).map((t: any) => <li key={t.id} className="muted">{t.text} (B{t.opened_in} → B{t.resolved_in})</li>)}</ul>
        <h3>Kim neyi biliyor?</h3>
        <table><tbody>{(s.facts || []).map((f: any) => (
          <tr key={f.id}><td>{f.text}</td><td className="muted">{(f.known_by || []).map(name).join(", ")}</td><td className="muted">B{f.episode}</td></tr>
        ))}</tbody></table>
        <h3>Mekânlar</h3>
        <div className="muted">{(s.locations || []).join(", ")}</div>
      </div>
      <h2>Hafızayı düzenle</h2>
      <form action={updateBible} className="card">
        <input type="hidden" name="id" value={id} />
        <label>Evren kuralları</label><textarea name="rules" defaultValue={(s.universe_rules || []).join("\n")} />
        <label>Gelecek bölüm planları</label><textarea name="plans" defaultValue={(s.future_plans || []).join("\n")} />
        <label>Yeni bilgi (fact) ekle</label><input name="new_fact" placeholder="ör. Ada yüzme bilmiyor" />
        <div className="row">{cast.map((c) => <span key={c.id}><input type="checkbox" name="fact_known_by" value={c.id} /> {c.name} biliyor</span>)}</div>
        <label>Yeni ilişki</label>
        <div className="row">
          <select name="rel_a" style={{ width: "auto" }}>{cast.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <select name="rel_b" style={{ width: "auto" }}>{cast.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <input name="new_rel" placeholder="ilişki türü" style={{ width: 160 }} />
        </div>
        <p><button className="btn">Kaydet</button></p>
      </form>
    </>
  );
}
