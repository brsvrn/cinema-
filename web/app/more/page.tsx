import Link from "next/link";
import { logout } from "../actions";
import { backend } from "@/lib/store";
const links: [string, string, string][] = [
  ["/", "🏠", "Ana sayfa"], ["/series/new", "📺", "Dizi oluştur"], ["/characters", "🧑‍🎨", "Karakter stüdyosu (tasarım + ses)"],
  ["/locations", "🏝️", "Mekân stüdyosu"], ["/episodes/new", "🎬", "Bölüm üretimi"], ["/queue", "⏳", "Render kuyruğu"],
  ["/schedule", "🗓️", "Yayın planlaması"], ["/costs", "💰", "Maliyet kontrolü"],
];
export default function More() {
  return (
    <>
      <h1>Menü</h1>
      {links.map(([h, i, l]) => <Link key={h} href={h} className="tile" style={{ marginBottom: 8 }}>{i} {l}</Link>)}
      <p className="muted">Senaryo editörü, storyboard, video düzenleme, dizi hafızası ve YouTube dışa aktarma her bölüm/dizi sayfasının içindedir.</p>
      <p className="muted">Veri kaynağı: {backend}</p>
      <form action={logout}><button className="btn secondary small">Çıkış</button></form>
    </>
  );
}
