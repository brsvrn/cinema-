import "server-only";
// Wakes the GitHub Actions render worker (workflow_dispatch). The job itself is
// already persisted in the queue, so if this call fails the scheduled fallback run picks it up.
export async function wakeWorker(reason: string): Promise<{ ok: boolean; detail: string }> {
  const token = process.env.GH_DISPATCH_TOKEN;
  const repo = process.env.GH_REPO; // owner/name
  const wf = process.env.GH_WORKFLOW || "render-worker.yml";
  const ref = process.env.GH_REF || "main";
  if (!token || !repo) return { ok: false, detail: "GH_DISPATCH_TOKEN/GH_REPO tanımlı değil - zamanlanmış çalıştırma bekleniyor" };
  const r = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/${wf}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ ref, inputs: { reason: reason.slice(0, 60) } }),
    cache: "no-store",
  });
  return { ok: r.status === 204, detail: r.status === 204 ? "worker tetiklendi" : `GitHub ${r.status}` };
}
