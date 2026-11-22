import { NextRequest } from "next/server";
import { readLocalFile } from "@/lib/store";

const TYPES: Record<string, string> = { mp4: "video/mp4", png: "image/png", srt: "application/x-subrip; charset=utf-8",
  json: "application/json; charset=utf-8", wav: "audio/wav" };

export async function GET(req: NextRequest) {
  const key = req.nextUrl.searchParams.get("key") || "";
  const buf = await readLocalFile(key);
  if (!buf) return new Response("not found", { status: 404 });
  const ext = key.split(".").pop() || "";
  const headers: Record<string, string> = { "Content-Type": TYPES[ext] || "application/octet-stream", "Accept-Ranges": "bytes" };
  if (req.nextUrl.searchParams.get("dl")) headers["Content-Disposition"] = `attachment; filename="${key.split("/").pop()}"`;
  const range = req.headers.get("range");
  if (range) {
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    const start = m && m[1] ? parseInt(m[1]) : 0;
    const end = m && m[2] ? parseInt(m[2]) : buf.length - 1;
    return new Response(new Uint8Array(buf.subarray(start, end + 1)), { status: 206,
      headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${buf.length}`, "Content-Length": String(end - start + 1) } });
  }
  return new Response(new Uint8Array(buf), { headers: { ...headers, "Content-Length": String(buf.length) } });
}
