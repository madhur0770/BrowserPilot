// End-to-end check of the tool layer BrowserPilot relies on: a real
// @playwright/mcp server driving a real browser against a local fixture site.
// No LLM and no network access are involved. Dependency-free (Node 18+).
//
//   node scripts/mcp_smoke_test.mjs [--screenshot docs/assets/screenshot.png]
//
// Environment:
//   BROWSERPILOT_MCP_CMD   command to start the server (default: npx --yes @playwright/mcp@0.0.68)
//   BROWSERPILOT_BROWSER_EXECUTABLE   optional browser binary path
//   BROWSERPILOT_BROWSER              browser or channel for --browser (for example: chrome)
//   BROWSERPILOT_NO_SANDBOX=1         pass --no-sandbox (needed when running as root)
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const siteDir = path.join(root, 'examples', 'site');
const shotFlag = process.argv.indexOf('--screenshot');
const screenshotPath = shotFlag > -1 ? path.resolve(process.argv[shotFlag + 1]) : null;
const policy = JSON.parse(fs.readFileSync(path.join(root, 'browserpilot', 'policy.json'), 'utf8'));
const PINNED = `@playwright/mcp@${policy.playwright_mcp_version}`;

let failures = 0;
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : `\n      ${detail}`}`);
  if (!ok) failures += 1;
};

function startFixtureServer() {
  const server = http.createServer((req, res) => {
    const name = req.url === '/' ? 'index.html' : path.basename(req.url.split('?')[0]);
    const file = path.join(siteDir, name);
    if (!file.startsWith(siteDir) || !fs.existsSync(file)) { res.writeHead(404).end('not found'); return; }
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(fs.readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

class McpClient {
  constructor(extraArgs) {
    const base = (process.env.BROWSERPILOT_MCP_CMD || `npx --yes ${PINNED}`).split(/\s+/);
    const args = [...base.slice(1), '--headless', '--isolated', ...extraArgs];
    if (process.env.BROWSERPILOT_BROWSER) args.push('--browser', process.env.BROWSERPILOT_BROWSER);
    if (process.env.BROWSERPILOT_NO_SANDBOX === '1') args.push('--no-sandbox');
    if (process.env.BROWSERPILOT_BROWSER_EXECUTABLE) args.push('--executable-path', process.env.BROWSERPILOT_BROWSER_EXECUTABLE);
    this.proc = spawn(base[0], args, { stdio: ['pipe', 'pipe', 'pipe'], shell: process.platform === 'win32' });
    this.nextId = 1; this.pending = new Map(); this.buffer = ''; this.stderr = '';
    this.proc.stdout.on('data', (chunk) => {
      this.buffer += chunk;
      let nl;
      while ((nl = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, nl).trim(); this.buffer = this.buffer.slice(nl + 1);
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        const waiter = msg.id !== undefined && this.pending.get(msg.id);
        if (waiter) { this.pending.delete(msg.id); waiter(msg); }
      }
    });
    this.proc.stderr.on('data', (c) => { this.stderr += c; });
  }
  request(method, params = {}, timeoutMs = 60000) {
    const id = this.nextId++;
    this.proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`timeout: ${method}\n${this.stderr.slice(-500)}`)); }, timeoutMs);
      this.pending.set(id, (m) => { clearTimeout(timer); resolve(m); });
    });
  }
  notify(method, params = {}) { this.proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n'); }
  async start() {
    const init = await this.request('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'browserpilot-smoke-test', version: '1.0.0' } });
    this.notify('notifications/initialized');
    return init;
  }
  async call(name, args = {}) {
    const res = await this.request('tools/call', { name, arguments: args });
    if (res.error) throw new Error(`${name}: ${JSON.stringify(res.error)}`);
    const text = (res.result.content || []).filter((c) => c.type === 'text').map((c) => c.text).join('\n');
    return { text, isError: Boolean(res.result.isError) };
  }
  stop() { try { this.proc.kill(); } catch { /* ignore */ } }
}

const refFor = (snapshot, label) => {
  const m = snapshot.split('\n').find((l) => l.includes(`"${label}"`) && /\[ref=/.test(l));
  return m ? /\[ref=([^\]]+)\]/.exec(m)[1] : null;
};

const server = await startFixtureServer();
const origin = `http://127.0.0.1:${server.address().port}`;
console.log(`Fixture site: ${origin}`);

try {
  // 1) Full browsing flow against the fixture site.
  const client = new McpClient([]);
  try {
    const init = await client.start();
    check('server initialises', Boolean(init.result?.serverInfo), JSON.stringify(init.error || ''));
    const tools = (await client.request('tools/list')).result.tools.map((t) => t.name);
    for (const t of ['browser_navigate', 'browser_snapshot', 'browser_click', 'browser_take_screenshot', 'browser_evaluate']) {
      check(`exposes ${t}`, tools.includes(t), `available: ${tools.join(', ')}`);
    }
    const nav = await client.call('browser_navigate', { url: `${origin}/index.html` });
    check('navigates to home page', !nav.isError && nav.text.includes('Lumen Notes'), nav.text.slice(0, 300));
    const snap = await client.call('browser_snapshot');
    check('snapshot contains page heading', snap.text.includes('Notes that stay out of your way'));
    const ref = refFor(snap.text, 'Pricing');
    check('finds the Pricing link in the snapshot', Boolean(ref), snap.text.slice(0, 400));
    const click = await client.call('browser_click', { element: 'Pricing link', ref });
    check('clicks through to pricing', !click.isError, click.text.slice(0, 300));
    const after = await client.call('browser_snapshot');
    check('pricing page shows the Pro plan', after.text.includes('Pro') && after.text.includes('$12'));
    const rows = await client.call('browser_evaluate', { function: "() => [...document.querySelectorAll('#plans tbody tr')].map(r => [...r.cells].map(c => c.textContent))" });
    check('extracts table rows via evaluate', rows.text.includes('Unlimited notes, sync'), rows.text.slice(0, 300));
    if (screenshotPath) {
      fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
      const shot = await client.call('browser_take_screenshot', { type: 'png', filename: screenshotPath });
      check('takes a screenshot', !shot.isError && fs.existsSync(screenshotPath), shot.text.slice(0, 300));
    }
  } finally { client.stop(); }

  // 2) The default origin policy (browserpilot/policy.json) really blocks requests.
  const guarded = new McpClient(['--blocked-origins', policy.blocked_origins.join(';')]);
  try {
    await guarded.start();
    let text = '';
    try { text = (await guarded.call('browser_navigate', { url: `${origin}/pricing.html` })).text; }
    catch (e) { text = String(e.message); }
    check('default policy blocks loopback origins', text.includes('ERR_BLOCKED_BY_CLIENT'), text.slice(0, 300));
  } finally { guarded.stop(); }
} catch (e) {
  check('smoke test completed without exception', false, String(e.stack || e));
} finally {
  server.close();
}

console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
