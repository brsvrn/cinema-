"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { get, list, put, newId } from "@/lib/store";
import { wakeWorker } from "@/lib/github";
import { estimate } from "@/lib/cost";
import { COOKIE, sessionToken } from "@/lib/auth";

const str = (f: FormData, k: string) => String(f.get(k) ?? "").trim();
const num = (f: FormData, k: string, d = 0) => {
  const v = parseFloat(str(f, k));
  return Number.isFinite(v) ? v : d;
};

export async function login(form: FormData) {
  if (str(form, "password") !== (process.env.STUDIO_PASSWORD || "")) redirect("/login?e=1");
  (await cookies()).set(COOKIE, await sessionToken(), { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 60 });
  redirect("/");
}

export async function logout() {
  (await cookies()).delete(COOKIE);
  redirect("/login");
}

async function budget() {
  return (await get("settings", "budget")) || { id: "budget", daily_usd: 1, monthly_usd: 10, allow_paid: false };
}

export async function enqueue(kind: string, episodeId: string | null, data: Record<string, any>, estimateUsd = 0) {
  const b = await budget();
  if (estimateUsd > 0) {
    if (!b.allow_paid) throw new Error("Ücretli işlem onaylı değil. Maliyet Kontrolü'nden izin verin.");
    const ledger = await list("cost_ledger");
    const now = Date.now() / 1000;
    const day = ledger.filter((e) => now - (e.ts || 0) < 86400).reduce((a, e) => a + (e.usd || 0), 0);
    const month = ledger.filter((e) => now - (e.ts || 0) < 30 * 86400).reduce((a, e) => a + (e.usd || 0), 0);
    if (day + estimateUsd > b.daily_usd || month + estimateUsd > b.monthly_usd) throw new Error("Bütçe limiti aşılıyor.");
  }
  const id = newId("job");
  await put("jobs", id, { kind, episode_id: episodeId, status: "queued", data: { kind, episode_id: episodeId, ...data },
    estimate_usd: estimateUsd, created_at: Date.now() / 1000, attempts: 0 });
  const w = await wakeWorker(`${kind} ${episodeId ?? ""}`);
  return { id, wake: w };
}

// ------------------------------------------------------------- series
export async function createSeries(form: FormData) {
  const id = newId("ser");
  const chars = form.getAll("characters").map(String);
  const locs = form.getAll("locations").map(String);
  await put("series", id, {
    title: str(form, "title"), title_en: str(form, "title_en"), logline: str(form, "logline"), logline_en: "",
    language: "tr", subtitle_languages: ["tr", "en"], music_mood: str(form, "music_mood") || "warm", style: "economic_2d",
    universe_rules: str(form, "rules").split("\n").map((s) => s.trim()).filter(Boolean),
    characters: chars, locations: locs, relationships: [], facts: [], episodes: [], events: [], timeline: [],
    threads: [], future_plans: str(form, "plans").split("\n").map((s) => s.trim()).filter(Boolean),
    character_history: {}, end_state: null, end_states: {}, created_at: Date.now() / 1000,
  });
  redirect(`/series/${id}`);
}

export async function updateBible(form: FormData) {
  const id = str(form, "id");
  const s = await get("series", id);
  if (!s) throw new Error("dizi yok");
  s.universe_rules = str(form, "rules").split("\n").map((x) => x.trim()).filter(Boolean);
  s.future_plans = str(form, "plans").split("\n").map((x) => x.trim()).filter(Boolean);
  const fact = str(form, "new_fact");
  if (fact) {
    s.facts = [...(s.facts || []), { id: newId("f"), text: fact, known_by: form.getAll("fact_known_by").map(String), episode: 0 }];
  }
  const rel = str(form, "new_rel");
  if (rel) s.relationships = [...(s.relationships || []), { a: str(form, "rel_a"), b: str(form, "rel_b"), type: rel, notes: "" }];
  await put("series", id, s);
  revalidatePath(`/series/${id}`);
}

// ------------------------------------------------------------- characters
export async function saveCharacter(form: FormData) {
  const id = str(form, "id") || newId("chr");
  const prev: Record<string, any> = (await get("characters", id)) || {};
  const design: Record<string, any> = {
    ...(prev.design || {}),
    name: str(form, "name"),
    height: num(form, "height", 1), head_ratio: num(form, "head_ratio", 0.22), build: num(form, "build", 1),
    skin: str(form, "skin"), eye_color: str(form, "eye_color"), brow_color: str(form, "brow_color"),
    hair: { style: str(form, "hair_style"), color: str(form, "hair_color") },
    freckles: form.get("freckles") === "on", glasses: form.get("glasses") === "on",
    outfit: { ...(prev.design?.outfit || {}), top: str(form, "top"), top_color: str(form, "top_color"),
      bottom: str(form, "bottom"), bottom_color: str(form, "bottom_color"), shoes: str(form, "shoes") },
  };
  if (form.get("beard") === "on") { design.beard = str(form, "beard_color") || "#eeeeee"; design.mustache = design.beard; }
  else { delete design.beard; delete design.mustache; }
  const voice = { ...(prev.voice || {}), engine: str(form, "voice_engine") || "piper", model: str(form, "voice_model") || "tr_TR-dfki-medium",
    pitch_semitones: num(form, "pitch", 0), speed: num(form, "speed", 1), noise_scale: num(form, "noise", 0.6),
    elevenlabs_voice_id: str(form, "eleven_id") || null, description: str(form, "voice_desc") };
  await put("characters", id, {
    ...prev, name: str(form, "name"), series_id: str(form, "series_id") || prev.series_id || null,
    role: str(form, "role"), personality: str(form, "personality"), backstory: str(form, "backstory"),
    design, voice, approved: false, version: (prev.version || 0) + 1, created_at: prev.created_at || Date.now() / 1000,
  });
  // worker recomputes identity hashes, renders model sheet / mouth chart / voice sample
  await enqueue("character_sheets", null, { character_id: id, approve: false });
  redirect(`/characters/${id}`);
}

export async function approveCharacter(form: FormData) {
  const id = str(form, "id");
  await enqueue("character_sheets", null, { character_id: id, approve: true });
  const c = await get("characters", id);
  if (c) await put("characters", id, { ...c, approval_pending: true });
  revalidatePath(`/characters/${id}`);
}

// ------------------------------------------------------------- episodes
export async function createEpisode(form: FormData) {
  const seriesId = str(form, "series_id");
  const s = await get("series", seriesId);
  if (!s) throw new Error("dizi yok");
  const eps = await list("episodes", { series_id: seriesId });
  const n = Math.max(0, ...eps.map((e) => e.episode_number || 0)) + 1;
  const id = `${seriesId}_ep${String(n).padStart(3, "0")}`;
  const mode = str(form, "mode") || "economic";
  const est = estimate(mode, { llm: !!process.env.ANTHROPIC_API_KEY });
  await put("episodes", id, { series_id: seriesId, episode_number: n, title: str(form, "topic").slice(0, 60),
    topic: str(form, "topic"), mode, status: "queued", estimate: est, created_at: Date.now() / 1000 });
  const stopAfter = str(form, "action") === "preview" ? "storyboard" : null;
  await enqueue("produce_episode", id, { episode_id: id, stop_after: stopAfter, mode }, est.total);
  redirect(`/episodes/${id}`);
}

export async function saveScript(form: FormData) {
  const id = str(form, "id");
  const ep = await get("episodes", id);
  if (!ep?.script) throw new Error("senaryo yok");
  const beats = ep.script.beats.map((b: any, i: number) => {
    const nb = { ...b };
    if (b.type === "line") {
      nb.text = str(form, `text_${i}`) || b.text;
      nb.text_en = str(form, `text_en_${i}`) || b.text_en;
      nb.emotion = str(form, `emotion_${i}`) || b.emotion;
      const act = str(form, `action_${i}`);
      if (act) nb.action = act; else delete nb.action;
    }
    const cam = str(form, `camera_${i}`);
    if (cam) nb.camera = cam; else if (b.type === "line") delete nb.camera;
    if (form.get(`delete_${i}`) === "on") return null;
    return nb;
  }).filter(Boolean);
  ep.script = { ...ep.script, title: str(form, "title") || ep.script.title, beats };
  ep.title = ep.script.title;
  ep.status = "draft";
  await put("episodes", id, ep);
  if (str(form, "action") === "render") {
    await enqueue("produce_episode", id, { episode_id: id, mode: ep.mode || "economic" });
    await put("episodes", id, { ...ep, status: "queued" });
  }
  redirect(`/episodes/${id}`);
}

export async function rerender(form: FormData) {
  const id = str(form, "id");
  const ep = await get("episodes", id);
  if (!ep) throw new Error("bölüm yok");
  await put("episodes", id, { ...ep, status: "queued" });
  await enqueue("produce_episode", id, { episode_id: id, mode: ep.mode || "economic", force: form.get("force") === "on" });
  redirect(`/episodes/${id}`);
}

export async function scheduleEpisode(form: FormData) {
  const id = str(form, "id");
  const ep = await get("episodes", id);
  if (!ep) throw new Error("bölüm yok");
  const platforms = form.getAll("platforms").map(String);
  ep.schedule = { at: str(form, "at"), platforms, note: str(form, "note") };
  if (ep.status === "ready" && ep.schedule.at) ep.publish_state = "scheduled";
  await put("episodes", id, ep);
  revalidatePath("/schedule");
}

// ------------------------------------------------------------- queue + budget
export async function retryJob(form: FormData) {
  const id = str(form, "id");
  const j = await get("jobs", id);
  if (!j) return;
  await put("jobs", id, { ...j, status: "queued", error: null, attempts: 0 });
  await wakeWorker(`retry ${id}`);
  revalidatePath("/queue");
}

export async function cancelJob(form: FormData) {
  const id = str(form, "id");
  const j = await get("jobs", id);
  if (j && j.status === "queued") await put("jobs", id, { ...j, status: "cancelled" });
  revalidatePath("/queue");
}

export async function wake() {
  await wakeWorker("manual");
  revalidatePath("/queue");
}

export async function saveBudget(form: FormData) {
  await put("settings", "budget", { daily_usd: num(form, "daily", 1), monthly_usd: num(form, "monthly", 10),
    allow_paid: form.get("allow_paid") === "on", prefer_free: true });
  revalidatePath("/costs");
}
