// Mirrors worker/studio/cost.py
export const PRICES = { github_actions_min: 0.008, claude_script: 0.03, elevenlabs_char: 0.00018, runpod_gpu_sec: 0.00044 };
const CPU_SEC: Record<string, number> = { economic: 360, advanced: 840, cinematic: 240 };
export type Estimate = { mode: string; items: { item: string; usd: number; free: boolean; qty: string }[]; total: number; paid: boolean };

export function estimate(mode: string, opts: { duration?: number; chars?: number; llm?: boolean; eleven?: boolean } = {}): Estimate {
  const d = opts.duration ?? 30, chars = opts.chars ?? 400;
  const items: Estimate["items"] = [];
  const min = (CPU_SEC[mode] ?? 360) * (d / 30) / 60;
  items.push({ item: "GitHub Actions render (ücretsiz kota)", usd: 0, free: true, qty: `${min.toFixed(0)} dk` });
  items.push(opts.llm ? { item: "Claude senaryo + tutarlılık", usd: PRICES.claude_script, free: false, qty: "1" }
    : { item: "Şablon senaryo", usd: 0, free: true, qty: "1" });
  items.push(opts.eleven ? { item: "ElevenLabs ses", usd: +(chars * PRICES.elevenlabs_char).toFixed(4), free: false, qty: `${chars} kar.` }
    : { item: "Piper TTS", usd: 0, free: true, qty: `${chars} kar.` });
  if (mode === "cinematic") items.push({ item: "RunPod GPU (Wan / ComfyUI)", usd: +(d * 40 * PRICES.runpod_gpu_sec).toFixed(3), free: false, qty: `${d * 40} gpu-sn` });
  const total = +items.reduce((a, i) => a + (i.free ? 0 : i.usd), 0).toFixed(4);
  return { mode, items, total, paid: total > 0 };
}
