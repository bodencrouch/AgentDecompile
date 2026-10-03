import { constants } from "node:fs";
import * as fs from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";

const metadataName = "react-publication.json";
const digest = bytes => createHash("sha256").update(bytes).digest("hex");

export class PublicationError extends Error {
  constructor(code, message, entryState = "unchanged", cause) {
    super(`${code}: ${message}`, { cause });
    this.code = code;
    this.entryState = entryState;
  }
}

function refuse(code, message) { throw new PublicationError(code, message); }

function assetPath(value) {
  if (typeof value !== "string" || !/^[A-Za-z0-9_./-]+$/.test(value) ||
      value.split("/").some(part => !part || part === "." || part === "..")) {
    refuse("UNSAFE_PATH", String(value));
  }
  if (value !== "index.html" && !/^assets\/.+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9.]+$/.test(value)) {
    refuse("UNVERSIONED_ASSET", value);
  }
  return value;
}

// Refuse all symlinks, even inward ones, instead of following ambiguous roots.
async function directoryChain(io, absolute, create = false) {
  let current = path.parse(absolute).root;
  for (const part of absolute.slice(current.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    if (create) {
      try { await io.mkdir(current); } catch (error) { if (error.code !== "EEXIST") throw error; }
    }
    const stat = await io.lstat(current);
    if (!stat.isDirectory() || stat.isSymbolicLink()) refuse("UNSAFE_DIRECTORY", current);
  }
}

async function readRegular(io, filename) {
  const stat = await io.lstat(filename);
  if (!stat.isFile() || stat.isSymbolicLink()) refuse("UNSAFE_FILE", filename);
  const handle = await io.open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    if (!(await handle.stat()).isFile()) refuse("UNSAFE_FILE", filename);
    return await handle.readFile();
  } finally { await handle.close(); }
}

async function syncDirectory(io, directory) {
  const handle = await io.open(directory, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  try { await handle.sync(); } finally { await handle.close(); }
}

async function inventory(io, root, prefix = "") {
  const files = [];
  for (const entry of await io.readdir(path.join(root, prefix), { withFileTypes: true })) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isSymbolicLink()) refuse("UNSAFE_FILE", relative);
    if (entry.isDirectory()) files.push(...await inventory(io, root, relative));
    else if (entry.isFile()) files.push(relative);
    else refuse("UNSAFE_FILE", relative);
  }
  return files.sort();
}

async function snapshot(io, stage) {
  let metadata;
  try { metadata = JSON.parse(await readRegular(io, path.join(stage, metadataName))); }
  catch (cause) { throw new PublicationError("INVALID_METADATA", "missing or malformed build metadata", "unchanged", cause); }
  if (metadata?.schema !== "agentdecompile.react-publication/v1" || metadata.base !== "/react/" ||
      metadata.entry !== "index.html" || !Array.isArray(metadata.files) || !Array.isArray(metadata.references)) {
    refuse("INVALID_METADATA", "unsupported publication schema");
  }
  const files = new Map();
  for (const row of metadata.files) {
    if (!row || typeof row !== "object") refuse("INVALID_METADATA", "invalid file record");
    const name = assetPath(row.path);
    if (files.has(name) || !Number.isSafeInteger(row.size) || row.size < 0 ||
        typeof row.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(row.sha256)) {
      refuse("INVALID_METADATA", `invalid or duplicate file: ${name}`);
    }
    await directoryChain(io, path.dirname(path.join(stage, name)));
    const bytes = await readRegular(io, path.join(stage, name));
    if (bytes.length !== row.size || digest(bytes) !== row.sha256) refuse("STAGE_BYTES_CHANGED", name);
    files.set(name, bytes);
  }
  if (!files.has("index.html") || files.size < 2 ||
      !/^\s*<!doctype html>/i.test(files.get("index.html").toString("utf8"))) {
    refuse("INCOMPLETE_STAGE", "expected HTML entry and emitted assets");
  }
  for (const reference of metadata.references) {
    if (!files.has(assetPath(reference))) refuse("MISSING_REFERENCE", reference);
  }
  const expected = [...files.keys(), metadataName].sort();
  if (JSON.stringify(await inventory(io, stage)) !== JSON.stringify(expected)) {
    refuse("STAGE_INVENTORY_MISMATCH", "metadata must cover every staged file");
  }
  // Use these verified immutable buffers for publication, never reread a build
  // directory that another compiler could replace after validation.
  return files;
}

async function existingBytes(io, filename) {
  try { return await readRegular(io, filename); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

async function prepareFile(io, filename, bytes) {
  const handle = await io.open(filename, "wx", 0o644);
  try { await handle.writeFile(bytes); await handle.sync(); }
  finally { await handle.close(); }
}

/** Publish a completed local Vite stage. No build, server or deployment discovery.
 * `io` is only a regression fault-injection seam; the CLI always uses Node fs.
 * Cooperative publishers serialize via an exclusive sibling lock. An abandoned
 * lock requires ownership inspection/removal by an operator; it is never stolen.
 */
export async function publishReact(stagePath, destinationPath, { io = fs } = {}) {
  const stage = path.resolve(stagePath), destination = path.resolve(destinationPath);
  if (stage === destination || stage.startsWith(destination + path.sep) || destination.startsWith(stage + path.sep)) {
    refuse("OVERLAPPING_PATHS", "stage and destination must be separate directories");
  }
  await directoryChain(io, stage);
  const parent = path.dirname(destination);
  await directoryChain(io, parent);
  let files;
  try { files = await snapshot(io, stage); }
  catch (cause) {
    if (cause instanceof PublicationError) throw cause;
    throw new PublicationError("STAGE_VALIDATION_FAILED", cause.message, "unchanged", cause);
  }
  const lockPath = path.join(parent, `.${path.basename(destination)}.publish.lock`);
  let lock;
  try { lock = await io.open(lockPath, "wx", 0o600); }
  catch (cause) {
    if (cause.code === "EEXIST") throw new PublicationError("PUBLICATION_BUSY", lockPath, "unchanged", cause);
    throw cause;
  }
  const temporaries = new Set();
  let committed = false, failure, result;
  try {
    await lock.writeFile(JSON.stringify({ pid: process.pid, stage, destination }) + "\n");
    await lock.sync();
    await directoryChain(io, destination, true);
    // Preflight every conflict before adding files. Never replace old chunks.
    for (const [name, bytes] of files) {
      if (name === "index.html") continue;
      await directoryChain(io, path.dirname(path.join(destination, name)), true);
      const previous = await existingBytes(io, path.join(destination, name));
      if (previous && !previous.equals(bytes)) refuse("ASSET_CONFLICT", name);
    }
    const entryPath = path.join(destination, "index.html");
    await existingBytes(io, entryPath); // Refuse a symlink or special old entry.
    for (const [name, bytes] of files) {
      if (name === "index.html") continue;
      const filename = path.join(destination, name);
      if (await existingBytes(io, filename) !== null) continue;
      const temporary = path.join(path.dirname(filename), `.react-${randomUUID()}.tmp`);
      temporaries.add(temporary);
      await prepareFile(io, temporary, bytes);
      // Hard linking an already synced temporary atomically creates a complete
      // asset without overwriting any existing path (rename would overwrite).
      try { await io.link(temporary, filename); }
      catch (cause) {
        if (cause.code !== "EEXIST") throw cause;
        const previous = await existingBytes(io, filename);
        if (!previous?.equals(bytes)) refuse("ASSET_CONFLICT", name);
      }
      await io.unlink(temporary);
      temporaries.delete(temporary);
    }
    // Sync reused files too: an earlier interrupted attempt may have left them.
    // Directory entries are flushed from leaves up before the entry commit.
    const directories = new Set([destination]);
    for (const [name, bytes] of files) {
      if (name === "index.html") continue;
      const filename = path.join(destination, name);
      if (!(await readRegular(io, filename)).equals(bytes)) refuse("ASSET_CONFLICT", name);
      const handle = await io.open(filename, constants.O_RDONLY | constants.O_NOFOLLOW);
      try { await handle.sync(); } finally { await handle.close(); }
      let directory = path.dirname(filename);
      while (directory !== parent) { directories.add(directory); directory = path.dirname(directory); }
    }
    for (const directory of [...directories].sort((a, b) => b.length - a.length)) await syncDirectory(io, directory);
    await syncDirectory(io, parent);
    const temporaryEntry = path.join(destination, `.react-index-${randomUUID()}.tmp`);
    temporaries.add(temporaryEntry);
    await prepareFile(io, temporaryEntry, files.get("index.html"));
    await io.rename(temporaryEntry, entryPath);
    committed = true;
    temporaries.delete(temporaryEntry);
    // If this fails the new entry is already visible. Never claim rollback.
    await syncDirectory(io, destination);
    result = { entryState: "committed", entrySha256: digest(files.get("index.html")), files: files.size };
  } catch (cause) {
    failure = committed
      ? new PublicationError("COMMITTED_DURABILITY_UNCERTAIN", "new entry is visible; directory durability is unconfirmed", "committed", cause)
      : cause instanceof PublicationError ? cause
        : new PublicationError("PUBLICATION_FAILED", cause.message, "unchanged", cause);
  } finally {
    const cleanup = [...temporaries].map(filename => () => io.rm(filename, { force: true }));
    cleanup.push(() => lock.close(), () => io.unlink(lockPath));
    for (const action of cleanup) {
      try { await action(); }
      catch (cause) {
        failure ??= new PublicationError("PUBLICATION_CLEANUP_FAILED", cause.message, committed ? "committed" : "unchanged", cause);
      }
    }
  }
  if (failure) throw failure;
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  if (process.argv.length !== 4) {
    console.error("Usage: node publish-react.mjs <completed-stage> <destination>");
    process.exitCode = 2;
  } else {
    try { console.log(JSON.stringify(await publishReact(process.argv[2], process.argv[3]))); }
    catch (error) {
      console.error(JSON.stringify({ code: error.code ?? "PUBLICATION_FAILED", entryState: error.entryState ?? "unchanged", message: error.message }));
      process.exitCode = 1;
    }
  }
}
