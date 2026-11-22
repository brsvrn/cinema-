import { notFound } from "next/navigation";
import { get, fileUrl } from "@/lib/store";
export const dynamic = "force-dynamic";
export default async function Export({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ep = await get("episodes", id);
  if (!ep) notFound();
  const o = ep.outputs || {};
  const m = ep.metadata || {};
  const [mp4, sh, tr, en, th] = await Promise.all([fileUrl(o.youtube_mp4_key, true), fileUrl(o.shorts_mp4_key, true),
    fileUrl(o.srt_tr_key, true), fileUrl(o.srt_en_key, true), fileUrl(o.thumbnail_key)]);
  return (
    <>
      <h1>YouTube dışa aktarma</h1>
      {!mp4 && <p className="muted">Bölüm henüz hazır değil.</p>}
      {th && <img className="media" src={th} alt="thumbnail" />}
      <div className="card">
        <h3>1. Video</h3><div className="row">{mp4 && <a className="btn small" href={mp4}>1920×1080 MP4</a>}{sh && <a className="btn small" href={sh}>Shorts MP4</a>}</div>
        <h3>2. Başlık</h3><pre>{m.title}</pre><div className="muted">EN: {m.title_en}</div>
        <h3>3. Açıklama</h3><pre>{m.description}</pre>
        <h3>4. Etiketler</h3><pre>{(m.tags || []).join(", ")}</pre>
        <h3>5. Altyazılar</h3><div className="row">{tr && <a className="btn small secondary" href={tr}>Türkçe .srt</a>}{en && <a className="btn small secondary" href={en}>English .srt</a>}</div>
        <h3>6. Ayarlar</h3><div className="muted">Kategori: {m.category} · Çocuklar için: {m.made_for_kids ? "evet" : "hayır"}</div>
      </div>
      <p className="muted">Telefonda: MP4’ü indirip YouTube uygulamasından yükleyin, başlık/açıklama/etiketleri kopyalayın. YouTube Data API OAuth bilgileri eklendiğinde bu sayfaya “Doğrudan yükle” düğmesi gelir.</p>
    </>
  );
}
