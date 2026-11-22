import Link from "next/link";

const items = [
  ["/", "🏠", "Ana sayfa"],
  ["/episodes/new", "🎬", "Üret"],
  ["/characters", "🧑‍🎨", "Karakter"],
  ["/queue", "⏳", "Kuyruk"],
  ["/more", "☰", "Diğer"],
];

export default function Nav() {
  return (
    <nav className="bottom">
      {items.map(([href, icon, label]) => (
        <Link key={href} href={href}><span>{icon}</span>{label}</Link>
      ))}
    </nav>
  );
}
