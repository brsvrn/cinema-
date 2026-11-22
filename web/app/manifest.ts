import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Cloud AI Animation Studio", short_name: "Studio", start_url: "/", display: "standalone",
    background_color: "#0f1117", theme_color: "#0f1117", orientation: "portrait", lang: "tr",
    description: "Telefonundan yönetilen bulut animasyon stüdyosu",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
