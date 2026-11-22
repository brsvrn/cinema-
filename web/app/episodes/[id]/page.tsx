import Link from "next/link";
import { notFound } from "next/navigation";
import { get, fileUrl } from "@/lib/store";
import { STAGES } from "@/lib/types";
import Badge from "@/components/Badge";
import AutoRefresh from "@/components/AutoRefresh";
import { rerender } from "../../actions";
export const dynamic = "force-dynamic";

export default async function EpisodePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ep = await get("episodes", id);
  if (!ep) notFound();
  const o = ep.outputs || {};
  const [yt, sh, thumb, sb, ytDl, shDl, trDl, enDl, metaDl] = await Promise.all([
    fileUrl(o.youtube_mp4_key), fileUrl(o.shorts_mp4_key), fileUrl(o.thumbnail_key), fileUrl(o.storyboard_key),
    fileUrl(o.youtube_mp4_key, true), fileUrl(o.shorts_mp4_key, true), fileUrl(o.srt_tr_key, true), fileUrl(o.srt_en_key, true),
    fileUrl(o.metadata_key, true)]);
  const busy = ["queued", "rendering"].includes(ep.status);
  const stages = ep.pipeline?.stages || {};
  const cont = ep.continuity;
  return (
    <>
      <AutoRefresh active={busy} />
      <div className="row between"><h1>{ep.episode_number}. {ep.title}</h1><Badge s={ep.status} /></div>
      <p className="muted"><Link href={`/series/${ep.series_id}`}>← dizi</Link> · mod: {ep.mode || "economic"} {ep.duration ? `· ${ep.duration.toFixed(1)} sn` : ""}</p>
      {busy && (
        <div className="card">
          <div className="row between"><b>{ep.pipeline?.stage_label || "Kuyrukta, worker bekleniyor"}</b><span>%{ep.pipeline?.percent ?? 0}</span></div>
          <div className="progress" style={{ margin: "8px 0" }}><i style={{ width: `${ep.pipeline?.percent ?? 2}%` }} /></div>
          {STAGES.map(([k, l]) => <div key={k} className="stage"><i className={`dot ${stages[k] || ""}`} />{l}</div>)}
          <p className="muted">Ekranı kapatabilirsiniz; render bulutta devam eder ve kesintide kaldığı yerden sürer.</p>
        </div>
      )}
      {ep.error && <div className="card" style={{ borderColor: "var(--bad)" }}><b>Hata:</b> {ep.error}</div>}
      {yt && (<><h2>YouTube 1920×1080</h2><video controls playsInline preload="metadata" poster={thumb || undefined} src={yt} /></>)}
      {sh && (<><h2>Shorts / Reels / TikTok 1080×1920</h2><div className="vertical"><video controls playsInline preload="metadata" src={sh} /></div></>)}
      {ytDl && (
        <div className="card">
          <h3>İndir</h3>
          <div className="row">
            <a className="btn small" href={ytDl}>MP4 1080p</a>
            {shDl && <a className="btn small" href={shDl}>MP4 Shorts</a>}
            {trDl && <a className="btn small secondary" href={trDl}>Altyazı TR</a>}
            {enDl && <a className="btn small secondary" href={enDl}>Altyazı EN</a>}
            {thumb && <a className="btn small secondary" href={thumb} download>Thumbnail</a>}
            {metaDl && <a className="btn small secondary" href={metaDl}>Metadata</a>}
          </div>
          <p><Link className="btn small secondary" href={`/export/${id}`}>▶ YouTube dışa aktarma paketi</Link></p>
        </div>
      )}
      <div className="row">
        <Link className="btn secondary" href={`/episodes/${id}/script`}>📝 Senaryo editörü / video düzenleme</Link>
        {!busy && <form action={rerender}><input type="hidden" name="id" value={id} /><button className="btn secondary">🔁 Yeniden üret</button></form>}
      </div>
      {sb && (<><h2>Storyboard</h2><img className="media" src={sb} alt="storyboard" /></>)}
      {ep.metadata && (
        <div className="card"><h3>Başlık</h3><p>{ep.metadata.title}</p><h3>Açıklama</h3><pre>{ep.metadata.description}</pre>
          <h3>Etiketler</h3><p className="muted">{(ep.metadata.tags || []).join(", ")}</p><h3>Bölüm özeti</h3><p>{ep.metadata.summary}</p></div>
      )}
      {cont && (
        <div className="card"><h3>Hikâye tutarlılığı {cont.ok ? "✅" : "❌"}</h3>
          {(cont.errors || []).map((e: string, i: number) => <div key={i} style={{ color: "var(--bad)" }}>✖ {e}</div>)}
          {(cont.warnings || []).map((e: string, i: number) => <div key={i} className="muted">⚠ {e}</div>)}
          {cont.ok && !cont.errors?.length && <div className="muted">Karakter bilgisi, olaylar, mekân ve zaman çizelgesi önceki bölümlerle uyumlu.</div>}
        </div>
      )}
      {ep.qc && (
        <div className="card"><h3>Kalite kontrol {ep.qc.ok ? "✅" : "❌"}</h3>
          {Object.entries(ep.qc.formats || {}).map(([k, v]: [string, any]) => (
            <div key={k} className="muted">{k}: {v.width}×{v.height}, {v.duration?.toFixed(1)} sn, ses {v.mean_volume_db} dB, {(v.size / 1e6).toFixed(1)} MB {v.issues?.length ? "· " + v.issues.join(", ") : ""}</div>
          ))}
        </div>
      )}
    </>
  );
}
