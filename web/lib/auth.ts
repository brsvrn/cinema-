// Single-owner auth: password -> HMAC-signed httpOnly cookie (Web Crypto, works in middleware).
export const COOKIE = "studio_session";

async function hmac(secret: string, msg: string) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function authEnabled() {
  return Boolean(process.env.STUDIO_PASSWORD);
}

export async function sessionToken() {
  const secret = process.env.STUDIO_SESSION_SECRET || process.env.STUDIO_PASSWORD || "dev";
  return hmac(secret, "owner:" + (process.env.STUDIO_PASSWORD || ""));
}

export async function validToken(tok: string | undefined) {
  if (!authEnabled()) return process.env.NODE_ENV !== "production" || process.env.STUDIO_ALLOW_OPEN === "1";
  return !!tok && tok === (await sessionToken());
}
