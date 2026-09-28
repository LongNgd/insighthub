import { collectDefaultMetrics, Registry } from "prom-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const registry = new Registry();
collectDefaultMetrics({ register: registry, prefix: "insighthub_web_" });

export async function GET() {
  return new Response(await registry.metrics(), {
    headers: { "Content-Type": registry.contentType },
  });
}
