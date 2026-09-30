/**
 * Fixed local STDIO bridge for the ChatOps worker.
 *
 * This is deliberately not a generic MCP proxy: Python can select only one of
 * five opaque capability identifiers, and Slack text never reaches this file.
 */
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const INSIGHTHUB_SERVER = fileURLToPath(new URL('./server.mjs', import.meta.url));
const KUBERNETES_SERVER = path.join(
  ROOT,
  'node_modules',
  'kubernetes-mcp-server',
  'bin',
  'index.js',
);

const CAPABILITIES = Object.freeze({
  health: { backend: 'insighthub', tool: 'insighthub_health', arguments: {} },
  requests_5m: {
    backend: 'insighthub',
    tool: 'prometheus_summary',
    arguments: { query: 'requests_5m' },
  },
  errors_5m: {
    backend: 'insighthub',
    tool: 'prometheus_summary',
    arguments: { query: 'errors_5m' },
  },
  ingest_count_today_utc: {
    backend: 'insighthub',
    tool: 'insighthub_ingest_count_today_utc',
    arguments: {},
  },
  pods_in_configured_namespace: {
    backend: 'kubernetes',
    tool: 'pods_list_in_namespace',
    arguments: () => ({ namespace: process.env.CHATOPS_KUBERNETES_NAMESPACE }),
  },
});

function output(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function bridgeEnvironment() {
  return {
    PATH: process.env.PATH ?? '',
    INSIGHTHUB_API_URL: process.env.CHATOPS_INSIGHTHUB_API_URL ?? 'http://127.0.0.1:8000',
    INSIGHTHUB_PROMETHEUS_URL: process.env.CHATOPS_PROMETHEUS_URL ?? 'http://127.0.0.1:9090',
    INSIGHTHUB_MCP_PROMETHEUS: '1',
    INSIGHTHUB_MCP_TOOLS:
      'insighthub_health,insighthub_ingest_count_today_utc,prometheus_summary',
  };
}

function transportFor(capability) {
  if (capability.backend === 'insighthub') {
    return new StdioClientTransport({
      command: process.execPath,
      args: [INSIGHTHUB_SERVER],
      env: bridgeEnvironment(),
      stderr: 'pipe',
    });
  }
  const kubeconfig = process.env.CHATOPS_KUBERNETES_KUBECONFIG ?? '';
  const namespace = process.env.CHATOPS_KUBERNETES_NAMESPACE ?? '';
  if (!path.isAbsolute(kubeconfig) || !namespace) throw new Error('KUBERNETES_NOT_CONFIGURED');
  return new StdioClientTransport({
    command: process.execPath,
    args: [
      KUBERNETES_SERVER,
      '--read-only',
      '--disable-destructive',
      '--disable-multi-cluster',
      '--cluster-provider=kubeconfig',
      '--kubeconfig',
      kubeconfig,
      '--toolsets=core',
      '--list-output=yaml',
      '--log-file=stderr',
    ],
    env: { PATH: process.env.PATH ?? '' },
    stderr: 'pipe',
  });
}

function safeStructuredContent(result) {
  if (
    result?.structuredContent === null ||
    typeof result?.structuredContent !== 'object' ||
    Array.isArray(result.structuredContent)
  ) {
    return null;
  }
  return result.structuredContent;
}

async function run() {
  const name = process.argv[2];
  if (process.argv.length !== 3 || !Object.hasOwn(CAPABILITIES, name)) {
    output({ ok: false, category: 'schema' });
    return;
  }
  const capability = CAPABILITIES[name];
  let client;
  try {
    const transport = transportFor(capability);
    transport.stderr?.resume();
    client = new Client({ name: 'insighthub-chatops-bridge', version: '1.0.0' });
    await client.connect(transport, { timeout: 5000 });
    const listed = await client.listTools();
    if (!listed.tools.some((tool) => tool.name === capability.tool)) {
      output({ ok: false, category: 'schema' });
      return;
    }
    const argumentsValue =
      typeof capability.arguments === 'function'
        ? capability.arguments()
        : capability.arguments;
    const result = await client.callTool({
      name: capability.tool,
      arguments: argumentsValue,
    });
    if (result.isError === true) {
      output({ ok: false, category: 'unavailable' });
      return;
    }
    const structuredContent = safeStructuredContent(result);
    if (structuredContent === null) {
      output({ ok: false, category: 'schema' });
      return;
    }
    output({ ok: true, result: structuredContent });
  } catch {
    output({ ok: false, category: 'unavailable' });
  } finally {
    await client?.close();
  }
}

await run();
