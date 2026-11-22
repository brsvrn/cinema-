import type { Metadata, Viewport } from "next";
import "./globals.css";
import Nav from "@/components/Nav";
import Script from "next/script";

export const metadata: Metadata = {
  title: "Cloud Animation Studio",
  description: "Bulut tabanlı yapay zekâ animasyon stüdyosu",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Studio", statusBarStyle: "black-translucent" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
};
export const viewport: Viewport = { themeColor: "#0f1117", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <header className="top"><b>🎞️ Cloud Animation Studio</b><a href="/more" className="muted">Menü</a></header>
        <main>{children}</main>
        <Nav />
        <Script id="sw" strategy="afterInteractive">{`if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{})}`}</Script>
      </body>
    </html>
  );
}
