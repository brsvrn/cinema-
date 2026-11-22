import { list } from "@/lib/store";
import { createSeries } from "../../actions";
export const dynamic = "force-dynamic";
export default async function NewSeries() {
  const [chars, locs] = await Promise.all([list("characters"), list("locations")]);
  return (
    <>
      <h1>Dizi oluştur</h1>
      <form action={createSeries} className="card">
        <label>Dizi adı</label><input name="title" required />
        <label>İngilizce ad</label><input name="title_en" />
        <label>Kısa özet (logline)</label><textarea name="logline" />
        <label>Evren kuralları (her satır bir kural)</label><textarea name="rules" />
        <label>Gelecek bölüm planları (her satır)</label><textarea name="plans" />
        <label>Müzik teması</label>
        <select name="music_mood">{["warm", "mystery", "adventure", "tense", "wonder"].map((m) => <option key={m}>{m}</option>)}</select>
        <label>Kadro (onaylı karakterler)</label>
        {chars.map((c) => <div key={c.id}><input type="checkbox" name="characters" value={c.id} /> {c.name} <span className="muted">{c.id}</span></div>)}
        <label>Mekânlar</label>
        {locs.map((l) => <div key={l.id}><input type="checkbox" name="locations" value={l.id} defaultChecked /> {l.name}</div>)}
        <p><button className="btn">Oluştur</button></p>
      </form>
    </>
  );
}
