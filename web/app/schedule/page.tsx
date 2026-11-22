import { list } from "@/lib/store";
import Badge from "@/components/Badge";
import { scheduleEpisode } from "../actions";
export const dynamic = "force-dynamic";
export default async function Schedule() {
  const eps = (await list("episodes")).sort((a, b) => (a.schedule?.at || "9").localeCompare(b.schedule?.at || "9"));
  return (
    <>
      <h1>Yayın planlaması</h1>
      <p className="muted">Her bölüm için tarih/saat ve platform seçin. YouTube API bağlantısı yapılandırılınca planlanan bölümler otomatik yüklenir; o zamana kadar plan + dışa aktarma paketi hazırlanır.</p>
      {eps.map((e) => (
        <form key={e.id} action={scheduleEpisode} className="card">
          <input type="hidden" name="id" value={e.id} />
          <div className="row between"><b>{e.episode_number}. {e.title}</b><Badge s={e.publish_state || e.status} /></div>
          <div className="two">
            <div><label>Yayın zamanı</label><input type="datetime-local" name="at" defaultValue={e.schedule?.at || ""} /></div>
            <div><label>Not</label><input name="note" defaultValue={e.schedule?.note || ""} /></div>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            {["youtube", "shorts", "instagram", "tiktok"].map((p) => (
              <span key={p}><input type="checkbox" name="platforms" value={p} defaultChecked={(e.schedule?.platforms || []).includes(p)} /> {p}</span>
            ))}
            <button className="btn small">Kaydet</button>
          </div>
        </form>
      ))}
    </>
  );
}
