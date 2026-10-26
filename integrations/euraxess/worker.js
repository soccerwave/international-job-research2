// EURAXESS-only authorised fetch endpoint. Configure WORKER_TOKEN as a secret.
// Use only after confirming the access permission and request-rate agreement.
const BASE = "https://euraxess.ec.europa.eu";
export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Method not allowed", {status:405});
    if (!env.WORKER_TOKEN || request.headers.get("Authorization") !== "Bearer " + env.WORKER_TOKEN)
      return new Response("Unauthorized", {status:401});
    let body;
    try { body = await request.json(); } catch { return new Response("Bad JSON",{status:400}); }
    const path = String(body.path || "");
    const method = String(body.method || "GET").toUpperCase();
    if (!["GET","POST"].includes(method)) return new Response("Bad method",{status:400});
    if (!(path === "/jobs/search" || /^\\/jobs\\/\\d+$/.test(path)))
      return new Response("Path not allowed",{status:400});
    const query = String(body.query || "");
    if (query.length > 1500) return new Response("Query too long",{status:400});
    const upstream = new URL(BASE + path);
    upstream.search = query;
    const response = await fetch(upstream.toString(), {
      method, redirect:"follow",
      headers:{"Accept":"text/html"},
      signal:AbortSignal.timeout(20000)
    });
    const html = await response.text();
    if (html.length > 1_500_000) return new Response("Upstream page too large",{status:502});
    return new Response(html,{
      status:response.status,
      headers:{"content-type":"text/html; charset=utf-8",
        "x-euraxess-final-url":response.url}
    });
  }
};
