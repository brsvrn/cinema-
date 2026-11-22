import "server-only";
import { promises as fs } from "fs";
import path from "path";
import type { Doc } from "./types";

const SB_URL = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
const SB_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
const BUCKET = process.env.SUPABASE_BUCKET || "studio";
const LOCAL_DIR = process.env.STUDIO_DATA_DIR || path.join(process.cwd(), "..", "worker", "data");
const INDEX: Record<string, string[]> = {
  episodes: ["series_id", "status", "episode_number"],
  jobs: ["status", "kind", "episode_id"],
  characters: ["series_id"],
  locations: ["series_id"],
  cost_ledger: ["job_id"],
};
export const backend = SB_URL && SB_KEY ? "supabase" : "local";

async function rest(method: string, p: string, body?: unknown, headers: Record<string, string> = {}) {
  const r = await fetch(`${SB_URL}/rest/v1/${p}`, {
    method,
    headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`supabase ${method} ${p}: ${r.status} ${await r.text()}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

function rowToDoc(coll: string, row: any): Doc {
  const d: Doc = { ...(row.data || {}), id: row.id };
  for (const k of INDEX[coll] || []) if (row[k] !== null && row[k] !== undefined) d[k] = row[k];
  if (row.created_at && !d.created_at) d.created_at = row.created_at;
  return d;
}

export async function get(coll: string, id: string): Promise<Doc | null> {
  if (backend === "supabase") {
    const rows = await rest("GET", `${coll}?id=eq.${encodeURIComponent(id)}&select=*`);
    return rows?.length ? rowToDoc(coll, rows[0]) : null;
  }
  try {
    return JSON.parse(await fs.readFile(path.join(LOCAL_DIR, coll, `${id}.json`), "utf8"));
  } catch {
    return null;
  }
}

export async function list(coll: string, filter: Record<string, any> = {}): Promise<Doc[]> {
  let docs: Doc[] = [];
  if (backend === "supabase") {
    const q = Object.entries(filter).filter(([k]) => (INDEX[coll] || []).includes(k))
      .map(([k, v]) => `&${k}=eq.${encodeURIComponent(String(v))}`).join("");
    const rows = await rest("GET", `${coll}?select=*${q}&order=id`);
    docs = (rows || []).map((r: any) => rowToDoc(coll, r));
  } else {
    try {
      const dir = path.join(LOCAL_DIR, coll);
      const files = (await fs.readdir(dir)).filter((f) => f.endsWith(".json")).sort();
      docs = await Promise.all(files.map(async (f) => JSON.parse(await fs.readFile(path.join(dir, f), "utf8"))));
    } catch {
      docs = [];
    }
  }
  return docs.filter((d) => Object.entries(filter).every(([k, v]) => d[k] === v));
}

export async function put(coll: string, id: string, data: Record<string, any>): Promise<Doc> {
  const doc: Record<string, any> = { ...data, id, updated_at: Date.now() / 1000 };
  if (backend === "supabase") {
    const row: Record<string, any> = { id, data: doc };
    for (const k of INDEX[coll] || []) if (k in doc) row[k] = doc[k];
    await rest("POST", `${coll}?on_conflict=id`, row, { Prefer: "resolution=merge-duplicates,return=minimal" });
  } else {
    const dir = path.join(LOCAL_DIR, coll);
    await fs.mkdir(dir, { recursive: true });
    const tmp = path.join(dir, `${id}.web.tmp`);
    await fs.writeFile(tmp, JSON.stringify(doc, null, 2));
    await fs.rename(tmp, path.join(dir, `${id}.json`));
  }
  return doc as Doc;
}

export async function remove(coll: string, id: string) {
  if (backend === "supabase") await rest("DELETE", `${coll}?id=eq.${encodeURIComponent(id)}`);
  else await fs.rm(path.join(LOCAL_DIR, coll, `${id}.json`), { force: true });
}

/** URL the browser can use to view/download a stored file. */
export async function fileUrl(key: string | undefined, download = false): Promise<string | null> {
  if (!key) return null;
  if (backend === "supabase") {
    const r = await fetch(`${SB_URL}/storage/v1/object/sign/${BUCKET}/${key}`, {
      method: "POST",
      headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ expiresIn: 60 * 60 * 6 }),
      cache: "no-store",
    });
    if (!r.ok) return null;
    const j = await r.json();
    const u = `${SB_URL}/storage/v1${j.signedURL}`;
    return download ? `${u}&download=${encodeURIComponent(key.split("/").pop() || "file")}` : u;
  }
  return `/api/file?key=${encodeURIComponent(key)}${download ? "&dl=1" : ""}`;
}

export async function readLocalFile(key: string): Promise<Buffer | null> {
  const p = path.normalize(path.join(LOCAL_DIR, "files", key));
  if (!p.startsWith(path.join(LOCAL_DIR, "files"))) return null;
  try {
    return await fs.readFile(p);
  } catch {
    return null;
  }
}

export function newId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
