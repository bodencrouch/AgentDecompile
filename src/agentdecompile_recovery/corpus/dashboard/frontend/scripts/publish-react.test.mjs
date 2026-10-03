// Regression SOURCE ONLY in Task42.1. Execution requires separate authorization.
import assert from "node:assert/strict";
import { test } from "vitest";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { publishReact } from "./publish-react.mjs";

const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const entry = tag => `<!doctype html><html><script type="module" src="/react/assets/main-${tag}.js"></script></html>`;
const generation = tag => ({
  "index.html": entry(tag),
  [`assets/main-${tag}.js`]: `import('./lazy-${tag}.js')`,
  [`assets/lazy-${tag}.js`]: `new Worker(new URL('./worker-${tag}.js', import.meta.url))`,
  [`assets/worker-${tag}.js`]: `fetch('/react/assets/code-${tag}.wasm')`,
  [`assets/code-${tag}.wasm`]: Buffer.from([0, 97, 115, 109, 1, 0, 0, 0]),
  [`assets/style-${tag}.css`]: `@font-face { src: url('./font-${tag}.woff2') }`,
  [`assets/font-${tag}.woff2`]: "fixture-font-bytes",
});

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(tmpdir(), "react-publisher-"));
  t.onTestFinished(() => fs.rm(root, { recursive: true, force: true }));
  const destination = path.join(root, "published");
  await fs.mkdir(destination);
  await fs.writeFile(path.join(destination, "index.html"), entry("old00000"));
  await fs.mkdir(path.join(destination, "assets"));
  await fs.writeFile(path.join(destination, "assets/lazy-old00000.js"), "old lazy bytes");
  return { root, destination };
}

async function writeStage(root, contents = generation("new00000"), name = "stage") {
  const stage = path.join(root, name);
  for (const [relative, bytes] of Object.entries(contents)) {
    await fs.mkdir(path.dirname(path.join(stage, relative)), { recursive: true });
    await fs.writeFile(path.join(stage, relative), bytes);
  }
  await fs.writeFile(path.join(stage, "react-publication.json"), JSON.stringify({
    schema: "agentdecompile.react-publication/v1", base: "/react/", entry: "index.html",
    files: Object.entries(contents).map(([relative, bytes]) => ({ path: relative, size: Buffer.byteLength(bytes), sha256: hash(bytes) })),
    references: Object.keys(contents).filter(name => name !== "index.html"),
  }));
  return stage;
}

async function oldEntry(destination) {
  assert.equal(await fs.readFile(path.join(destination, "index.html"), "utf8"), entry("old00000"));
  assert.equal(await fs.readFile(path.join(destination, "assets/lazy-old00000.js"), "utf8"), "old lazy bytes");
}

test("publishes entry last, retains old lazy chunks and repeats identically", async t => {
  const { root, destination } = await fixture(t), contents = generation("new00000");
  const stage = await writeStage(root, contents);
  const io = { ...fs, async rename(from, to) {
    await oldEntry(destination);
    for (const [name, bytes] of Object.entries(contents)) {
      if (name !== "index.html") assert.deepEqual(await fs.readFile(path.join(destination, name)), Buffer.from(bytes));
    }
    return fs.rename(from, to);
  } };
  assert.equal((await publishReact(stage, destination, { io })).entryState, "committed");
  assert.equal((await publishReact(stage, destination)).entrySha256, hash(contents["index.html"]));
  assert.equal(await fs.readFile(path.join(destination, "assets/lazy-old00000.js"), "utf8"), "old lazy bytes");
});

for (const mutation of ["missing-lazy", "missing-worker", "missing-wasm", "missing-font", "changed", "extra", "malformed", "missing-reference", "traversal", "symlink"]) {
  test(`refuses ${mutation} before entry publication`, async t => {
    const { root, destination } = await fixture(t), stage = await writeStage(root);
    const metadata = path.join(stage, "react-publication.json");
    if (mutation.startsWith("missing-") && mutation !== "missing-reference") {
      const suffix = { "missing-lazy": "lazy-new00000.js", "missing-worker": "worker-new00000.js", "missing-wasm": "code-new00000.wasm", "missing-font": "font-new00000.woff2" }[mutation];
      await fs.unlink(path.join(stage, "assets", suffix));
    } else if (mutation === "changed") await fs.writeFile(path.join(stage, "assets/main-new00000.js"), "changed");
    else if (mutation === "extra") await fs.writeFile(path.join(stage, "assets/unlisted-00000000.js"), "extra");
    else if (mutation === "malformed") await fs.writeFile(metadata, "{");
    else if (mutation === "missing-reference" || mutation === "traversal") {
      const value = JSON.parse(await fs.readFile(metadata));
      value.references.push(mutation === "traversal" ? "assets/../../escape.js" : "assets/absent-00000000.js");
      await fs.writeFile(metadata, JSON.stringify(value));
    } else {
      await fs.unlink(path.join(stage, "assets/main-new00000.js"));
      await fs.symlink(path.join(destination, "index.html"), path.join(stage, "assets/main-new00000.js"));
    }
    await assert.rejects(publishReact(stage, destination));
    await oldEntry(destination);
  });
}

test("same name with different bytes refuses without adding assets", async t => {
  const { root, destination } = await fixture(t), stage = await writeStage(root);
  await fs.writeFile(path.join(destination, "assets/main-new00000.js"), "existing different bytes");
  await assert.rejects(publishReact(stage, destination), { code: "ASSET_CONFLICT", entryState: "unchanged" });
  await oldEntry(destination);
  assert.deepEqual((await fs.readdir(path.join(destination, "assets"))).sort(), ["lazy-old00000.js", "main-new00000.js"]);
});

test("an overlapping publisher is refused while the lock owner can finish", async t => {
  const { root, destination } = await fixture(t), stage = await writeStage(root);
  let announce, release;
  const entered = new Promise(resolve => { announce = resolve; });
  const proceed = new Promise(resolve => { release = resolve; });
  const io = { ...fs, async link(from, to) { announce(); await proceed; return fs.link(from, to); } };
  const first = publishReact(stage, destination, { io });
  await entered;
  try { await assert.rejects(publishReact(stage, destination), { code: "PUBLICATION_BUSY" }); await oldEntry(destination); }
  finally { release(); }
  await first;
});

for (const operation of ["link", "rename"]) {
  test(`${operation} interruption preserves old entry and retry succeeds`, async t => {
    const { root, destination } = await fixture(t), stage = await writeStage(root);
    const io = { ...fs, async [operation]() { throw new Error(`injected ${operation} failure`); } };
    await assert.rejects(publishReact(stage, destination, { io }), { code: "PUBLICATION_FAILED", entryState: "unchanged" });
    await oldEntry(destination);
    await publishReact(stage, destination);
  });
}

for (const afterCommit of [false, true]) {
  test(`directory fsync failure ${afterCommit ? "after" : "before"} commit reports actual entry state`, async t => {
    const { root, destination } = await fixture(t), stage = await writeStage(root);
    let renamed = false;
    const io = { ...fs,
      async rename(from, to) { await fs.rename(from, to); renamed = true; },
      async open(filename, ...args) {
        const handle = await fs.open(filename, ...args);
        if (filename === destination) {
          const sync = handle.sync.bind(handle);
          handle.sync = async () => {
            if (renamed === afterCommit) throw new Error("injected directory fsync failure");
            await sync();
          };
        }
        return handle;
      },
    };
    await assert.rejects(publishReact(stage, destination, { io }), {
      code: afterCommit ? "COMMITTED_DURABILITY_UNCERTAIN" : "PUBLICATION_FAILED",
      entryState: afterCommit ? "committed" : "unchanged",
    });
    if (afterCommit) assert.equal(await fs.readFile(path.join(destination, "index.html"), "utf8"), entry("new00000"));
    else await oldEntry(destination);
  });
}

test("destination symlink and nested stage are refused", async t => {
  const { root, destination } = await fixture(t), stage = await writeStage(root);
  const alias = path.join(root, "alias");
  await fs.symlink(destination, alias);
  await assert.rejects(publishReact(stage, alias), { code: "UNSAFE_DIRECTORY" });
  await assert.rejects(publishReact(path.join(destination, "stage"), destination), { code: "OVERLAPPING_PATHS" });
  await oldEntry(destination);
});

test("abandoned lock is refused and never removed by a new publisher", async t => {
  const { root, destination } = await fixture(t), stage = await writeStage(root);
  const lock = path.join(root, ".published.publish.lock");
  await fs.writeFile(lock, "existing owner");
  await assert.rejects(publishReact(stage, destination), { code: "PUBLICATION_BUSY" });
  assert.equal(await fs.readFile(lock, "utf8"), "existing owner");
  await oldEntry(destination);
});

test("index preparation fsync failure leaves old entry selected", async t => {
  const { root, destination } = await fixture(t), stage = await writeStage(root);
  const io = { ...fs, async open(filename, ...args) {
    const handle = await fs.open(filename, ...args);
    if (path.basename(filename).startsWith(".react-index-")) {
      handle.sync = async () => { throw new Error("injected index preparation fsync failure"); };
    }
    return handle;
  } };
  await assert.rejects(publishReact(stage, destination, { io }), { code: "PUBLICATION_FAILED", entryState: "unchanged" });
  await oldEntry(destination);
});

test("Vite metadata covers emitted assets and URL postfixes without changing URLs", { timeout: 30_000 }, async t => {
  // This is a real bundler regression when authorized, not a synthetic manifest
  // standing in for bundler coverage. It never writes the packaged destination.
  const { root, destination } = await fixture(t);
  const source = path.join(root, "source"), stage = path.join(root, "bundle");
  await fs.mkdir(source);
  const inputs = {
    "index.html": '<!doctype html><html><script type="module" src="/main.js"></script></html>',
    "main.js": "import './style.css'; import fragmentIcon from './icon.svg?url#symbol'; import queriedIcon from './icon.svg?url&variant=dark#symbol'; globalThis.fixtureUrls=[fragmentIcon,queriedIcon]; document.body.onclick=()=>import('./lazy.js');",
    "lazy.js": "export const worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});",
    "worker.js": "import wasm from './code.wasm?url'; self.postMessage(wasm);",
    "style.css": "@font-face { font-family:fixture; src:url('./font.woff2') } body { font-family:fixture }",
    "font.woff2": "fixture-font-bytes",
    "icon.svg": '<svg xmlns="http://www.w3.org/2000/svg"><symbol id="symbol"><path d="M0 0h1v1z"/></symbol></svg>',
    "code.wasm": Buffer.from([0, 97, 115, 109, 1, 0, 0, 0]),
  };
  for (const [name, bytes] of Object.entries(inputs)) await fs.writeFile(path.join(source, name), bytes);
  const { build } = await import("vite");
  await build({ configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)), root: source,
    build: { outDir: stage, assetsInlineLimit: 0 } });
  const manifest = JSON.parse(await fs.readFile(path.join(stage, "react-publication.json")));
  for (const pattern of [/lazy-.+\.js$/, /worker-.+\.js$/, /\.css$/, /\.woff2$/, /\.wasm$/, /\.svg$/]) {
    assert.ok(manifest.files.some(file => pattern.test(file.path)), `missing output ${pattern}`);
  }
  const icon = manifest.files.find(file => file.path.endsWith(".svg"));
  assert.ok(manifest.references.includes(icon.path), "URL dependencies retain their disk identity");
  assert.ok(manifest.references.every(reference => !/[?#]/.test(reference)), "metadata contains disk paths only");
  const scripts = (await Promise.all(manifest.files.filter(file => file.path.endsWith(".js"))
    .map(file => fs.readFile(path.join(stage, file.path), "utf8")))).join("\n");
  assert.ok(scripts.includes(`/react/${icon.path}#symbol`), "fragment remains in emitted URL");
  assert.ok(scripts.includes(`/react/${icon.path}?variant=dark#symbol`), "query and fragment remain in emitted URL");
  const iconBytes = await fs.readFile(path.join(stage, icon.path));
  await fs.unlink(path.join(stage, icon.path));
  await assert.rejects(publishReact(stage, destination), { code: "STAGE_VALIDATION_FAILED" });
  await oldEntry(destination);
  await fs.writeFile(path.join(stage, icon.path), iconBytes);
  await publishReact(stage, destination);
  assert.equal(await fs.readFile(path.join(destination, "assets/lazy-old00000.js"), "utf8"), "old lazy bytes");
  await fs.writeFile(path.join(source, "style.css"), "body { background: url('./missing.png') }");
  await assert.rejects(build({ configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)), root: source,
    build: { outDir: stage, assetsInlineLimit: 0 } }), /REACT_BUILD_WARNING/);
});
