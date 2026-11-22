import Link from "next/link";
import { list } from "@/lib/store";
import Badge from "@/components/Badge";
import AutoRefresh from "@/components/AutoRefresh";
import { retryJob, cancelJob, wake } from "../actions";
export const dynamic = "force-dynamic";
export default async function Queue() {
  const jobs = (await list("jobs")).sort((a, b) => (b.created_at || 0) - (a.created_at || 0)).slice(0, 50);
  const active = jobs.some((j) => ["queued", "running"].includes(j.status));
  return (
    <>
      <AutoRefresh active={active} />
      <div className="row between"><h1>Render kuyruğu</h1><form action={wake}><button className="btn small secondary">Worker’ı uyandır</button></form></div>
      <p className="muted">Kuyruk veritabanında kalıcıdır. Worker çökerse kilit (lease) süresi dolunca iş başka bir worker tarafından alınır ve kaldığı aşamadan devam eder.</p>
      {jobs.length === 0 && <p className="muted">Kuyruk boş.</p>}
      {jobs.map((j) => (
        <div key={j.id} className="card">
          <div className="row between"><b>{j.kind === "produce_episode" ? "Bölüm üretimi" : j.kind === "character_sheets" ? "Karakter model sayfası" : j.kind}</b><Badge s={j.status} /></div>
          <div className="muted">{j.id} · deneme {j.attempts || 0} {j.worker ? `· ${j.worker}` : ""}</div>
          {j.episode_id && <Link href={`/episodes/${j.episode_id}`} className="muted">→ {j.episode_id}</Link>}
          {j.error && <pre>{j.error}</pre>}
          <div className="row">
            {["failed", "cancelled"].includes(j.status) && <form action={retryJob}><input type="hidden" name="id" value={j.id} /><button className="btn small">Tekrar dene</button></form>}
            {j.status === "queued" && <form action={cancelJob}><input type="hidden" name="id" value={j.id} /><button className="btn small secondary">İptal</button></form>}
          </div>
        </div>
      ))}
    </>
  );
}
