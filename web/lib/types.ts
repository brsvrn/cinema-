export type Doc = { id: string; [k: string]: any };
export const STAGES: [string, string][] = [
  ["memory", "Dizi hafızasını oku"], ["script", "Senaryoyu üret"], ["continuity", "Tutarlılık kontrolü"],
  ["storyboard", "Storyboard"], ["voices", "Seslendirme"], ["animate", "Animasyon"], ["lipsync", "Dudak senkronu"],
  ["staging", "Mekân ve kamera"], ["audio", "Müzik ve efektler"], ["render", "Render"], ["assemble", "Birleştirme"],
  ["qc", "Kalite kontrol"], ["repair", "Onarım"], ["upload", "Yükleme"], ["publish", "Yayın"],
];
export const STATUS_TR: Record<string, string> = {
  draft: "Taslak", queued: "Kuyrukta", rendering: "Üretiliyor", running: "Çalışıyor", ready: "Hazır",
  failed: "Hata", needs_attention: "Dikkat gerekiyor", done: "Tamamlandı", cancelled: "İptal",
  scheduled: "Planlandı", published: "Yayınlandı", script_ready: "Senaryo hazır",
};
export const POSES = ["idle", "talk_a", "talk_b", "talk_open", "point", "point_up", "surprised", "think", "wave",
  "shrug", "hold", "crouch", "hands_hips", "excited", "lookout"];
export const EMOTIONS = ["neutral", "happy", "laugh", "sad", "surprised", "angry", "worried", "thinking",
  "determined", "scared", "curious"];
export const CAMERAS = ["", "cu", "mcu", "ots", "two", "wide"];
