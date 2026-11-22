import { list } from "@/lib/store";
export const dynamic = "force-dynamic";
export default async function Locations() {
  const locs = await list("locations");
  return (
    <>
      <h1>Mekân stüdyosu</h1>
      <p className="muted">Mekânlar sabit setlerdir: aynı ID her bölümde aynı geometriyle çizilir; yalnızca ışık (gündüz, gün batımı, alacakaranlık, gece) ve canlı öğeler (deniz, bulut, fener ışığı, yağmur, ateş böcekleri) değişir.</p>
      {locs.map((l) => (
        <div key={l.id} className="card">
          <div className="row between"><b>{l.name}</b><span className="badge ready">Onaylı set</span></div>
          <div className="muted">{l.id} · tür: {l.kind}</div>
          <p>{l.description}</p>
          <div className="row">{Object.entries(l.palette || {}).map(([k, v]) => <span key={k} className="muted"><i className="swatch" style={{ background: String(v) }} /> {k}</span>)}</div>
          <h3>Sahne noktaları</h3>
          <div className="muted">{Object.entries(l.spots || {}).map(([k, v]) => `${k} (${v})`).join(" · ")}</div>
          <h3>Kamera hedefleri</h3>
          <div className="muted">lamp · tower · door · boat · sea · bench · ground</div>
          <h3>Işık ön ayarları</h3>
          <div className="muted">day · sunset · dusk · night</div>
        </div>
      ))}
      <p className="muted">Yeni prosedürel set türleri (orman, şehir, iç mekân) worker/studio/location.py içine eklenir — Claude Code oturumunda “yeni mekân türü ekle” skill’i ile.</p>
    </>
  );
}
