/* AgentDecompile workbench — React 18 + htm. Session tabs stay sticky; surfaces stay in flow. */
(function () {
  "use strict";

  const e = React.createElement;
  const html = htm.bind(e);
  const { useCallback, useEffect, useMemo, useRef, useState } = React;

  const API = {
    binaries: "/dashboard/api/workbench/binaries",
    functions: "/dashboard/api/workbench/functions",
    detail: "/dashboard/api/workbench/function",
    browse: "/dashboard/api/workbench/browse",
    classify: "/dashboard/api/workbench/classify",
    inspect: "/dashboard/api/workbench/inspect",
    resolveDrop: "/dashboard/api/workbench/resolve-drop",
    stageDrop: "/dashboard/api/workbench/stage-drop",
    projects: "/dashboard/api/workbench/projects",
    save: "/dashboard/api/workbench/save",
    saveAs: "/dashboard/api/workbench/save-as",
    sessions: "/dashboard/api/workbench/sessions",
    ensureProgram: "/dashboard/api/workbench/ensure-program",
    workspace: "/dashboard/api/workbench/workspace",
    programs: "/dashboard/api/workbench/programs",
    matchStatus: "/dashboard/api/workbench/match-status",
    matchDecide: "/dashboard/api/workbench/match-decide",
    matchDecideBatch: "/dashboard/api/workbench/match-decide-batch",
    matchReview: "/dashboard/api/workbench/match-review",
    recoverStatus: "/dashboard/api/workbench/recover-status",
    corpusStatus: "/dashboard/api/workbench/corpus-status",
    corpusDb: "/dashboard/api/workbench/corpus-db",
    progressReport: "/dashboard/api/workbench/progress-report",
    preparations: "/dashboard/api/workbench/preparations",
    ghidraDefaults: "/dashboard/api/workbench/ghidra-defaults",
    artifacts: "/dashboard/artifact",
    evidence: "/dashboard/evidence/database",
    context: "/dashboard/api/workbench/context",
    actions: "/api/v1/actions",
    jobs: "/api/v1/jobs",
    jobsCurrent: "/api/v1/jobs/current",
    jobsHistory: "/api/v1/jobs/history",
    serverShutdown: "/dashboard/api/server/shutdown",
    serverRestart: "/dashboard/api/server/restart",
    panel: "/dashboard/panel"
  };
  const JOB_PAGE_SIZE = 100;

  const SURFACES = [
    { id: "wb-overview", title: "Overview", keys: ["overview", "corpus"] },
    { id: "wb-ingest", title: "Project", keys: ["add", "drop", "gpr", "upload", "project", "source", "binary"] },
    { id: "wb-sources", title: "Project", keys: ["source", "binary"] },
    { id: "wb-inspect", title: "Inspector", keys: ["inspect", "sibling", "preview"] },
    { id: "wb-graph", title: "Call trees", keys: ["graph", "call"] },
    { id: "wb-jobs", title: "Jobs", keys: ["job", "pulse"] },
    { id: "wb-atlas", title: "Atlas", keys: ["atlas", "map", "score", "prompt"] },
    { id: "wb-report", title: "Report", keys: ["report"] },
    { id: "wb-fnbrowse", title: "Functions", keys: ["function", "func", "addr", "browse", "page"] },
    { id: "wb-review", title: "Review", keys: ["review"] },
    { id: "wb-logical", title: "Logical identities", keys: ["logical", "identity", "sibling"] },
    { id: "wb-artifacts", title: "Artifacts", keys: ["artifact"] },
    { id: "wb-pipeline", title: "Pipeline", keys: ["pipeline", "steps"] },
    { id: "wb-match", title: "Cross-build", keys: ["match", "cross", "logical identity", "counterpart"] },
    { id: "wb-recovery", title: "Recover", keys: ["recovery", "recover", "dump"] },
    { id: "wb-stabs", title: "STABS", keys: ["stabs", "donor"] },
    { id: "wb-knowledge", title: "Knowledge", keys: ["knowledge"] },
    { id: "wb-roundtrip", title: "Roundtrip", keys: ["roundtrip", "rebuild"] },
    { id: "wb-processes", title: "Process log", keys: ["process", "log"] },
    { id: "wb-mission", title: "Mission", keys: ["mission", "directive"] },
    { id: "wb-corpus", title: "Corpus table", keys: ["corpus"] },
    { id: "wb-tools", title: "Commands", keys: ["mcp", "cli", "tool", "command", "swagger"] }
  ];

  /* Three destinations share the same project universe. */
  const EDITOR_PRIMARY = [
    { id: "wb-overview", title: "Compare" },
    { id: "wb-artifacts", title: "Recover" },
    { id: "wb-pipeline", title: "Work" }
  ];

  function slugFromDiskPath(filePath, fileName) {
    const parts = String(filePath || "").replace(/\\/g, "/").split("/").filter(Boolean);
    let base = (fileName || parts[parts.length - 1] || "binary").trim();
    if (base.indexOf(".") > 0 && base === (parts[parts.length - 1] || "")) {
      base = base.replace(/\.[^.]+$/, "") || base;
    }
    const platforms = {
      win32: 1, win64: 1, macos: 1, darwin: 1,
      "linux-x86": 1, "linux-x64": 1, "linux-arm64": 1, "linux-armhf": 1, "linux-aarch64": 1
    };
    let platform = "";
    for (let i = parts.length - 2; i >= 0; i--) {
      const key = String(parts[i] || "").toLowerCase();
      if (platforms[key]) { platform = key; break; }
    }
    if (!platform) return base;
    const lower = base.toLowerCase();
    if (lower.endsWith("-" + platform)) return base;
    if (platform.indexOf("linux-") === 0 && lower.endsWith("-linux")) base = base.slice(0, -6);
    else if (platform.indexOf("win") === 0 && lower.endsWith("-win")) base = base.slice(0, -4);
    return base + "-" + platform;
  }

  function humanError(raw) {
    const text = String(raw || "").trim();
    if (!text) return "";
    if (text.charAt(0) === "{") {
      try {
        const obj = JSON.parse(text);
        return String(obj.error || obj.message || text).slice(0, 280);
      } catch (_err) {
        return text.slice(0, 280);
      }
    }
    return text.slice(0, 280);
  }

  function sameFunctionAddress(left, right) {
    function canonical(value) {
      if (typeof value === "number") return Number.isSafeInteger(value) && value >= 0 ? value.toString(16) : null;
      const text = String(value == null ? "" : value).trim().replace(/^0x/i, "");
      return /^[0-9a-f]+$/i.test(text) ? text.toLowerCase().replace(/^0+(?=.)/, "") : null;
    }
    const address = canonical(left);
    return address !== null && address === canonical(right);
  }

  function importSlug(item) {
    if (!item) return "";
    if (typeof item === "string") return item.trim();
    if (typeof item === "object") {
      return String(item.slug || item.id || item.name || item.path || "").trim();
    }
    return "";
  }

  function sessionImportSlugs(session) {
    if (!session) return [];
    const out = [];
    const seen = new Set();
    (session.imports || []).forEach(function (item) {
      const name = importSlug(item);
      if (!name || seen.has(name)) return;
      seen.add(name);
      out.push(name);
    });
    return out;
  }

  function mergeImportSlugs(existing, extra, projectSlug) {
    const skip = new Set();
    if (projectSlug) skip.add(String(projectSlug).trim());
    const out = [];
    const seen = new Set();
    function add(name) {
      const slugName = String(name || "").trim();
      if (!slugName || skip.has(slugName) || seen.has(slugName)) return;
      seen.add(slugName);
      out.push(slugName);
    }
    (existing || []).forEach(add);
    (extra || []).forEach(add);
    return out;
  }

  function importsContain(session, slugName) {
    if (!slugName) return false;
    return sessionImportSlugs(session).indexOf(slugName) >= 0;
  }

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function dualBar(decomp, validate) {
    const d = decomp || {};
    const v = validate || {};
    const dTotal = Math.max(1, (d.none || 0) + (d.asm || 0) + (d.c || 0));
    const vTotal = Math.max(1, (v.none || 0) + (v.obj || 0) + (v.linked || 0));
    function segs(parts, total, keys) {
      return keys.map(function (key) {
        const pct = ((parts[key] || 0) / total) * 100;
        return html`<i className=${"seg-" + key} style=${{ width: pct + "%" }} />`;
      });
    }
    return html`<div className="dual-bar" title="decomp vs validate">
      <div className="track-decomp">${segs(d, dTotal, ["none", "asm", "c"])}</div>
      <div className="track-validate">${segs(v, vTotal, ["none", "obj", "linked"])}</div>
    </div>`;
  }

  function rowBar(decomp, validate) {
    return dualBar(
      { none: decomp === "none" ? 1 : 0, asm: decomp === "asm" ? 1 : 0, c: decomp === "c" ? 1 : 0 },
      { none: validate === "none" ? 1 : 0, obj: validate === "obj" ? 1 : 0, linked: validate === "linked" ? 1 : 0 }
    );
  }

  function kindLabel(row) {
    const kind = (row && row.kind) || "binary";
    if (kind === "ghidra-project") return "gpr";
    if (kind === "packed-program") return "gzf";
    if (kind === "shared-fs") return "shared-fs";
    if (kind === "shared-project" || kind === "shared-http") return "ghidra-server";
    if (kind === "draft") return "draft";
    return "bin";
  }

  function styleKind(kind) {
    if (kind === "ghidra-project" || kind === "gpr") return "gpr";
    if (kind === "packed-program" || kind === "gzf") return "gzf";
    if (kind === "shared-fs") return "shared-fs";
    if (kind === "shared-project" || kind === "shared-http" || kind === "ghidra-server") return "ghidra-server";
    if (kind === "draft") return "draft";
    return "bin";
  }

  function kindTitle(kind) {
    if (kind === "ghidra-project" || kind === "gpr" || kind === "project-dir") return "Local Ghidra project";
    if (kind === "packed-program" || kind === "gzf") return "Packed Ghidra program";
    if (kind === "dir") return "Folder";
    if (kind === "shared-fs") return "Local shared-project repository folder (not a .gpr project file)";
    if (kind === "shared-project" || kind === "shared-http" || kind === "ghidra-server") return "Ghidra Server";
    if (kind === "draft") return "New session";
    if (kind === "binary" || kind === "bin") return "Binary";
    return kind || "Unknown";
  }

  function sessionKindLabel(item) {
    const savedName = String(item && (item.title || item.locator) || "");
    if (/\.gpr(?:$|[?#])/i.test(savedName)) {
      return "Saved .gpr path";
    }
    if (/\.(?:exe|dll|so|dylib|bin)(?:$|[?#])/i.test(savedName)) return "Binary";
    const labels = {
      "ghidra-project": "Ghidra project", gpr: "Ghidra project", "project-dir": "Project folder",
      "shared-fs": "Shared folder", "shared-project": "Server project", "shared-http": "Server project",
      "ghidra-server": "Server project", "packed-program": "GZF program", gzf: "GZF program",
      bin: "Binary", binary: "Binary", draft: "New tab", dir: "Folder"
    };
    return labels[item && item.kind] || "Unknown type";
  }

  function formatBytes(n) {
    const size = Number(n || 0);
    if (size < 1024) return size + " B";
    if (size < 1048576) return (size / 1024).toFixed(1) + " KB";
    return (size / 1048576).toFixed(1) + " MB";
  }

  function formatWhen(ts) {
    if (!ts) return "";
    const date = new Date(Number(ts) * 1000);
    if (Number.isNaN(date.getTime())) return String(ts);
    return date.toLocaleString();
  }

  function programName(item) {
    return typeof item === "string" ? item : (item && (item.name || item.id)) || "";
  }

  function tabHasRealProject(session) {
    if (!session) return false;
    if (String(session.kind || "") === "draft") return false;
    return Boolean(String(session.locator || "").trim());
  }

  function preservedImports(session, nextProjectSlug) {
    if (!session) return [];
    return sessionImportSlugs(session).filter(function (slug) {
      return slug !== String(session.projectSlug || "").trim()
        && slug !== String(nextProjectSlug || "").trim();
    });
  }

  function tabProjectName(session, fallback) {
    const title = (session && session.title) || "";
    if (title && title !== "Untitled") return title;
    const stem = String(fallback || "Project").replace(/\.[^.]+$/, "");
    return stem || "Project";
  }

  const SLUG_FIELD_NAMES = new Set(["id", "slug", "binary-id", "binary_id", "binary-id"]);
  const PATH_FIELD_NAMES = new Set(["binary", "path", "repo-path", "repo_path", "archive", "directory", "from-json", "manifest", "snapshot-dir", "snapshot_dir"]);
  const PROGRAM_FIELD_NAMES = new Set(["program", "programpath", "program-path", "from", "repo"]);
  const WORK_DIR_FIELD_NAMES = new Set(["work-dir", "work_dir", "out-dir", "out_dir", "outdir", "out", "workspace", "snapshot-dir", "snapshot_dir"]);
  const DB_FIELD_NAMES = new Set(["db", "corpus"]);
  const ADDR_FIELD_NAMES = new Set(["addr", "address", "addressorsymbol", "address-or-symbol", "target", "function", "identifier", "functionidentifier"]);
  const ROLE_CHOICES = ["member", "donor", "layout source"];

  function normFieldName(name) {
    return String(name || "").toLowerCase().replace(/_/g, "-");
  }

  function toolWidgetKind(field) {
    if (!field) return "text";
    if (field.kind === "bool") return "bool";
    if (field.choices && field.choices.length) return "choices";
    const name = normFieldName(field.name);
    if (field.from_context === "slug" || SLUG_FIELD_NAMES.has(name)) return "slug";
    if (field.from_context === "addr" || ADDR_FIELD_NAMES.has(name)) return "addr";
    if (field.from_context === "db" || DB_FIELD_NAMES.has(name)) return "db";
    if (field.from_context === "work_dir" || WORK_DIR_FIELD_NAMES.has(name)) return "workdir";
    if (field.from_context === "kb" || name === "kb") return "kb";
    if (field.from_context === "program" || PROGRAM_FIELD_NAMES.has(name)) return "program";
    if (name === "role") return "role";
    if (field.kind === "path" && (PATH_FIELD_NAMES.has(name) || name.indexOf("dir") >= 0)) return "path";
    if (field.kind === "int" || field.kind === "float") return "number";
    if (field.kind === "text") return "textarea";
    return "text";
  }

  function defaultToolValue(field, ctx) {
    if (!field) return "";
    if (field.default != null && field.default !== "") return String(field.default);
    const alias = {
      program: ctx.program || ctx.slug || "",
      slug: ctx.slug || "",
      repo: ctx.repo || "",
      addr: ctx.addr || "",
      name: ctx.name || "",
      db: ctx.db || "",
      work_dir: ctx.work_dir || "",
      kb: ctx.kb || ""
    };
    if (field.from_context && alias[field.from_context]) return alias[field.from_context];
    const name = normFieldName(field.name);
    if (SLUG_FIELD_NAMES.has(name)) return ctx.slug || "";
    if (name === "binary" && field.kind === "path") {
      const row = ctx.tabRows.find(function (item) { return item.slug === ctx.slug; }) || ctx.tabRows[0];
      return (row && row.repo) || ctx.repo || "";
    }
    if (PROGRAM_FIELD_NAMES.has(name)) return ctx.program || ctx.repo || ctx.slug || "";
    if (DB_FIELD_NAMES.has(name)) return ctx.db || "";
    if (WORK_DIR_FIELD_NAMES.has(name)) return ctx.work_dir || "";
    if (name === "kb") return ctx.kb || "";
    if (ADDR_FIELD_NAMES.has(name)) return ctx.addr || "";
    return "";
  }

  function ToolField({ field, value, ctx, listPrefix }) {
    const kind = toolWidgetKind(field);
    const label = field.name + (field.required ? " *" : "");
    const hint = field.help ? html`<span className="wb-field-hint">${field.help}</span>` : null;
    const safeList = (listPrefix || "wb") + "-" + normFieldName(field.name);

    if (kind === "bool") {
      return html`<label key=${field.name} className="wb-tool-field wb-tool-field-bool">
        <span>${label}</span>
        <input type="checkbox" name=${field.name} defaultChecked=${Boolean(value)} />
        ${hint}
      </label>`;
    }

    if (kind === "choices") {
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <select name=${field.name} defaultValue=${value || ""} required=${field.required}>
          ${!field.required ? html`<option value="">—</option>` : null}
          ${(field.choices || []).map(function (choice) {
            return html`<option key=${choice} value=${choice}>${choice}</option>`;
          })}
        </select>
        ${hint}
      </label>`;
    }

    if (kind === "slug") {
      const slugs = ctx.tabSlugs.length ? ctx.tabSlugs.slice() : ctx.allBinaries.map(function (row) { return row.slug; });
      const unique = [];
      const seen = new Set();
      slugs.forEach(function (item) {
        if (!item || seen.has(item)) return;
        seen.add(item);
        unique.push(item);
      });
      const picked = value || ctx.slug || unique[0] || "";
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <select name=${field.name} defaultValue=${picked} required=${field.required}>
          ${!field.required ? html`<option value="">— pick binary —</option>` : null}
          ${unique.length ? unique.map(function (item) {
            const row = ctx.allBinaries.find(function (bin) { return bin.slug === item; });
            const meta = row ? (row.kind || "bin") + (row.funcs ? " · " + row.funcs + " fn" : "") : "";
            return html`<option key=${item} value=${item}>${item}${meta ? " (" + meta + ")" : ""}</option>`;
          }) : html`<option value="">No binaries in this tab</option>`}
        </select>
        ${hint}
      </label>`;
    }

    if (kind === "program") {
      const programs = (ctx.programs || []).slice();
      const extras = ctx.tabRows.map(function (row) { return row.slug; }).filter(Boolean);
      extras.forEach(function (item) {
        if (programs.indexOf(item) < 0) programs.push(item);
      });
      const picked = value || ctx.program || programs[0] || ctx.slug || "";
      if (programs.length) {
        return html`<label key=${field.name} className="wb-tool-field">
          <span>${label}</span>
          <select name=${field.name} defaultValue=${picked} required=${field.required}>
            ${!field.required ? html`<option value="">—</option>` : null}
            ${programs.map(function (item) {
              return html`<option key=${item} value=${item}>${item}</option>`;
            })}
          </select>
          ${hint}
        </label>`;
      }
    }

    if (kind === "addr") {
      const addrs = (ctx.functions || []).slice(0, 200);
      if (addrs.length) {
        const picked = value || ctx.addr || "";
        return html`<label key=${field.name} className="wb-tool-field">
          <span>${label}</span>
          <select name=${field.name} defaultValue=${picked} required=${field.required}>
            ${!field.required ? html`<option value="">—</option>` : null}
            ${addrs.map(function (row) {
              return html`<option key=${row.addr} value=${row.addr}>${row.addr} ${row.name || ""}</option>`;
            })}
          </select>
          ${hint}
        </label>`;
      }
    }

    if (kind === "db") {
      const paths = [];
      if (ctx.db) paths.push(ctx.db);
      if (ctx.work_dir) paths.push(ctx.work_dir.replace(/\/?$/, "/") + "corpus.sqlite");
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <input name=${field.name} list=${safeList} defaultValue=${value || paths[0] || ""} required=${field.required} />
        <datalist id=${safeList}>${paths.map(function (item) {
          return html`<option key=${item} value=${item} />`;
        })}</datalist>
        ${hint}
      </label>`;
    }

    if (kind === "workdir") {
      const paths = [];
      if (ctx.work_dir) {
        paths.push(ctx.work_dir);
        paths.push(ctx.work_dir.replace(/\/?$/, "/") + "extract/stabs");
        paths.push(ctx.work_dir.replace(/\/?$/, "/") + "target");
        paths.push(ctx.work_dir.replace(/\/?$/, "/") + "imports");
      }
      if (ctx.recovered) paths.push(ctx.recovered);
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <input name=${field.name} list=${safeList} defaultValue=${value || paths[0] || ""} required=${field.required} />
        <datalist id=${safeList}>${paths.map(function (item) {
          return html`<option key=${item} value=${item} />`;
        })}</datalist>
        ${hint}
      </label>`;
    }

    if (kind === "kb") {
      const paths = ctx.kb ? [ctx.kb] : [];
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <input name=${field.name} list=${safeList} defaultValue=${value || paths[0] || ""} required=${field.required} />
        <datalist id=${safeList}>${paths.map(function (item) {
          return html`<option key=${item} value=${item} />`;
        })}</datalist>
        ${hint}
      </label>`;
    }

    if (kind === "path") {
      const paths = ctx.tabRows.map(function (row) { return row.repo; }).filter(Boolean);
      const corpusPaths = ctx.allBinaries.map(function (row) { return row.repo; }).filter(Boolean);
      corpusPaths.forEach(function (item) {
        if (paths.indexOf(item) < 0) paths.push(item);
      });
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <input name=${field.name} list=${safeList} defaultValue=${value || paths[0] || ""} required=${field.required} />
        <datalist id=${safeList}>${paths.map(function (item) {
          return html`<option key=${item} value=${item} />`;
        })}</datalist>
        ${hint}
      </label>`;
    }

    if (kind === "role") {
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <select name=${field.name} defaultValue=${value || "member"}>
          ${ROLE_CHOICES.map(function (choice) {
            return html`<option key=${choice} value=${choice}>${choice}</option>`;
          })}
        </select>
        ${hint}
      </label>`;
    }

    if (kind === "number") {
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <input type="number" name=${field.name} step=${field.kind === "int" ? "1" : "any"}
          defaultValue=${value || ""} required=${field.required} />
        ${hint}
      </label>`;
    }

    if (kind === "textarea") {
      return html`<label key=${field.name} className="wb-tool-field">
        <span>${label}</span>
        <textarea name=${field.name} rows="4" defaultValue=${value || ""} required=${field.required}></textarea>
        ${hint}
      </label>`;
    }

    return html`<label key=${field.name} className="wb-tool-field">
      <span>${label}</span>
      <input type="text" name=${field.name} defaultValue=${value || ""} required=${field.required} />
      ${hint}
    </label>`;
  }

  function runScripts(host) {
    host.querySelectorAll("script").forEach(function (node) {
      const run = document.createElement("script");
      if (node.src) run.src = node.src;
      else run.textContent = node.textContent;
      node.replaceWith(run);
    });
  }

  function sanitizeLegacy(host) {
    if (!host) return;
    host.querySelectorAll(
      ".skip-link, header.top, header.topbar, nav.workspace-nav, footer.foot, .tail, .wrap > header, .hero, .livepri"
    ).forEach(function (node) { node.remove(); });
    host.querySelectorAll("details.binladder, .perbinary details.binladder").forEach(function (node) {
      node.open = false;
    });
    host.querySelectorAll(".ladder .step").forEach(function (node, index) {
      if (index >= 6) return;
      node.open = node.classList.contains("st-not-started") || node.classList.contains("st-failed");
    });
  }

  function wireStepActions(host) {
    if (!host || host.dataset.stepActionsWired) return;
    host.dataset.stepActionsWired = "1";
    host.addEventListener("click", function (ev) {
      const link = ev.target.closest("a.step-run[data-action-id]");
      if (!link || !host.contains(link)) return;
      ev.preventDefault();
      if (link.classList.contains("disabled") || link.getAttribute("aria-disabled") === "true") return;
      const actionId = link.getAttribute("data-action-id");
      if (!actionId) return;
      const params = {};
      const slug = link.getAttribute("data-action-slug");
      const program = link.getAttribute("data-action-program");
      const src = link.getAttribute("data-action-src");
      const dst = link.getAttribute("data-action-dst");
      if (slug) {
        params.slug = slug;
        params.id = slug;
      }
      if (program) params.program = program;
      if (src) params.src = src;
      if (dst) params.dst = dst;
      if (slug && !params.db) {
        const uiEnv = window.AgentDecompileUI;
        if (uiEnv && typeof uiEnv.getEnvDefaults === "function") {
          const env = uiEnv.getEnvDefaults();
          if (env && env.db) params.db = env.db;
        }
      }
      const ui = window.AgentDecompileUI;
      if (ui && typeof ui.runCatalogAction === "function") {
        ui.runCatalogAction(actionId, params);
        return;
      }
      if (window.AgentDecompileActions && window.AgentDecompileActions.openForm) {
        window.AgentDecompileActions.openForm(actionId);
      }
    });
  }

  /* Review decisions follow one contract on every surface (see MatchReview.tsx):
     rows and tokens come from API.matchReview; a decision is a pending job
     (HTTP 202) until /api/v1/jobs/{id} ends "ok" with acceptance
     "review-decision-only". Nothing here marks a row decided before that. */
  const REVIEW_ERRORS = {
    stale_basis: "A row changed after you loaded it, or was already decided. Nothing was saved. Refresh the rows and decide again.",
    context_changed: "The selected database changed after these rows loaded. Nothing was saved. Refresh the rows and decide again.",
    busy: "The database is busy. Nothing was saved. Try again shortly.",
    unavailable: "The review database is unavailable. Nothing was saved.",
    review_schema_required: "This database has no review tables yet. Run its schema migration first.",
    review_schema_corrupt: "The review tables in this database are damaged. Nothing was saved.",
    schema_required: "This database needs a schema migration before review.",
    duplicate_match: "The same match was submitted twice. Nothing was saved.",
    malformed_request: "The server refused the request format. Refresh the rows and try again.",
    malformed_context: "The request had no current selection. Refresh the rows and try again.",
    request_too_large: "Too many rows in one request. Decide fewer rows at a time.",
    unsafe_database_alias: "The review database path is a link or has extra hard links. Review is refused for it.",
    corrupt_basis: "One review row has damaged data, so the whole review list could not load. Nothing was saved.",
    basis_too_large: "One review row has too much recorded data, so the whole review list could not load. Nothing was saved.",
    cancelled: "The decision was cancelled before it ran. Nothing was saved.",
    ranked_cursor_retired: "This link used the old score-ranked page cursor. Rows are now listed by match ID."
  };
  const REVIEW_REFRESH = ["stale_basis", "context_changed", "malformed_context", "ranked_cursor_retired"];

  function reviewErrorText(code) {
    const text = String(code == null ? "" : code).trim();
    return REVIEW_ERRORS[text] || text || "The review request failed.";
  }

  function reviewFailure(kind, code, text) {
    const error = new Error(text || reviewErrorText(code));
    error.kind = kind; /* "refused": nothing saved. "unknown": may have been saved. */
    error.code = code || "";
    error.refresh = kind === "unknown" || REVIEW_REFRESH.indexOf(code) >= 0;
    return error;
  }

  function reviewOutcomeText(decisions) {
    return (decisions || []).map(function (item) {
      if (item.status === "verify") return "Match " + item.matchId + " moved to verification.";
      if (item.status === "rejected") return "Match " + item.matchId + " rejected.";
      return "Match " + item.matchId + " is now \"" + item.status + "\".";
    }).join(" ");
  }

  /* Returns the decisions list on a committed result, or null while still running. */
  async function observeReviewDecision(jobId, stopped) {
    for (let attempt = 0; attempt < 40; attempt++) {
      if (stopped && stopped()) return null;
      const response = await fetch(API.jobs + "/" + encodeURIComponent(jobId), { cache: "no-store" });
      if (response.status === 404) {
        throw reviewFailure("unknown", "", "The server no longer knows this decision job. Refresh the rows to see whether it was saved.");
      }
      let data = {};
      try { data = await response.json(); } catch (_) { data = {}; }
      if (!response.ok) throw new Error("Could not read the decision job (" + response.status + "). Check its result again.");
      const job = data.job || {};
      if (["ok", "failed", "cancelled", "interrupted"].indexOf(job.status) >= 0) {
        let result = {};
        try { result = JSON.parse(job.log || "{}"); } catch (_) { result = {}; }
        if (job.status === "ok" && result.ok === true && result.acceptance === "review-decision-only" && Array.isArray(result.decisions)) {
          return result.decisions;
        }
        if (typeof result.error === "string" && result.error) throw reviewFailure("refused", result.error);
        throw reviewFailure("unknown", "", "The decision job ended as \"" + job.status + "\" without a result. It may have been saved. Refresh the rows to see the current state.");
      }
      await new Promise(function (resolve) { setTimeout(resolve, 750); });
    }
    return null;
  }

  /* rows: [{match_id, token}] exactly as observed. Returns the pending job ID. */
  async function submitReviewRows(rows, selection, decision) {
    if (!selection || !rows.length || rows.some(function (row) {
      return !Number.isSafeInteger(row.match_id) || !row.token;
    })) throw reviewFailure("refused", "malformed_context");
    const response = await fetch(API.matchDecideBatch, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection: selection, entries: rows.map(function (row) {
        return { matchId: row.match_id, token: row.token, decision: decision };
      }) })
    });
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!(response.ok || response.status === 202) || data.ok === false) {
      const code = data.error || "";
      if (REVIEW_ERRORS[code]) throw reviewFailure("refused", code);
      throw new Error(code || ("The server refused the decision (" + response.status + ")."));
    }
    const jobId = data.job_id || (data.job && data.job.id);
    if (!jobId) throw new Error("The server returned no decision job. Refresh the rows before you decide again.");
    return String(jobId);
  }

  /* Decision links in server-rendered review tables (panels/entities.py). Each
     link carries data-match-id, data-token and data-selection from one review read.
     A click asks for confirmation first, because a decision cannot be undone. */
  function wireMatchDecide(host) {
    if (!host || host.dataset.matchDecideWired) return;
    host.dataset.matchDecideWired = "1";
    function toast(text, tone) {
      const ui = window.AgentDecompileUI || {};
      if (typeof ui.showToast === "function") ui.showToast(text, tone);
    }
    /* The busy flag lives on the rendered table, so a refresh that replaces it
       also releases a lock left by a still-running job. */
    function lock(scope, on) {
      scope.querySelectorAll("a.wb-match-decide").forEach(function (item) {
        if (on) item.setAttribute("aria-disabled", "true"); else item.removeAttribute("aria-disabled");
      });
      scope.dataset.reviewBusy = on ? "1" : "";
    }
    /* Status text for one row, with optional buttons: [[label, onClick], ...]. */
    function note(link, text, buttons) {
      const cell = link.closest("td") || link.parentNode;
      if (!cell) return;
      let status = cell.querySelector(".wb-review-status");
      if (!status) {
        status = document.createElement("span");
        status.className = "wb-review-status";
        status.setAttribute("role", "status");
        cell.appendChild(status);
      }
      status.textContent = " " + text + " ";
      (buttons || []).forEach(function (spec) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "wb-btn wb-btn-mini";
        button.textContent = spec[0];
        button.addEventListener("click", function (ev) { ev.preventDefault(); spec[1](); });
        status.appendChild(button);
        status.appendChild(document.createTextNode(" "));
      });
      return status;
    }
    function watch(link, scope, jobId) {
      note(link, "Waiting for job " + jobId + "…");
      const stopped = function () { return !scope.isConnected; };
      const again = ["Check result", function () { watch(link, scope, jobId); }];
      observeReviewDecision(jobId, stopped).then(function (decisions) {
        if (stopped()) return;
        if (decisions) {
          const text = reviewOutcomeText(decisions);
          note(link, text);
          toast(text, "info");
          lock(scope, false);
          reloadIslands();
          return;
        }
        note(link, "Job " + jobId + " is still running. The table stays locked until you check its result or refresh the panel.", [again]);
      }).catch(function (err) {
        if (stopped()) return;
        const text = String((err && err.message) || err);
        toast(text, "error");
        if (err && err.kind) {
          note(link, text);
          lock(scope, false);
          if (err.refresh) reloadIslands();
          return;
        }
        /* The job could not be read. It may still save, so keep its handle. */
        note(link, text + " Job " + jobId + " may still save.", [again]);
      });
    }
    host.addEventListener("click", function (ev) {
      const link = ev.target.closest("a.wb-match-decide[data-match-id][data-decision]");
      if (!link || !host.contains(link)) return;
      ev.preventDefault();
      const scope = link.closest(".wb-legacy") || host;
      if (scope.dataset.reviewBusy === "1") return;
      const matchId = Number(link.getAttribute("data-match-id"));
      const token = link.getAttribute("data-token") || "";
      const selection = link.getAttribute("data-selection") || "";
      const decision = link.getAttribute("data-decision");
      if (decision !== "accept" && decision !== "reject") return;
      lock(scope, true);
      const question = decision === "accept"
        ? "Move match " + matchId + " to verification? This cannot be undone here."
        : "Reject match " + matchId + "? This cannot be undone here.";
      const status = note(link, question, [
        ["Cancel", function () { note(link, ""); lock(scope, false); }],
        [decision === "accept" ? "Confirm accept" : "Confirm reject", function () {
          note(link, "Sending…");
          submitReviewRows([{ match_id: matchId, token: token }], selection, decision).then(function (jobId) {
            watch(link, scope, jobId);
          }).catch(function (err) {
            const text = String((err && err.message) || err);
            note(link, text);
            toast(text, "error");
            lock(scope, false);
            if (err && err.refresh) reloadIslands();
          });
        }]
      ]);
      const first = status && status.querySelector("button");
      if (first) first.focus();
    });
  }

  function TabRoster({ programs, imports, selectedSlug, selectedProgram, onPickProgram, onPickImport }) {
    const programList = programs || [];
    const importList = imports || [];
    if (!programList.length && !importList.length) {
      return html`<div className="wb-tab-roster wb-empty">Nothing in this tab yet. File → Open, then Add to project…</div>`;
    }
    return html`<div className="wb-tab-roster" id="wb-tab-roster">
      <p className="wb-hint">This list is the Ghidra project. Add and Remove change it.</p>
      ${!programList.length && importList.length ? html`<table className="wb-roster-table">
        <caption className="wb-kicker">Binaries</caption>
        <thead><tr><th>Name</th><th>Kind</th></tr></thead>
        <tbody>
          ${importList.map(function (item) {
            const row = item.row || {};
            const on = selectedSlug && selectedSlug === row.slug && !selectedProgram;
            return html`<tr key=${item.key} className=${on ? "on" : ""}>
              <td><button type="button" className="wb-text-action"
                onClick=${function () { onPickImport(row); }}>${item.name}</button></td>
              <td>${item.kind || "binary"}</td>
            </tr>`;
          })}
        </tbody>
      </table>` : null}
      ${programList.length ? html`<table className="wb-roster-table">
        <caption className="wb-kicker">Programs · open Ghidra project</caption>
        <thead><tr><th>Program</th><th>Kind</th></tr></thead>
        <tbody>
          ${programList.map(function (name) {
            const on = selectedProgram === name;
            return html`<tr key=${"prog-" + name} className=${on ? "on" : ""}>
              <td><button type="button" className="wb-text-action"
                onClick=${function () { onPickProgram(name); }}>${name}</button></td>
              <td>Ghidra program</td>
            </tr>`;
          })}
        </tbody>
      </table>` : html`<p className="wb-hint">No Ghidra programs listed on this project.</p>`}
    </div>`;
  }

  /* Legacy panels answer immediately with a `data-pending="1"` placeholder while the
     store read finishes. The full legacy page re-polls those blocks; an island inside
     the SPA has to do the same or the panel stays on "reading … 0s so far" forever. */
  const PENDING_DELAYS = [900, 1200, 1800, 2500, 3500, 5000, 5000, 5000, 8000, 8000, 8000, 8000];

  /* File → Reload has to reach the legacy fragments too, and those are mounted all over
     the tree. A tiny bus beats threading a nonce through every call site. */
  const ISLAND_BUS = { subs: [] };
  function reloadIslands() {
    ISLAND_BUS.subs.slice().forEach(function (fn) { fn(); });
  }

  function IdentityReceiptDetails({ record, label }) {
    const [open, setOpen] = useState(false);
    const contents = useMemo(function () { return open ? JSON.stringify(record, null, 2) : null; }, [open, record]);
    return html`<details onToggle=${function (event) { setOpen(event.currentTarget.open); }}>
      <summary>${label}</summary><span>${record.method || "Identity method not supplied"}</span>
      ${open ? html`<pre>${contents}</pre>` : null}
    </details>`;
  }

  function CallGraphView({ graph, onPick, compact }) {
    const data = graph || {};
    const center = data.center || null;
    const callers = data.callers || [];
    const callees = data.callees || [];
    const neighbors = data.neighbors || [];
    if (!center && !callers.length && !callees.length && !neighbors.length) {
      return html`<div id=${compact ? undefined : "wb-callgraph"} className="wb-callgraph wb-callgraph-empty">
        <p>Call context is not loaded for this function. Missing evidence does not establish that it has no callers or callees.</p>
        ${data.callersError || data.calleesError ? html`<p role="alert">${data.callersError || data.calleesError}</p>` : null}
      </div>`;
    }
    function nodeBtn(node, extra) {
      if (!node) return null;
      return html`<button type="button" className=${"wb-cg-node " + (extra || "")}
        data-addr=${node.addr}
        title=${(node.kind || "") + " " + (node.addr || "")}
        onClick=${function () { if (onPick) onPick(node); }}>
        <code>${node.addr}</code>
        <span>${node.name}</span>
        ${node.kind ? html`<i>${node.kind}</i>` : null}
      </button>`;
    }
    return html`<div id=${compact ? undefined : "wb-callgraph"} className=${"wb-callgraph" + (compact ? " wb-callgraph-compact" : "")}>
      <div className="wb-cg-col wb-cg-callers">
        <h3>Callers · ${callers.length} shown</h3>
        ${data.callersError ? html`<p role="alert">Caller evidence unavailable: ${data.callersError}</p>` : null}
        ${data.callersTruncated ? html`<p className="wb-hint">This is a bounded caller list, not the full neighborhood.</p>` : null}
        ${callers.length ? callers.map(function (node) { return nodeBtn(node, "in"); })
          : html`<p class="wb-hint">${data.callersError ? "Caller lookup did not complete." : "No incoming calls in this recorded snapshot."}</p>`}
      </div>
      ${callers.length && center ? html`<div className="wb-cg-direction"><span>Callers call this function</span><b aria-hidden="true">→</b></div>` : html`<div className="wb-cg-direction is-empty"></div>`}
      <div className="wb-cg-col wb-cg-center">
        <h3>This function</h3>
        ${nodeBtn(center, "on")}
      </div>
      ${callees.length && center ? html`<div className="wb-cg-direction"><span>This function calls callees</span><b aria-hidden="true">→</b></div>` : html`<div className="wb-cg-direction is-empty"></div>`}
      <div className="wb-cg-col wb-cg-callees">
        <h3>Callees · ${callees.length} shown</h3>
        ${data.calleesError ? html`<p role="alert">Callee evidence unavailable: ${data.calleesError}</p>` : null}
        ${data.calleesTruncated ? html`<p className="wb-hint">This is a bounded callee list, not the full neighborhood.</p>` : null}
        ${callees.length ? callees.map(function (node) { return nodeBtn(node, "out"); })
          : html`<p class="wb-hint">${data.calleesError ? "Callee lookup did not complete." : "No outgoing calls in this recorded snapshot."}</p>`}
      </div>
      ${neighbors.length ? html`<div className="wb-cg-neighbors">
        <h3>Nearby · no call relationship implied</h3>
        ${neighbors.map(function (node) { return nodeBtn(node, "near"); })}
      </div>` : null}
    </div>`;
  }

  function fmtCount(n) {
    if (n == null || n === "") return "—";
    return String(n);
  }

  function fmtByteExact(n) {
    if (n == null || n === "" || n === "unmeasured") return "unmeasured";
    return String(n);
  }

  function stepStateClass(state) {
    const key = String(state || "unmeasured").replace(/\s+/g, "-");
    return "wb-step st-" + key;
  }

  function atlasHref(status) {
    const raw = status && status.atlas && status.atlas.decomp;
    if (raw) {
      try {
        const u = new URL(raw, window.location.href);
        u.hostname = window.location.hostname;
        return u.toString();
      } catch (_err) {
        return raw;
      }
    }
    return "http://" + window.location.hostname + ":5173/";
  }

  function TierProgress({ slug, version, corpusIdentity, revision }) {
    const [result,setResult]=useState({key:"",data:null,error:""});
    const key=[slug,version,corpusIdentity,revision].join(":");
    useEffect(function () {
      let alive=true;const controller=new AbortController();setResult({key:key,data:null,error:slug&&!version?"Exact content-hash version unavailable for this build.":""});
      const query=new URLSearchParams({slug:slug||"",version:version||"",corpusIdentity:corpusIdentity||""});
      if(slug&&version)fetch(API.progressReport+"?"+query,{signal:controller.signal,cache:"no-store"})
        .then(function(r){return r.json();}).then(function(body){if(alive){const p=body.matrix_projection,b=p&&p.binary;if(body.ok&&p&&p.corpus_identity===corpusIdentity&&b&&b.slug===slug&&b.version===version&&b.content_sha256===version)setResult({key:key,data:body,error:""});else setResult({key:key,data:null,error:body.error||"Progress basis does not match this selection"});}})
        .catch(function(e){if(alive)setResult({key:key,data:null,error:String(e.message||e)});});
      return function(){alive=false;controller.abort();};
    },[key]);
    if(!slug)return null;
    const current=result.key===key?result:{key:key,data:null,error:""},data=current.data,error=current.error;
    const report=data&&data.report||{},tiers=report.tiers||{},total=report.measures&&report.measures.total_functions;
    const verified=tiers["verified-byte-exact"]&&tiers["verified-byte-exact"].functions,advisory=tiers["advisory-ghidra"]&&tiers["advisory-ghidra"].functions,provider=data&&data.matrix_projection&&data.matrix_projection.provider||{};
    const valid=[total,advisory].every(function(v){return Number.isSafeInteger(v)&&v>=0;})&&advisory<=total,verifiedAvailable=provider.status==="connected"&&Number.isSafeInteger(verified)&&verified>=0&&verified+advisory<=total;
    return html`<section aria-label="Separate verified and advisory progress"><h3>Recorded source coverage</h3>
      ${error?html`<p className="wb-dialog-error">${error}</p>`:!data?html`<p role="status">Reading inventory accounting…</p>`:null}
      ${valid?html`<div style=${{display:"flex",height:"12px",background:"#333943"}} role="img" aria-label=${(verifiedAvailable?verified+" accepted byte-exact receipts":"Verified count unavailable")+"; "+advisory+" advisory source records; "+total+" inventory members"}>${verifiedAvailable?html`<span style=${{width:(total?verified*100/total:0)+"%",background:"#79bd98"}}></span>`:null}<span style=${{width:(total?advisory*100/total:0)+"%",background:"repeating-linear-gradient(135deg,#8baee0 0,#8baee0 3px,#343f52 3px,#343f52 7px)"}}></span></div><p>${verifiedAvailable?verified+" accepted byte-exact receipts":"Verified unavailable"} · ${advisory} advisory source records · ${total} inventory members</p>`:data?html`<p>No reconciled tier counts available.</p>`:null}
      ${data&&data.acceptance_provider?html`<p className="wb-hint">${data.acceptance_provider.reason}</p>`:null}
      ${report.accounting?html`<p>Member accounting: ${report.accounting.status}. Byte extents: ${report.accounting.byte_accounting}. Function counts do not establish whole-image parity.</p>`:null}
    </section>`;
  }

  function CorpusHeadline({ headline, claim, slug, version, corpusIdentity, revision }) {
    const h = headline || {};
    return html`<section className="wb-corpus-hero" id="wb-corpus-hero">
      <p className="wb-kicker">Readable C and byte identity stay separate</p>
      <${TierProgress} slug=${slug} version=${version} corpusIdentity=${corpusIdentity} revision=${revision}/>
      <div className="wb-corpus-pair">
        <div>
          <p className="wb-hero-n">${fmtCount(h.real_c)} <span class="of">logical functions with real C</span></p>
          <p className="wb-hint">${fmtCount(h.placed_concrete)} concrete instances · ${fmtCount(h.unplaced_real_c)} without a logical id</p>
        </div>
        <div>
          <p className="wb-hero-n">${fmtByteExact(h.byte_exact)} <span class="of">byte-exact receipts</span></p>
          <p className="wb-hint">Not added to real C. A compile is not a match.</p>
        </div>
      </div>
      ${h.queued != null ? html`<p className="wb-hint">Queue still holds ${fmtCount(h.queued)} logical functions.</p>` : null}
      <p className="wb-claim">${claim || "This is a live view. It is not completion."}</p>
    </section>`;
  }

  function HealthStrip({ probes, atlasUrl }) {
    const list = probes || [];
    return html`<div className="wb-health" id="wb-health">
      ${list.map(function (p, i) {
        const text = (p && p.text) || "probe";
        const st = (p && p.state) || "unmeasured";
        const ok = st === "done" || st === "up";
        return html`<span key=${i} className=${"wb-health-chip" + (ok ? "" : " is-down")}>${text}</span>`;
      })}
      ${atlasUrl ? html`<a className="wb-health-chip" href=${atlasUrl} target="_blank" rel="noreferrer">Atlas :5173</a>` : null}
    </div>`;
  }

  function AtlasReact({ onToast }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");
    const [picked, setPicked] = useState(null);
    useEffect(function () {
      let gone = false;
      fetch("/atlas/api/loadProject", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })
        .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
        .then(function (pack) {
          if (gone) return;
          if (!pack.ok || pack.body.error) {
            setErr(pack.body.error || "Atlas project is not loaded.");
            setData(null);
            return;
          }
          setErr("");
          setData(pack.body);
        })
        .catch(function (e) { if (!gone) setErr(String(e && e.message || e)); });
      return function () { gone = true; };
    }, []);
    const fns = ((data && data.data && data.data.functions) || []).slice(0, 80);
    return html`<div className="wb-atlas-react">
      <p className="wb-hint">${data && data.platform ? ("Platform " + data.platform) : "In-tree Atlas API. Decomp Atlas on :5173 stays a separate app."}</p>
      ${err ? html`<p className="wb-hint">${err}</p>` : null}
      <table className="wb-fnb-table">
        <thead><tr><th>Function</th><th>C module</th><th>Calls</th></tr></thead>
        <tbody>
          ${fns.length ? fns.map(function (fn) {
            return html`<tr key=${fn.id || fn.name} className=${picked && picked.id === fn.id ? "on" : ""}
              onClick=${function () { setPicked(fn); if (onToast) onToast(fn.name || fn.id); }}>
              <td><code>${fn.name || fn.id}</code></td>
              <td>${fn.cModulePath || ""}</td>
              <td>${(fn.callsFunctions || []).length}</td>
            </tr>`;
          }) : html`<tr><td colspan="3">No Atlas index on this server yet.</td></tr>`}
        </tbody>
      </table>
      ${picked ? html`<pre className="wb-job-log">${(picked.cCode || picked.asmCode || "").slice(0, 4000)}</pre>` : null}
    </div>`;
  }

  function ReportReact({ report }) {
    const r = report || {};
    return html`<div className="wb-report-react">
      <div className="wb-corpus-pair">
        <p className="wb-hero-n">${fmtCount(r.logical)} <span class="of">logical recovered</span></p>
        <p className="wb-hero-n">${fmtCount(r.artifacts)} <span class="of">artifacts</span></p>
      </div>
      <p className="wb-hint">Unplaced ${fmtCount(r.unplaced)} · unbound ${fmtCount(r.unbound)}. Real C only.</p>
      <table className="wb-fnb-table">
        <thead><tr><th>Build</th><th>Artifacts</th><th>Logical</th><th>Concrete</th></tr></thead>
        <tbody>
          ${(r.by_build || []).map(function (b) {
            return html`<tr key=${b.slug}>
              <td><code>${b.slug}</code></td>
              <td>${fmtCount(b.artifacts)}</td>
              <td>${fmtCount(b.logical)}</td>
              <td>${fmtCount(b.concrete)}</td>
            </tr>`;
          })}
        </tbody>
      </table>
      <table className="wb-fnb-table">
        <thead><tr><th>Function</th><th>Build</th><th>Bytes</th><th>Convention</th><th>Logical</th></tr></thead>
        <tbody>
          ${(r.functions || []).map(function (fn, i) {
            return html`<tr key=${i}>
              <td><code>${fn.name || ""}</code></td>
              <td>${fn.slug || ""}</td>
              <td>${fmtCount(fn.size)}</td>
              <td>${fn.convention || ""}</td>
              <td>${fn.logical_id != null ? fn.logical_id : "—"}</td>
            </tr>`;
          })}
        </tbody>
      </table>
    </div>`;
  }

  function MissionReact({ mission }) {
    const m = mission || {};
    if (!m.ok) return html`<p className="wb-hint">${m.error || "No mission contract on disk."}</p>`;
    return html`<article className="wb-mission-react">
      <p className="wb-kicker">${m.id} · ${m.status}</p>
      <h3>${m.title || "Mission"}</h3>
      <p>${m.objective || ""}</p>
      <h4>Acceptance</h4>
      <ol>${(m.acceptance || []).map(function (item, i) { return html`<li key=${i}>${item}</li>`; })}</ol>
      <h4>Evidence paths</h4>
      <ul>${(m.evidence || []).map(function (item, i) { return html`<li key=${i}><code>${item}</code></li>`; })}</ul>
    </article>`;
  }

  function MatchAvailability({ match, selection, checks }) {
    const [data,setData]=useState(null),[error,setError]=useState("");
    useEffect(function () {
      let alive=true;const controller=new AbortController();setData(null);setError("");
      if(!Array.isArray(checks)&&selection)fetch("/dashboard/api/workbench/matching-availability?"+new URLSearchParams({match_ids:String(match.id),selection:selection}),{signal:controller.signal,cache:"no-store"})
        .then(function(r){return r.json().then(function(body){if(!r.ok||!body.ok)throw new Error(body.error||"Matching availability unavailable");return body;});})
        .then(function(body){if(!alive)return;const row=(body.rows||[]).find(function(item){return item.matchId===match.id&&item.srcBinary===match.src_binary&&item.dstBinary===match.dst_binary&&item.srcAddr===match.src_addr&&item.run===match.run;});if(body.selection!==selection||!row)throw new Error("The matching evidence changed. Refresh this page.");setData(row);})
        .catch(function(e){if(alive)setError(String(e.message||e));});
      return function(){alive=false;controller.abort();};
    },[selection,match.id,match.src_binary,match.dst_binary,match.src_addr,match.run,checks]);
    const inlineChecks=Array.isArray(checks);
    const channels=inlineChecks?checks:data&&data.channels||[];
    const receiptMissing=channels.filter(function(channel){return channel.reason==="no_method_execution_receipt";});
    const recorded=channels.filter(function(channel){return channel.reason!=="no_method_execution_receipt";});
    return html`<section className="wb-match-methods" aria-label="Recorded matching checks">
      <h4>Recorded checks</h4>
      ${!inlineChecks&&error?html`<p role="alert">${error}</p>`:!inlineChecks&&!data&&selection?html`<p role="status">Reading the selected candidate’s check receipts…</p>`:null}
      ${recorded.length?html`<ul>${recorded.map(function(channel){return html`<li key=${channel.channel}><strong>${channel.label}</strong><span>${channel.state}</span>${channel.reason?html`<small>${String(channel.reason).replace(/_/g," ")}</small>`:null}</li>`;})}</ul>`:null}
      ${receiptMissing.length?html`<p className="wb-match-gap">This run has no method-execution receipts for ${receiptMissing.length} checks. That means their execution is unknown, not that those tools are unavailable. The recorded candidate signals above remain inspectable.</p>`:null}
      ${(inlineChecks||data)&&!channels.length?html`<p>No check receipts were returned for this candidate.</p>`:null}
    </section>`;
  }

  function CorrespondenceBadge({ label, state, description }) {
    const [open,setOpen]=useState(false), tipId=React.useId(), trigger=useRef(null);
    const closeTimer=useRef(null);
    useEffect(function(){return function(){window.clearTimeout(closeTimer.current);};},[]);
    useEffect(function(){if(!open)return;const dismiss=function(event){if(event.type==="scroll"&&event.target&&event.target.closest&&event.target.closest(".wb-correspondence-tooltip"))return;setOpen(false);};window.addEventListener("resize",dismiss);window.addEventListener("scroll",dismiss,true);return function(){window.removeEventListener("resize",dismiss);window.removeEventListener("scroll",dismiss,true);};},[open]);
    const bounds=open&&trigger.current?trigger.current.getBoundingClientRect():null;
    const tipWidth=Math.min(480,window.innerWidth-24);
    const position=bounds?{left:Math.max(12,Math.min(bounds.left,window.innerWidth-tipWidth-12))+"px",top:Math.min(bounds.bottom+4,window.innerHeight-120)+"px",width:tipWidth+"px",maxHeight:Math.max(100,window.innerHeight-Math.min(bounds.bottom+4,window.innerHeight-120)-12)+"px"}:undefined;
    const symbol=state==="stored"?"◇":state==="blocked"?"⊗":"△";
    return html`<span className="wb-correspondence-badge" onMouseEnter=${()=>{window.clearTimeout(closeTimer.current);setOpen(true);}} onMouseLeave=${()=>{if(document.activeElement!==trigger.current)closeTimer.current=window.setTimeout(()=>setOpen(false),150);}}>
      <button ref=${trigger} type="button" className=${"wb-correspondence-evidence is-"+state} aria-expanded=${open} aria-describedby=${open?tipId:undefined} onFocus=${()=>setOpen(true)} onBlur=${()=>setOpen(false)} onClick=${()=>setOpen(true)} onKeyDown=${event=>{if(event.key==="Escape"){event.preventDefault();setOpen(false);}}}><span aria-hidden="true">${symbol}</span> ${label}</button>
      ${open?html`<span id=${tipId} role="tooltip" className="wb-correspondence-tooltip" style=${position}>${description}</span>`:null}
    </span>`;
  }

  function ReviewReact({ onRefresh, binaryIds, onInspect, focus, corpusIdentity }) {
    const membershipKey = Array.from(new Set((binaryIds || []).map(Number))).sort(function (a, b) { return a - b; }).join(",");
    const requestFocusKey=focus?[focus.binaryId,focus.addr].join(":"):"";
    const hasFocus=Boolean(focus&&focus.binaryId!=null&&focus.addr!=null&&Number.isSafeInteger(Number(focus.binaryId))&&Number.isSafeInteger(Number(focus.addr))&&Number(focus.binaryId)>=0&&Number(focus.addr)>=0);
    const scopeKey=String(corpusIdentity||"")+"|"+membershipKey+"|"+requestFocusKey;
    const rowKey=function(row){return row.correspondenceKey||"match:"+row.match.id;};
    /* Deep links from panels/entities.py carry review_after_id and
       review_page_size. The retired score:id cursor is refused by name. */
    const start = useMemo(function () {
      const query = new URLSearchParams(window.location.search);
      const rawAfter = query.get("review_after_id") || "";
      const rawSize = (query.get("review_page_size") || query.get("page_size") || "").trim().toLowerCase();
      const after = /^[0-9]{1,19}$/.test(rawAfter) && Number.isSafeInteger(Number(rawAfter)) ? Number(rawAfter) : 0;
      let size = /^[0-9]{1,6}$/.test(rawSize) && Number(rawSize) > 0 ? Number(rawSize) : 50;
      const capped = rawSize === "all" || size > 100;
      if (capped) size = 100;
      return {
        after: after, size: size, capped: capped,
        badCursor: Boolean(rawAfter) && !after && rawAfter !== "0",
        legacy: Boolean(query.get("review_after")) || /^-?[0-9.]+(e-?[0-9]+)?:[0-9]+$/i.test(query.get("after") || "")
      };
    }, []);
    const pageSize = start.size;
    const legacyCursor = start.legacy;
    /* Bumped to stop a poll loop: Stop waiting, a new poll, or unmount. */
    const watchSeq = useRef(0);
    const confirmRef = useRef(null);
    /* Tracks mount state across an await so a resumed callback (e.g. send())
       does not touch state or start a fresh watch() after unmount. Separate
       from watchSeq, which only defeats an in-flight watch's own poll loop. */
    const mountedRef = useRef(true);
    useEffect(function () { return function () { watchSeq.current++; mountedRef.current = false; }; }, []);
    const [page, setPage] = useState({ rows: [], total: 0, nextAfterId: null, selection: "",scope:scopeKey });
    const [afterId, setAfterId] = useState(legacyCursor ? 0 : start.after);
    const [cursorScope,setCursorScope]=useState(scopeKey);
    const [history, setHistory] = useState([]);
    const [nonce, setNonce] = useState(0);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState([]);
    const [submitting, setSubmitting] = useState(false);
    const [watching, setWatching] = useState("");
    /* Open decision jobs: [{id, tokens, matchIds}]. Their rows stay locked. */
    const [jobs, setJobs] = useState([]);
    const [confirm, setConfirm] = useState(null);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [focusedMatch, setFocusedMatch] = useState(null);
    const [graphEvidence,setGraphEvidence]=useState(null);
    const receiveGraphEvidence=React.useCallback(function(value){setGraphEvidence(value);},[]);
    const preferenceStorage="agentdecompile.correspondence-inspection.v1";
    const [inspectionPreferences,setInspectionPreferences]=useState(function(){try{const value=JSON.parse(localStorage.getItem(preferenceStorage)||"{}");return value&&typeof value==="object"&&!Array.isArray(value)?value:{};}catch(_){return {};}});
    function retainInspection(value) {
      setInspectionPreferences(function(old){const next=Object.assign({},old);delete next[scopeKey];if(value)next[scopeKey]=value;const bounded=Object.fromEntries(Object.entries(next).slice(-128));try{localStorage.setItem(preferenceStorage,JSON.stringify(bounded));}catch(_){/* The in-memory choice remains usable if storage is unavailable. */}return bounded;});
    }
    const [filter, setFilter] = useState("");
    const [receiptOpen, setReceiptOpen] = useState(false);
    const [expertOpen,setExpertOpen]=useState(false);
    useEffect(function(){setFilter("");setReceiptOpen(false);setConfirm(null);setExpertOpen(false);},[scopeKey]);
    useEffect(function(){setFocusedMatch(null);},[scopeKey]);
    useEffect(function () {
      let dead = false; const controller=new AbortController();
      if(binaryIds&&(!corpusIdentity||!membershipKey||!hasFocus)) {
        setLoading(false);setError("");setPage({rows:[],total:null,nextAfterId:null,selection:"",scope:scopeKey});
        return function(){dead=true;controller.abort();};
      }
      setLoading(true);setError("");
      const cursor=cursorScope===scopeKey?afterId:0;
      const query=new URLSearchParams({after_id:String(cursor),limit:String(pageSize)});
      if(binaryIds) {
        query.set("binary_ids",membershipKey);
        query.set("corpus_identity",String(corpusIdentity));
        if(page.selection&&page.corpusIdentity===corpusIdentity&&page.membershipKey===membershipKey)query.set("selection",page.selection);
        if(hasFocus) {query.set("binary_id",String(Number(focus.binaryId)));query.set("addr",String(Number(focus.addr)));}
      }
      fetch((binaryIds?"/api/v1/projects/correspondence":API.matchReview) + "?" + query, { cache: "no-store", signal:controller.signal }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok || data.ok === false) throw reviewFailure("refused", data.error || "", data.error ? "" : "Could not load review rows (" + res.status + ").");
          return data;
        });
      }).then(function (data) {
        if (dead) return;
        if(binaryIds) {
          const returned=data.scope||{},expectedFocus=hasFocus;
          if(data.corpusIdentity!==corpusIdentity||!Array.isArray(returned.binaryIds)||returned.binaryIds.slice().sort(function(a,b){return a-b;}).join(",")!==membershipKey||returned.binaryId!==(expectedFocus?Number(focus.binaryId):null)||returned.addr!==(expectedFocus?Number(focus.addr):null))throw new Error("The returned candidate scope does not match this project, database and function cursor. Refresh project facts before continuing.");
        }
        const allowed = new Set((binaryIds || []).map(Number));
        const rows = (data.identityCorrespondences||[]).concat(data.rows || []).filter(function (row) { return !binaryIds || allowed.has(Number(row.match.src_binary)) && allowed.has(Number(row.match.dst_binary)); });
        setPage({ rows: rows, total: binaryIds ? rows.length : data.total, nextAfterId: data.nextAfterId == null ? null : data.nextAfterId, selection: data.selection || "",scope:scopeKey,corpusIdentity:corpusIdentity,membershipKey:membershipKey,preferredMatchId:data.preferredMatchId,preferredByBinary:data.preferredByBinary||[] });
        if(cursorScope!==scopeKey) {setCursorScope(scopeKey);setAfterId(0);setHistory([]);}
        setError(""); setConfirm(null);
        /* Keep checked rows that are still on this page with the same token. */
        const present = rows.map(function (row) { return row.token; });
        setSelected(function (old) { return old.filter(function (token) { return present.indexOf(token) >= 0; }); });
      }).catch(function (err) {
        if (dead) return;
        setPage({ rows: [], total: 0, nextAfterId: null, selection: "",scope:scopeKey });
        setSelected([]); setConfirm(null);
        setError(String((err && err.message) || err));
      }).then(function () { if (!dead) setLoading(false); });
      return function () { dead = true; controller.abort(); };
    }, [afterId, nonce, scopeKey]);
    useEffect(function () {
      if (!confirm || !confirmRef.current) return;
      confirmRef.current.scrollIntoView({ block: "nearest" });
      const first = confirmRef.current.querySelector("button");
      if (first) first.focus({ preventScroll: true });
    }, [confirm]);
    function reload() { setNonce(function (n) { return n + 1; }); }
    function closeJob(jobId) { setJobs(function (old) { return old.filter(function (job) { return job.id !== jobId; }); }); }
    async function watch(jobId) {
      const seq = ++watchSeq.current;
      const stopped = function () { return seq !== watchSeq.current; };
      setWatching(jobId); setError("");
      try {
        const decisions = await observeReviewDecision(jobId, stopped);
        if (stopped()) return;
        if (decisions) {
          closeJob(jobId); setMessage(reviewOutcomeText(decisions));
          reload();
          if (onRefresh) onRefresh();
        } else setMessage("Job " + jobId + " is still running. Its rows stay locked until you check its result or refresh the rows.");
      } catch (err) {
        if (stopped()) return;
        setMessage("");
        setError(String((err && err.message) || err));
        if (err && err.kind) {
          closeJob(jobId);
          if (err.refresh) reload();
        }
        /* Any other failure only means the job could not be read. Keep it open. */
      } finally { if (!stopped()) setWatching(""); }
    }
    function ask(rows, decision) {
      if (busy || !rows.length) return;
      if(rows.some(function(row){return !eligible(row);})) {setError("Only current review candidates with their own unchanged decision token can be edited here.");return;}
      if(decision==="accept"&&rows.some(function(row){return !mayRecordReview(row);})) {setError("A conflicting or ambiguous candidate cannot be advanced by a browser review decision. Inspect caller/callee evidence and resolve the competing assignments first.");return;}
      setError(""); setConfirm({ rows: rows, decision: decision,scope:scopeKey });
    }
    async function send() {
      if (!confirm || busy || confirm.scope!==scopeKey) return;
      const rows = confirm.rows, decision = confirm.decision;
      setConfirm(null); setSubmitting(true); setError(""); setMessage("Sending the decision…");
      try {
        const jobId = await submitReviewRows(rows.map(function (row) {
          return { match_id: row.match.id, token: row.token };
        }), page.selection, decision);
        if (!mountedRef.current) return;
        const tokens = rows.map(function (row) { return row.token; });
        setJobs(function (old) { return old.concat([{ id: jobId, selection:page.selection, tokens: tokens, matchIds: rows.map(function (row) { return row.match.id; }) }]); });
        setSelected(function (old) { return old.filter(function (token) { return tokens.indexOf(token) < 0; }); });
        setMessage("Decision sent as job " + jobId + ". Waiting for the server to record it.");
        setSubmitting(false);
        await watch(jobId);
      } catch (err) {
        if (!mountedRef.current) return;
        setMessage("");
        setError(String((err && err.message) || err));
        if (err && err.refresh) reload();
      } finally { if (mountedRef.current) setSubmitting(false); }
    }
    function stopWaiting() {
      const jobId = watching;
      watchSeq.current++;
      setWatching("");
      setMessage("Stopped waiting for job " + jobId + ". It may still save. Its rows stay locked until you check its result or refresh the rows.");
    }
    function refreshRows() {
      if (jobs.length) setMessage("Refreshing the candidate snapshot. Pending decisions stay locked until their jobs finish; already decided candidates leave the list.");
      reload();
    }
    const isLocked=function(row){return jobs.some(function(job){return job.tokens.includes(row.token)||job.selection===page.selection&&job.matchIds.includes(row.match.id);});};
    const scopePending=page.scope!==scopeKey;
    const currentRows=scopePending?[]:page.rows;
    const busy = loading || scopePending || submitting || Boolean(watching);
    const eligible = function (row) { return Boolean(row.match&&row.match.status==="review"&&row.token && page.selection && Number.isSafeInteger(row.match.id)) && !isLocked(row); };
    const chosen = currentRows.filter(function (row) { return selected.indexOf(row.token) >= 0 && eligible(row); });
    const slug = function (row, i) { const b = (row.binaries || [])[i] || {}; return (b.row && b.row.slug) || (i ? row.match.dst_binary : row.match.src_binary); };
    const hex = function (value) { return Number.isSafeInteger(value) ? "0x" + value.toString(16) : String(value == null ? "Unavailable" : value); };
    const policy = function(row) { return row.decision || {state:"unresolved",headline:"Evidence assessment not returned",recommendation:"Inspect the recorded evidence before requesting verification.",reasons:[],signals:[],automaticEligible:false}; };
    const mayRecordReview=function(row){const decision=policy(row);return row.match.status==="review"&&Boolean(row.decision)&&decision.state!=="blocked"&&decision.state!=="ambiguous";};
    const groupKey = function(row) { return [row.match.src_binary,row.match.src_addr,row.match.dst_binary].join(":"); };
    const preferredKeys=new Set((page.preferredByBinary||[]).map(function(item){return item.correspondenceKey||(Number.isSafeInteger(item.matchId)?"match:"+item.matchId:"");}).filter(Boolean));
    function preferredRow(rows) {
      return rows.find(function(row){return Number.isSafeInteger(page.preferredMatchId)&&row.match.id===page.preferredMatchId&&row.storedSelection===true;})||rows.find(function(row){return row.storedSelection===true&&preferredKeys.has(rowKey(row));})||rows.find(function(row){return row.storedSelection===true;})||rows[0];
    }
    const groups = useMemo(function() {
      const grouped=new Map(),needle=filter.trim().toLowerCase();
      currentRows.forEach(function(row) {
        const key=groupKey(row);if(!grouped.has(key))grouped.set(key,{key:key,rows:[]});grouped.get(key).rows.push(row);
      });
      return Array.from(grouped.values()).map(function(group) {
        group.rows.sort(function(a,b) {
          const ap=policy(a),bp=policy(b);
          const priority=function(decision){return decision.state==="blocked"?0:decision.state==="ambiguous"?1:2;};
          /* Ranking selects an inspection cursor only. It never authorizes a decision. */
          return Number(b.storedSelection===true)-Number(a.storedSelection===true)||Number(preferredKeys.has(rowKey(b)))-Number(preferredKeys.has(rowKey(a)))||Number(bp.automaticEligible===true)-Number(ap.automaticEligible===true)||
            priority(bp)-priority(ap)||
            (Number(b.match.score)||0)-(Number(a.match.score)||0)||
            (Number(b.match.margin)||0)-(Number(a.match.margin)||0)||a.match.id-b.match.id;
        });return group;
      }).filter(function(group) {
        return !needle||group.rows.some(function(row) {
          const decision=policy(row);
          return [slug(row,0),slug(row,1),row.functions&&row.functions.source&&row.functions.source.name,row.functions&&row.functions.destination&&row.functions.destination.name,hex(row.match.src_addr),hex(row.match.dst_addr),decision.headline,decision.recommendation].join(" ").toLowerCase().includes(needle);
        });
      });
    },[currentRows,filter,page.preferredByBinary]);
    const savedInspection=inspectionPreferences[scopeKey];
    const restoredRow=savedInspection&&currentRows.find(function(row){return rowKey(row)===savedInspection.key&&row.match.src_binary===savedInspection.srcBinary&&row.match.src_addr===savedInspection.srcAddr&&row.match.dst_binary===savedInspection.dstBinary&&row.match.dst_addr===savedInspection.dstAddr&&(row.token||null)===savedInspection.token;});
    useEffect(function() {
      const matching=groups.flatMap(function(group){return group.rows;}).filter(function(row){return focus&&(Number(row.match.src_binary)===Number(focus.binaryId)&&Number(row.match.src_addr)===Number(focus.addr)||Number(row.match.dst_binary)===Number(focus.binaryId)&&Number(row.match.dst_addr)===Number(focus.addr));});
      if(matching.length)setFocusedMatch(function(){const chosen=restoredRow||preferredRow(matching);return rowKey(chosen);});
    },[requestFocusKey,page.rows,inspectionPreferences]);
    const defaultRow=preferredRow(groups.flatMap(function(group){return group.rows;}));
    const activeGroup=groups.find(function(group){return group.rows.some(function(row){return rowKey(row)===focusedMatch;});})||groups.find(function(group){return defaultRow&&group.key===groupKey(defaultRow);})||groups[0];
    const activeRow=activeGroup&&(activeGroup.rows.find(function(row){return rowKey(row)===focusedMatch;})||preferredRow(activeGroup.rows));
    const visibleRows=groups.flatMap(function(group){return group.rows;});
    const duplicateTargets=new Set(),duplicateSources=new Set();
    const conflictingBatch=chosen.some(function(row) {
      if(row.match.relation&&row.match.relation!=="one_to_one")return false;
      const src=[row.match.src_binary,row.match.src_addr,row.match.dst_binary].join(":"),dst=[row.match.src_binary,row.match.dst_binary,row.match.dst_addr].join(":");
      const collision=duplicateTargets.has(dst)||duplicateSources.has(src);duplicateTargets.add(dst);duplicateSources.add(src);return collision;
    });
    function inspect(row,side,retain) {
      setFocusedMatch(rowKey(row));setReceiptOpen(false);
      if(retain!==false)retainInspection({key:rowKey(row),srcBinary:row.match.src_binary,srcAddr:row.match.src_addr,dstBinary:row.match.dst_binary,dstAddr:row.match.dst_addr,token:row.token||null});
      if(onInspect)onInspect({row:row,side:side,binaryId:side==="source"?row.match.src_binary:row.match.dst_binary,slug:slug(row,side==="source"?0:1),addr:side==="source"?row.match.src_addr:row.match.dst_addr,decision:policy(row)});
    }
    const confirmText = function (rows, decision) {
      const ids = rows.map(function (row) { return String(row.match.id); });
      const list = ids.length > 6 ? ids.slice(0, 6).join(", ") + " and " + (ids.length - 6) + " more" : ids.join(", ");
      const noun = rows.length === 1 ? "match" : rows.length + " matches";
      return decision === "accept"
        ? "Record a manual review decision for " + noun + " (" + list + ") and move its status to verify? This does not run matching checks, verify source or establish byte equality. This cannot be undone here."
        : "Reject " + noun + " (" + list + ")? This cannot be undone here.";
    };
    const decision=activeRow&&policy(activeRow);
    const stateLabel=function(state){return String(state||"unresolved").replace(/_/g," ");};
    const functionName=function(row,side){const value=row.functions&&row.functions[side];return value&&value.name||hex(side==="source"?row.match.src_addr:row.match.dst_addr);};
    function peerEndpoint(row) {
      const focusedDestination=hasFocus&&Number(row.match.dst_binary)===Number(focus.binaryId)&&Number(row.match.dst_addr)===Number(focus.addr);
      const focusedSource=hasFocus&&Number(row.match.src_binary)===Number(focus.binaryId)&&Number(row.match.src_addr)===Number(focus.addr);
      const side=focusedDestination&&!focusedSource?"source":"destination";
      return {side:side,binaryId:side==="source"?row.match.src_binary:row.match.dst_binary,addr:side==="source"?row.match.src_addr:row.match.dst_addr,slug:slug(row,side==="source"?0:1),name:functionName(row,side)};
    }
    const reasons=decision&&decision.reasons||[];
    const metricValue=function(value){return typeof value==="number"&&Number.isFinite(value)?Number(value.toPrecision(4)).toString():"Not recorded";};
    const evidenceTip=decision?[decision.headline,decision.recommendation,...reasons.map(function(reason){return reason.text;}),"Recorded comparisons: "+(decision.signals||[]).map(function(signal){return signal.label+": "+metricValue(signal.value);}).join(", "),decision.claimBoundary,activeRow&&activeRow.storedSelection===true?"Recorded identity does not establish source interchangeability, ABI/layout compatibility or byte parity; those require separate acceptance evidence.":null].filter(Boolean).join("\n"):"No correspondence evidence is loaded.";
    const decisiveReason=reasons.find(function(reason){return ["quarantined","contract_conflict","destination_collision","source_alternatives","no_distinguishing_content","evidence_gap"].includes(reason.code);});
    const stored=activeRow&&activeRow.storedSelection===true;
    const preferredForPeer=activeRow&&rowKey(preferredRow(activeGroup.rows))===rowKey(activeRow);
    function observedChoices(row) {
      const targets=new Set([row.match.dst_addr]),sources=new Set([row.match.src_addr]);
      currentRows.filter(function(item){return item.match.src_binary===row.match.src_binary&&item.match.dst_binary===row.match.dst_binary;}).forEach(function(item){
        if(item.match.src_addr===row.match.src_addr&&Number.isSafeInteger(item.match.dst_addr))targets.add(item.match.dst_addr);
        if(item.match.dst_addr===row.match.dst_addr&&Number.isSafeInteger(item.match.src_addr))sources.add(item.match.src_addr);
      });
      const assessment=policy(row);
      (assessment.alternatives||[]).forEach(function(item){
        if(!item||typeof item!=="object")return;
        if(item.srcAddr===row.match.src_addr&&Number.isSafeInteger(item.dstAddr))targets.add(item.dstAddr);
        if(item.dstAddr===row.match.dst_addr&&Number.isSafeInteger(item.srcAddr))sources.add(item.srcAddr);
      });
      (assessment.producerAlternatives||[]).forEach(function(item){if(item&&typeof item==="object"&&Number.isSafeInteger(item.dst))targets.add(item.dst);});
      return {targets:targets.size,otherSources:sources.size-1,truncated:assessment.alternativesTruncated===true||page.nextAfterId!==null};
    }
    const choices=activeRow&&observedChoices(activeRow);
    const graphSummary=activeRow&&graphEvidence&&graphEvidence.sourceBinary===activeRow.match.src_binary&&graphEvidence.sourceAddr===activeRow.match.src_addr&&graphEvidence.targetBinary===activeRow.match.dst_binary&&graphEvidence.targetAddr===activeRow.match.dst_addr?graphEvidence:null;
    const graphCount=function(key){return graphSummary&&Number.isSafeInteger(graphSummary[key])&&graphSummary[key]>=0?String(graphSummary[key]):"Not loaded";};
    const selectionCaption=restoredRow&&activeRow&&rowKey(restoredRow)===rowKey(activeRow)?"Browser-local inspection choice":stored?"Automatic · recorded identity":preferredForPeer?"Automatic · ranked proposal":"Inspected alternative";
    function correspondenceStatus(row) {
      const assessment=policy(row);
      if(row.storedSelection===true)return {state:"stored",symbol:"◇",label:"Recorded identity"};
      if(assessment.state==="blocked")return {state:"blocked",symbol:"⊗",label:"Conflicting evidence"};
      if(assessment.state==="ambiguous") {const count=observedChoices(row);return {state:"ambiguous",symbol:"△",label:count.targets>1?count.targets+" targets observed":count.otherSources?count.otherSources+" other "+(count.otherSources===1?"source claims":"sources claim")+" target":"Unresolved assignment"};}
      return {state:"provisional",symbol:"△",label:"Provisional correspondence"};
    }
    const CallComparison=window.AgentDecompileCallComparison;
    function inspectGraphNode(node) {
      if(!onInspect||!activeRow)return;
      onInspect({row:activeRow,side:node.side||"neighbor",binaryId:node.binaryId,slug:node.slug,addr:node.addr,name:node.name,decision:decision});
    }
    const picker=html`<div className="wb-correspondence-picker"><label>Inspect counterpart<select value=${activeRow?rowKey(activeRow):""} disabled=${busy||!visibleRows.length} onChange=${function(event){const row=visibleRows.find(function(row){return rowKey(row)===event.target.value;});if(row)inspect(row,peerEndpoint(row).side);}}>${groups.map(function(group){return html`<optgroup key=${group.key} label=${functionName(group.rows[0],"source")+" · "+slug(group.rows[0],0)+" → "+slug(group.rows[0],1)}>${group.rows.map(function(row){const peer=peerEndpoint(row),status=correspondenceStatus(row);return html`<option key=${rowKey(row)} value=${rowKey(row)}>${peer.slug} · ${peer.name} ${hex(peer.addr)} · ${status.label}</option>`;})}</optgroup>`;})}</select></label><label>Filter loaded counterparts<input type="search" value=${filter} placeholder="Build, function, address or reason" onInput=${function(event){setFilter(event.target.value);}}/></label></div>`;
    return html`<section className="wb-review-react wb-match-workspace wb-correspondence" aria-label="Cross-build correspondence" aria-busy=${loading||scopePending}>
      <header className="wb-correspondence-toolbar"><h3>Correspondence</h3>
        ${decision?html`<${CorrespondenceBadge} key=${rowKey(activeRow)} state=${correspondenceStatus(activeRow).state} label=${correspondenceStatus(activeRow).label} description=${evidenceTip}/>`:null}
        ${savedInspection?html`<button type="button" className="wb-btn wb-btn-mini" onClick=${function(){retainInspection(null);if(defaultRow)inspect(defaultRow,peerEndpoint(defaultRow).side,false);else setFocusedMatch(null);}} title="Forget this browser's inspected correspondence and follow the automatic evidence-based choice">Reset to automatic</button>`:null}
        <button type="button" className="wb-btn wb-btn-mini" disabled=${loading||submitting} onClick=${refreshRows} title="Read the current recorded correspondence snapshot; does not rerun analysis">Refresh</button>
      </header>
      ${legacyCursor ? html`<p role="alert">${REVIEW_ERRORS.ranked_cursor_retired} Showing the first page.</p>` : null}
      ${start.badCursor ? html`<p role="alert">The page cursor in this link is not a match ID. Showing the first page.</p>` : null}
      ${start.capped ? html`<p className="wb-hint">A bounded correspondence snapshot holds at most 100 proposals.</p>` : null}
      ${error ? html`<p role="alert">${error}</p>` : null}
      ${message ? html`<p role="status">${message}</p>` : null}
      ${savedInspection&&!scopePending&&!loading&&!restoredRow?html`<p className="wb-hint" role="status">The saved inspection is absent or changed in this bounded snapshot. Showing the automatic correspondence from the loaded evidence instead.</p>`:null}
      ${jobs.map(function (job) {
        return html`<p key=${job.id}>Decision job <a href=${API.jobs + "/" + encodeURIComponent(job.id)} target="_blank" rel="noreferrer">${job.id}</a>
          ${" for match" + (job.matchIds.length === 1 ? " " : "es ") + job.matchIds.join(", ") + " "}
          ${watching === job.id
            ? html`<button type="button" className="wb-btn wb-btn-mini" onClick=${stopWaiting}>Stop waiting</button>`
            : html`<button type="button" className="wb-btn wb-btn-mini" disabled=${busy} onClick=${function () { watch(job.id); }}>Check result</button>`}</p>`;
      })}
      ${confirm&&confirm.scope===scopeKey ? html`<div ref=${confirmRef} className="review-confirm" role="group" aria-label="Confirm match decision">
        <p>${confirmText(confirm.rows, confirm.decision)}</p>
        <button type="button" className="wb-btn wb-btn-mini" onClick=${function () { setConfirm(null); }}>Cancel</button>
        <button type="button" className="wb-btn wb-btn-mini" onClick=${send}>${confirm.decision === "accept" ? "Confirm review decision" : "Confirm rejection"}</button>
      </div>` : null}
      ${!activeRow&&filter?picker:null}
      ${activeRow?html`<div className="wb-correspondence-analysis"><aside className="wb-correspondence-summary" aria-label="Correspondence selection and recorded evidence">
        ${picker}<p className="wb-correspondence-selection">${selectionCaption}<small>Inspection only · recorded identities unchanged</small></p>
        <dl className="wb-correspondence-metrics">
          <div title="Distinct target addresses recorded for this source and peer build in the loaded rows and bounded evidence shortlist. This is not an exhaustive uniqueness check."><dt>Targets observed</dt><dd>${choices.targets}${choices.truncated?"+":""}</dd></div>
          <div title="Other recorded source addresses that claim this same target in this build pair; separate from alternative targets for this source."><dt>Other sources claiming target</dt><dd>${choices.otherSources}${choices.truncated?"+":""}</dd></div>
          <div title="Uncalibrated matcher ranking value, not an identity probability or proof."><dt>Matcher score</dt><dd>${metricValue(activeRow.match.score)}</dd></div>
          <div title="Margin recorded by this candidate's producer; not recomputed from the visible page."><dt>Recorded margin</dt><dd>${metricValue(activeRow.match.margin)}</dd></div>
          <div title="Caller pairs connected by usable recorded logical identities in the bounded call comparison. These links are not independent proof of this candidate."><dt>Linked caller pairs</dt><dd>${graphCount("callers")}${graphSummary&&graphSummary.truncated?"+":""}</dd></div>
          <div title="Callee pairs connected by usable recorded logical identities in the bounded call comparison. Missing links do not establish disagreement."><dt>Linked callee pairs</dt><dd>${graphCount("callees")}${graphSummary&&graphSummary.truncated?"+":""}</dd></div>
          <div title="This read API does not report measured opposing caller/callee evidence. Unaligned neighbors must not be treated as contradictory calls."><dt>Opposing call evidence</dt><dd>Not recorded</dd></div>
          <div><dt>Calling contract</dt><dd>${decision.contract==="conflict"?"Conflict":decision.contract==="compatible"?"Compatible":"Not recorded"}</dd></div>
        </dl>
        ${(decision.signals||[]).length?html`<dl className="wb-correspondence-signals" aria-label="Recorded ranking inputs">${decision.signals.map(function(signal){return html`<div key=${signal.key}><dt>${signal.label}</dt><dd>${metricValue(signal.value)}</dd></div>`;})}</dl>`:null}
        ${graphSummary&&graphSummary.ambiguousNeighborIdentities?html`<p className="wb-correspondence-reason">${graphSummary.ambiguousNeighborIdentities} neighbor identities are ambiguous; they are not supporting links.</p>`:null}
        ${decisiveReason?html`<p className="wb-correspondence-reason">${decisiveReason.text}</p>`:null}
        ${Number.isSafeInteger(decision.dependencyCount)&&decision.dependencyCount>0?html`<small className="wb-correspondence-lineage">Derived from ${decision.dependencyCount} recorded ${decision.dependencyCount===1?"anchor":"anchors"}; not independent checks.</small>`:null}
      </aside><div className="wb-correspondence-pair">
        ${CallComparison?html`<${CallComparison} binaryIds=${binaryIds||[]} corpusIdentity=${corpusIdentity} source=${{binaryId:activeRow.match.src_binary,addr:activeRow.match.src_addr,name:functionName(activeRow,"source"),slug:slug(activeRow,0)}} target=${{binaryId:activeRow.match.dst_binary,addr:activeRow.match.dst_addr,name:functionName(activeRow,"destination"),slug:slug(activeRow,1)}} claimState=${correspondenceStatus(activeRow).state} claimDescription=${evidenceTip} onInspect=${inspectGraphNode} onEvidenceSummary=${receiveGraphEvidence}/>`:html`<p className="wb-hint">The paired call-graph component is not loaded. No neighborhood alignment can be shown from this page.</p>`}
        <footer className="wb-correspondence-footer"><span title=${evidenceTip}>${stored?"Recorded identity · byte parity not established here":decision.state==="blocked"?"Propagation blocked":"Ranked inspection proposal · identity unconfirmed"}</span><button type="button" className="wb-btn wb-btn-mini" aria-expanded=${expertOpen} onClick=${function(){setExpertOpen(!expertOpen);}}>${activeRow.match.status==="review"?"Expert controls":"Evidence details"}</button></footer>
        ${expertOpen?html`<section className="wb-correspondence-expert" aria-label="Optional expert correspondence controls">${activeRow.match.status==="review"?html`<p>These optional controls change review status, not the inspected graph. Automatic evidence acquisition belongs to the pipeline. A manual decision does not run verification.</p>`:html`<p>This existing mapping is inspection-only here. Its stored status cannot be changed through candidate review controls.</p>`}<div className="wb-match-decision">${activeRow.match.status==="review"?html`<span>${isLocked(activeRow)?"This candidate has a decision pending.":mayRecordReview(activeRow)?"A manual decision changes status to verify without establishing identity, source or runtime proof.":"Promotion is blocked while evidence is conflicting or ambiguous."}</span>`:null}<div>${activeRow.match.status==="review"?html`<button type="button" className="wb-btn wb-btn-mini" disabled=${busy||Boolean(confirm)||!eligible(activeRow)||!mayRecordReview(activeRow)} onClick=${function(){ask([activeRow],"accept");}}>Record manual decision</button><button type="button" className="wb-btn wb-btn-mini" disabled=${busy||Boolean(confirm)||!eligible(activeRow)} onClick=${function(){ask([activeRow],"reject");}}>Reject proposal</button>`:null}<button type="button" className="wb-btn wb-btn-mini" aria-expanded=${receiptOpen} onClick=${function(){setReceiptOpen(!receiptOpen);}}>${receiptOpen?"Hide technical receipt":"Inspect technical receipt"}</button></div></div>
          ${receiptOpen?html`<section className="wb-match-receipt"><h4>${activeRow.match.status==="identity"?"Logical identity "+(activeRow.identityBinding&&activeRow.identityBinding.logicalId):"Candidate "+activeRow.match.id} · ${stateLabel(activeRow.match.relation||"relation not recorded")}</h4>${activeRow.match.run?html`<p>Recorded run: <code>${activeRow.match.run}</code></p>`:null}<pre>${activeRow.identityBinding?JSON.stringify(activeRow.identityBinding,null,2):activeRow.match.evidence||"No raw evidence was recorded."}</pre></section>`:null}
          ${activeGroup.rows.some(function(row){return row.match.status==="review";})?html`<div className="wb-correspondence-manual-list">${activeGroup.rows.filter(function(row){return row.match.status==="review";}).map(function(row){return html`<label key=${rowKey(row)}><input type="checkbox" aria-label=${"Include proposal "+row.match.id+" in a manual decision"} checked=${selected.indexOf(row.token)>=0} disabled=${busy||!eligible(row)} onChange=${function(event){const checked=event.target.checked;setSelected(function(old){return checked?old.filter(function(token){return token!==row.token;}).concat([row.token]):old.filter(function(token){return token!==row.token;});});}}/><span>${functionName(row,"destination")} <code>${hex(row.match.dst_addr)}</code></span></label>`;})}</div>`:null}
          ${chosen.length?html`<div className="wb-match-batch"><span>${chosen.length} selected</span><button type="button" className="wb-btn wb-btn-mini" disabled=${busy||Boolean(confirm)||conflictingBatch||chosen.some(function(row){return !mayRecordReview(row);})} onClick=${function(){ask(chosen,"accept");}}>Record selected decisions</button><button type="button" className="wb-btn wb-btn-mini" disabled=${busy||Boolean(confirm)} onClick=${function(){ask(chosen,"reject");}}>Reject selected</button>${conflictingBatch?html`<p role="status">Competing one-to-one assignments cannot be promoted together.</p>`:null}</div>`:null}
        </section>`:null}
      </div></div>`:!loading&&!scopePending&&!error?html`<p className="wb-match-empty">${binaryIds&&(!corpusIdentity||!membershipKey)?"Load project facts to bind correspondence to this project’s builds.":binaryIds&&!hasFocus?"Choose a function to show its automatic cross-build correspondence.":filter?"No loaded correspondences match this filter.":binaryIds?"No correspondence proposal is recorded for this function in the selected builds. This does not establish absence of a counterpart.":"No correspondence proposals are recorded in this snapshot."}</p>`:loading||scopePending?html`<p role="status">Reading the recorded correspondence for the current function…</p>`:null}
      ${page.nextAfterId!==null||history.length?html`<div className="wb-toolbar wb-match-pagination"><button type="button" className="wb-btn wb-btn-mini" disabled=${loading||!history.length} onClick=${function(){setAfterId(history[history.length-1]);setHistory(history.slice(0,-1));}}>Previous proposals</button><button type="button" className="wb-btn wb-btn-mini" disabled=${loading||page.nextAfterId===null} onClick=${function(){setHistory(history.concat([afterId]));setAfterId(page.nextAfterId);}}>More proposals</button><span>Bounded recorded snapshot, not an exhaustive uniqueness claim.</span></div>`:null}
    </section>`;
  }

  function SourcePreview({ text, name, addr, slug, source, path, truncated, previous, status, language, reason }) {
    const [wrap,setWrap]=useState(false),[feedback,setFeedback]=useState("");
    const tierDescriptionId=React.useId();
    useEffect(function(){setFeedback("");},[text,addr,slug]);
    const assembly=language==="assembly-listing";
    const tierDescription=assembly?"This is a disassembly observation, not buildable .S fallback source. Assembly-floor artifacts belong in the byte-accurate export and do not count as recovered C.":"Readable source is not matching C until its compiled output has a current source/target-bound acceptance receipt. No such proof accompanies this preview.";
    const tokens=useMemo(function() {
      if(assembly)return [text];
      const keywords=new Set("alignas alignof asm auto break case catch class const constexpr continue decltype default delete do else enum explicit extern false for friend goto if inline namespace new noexcept nullptr operator private protected public register reinterpret_cast return sizeof static static_cast struct switch template this throw true try typedef typename union using virtual volatile while".split(" "));
      const types=new Set("bool char double float int long short signed unsigned void wchar_t size_t ptrdiff_t uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t int64_t".split(" "));
      /* Render token text through React, never innerHTML. Bound colour work without dropping supplied text. */
      const cap=200000,body=text.slice(0,cap),pattern=/\/\*[\s\S]*?(?:\*\/|$)|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|^\s*#[^\n]*|\b(?:0[xX][\da-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*|[A-Za-z_]\w*)\b/gm;
      const parts=[];let end=0,match;
      while((match=pattern.exec(body))) {
        if(match.index>end)parts.push(body.slice(end,match.index));
        const value=match[0],kind=value.startsWith("/*")||value.startsWith("//")?"comment":/^\s*#/.test(value)?"directive":value[0]==='"'||value[0]==="'"?"string":/^\d/.test(value)?"number":keywords.has(value)?"keyword":types.has(value)||/^undefined\d*$/.test(value)||/^(?:u?int|uint)\d+_t$/.test(value)?"type":null;
        parts.push(kind?html`<span key=${match.index} className=${"wb-source-token-"+kind}>${value}</span>`:value);end=pattern.lastIndex;
      }
      if(end<body.length)parts.push(body.slice(end));if(text.length>cap)parts.push(text.slice(cap));return parts;
    },[text,assembly]);
    const extent=truncated===true?"Partial captured text":truncated===false?"Complete captured text":"Displayed text · completeness not recorded";
    const origin=source==="recovered"?"Recovered source candidate":source==="recorded-knowledge"?"Stored Ghidra knowledge":source==="recorded-mcp-evidence"?"Recorded Ghidra observation":source?String(source).replace(/-/g," "):"Captured analysis text";
    function download() {
      const stem=[slug,name,addr].filter(Boolean).join("-").replace(/[^A-Za-z0-9_.-]+/g,"_").slice(0,180)||"function";
      const suffix=assembly?"-instruction-listing.txt":"-advisory-"+(truncated===true?"partial":truncated===false?"captured":"displayed")+(/\.cpp$/i.test(path||"")?".cpp":".c");
      const url=URL.createObjectURL(new Blob([text],{type:"text/plain;charset=utf-8"})),link=document.createElement("a");link.href=url;link.download=stem+suffix;link.click();window.setTimeout(function(){URL.revokeObjectURL(url);},1000);setFeedback("Downloaded the displayed text only. This is not a complete source bundle or a build receipt.");
    }
    async function copy() {try{if(!navigator.clipboard)throw new Error("Clipboard access is unavailable in this browser.");await navigator.clipboard.writeText(text);setFeedback("Displayed text copied.");}catch(error){setFeedback(String(error.message||error));}}
    return html`<section className=${"wb-source-preview "+(assembly?"is-assembly-observation":"is-advisory")+(previous?" is-pinned":"")} aria-label=${assembly?"Recorded instruction listing":"Advisory source preview"}>
      <header className="wb-source-heading"><div><span className="wb-source-tier" tabIndex="0" title=${tierDescription} aria-describedby=${tierDescriptionId}>${assembly?"Instruction observation":"Advisory C/C++ · byte parity unproven"}<span aria-hidden="true"> ⓘ</span></span><span id=${tierDescriptionId} className="wb-source-a11y-note">${tierDescription}</span><h3>${name} <code>${addr}</code>${previous?" · previous function":""}</h3><p>${slug||"Build binding not recorded"} · ${origin}</p></div><div className="wb-source-tools"><button type="button" className="wb-btn wb-btn-mini" aria-pressed=${wrap} onClick=${function(){setWrap(!wrap);}}>Wrap lines</button><button type="button" className="wb-btn wb-btn-mini" onClick=${copy}>Copy text</button><button type="button" className="wb-btn wb-btn-mini" onClick=${download}>Download ${truncated===true?"fragment":"displayed text"}</button></div></header>
      ${status||reason?html`<p className="wb-hint" role="status">${status||reason}</p>`:null}
      <pre className=${"wb-preview wb-source-code"+(wrap?" is-wrapped":"")} id="wb-decompile-preview" tabIndex="0" aria-label=${assembly?"Instruction text":"Syntax-highlighted source"}><code>${tokens}</code></pre>
      <footer className="wb-source-foot"><span>${extent} · ${text.split("\n").length} lines</span>${path?html`<span title=${path}>Evidence file: <code>${path}</code></span>`:null}${text.length>200000&&!assembly?html`<span>Syntax colour is bounded to the first 200,000 characters; no supplied text is omitted.</span>`:null}</footer>
      ${feedback?html`<p role="status" className="wb-hint">${feedback}</p>`:null}
    </section>`;
  }

  function StepLadder({ steps, title }) {
    const list = steps || [];
    if (!list.length) return html`<p className="wb-hint">No ladder facts yet.</p>`;
    return html`<section className="wb-ladder">
      ${title ? html`<h3 className="wb-ladder-title">${title}</h3>` : null}
      <ol className="wb-ladder-list">
        ${list.map(function (step) {
          const st = step.state || step.status || "unmeasured";
          const completed = step.done != null ? step.done : step.completed;
          const unattempted = (st === "not started" || st === "unmeasured" || st === "queued") && !completed;
          const count = unattempted
            ? "not attempted"
            : (fmtCount(completed) + " / " + fmtCount(step.total) + (step.unit ? " " + step.unit : ""));
          return html`<li key=${step.key || step.title} className=${stepStateClass(st)}>
            <div className="wb-step-head">
              <span className="wb-step-no">${step.label || step.key || ""}</span>
              <span className="wb-step-name">${step.title || step.key}</span>
              <span className="wb-step-state">${st}</span>
              <span className="wb-step-count">${count}</span>
            </div>
            <p className="wb-hint">${step.why || step.reason || ""}</p>
            ${step.currentProgram || step.currentTarget ? html`<p className="wb-hint"><code>${step.currentProgram || step.currentTarget}</code>${step.currentAction ? " · " + step.currentAction : ""}</p>` : null}
            ${step.receipt ? html`<p className="wb-hint">Receipt: <code>${step.receipt}</code></p>` : null}
            ${step.next ? html`<p className="wb-hint">Next: ${step.next}</p>` : null}
          </li>`;
        })}
      </ol>
    </section>`;
  }

  function preparationResponse(data) {
  if (!data || data.ok === false || !Array.isArray(data.runs)) throw new Error("Invalid preparation response");
  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const texts = ["id", "status", "locator", "program", "slug", "title", "key", "reason", "error", "currentProgram", "currentTarget", "currentAction", "jobStatus", "unit", "nextFallback", "message", "action", "nextAction", "wakeCondition", "label", "state", "why", "next", "receipt", "programPath", "src", "dst", "actionId"];
  const numbers = ["completed", "total", "done", "attempts", "attemptsSpent", "attemptsRemaining", "executionLimitSeconds"];
  const times = ["updatedAt", "createdAt", "startedAt", "retryAt", "at", "executionDeadlineAt", "deadline"];
  function row(value) {
    if (!object(value)) return false;
    if (texts.some(key => value[key] != null && typeof value[key] !== "string")) return false;
    if (numbers.some(key => value[key] != null && (typeof value[key] !== "number" || !Number.isFinite(value[key])))) return false;
    if (times.some(key => value[key] != null && (typeof value[key] !== "number" || !Number.isFinite(value[key]) || Math.abs(value[key]) > 8640000000000))) return false;
    return true;
  }
  for (const run of data.runs) {
    if (!row(run)) throw new Error("Invalid preparation record");
    for (const key of ["stages", "events"]) {
      if (run[key] != null && (!Array.isArray(run[key]) || !run[key].every(row))) throw new Error("Invalid preparation " + key);
    }
    if (run.currentJob != null && (!row(run.currentJob) || (run.currentJob.params != null && !row(run.currentJob.params)))) throw new Error("Invalid current job");
    for (const stage of run.stages || []) {
      if (stage.workProgress != null && !row(stage.workProgress)) throw new Error("Invalid stage work progress");
    }
    if (run.programs != null && (!Array.isArray(run.programs) || !run.programs.every(value => typeof value === "string"))) throw new Error("Invalid preparation programs");
    if (run.retryDecisions != null && (!object(run.retryDecisions) || !Object.values(run.retryDecisions).every(row))) throw new Error("Invalid continuation decisions");
  }
  return data.runs;
  }

  function preparationBudgetText(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return "Action admissions: unknown";
    const budget = value;
    const count = (n) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
    const used = count(budget.consumed) ? String(budget.consumed) : "unknown";
    const limit = budget.maxActionAdmissions === null ? "unlimited" : count(budget.maxActionAdmissions) ? String(budget.maxActionAdmissions) : "unknown";
    const revision = count(budget.allocationRevision) ? String(budget.allocationRevision) : "unknown";
    const prior = budget.priorUsageUnknown === true ? " · earlier spending unknown; shown usage is a lower bound" : "";
    const exhausted = count(budget.consumed) && count(budget.maxActionAdmissions) && budget.consumed >= budget.maxActionAdmissions ? " · allowance exhausted" : "";
    return `Action admissions: ${used} used / ${limit} allowance · allocation revision ${revision}${exhausted}${prior}`;
  }

  function preparationProviderBudgetText(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return "MCP tool calls: unknown";
    const budget = value;
    if (budget.schema !== 1 || budget.accountingScope !== "mcp-tool-dispatches-since-allocation") return "MCP tool calls: unknown";
    const count = (n) => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
    const used = count(budget.consumed) ? String(budget.consumed) : "unknown";
    const limit = budget.maxMcpToolCalls === null ? "unlimited" : count(budget.maxMcpToolCalls) ? String(budget.maxMcpToolCalls) : "unknown";
    const revision = count(budget.allocationRevision) ? String(budget.allocationRevision) : "unknown";
    const prior = budget.priorUsageUnknown === true ? " · earlier spending unknown; shown usage is a lower bound" : "";
    const exhausted = count(budget.consumed) && count(budget.maxMcpToolCalls) && budget.consumed >= budget.maxMcpToolCalls ? " · allowance exhausted" : "";
    return `MCP tool calls: ${used} used / ${limit} allowance · allocation revision ${revision}${exhausted}${prior}`;
  }

  const PREPARATION_PAUSABLE = { queued: 1, running: 1, waiting: 1 };

  function PreparationObservation({ run, feed, now, onControl }) {
    const stale = ["disconnected", "resync"].includes(String(run && run.status)) || Boolean(feed.error) || Boolean(feed.receivedAt && now - feed.receivedAt > 10000);
    const decisions = Object.values(run && run.retryDecisions || {}).filter(function (value) { return value && typeof value === "object" && value.nextAction !== "dispatch"; });
    const [busy, setBusy] = useState("");
    const [ctlError, setCtlError] = useState("");
    function control(operation) {
      if (!run || !run.id || busy || !onControl) return;
      setBusy(operation);
      setCtlError("");
      Promise.resolve(onControl(run.id, operation)).then(function (result) {
        setBusy("");
        if (!result) setCtlError("Could not send " + operation + ". Try again.");
      }, function (err) {
        setBusy("");
        setCtlError(String((err && err.message) || err || ("Could not send " + operation + ".")));
      });
    }
    return html`<section className="wb-preparation-observation" aria-label="Recorded preparation state">
      <p role="status">${stale ? "Connection lost · showing last received state; current state unknown" : feed.receivedAt ? "Preparation feed connected" : "Preparation status not yet received"}</p>
      ${feed.receivedAt ? html`<p className="wb-hint">Last received: <time dateTime=${new Date(feed.receivedAt).toISOString()}>${new Date(feed.receivedAt).toLocaleString()}</time></p>` : null}
      ${feed.error ? html`<p className="wb-hint">${feed.error}</p>` : null}
      ${run ? html`<p>${preparationProviderBudgetText(run.providerBudget)}${stale ? " · last received observation; current usage unknown" : ""}</p>
        <p className="wb-hint">MCP allowance counts prerequisite, retry and check-in tools/call attempts since allocation. It is separate from action admissions and the execution deadline; it does not count tokens, money or provider-internal work.</p>
        <p>${preparationBudgetText(run.objectiveBudget)}</p>
        <p className="wb-hint">Admission allowance counts reserved action attempts, including uncertain or rejected dispatches. It is separate from the execution deadline and does not measure recovered code. Accounting scope: ${run.objectiveBudget && typeof run.objectiveBudget.accountingScope === "string" ? run.objectiveBudget.accountingScope : "unknown"}.</p>
        ${typeof run.updatedAt === "number" && Number.isFinite(run.updatedAt) ? html`<p className="wb-hint">Last recorded change: <time dateTime=${new Date(run.updatedAt * 1000).toISOString()}>${new Date(run.updatedAt * 1000).toLocaleString()}</time></p>` : null}
        ${decisions.map(function (decision, index) { return html`<p key=${index} className="wb-hint">${decision.reason || "Awaiting reconciliation"}${decision.wakeCondition ? " · Continues after: " + String(decision.wakeCondition).replace(/_/g, " ") : ""}</p>`; })}
        <p className="wb-hint">Stage completion does not establish byte verification or accepted source contribution.</p>
        ${onControl && run.id ? html`<div className="wb-fn-tools" role="group" aria-label="Workflow control">
          ${PREPARATION_PAUSABLE[run.status] ? html`<button type="button" className="wb-btn wb-btn-mini" disabled=${Boolean(busy)}
            onClick=${function () { control("pause"); }}>Pause this recovery run</button>` : null}
          ${run.status === "paused" && !(Number.isFinite(run.deadline) && run.deadline * 1000 <= now) ? html`<button type="button" className="wb-btn wb-btn-mini" disabled=${Boolean(busy)}
            onClick=${function () { control("resume"); }}>Resume this recovery run</button>` : null}
          ${run.status === "paused" && Number.isFinite(run.deadline) && run.deadline * 1000 <= now ? html`<p className="wb-hint">This run’s execution deadline has passed; resuming would be refused.</p>` : null}
          ${PREPARATION_PAUSABLE[run.status] || run.status === "paused" ? html`<details className="wb-run-extra-controls">
            <summary>More run controls</summary>
            <button type="button" className="wb-btn wb-btn-mini" disabled=${Boolean(busy)}
              onClick=${function () { control("stop"); }}>Stop this recovery run</button>
          </details>` : null}
          ${busy ? html`<span role="status" className="wb-hint">Submitting ${busy}…</span>` : null}
          ${ctlError ? html`<span role="status" className="wb-dialog-error">${ctlError}</span>` : null}
        </div>` : null}` : null}
    </section>`;
  }

  function selectPreparationRun(runs, locator, program, slug) {
    const normalizedLocator = String(locator || "").replace(/\/+$/, "");
    return (runs || []).filter(function (run) {
      const runLocator = String(run.locator || "").replace(/\/+$/, "");
      if (normalizedLocator) {
        return runLocator === normalizedLocator && (!program || !run.program || run.program === program || (run.programs || []).includes(program));
      }
      return Boolean(slug) && run.slug === slug;
    }).sort(function (left, right) {
      const active = ["queued", "running", "waiting", "cancelling", "disconnected", "resync"];
      return Number(active.includes(right.status)) - Number(active.includes(left.status))
        || Number(right.updatedAt || 0) - Number(left.updatedAt || 0);
    })[0] || null;
  }

  function BinaryCompareTable({ binaries, onOpen }) {
    const rows = binaries || [];
    if (!rows.length) return html`<p className="wb-hint">No non-DRM builds in the corpus snapshot.</p>`;
    return html`<table className="wb-fnb-table wb-compare-table">
      <thead><tr>
        <th>Build</th><th>Game</th><th>Functions</th><th>Bound</th><th>Real C</th><th>Named</th>
      </tr></thead>
      <tbody>
        ${rows.map(function (b) {
          return html`<tr key=${b.slug} onClick=${function () { if (onOpen) onOpen(b); }}>
            <td><code>${b.slug}</code></td>
            <td>${b.game || ""} ${b.platform || ""}</td>
            <td>${fmtCount(b.func_count)}</td>
            <td>${fmtCount(b.bound)}</td>
            <td>${fmtCount(b.real_c)}</td>
            <td>${fmtCount(b.named_count)}</td>
          </tr>`;
        })}
      </tbody>
    </table>`;
  }

  function ProgramHero({ overview }) {
    if (!overview) return null;
    const blocks = overview.memory || [];
    const named = Number(overview.namedCount || 0);
    const total = Number(overview.functionCount || 0);
    const pct = total ? Math.round((named / total) * 100) : 0;
    return html`<div id="wb-program-hero" className="wb-program-hero">
      <p className="wb-hero-n">${total || 0} <span class="of">functions</span>
        <span class="st">${named} named · ${pct}%</span></p>
      <p className="wb-hint">${overview.program || ""} ${overview.path || ""} · ${overview.language || ""} · base ${overview.imageBase || ""}</p>
      ${total ? html`<div className="wb-bar" aria-hidden="true"><i style=${{ width: pct + "%" }}></i></div>` : null}
      ${blocks.length ? html`<ul className="wb-mem">
        ${blocks.map(function (block) {
          return html`<li key=${block.name + block.start}><code>${block.start}</code> ${block.name} · ${block.length}</li>`;
        })}
      </ul>` : null}
    </div>`;
  }

  const BSIM_HONEST = {
    missing_datadir: "No BSim datadir on disk.",
    not_a_datadir: "The BSim path is not a directory.",
    no_postgres: "Datadir has no PostgreSQL cluster.",
    no_bsim_database: "Datadir has no BSim database.",
    empty_database: "BSim database exists but holds 0 executables.",
    populated: "BSim holds executables.",
    database_unreachable: "BSim did not answer."
  };

  function repoForSlug(slugName, binaries) {
    const row = (binaries || []).find(function (item) { return item.slug === slugName; });
    return (row && row.repo) || "";
  }

  function workDirPath(workDir) {
    return String(workDir || "").replace(/\/$/, "");
  }

  function hasCorpusContext(ctx) {
    return Boolean((ctx && ctx.slug) || (ctx && ctx.program));
  }

  function matchPairParams(ctx, binaries, siblings) {
    const srcSlug = (ctx && ctx.slug) || "";
    const sourceMember = ((ctx && ctx.tabRows) || []).find(function (row) { return row.slug === srcSlug; });
    const src = sourceMember ? (repoForSlug(srcSlug, binaries) || sourceMember.repo || "") : "";
    const candidates = Array.from(new Set(((ctx && ctx.tabRows) || [])
      .filter(function (row) { return row.slug && row.slug !== srcSlug && row.repo; })
      .map(function (row) { return row.repo; })));
    const dst = candidates.length === 1 ? candidates[0] : "";
    // A target is an explicit pair, never the first unrelated corpus binary.
    return { src: src, dst: dst, ok: Boolean(src && dst) };
  }

  function identityActionParams(actionId, ctx, binaries, siblings) {
    const work = workDirPath(ctx && ctx.work_dir);
    const slugName = (ctx && ctx.slug) || "";
    const programName = (ctx && ctx.program) || (ctx && ctx.repo) || slugName || "";
    const base = { program: programName, slug: slugName };
    if (actionId === "corpus.match-pair") {
      return Object.assign(base, matchPairParams(ctx, binaries, siblings));
    }
    if (actionId === "corpus.apply-stabs") {
      const out = Object.assign({}, base);
      if (work && slugName) out.manifest = work + "/extract/stabs/" + slugName + ".manifest.jsonl";
      const row = (binaries || []).find(function (item) { return item.slug === slugName; });
      if (row && row.id) out["binary-id"] = row.id;
      return out;
    }
    if (actionId === "corpus.logical-build") return base;
    if (actionId === "corpus.merge-parts") {
      const out = Object.assign({}, base);
      if (work) out["parts-dir"] = work + "/parts";
      return out;
    }
    if (actionId === "corpus.propagate-corpus" || actionId === "corpus.propagate-source") return base;
    return base;
  }

  function catalogParamsFor(actionId, overrides) {
    const extra = overrides || {};
    const ui = window.AgentDecompileUI || {};
    const ctx = typeof ui.getToolContext === "function" ? ui.getToolContext() : {};
    const env = typeof ui.getEnvDefaults === "function" ? ui.getEnvDefaults() : {};
    const binaries = typeof ui.getBinaries === "function" ? ui.getBinaries() : [];
    const siblings = typeof ui.getSiblings === "function" ? ui.getSiblings() : [];
    const slug = extra.slug || extra.id || ctx.slug || "";
    const mergedCtx = Object.assign({}, ctx, {
      slug: slug || ctx.slug || "",
      program: extra.program || ctx.program || "",
      db: ctx.db || env.db || "",
      work_dir: ctx.work_dir || env.work_dir || "",
      kb: ctx.kb || env.kb || ""
    });
    const base = identityActionParams(actionId, mergedCtx, binaries, siblings);
    const out = Object.assign({}, base, extra);
    if (slug && !out.db && (mergedCtx.db || env.db)) out.db = mergedCtx.db || env.db;
    if (slug && !out.slug) out.slug = slug;
    if (slug && !out.id) out.id = slug;
    return out;
  }

  function MatchWorkbench({
    program, selected, bsim, onRefresh
  }) {
    const state = (bsim && bsim.state) || "";
    let line = BSIM_HONEST[state] || (bsim && bsim.summary) || "Checking BSim…";
    if (state === "populated") {
      line = "BSim holds " + ((bsim && bsim.executables) || 0) + " executables.";
    }
    return html`<div className="wb-re-pane" id="wb-match-pane">
      <p className="wb-hint">${program ? ("Program " + program) : "Pick a program in Explorer."}
        ${selected ? (" · " + ((selected.name || selected.addr) + " " + (selected.addr || ""))) : ""}</p>
      <div id="wb-match-bsim" className=${"wb-bsim-state st-" + (state || "unknown")}>
        <strong>BSim</strong>
        <p>${line}</p>
        ${bsim && bsim.datadir ? html`<p className="wb-hint"><code>${bsim.datadir}</code></p>` : null}
      </div>
      <p className="wb-hint">BSim is a candidate-discovery signal. It does not establish an accepted cross-build identity.</p>
      <div className="wb-fn-tools" role="toolbar" aria-label="Cross-build source/index status">
        <button type="button" className="wb-btn" onClick=${onRefresh}>Refresh</button>
      </div>
      <section className="wb-stabs-detail">
        <h3>STABS</h3>
        <p className="wb-hint">Donor symbols for this program, when a STABS source is available.</p>
      </section>
    </div>`;
  }

  function LogicalCounterparts({ slug, selected, detail, binaries, onPick }) {
    const siblings = (detail && detail.siblings || []).filter(function (item) {
      return item && item.slug && item.addr && item.slug !== slug;
    });
    const currentBinary = (binaries || []).find(function (item) { return item.slug === slug; }) || {};
    const group = currentBinary.variant_group || currentBinary.variantGroup || null;
    const logicalId = (selected && (selected.logicalId || selected.logical_id))
      || (detail && detail.function && (detail.function.logicalId || detail.function.logical_id))
      || (siblings[0] && siblings[0].logicalId) || null;
    if (!selected) return html`<section className="wb-identity-map" aria-labelledby="wb-identity-title">
      <header className="wb-identity-head"><div><h3 id="wb-identity-title">Function identity across builds</h3>
        <p className="wb-hint">Select a function to inspect its recorded cross-build identity evidence.</p></div></header>
      <p className="wb-identity-empty">No function is selected. Open Functions, then choose a function to compare its recorded counterparts.</p>
    </section>`;
    return html`<section className="wb-identity-map" aria-labelledby="wb-identity-title">
      <header className="wb-identity-head">
        <div><h3 id="wb-identity-title">Function identity across builds</h3>
          <p className="wb-hint">${selected.name || selected.addr} · ${slug} · ${selected.addr}</p></div>
        ${logicalId != null ? html`<code className="wb-identity-id">Recorded logical group ${logicalId}</code>` : null}
      </header>
      <p className="wb-identity-caveat">Identity links describe recorded correspondence. They do not establish source interchangeability, ABI compatibility, equal bytes, or runtime safety.</p>
      <div className="wb-identity-source" aria-label="Selected function">
        <span className="wb-identity-source-mark" aria-hidden="true">●</span>
        <strong>${slug || "Selected build"}</strong><code>${selected.addr}</code>
        <span>${selected.name || "Unnamed function"}</span><b>Selected</b>
      </div>
      ${siblings.length ? html`<div className="wb-identity-links" aria-label="Recorded counterpart links">
        ${siblings.map(function (sibling, index) {
          const binary = (binaries || []).find(function (item) { return item.slug === sibling.slug; }) || {};
          return html`<article className="wb-identity-link" key=${sibling.slug + ":" + sibling.addr}>
            <div className="wb-identity-edge" aria-hidden="true"><span></span><i>${sibling.method || "identity evidence"}</i><span></span></div>
            <div className="wb-identity-counterpart">
              <strong>${sibling.slug}</strong><code>${sibling.addr}</code>
              <span>${sibling.name || binary.label || binary.platform || "Recorded counterpart"}</span>
              <small>${sibling.method || "Identity method not recorded"}</small>
              ${sibling.evidence ? html`<details><summary>Evidence detail</summary><pre>${typeof sibling.evidence === "string" ? sibling.evidence : JSON.stringify(sibling.evidence, null, 2)}</pre></details>` : null}
              <button type="button" className="wb-btn wb-btn-mini"
                aria-label=${"Open " + (sibling.name || "function") + " at " + sibling.addr + " in " + sibling.slug}
                onClick=${function () { if (onPick) onPick(sibling); }}>Open this counterpart</button>
            </div>
          </article>`;
        })}
      </div>` : html`<p className="wb-identity-empty">No counterpart link is recorded for this function. This does not establish that the function is absent from other builds.</p>`}
      ${group ? html`<details className="wb-variant-evidence">
        <summary>Build-family comparison · ${group.status || "unclassified"} · advisory only</summary>
        <p className="wb-hint">${group.policy && group.policy.description || "Build-family grouping is a navigation aid, not proof that functions or binaries are interchangeable."}</p>
        ${(group.evidence || []).length ? html`<ul>${group.evidence.map(function (item, index) {
          return html`<li key=${item.jobId || item.receipt || index}>
            <span>${item.source || "Build"} ↔ ${item.target || "Build"}</span>
            <span>${item.acceptedMatches == null ? "Accepted matches not recorded" : item.acceptedMatches + " accepted identity matches"}</span>
            <span>${item.minimumCoverage == null ? "Coverage not recorded" : "minimum coverage " + Number(item.minimumCoverage).toLocaleString(undefined, { style: "percent", maximumFractionDigits: 1 })}</span>
            ${item.receipt ? html`<code>${item.receipt}</code>` : null}
          </li>`;
        })}</ul>` : html`<p className="wb-identity-empty">No qualifying comparison receipt is recorded for this build family.</p>`}
      </details>` : null}
    </section>`;
  }

  function PreparationWorkMap({ run, feed, slug, program }) {
    const stages = run && Array.isArray(run.stages) ? run.stages : [];
    const active = stages.find(function (stage) { return stage.key === run.currentStage; })
      || stages.find(function (stage) { return stage.status === "running" || stage.status === "queued"; });
    const scopeLabel = run && run.scope === "project"
      ? "Project-wide run" + (run.executionLocator ? " · " + run.executionLocator : "")
      : (run && (run.program || run.slug)) || program || slug || "Current project";
    const feedStatus = feed && feed.error ? "Refresh failed · last observation may be stale"
      : feed && feed.receivedAt ? "Dashboard state refreshed " + new Date(feed.receivedAt).toLocaleTimeString()
        : "Not loaded · refresh to inspect pipeline status";
    function stageStatus(stage) {
      return String(stage.status || "unknown").toLowerCase().replace(/[^a-z0-9-]/g, "-");
    }
    function stageProgress(stage) {
      const progress = stage.workProgress || {};
      if (typeof progress.completed === "number" && typeof progress.total === "number" && progress.total > 0) {
        return progress.completed + " / " + progress.total + (progress.unit ? " " + progress.unit : "");
      }
      return stage.status === "running" ? "Active · no measured completion count" : "No measured progress reported";
    }
    const currentDescription = run
      ? [scopeLabel, run.status || "unknown state", active && active.title || "stage not recorded",
        active && active.currentProgram || "",
        active && active.status || "stage state not recorded", active && active.currentAction || "",
        active && active.reason || ""].filter(Boolean).join(" · ")
      : "No preparation run is associated with this selected project and build.";
    return html`<section className="wb-live-work" aria-labelledby="wb-preparation-map-title">
      <header className="wb-live-work-head">
        <div><h3 id="wb-preparation-map-title">Pipeline work path</h3>
          <p className="wb-hint">${run ? "Recorded stages for " + scopeLabel + ". Refresh status on request; this static page does not poll expensive project-wide aggregates." : "No preparation run is associated with this selection. This does not mean no work exists elsewhere."}</p></div>
        <span className="wb-feed-state"><i aria-hidden="true"></i>${feedStatus}</span>
      </header>
      <p className="sr-only" aria-live="polite" aria-atomic="true">${currentDescription}</p>
      ${run && stages.length ? html`<div className="wb-work-flow" aria-label="Recorded preparation stages">
        ${stages.map(function (stage, index) {
          const isActive = stage.key === (run.currentStage || (active && active.key));
          return html`<article key=${stage.key || index} className=${"wb-work-node wb-work-" + stageStatus(stage) + (isActive ? " is-current" : "")}>
            <div className="wb-work-node-title"><span>Stage ${index + 1}</span><strong>${stage.title || stage.key || "Unnamed stage"}</strong></div>
            <span className="wb-work-status">${stage.status || "Unknown state"}</span>
            ${stage.currentAction ? html`<p className="wb-work-action"><b>Doing</b> ${stage.currentAction}${stage.currentProgram ? " · " + stage.currentProgram : ""}</p>` : null}
            ${stage.reason ? html`<p className=${stage.status === "failed" || stage.status === "blocked" ? "wb-work-error" : "wb-work-stage"}>${stage.reason}</p>` : null}
            <p className="wb-work-progress">${stageProgress(stage)}</p>
            ${stage.jobId ? html`<code className="wb-work-job">${stage.jobId}</code>` : null}
            ${index < stages.length - 1 ? html`<div className="wb-work-connector" aria-hidden="true"><span></span><i>next</i></div>` : null}
          </article>`;
        })}
      </div>` : html`<div className="wb-live-work-empty">
        <p>${run ? "This run has not recorded a stage list." : "No preparation stages are recorded for this selection."}</p>
        <small>Unknown state is not a claim that the full recovery pipeline is idle.</small>
      </div>`}
    </section>`;
  }

  function RepoStatus({ dossier, user, session, program, slug, onRetry }) {
    if (!dossier || !dossier.ok) {
      if (session && session.locator) return html`<div id="wb-repo-status" className="wb-repo-row wb-repo-empty">
        <p role="status">${dossier && dossier.error ? "Saved tab “" + (session.title || "Untitled") + "” points to “" + session.locator + "”, which is not readable as a project here: " + dossier.error : "Reading saved project " + (session.title || session.locator) + "…"}</p>
        ${dossier && dossier.error && onRetry ? html`<button type="button" className="wb-btn wb-btn-mini" onClick=${onRetry}>Retry project inspection</button>` : null}
      </div>`;
      return html`<p id="wb-repo-status" className="wb-repo-row wb-repo-empty">
        ${session ? "Workspace: " + (session.title || "Untitled") + (slug ? " · Build: " + slug : " · No build selected") : "No workspace is open. Open a project to begin."}
      </p>`;
    }
    const kind = dossier.kind || "";
    const projectName = (session && session.title) || dossier.slug || dossier.repository || "Project";
    const programName = program || (slug && slug !== (session && session.projectSlug) ? slug : "");
    const context = html`<strong>Project: ${projectName}</strong><span>Program: ${programName || "not selected"}</span>`;
    if (kind === "shared-project") {
      const host = dossier.host || "";
      const port = Number(dossier.port || 0);
      const portBit = (port && port !== 13100) ? (":" + port) : "";
      const repo = dossier.repository || "";
      const who = dossier.user || user || "";
      return html`<p id="wb-repo-status" className=${"wb-repo-row" + (dossier.reachable ? " on" : " off")}>
        ${context}
        <span>Project Repository: ${repo || "—"}</span>
        <span>${dossier.reachable
          ? ("Reachable at " + host + portBit)
          : ("Disconnected from " + (host || "Ghidra Server"))}</span>
        ${who ? html`<span>User ${who}</span>` : null}
        ${dossier.mirror_available ? html`<span>Local copy bound for listing</span>` : null}
      </p>`;
    }
    if (kind === "shared-fs") {
      return html`<p id="wb-repo-status" className="wb-repo-row">${context}<span>Folder of shared projects · not itself a .gpr project · no live Ghidra Server session</span></p>`;
    }
    if (kind === "packed-program") {
      return html`<p id="wb-repo-status" className="wb-repo-row">${context}<span>Packed Ghidra program</span></p>`;
    }
    if (kind === "ghidra-project") {
      return html`<p id="wb-repo-status" className="wb-repo-row">${context}<span>Local Ghidra project</span></p>`;
    }
    return html`<p id="wb-repo-status" className="wb-repo-row">${context}<span>${kindTitle(kind)}</span></p>`;
  }

  function ExportBundles({ slug, locator }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    useEffect(function () {
      const controller = new AbortController();
      let alive = true;
      setData(null); setError("");
      const params = new URLSearchParams({slug: slug || "", locator: locator || ""});
      fetch("/dashboard/api/workbench/exports?" + params, {cache: "no-store", signal: controller.signal})
        .then(function (response) { if (!response.ok) throw new Error("Export listing unavailable (" + response.status + ")"); return response.json(); })
        .then(function (body) { if (alive) { if (!body.ok) setError(body.error || "Export listing unavailable"); else setData(body); } })
        .catch(function (err) { if (alive) setError(String(err.message || err)); });
      return function () { alive = false; controller.abort(); };
    }, [slug, locator]);
    return html`<section aria-label="Export readiness"><h3>Export bundles</h3>
      <p className="wb-hint">Recorded pipeline outputs. Locator readiness does not establish supported runtime operations or recovered-source parity.</p>
      ${error ? html`<p className="wb-dialog-error">${error}</p>` : !data ? html`<p role="status">Reading export manifests…</p>` : !(data.bundles || []).length ? html`<p role="status">${data.reason || "No complete export bundle is recorded for this selection. Nothing to download yet."}</p>` : null}
      ${(data && data.bundles || []).map(function (bundle) { return html`<article key=${bundle.bundle_sha256}>
        <h4>Bundle <code>${String(bundle.bundle_sha256).slice(0,16)}</code></h4>
        ${(bundle.readiness && bundle.readiness.builds || []).map(function (build) { return html`<p key=${build.build}>${build.summary}</p>`; })}
        <details><summary>Per-entity locator readiness</summary><table><thead><tr><th>Entity</th><th>Build</th><th>Status</th><th>Reason</th></tr></thead><tbody>
          ${(bundle.readiness && bundle.readiness.entities || []).map(function (row) { return html`<tr key=${row.entity+":"+row.build}><td>${row.entity}</td><td>${row.build}</td><td data-readiness=${row.status}>${row.status}</td><td>${row.reason}</td></tr>`; })}
        </tbody></table></details>
        <ul>${(bundle.artifacts || []).map(function (artifact) { return html`<li key=${artifact.path}><a href=${artifact.href} download>${artifact.path}</a> · ${artifact.size} bytes</li>`; })}</ul>
        ${(bundle.scope_receipts || []).map(function (receipt) { return html`<p key=${receipt.artifact}>${receipt.artifact}: ${receipt.status} · ${receipt.reason}</p>`; })}
      </article>`; })}
      ${(data && data.errors || []).map(function (message,index) { return html`<p className="wb-dialog-error" key=${index}>${typeof message === "string" ? message : (message.bundle || "Bundle") + ": " + (message.reason || "Unavailable")}</p>`; })}
    </section>`;
  }

  function ArtifactsReact({ path, onOpen }) {
    const [data, setData] = useState(null);
    const [note, setNote] = useState("");
    useEffect(function () {
      const url = API.artifacts + (path ? "?p=" + encodeURIComponent(path) : "");
      fetch(url, { cache: "no-store" }).then(function (res) { return res.json(); }).then(function (body) {
        setData(body);
        setNote("");
      }).catch(function (err) {
        setNote(String(err && err.message || err));
      });
    }, [path]);
    if (note) return html`<p className="wb-dialog-error">${note}</p>`;
    if (!data) return html`<p className="wb-hint">Reading artifacts…</p>`;
    if (!data.ok) return html`<p className="wb-hint">${data.error || "No artifacts."}</p>`;
    if (data.kind === "dir") {
      return html`<div className="wb-artifacts">
        <p className="wb-hint"><code>${data.path || "."}</code></p>
        ${data.parent != null && data.parent !== "" ? html`<button type="button" className="wb-text-action"
          onClick=${function () { if (onOpen) onOpen(data.parent); }}>Up</button>` : null}
        <ul className="wb-artifact-list">
          ${(data.entries || []).map(function (entry) {
            return html`<li key=${entry.path}>
              <button type="button" className="wb-text-action"
                onClick=${function () { if (onOpen) onOpen(entry.path); }}>
                ${entry.name}${entry.dir ? "/" : ""}
              </button>
              ${entry.size != null ? html`<span className="wb-hint">${formatBytes(entry.size)}</span>` : null}
            </li>`;
          })}
        </ul>
      </div>`;
    }
    return html`<div className="wb-artifacts">
      ${data.parent != null ? html`<button type="button" className="wb-text-action"
        onClick=${function () { if (onOpen) onOpen(data.parent); }}>Up</button>` : null}
      <p className="wb-hint"><code>${data.path || ""}</code></p>
      ${data.binary
        ? html`<p className="wb-hint">Binary file. Not shown as text.</p>`
        : html`<pre className="wb-preview">${data.text || ""}</pre>`}
    </div>`;
  }

  function EvidenceReact() {
    const [data, setData] = useState(null);
    useEffect(function () {
      fetch(API.evidence, { cache: "no-store" }).then(function (res) { return res.json(); }).then(setData)
        .catch(function () { setData({ ok: false, error: "Could not read database evidence." }); });
    }, []);
    if (!data) return html`<p className="wb-hint">Reading the corpus database…</p>`;
    if (!data.ok) return html`<p className="wb-hint">${data.error || "Database evidence is unset."}</p>`;
    return html`<div className="wb-evidence">
      <p className="wb-hint"><code>${data.path || ""}</code> ${data.size_mb != null ? data.size_mb + " MB" : ""}</p>
      <table className="wb-fnb-table">
        <thead><tr><th>Name</th><th>Type</th></tr></thead>
        <tbody>
          ${(data.objects || []).map(function (row) {
            return html`<tr key=${row.type + row.name}><td><code>${row.name}</code></td><td>${row.type}</td></tr>`;
          })}
        </tbody>
      </table>
    </div>`;
  }

  function RecoverWorkbench({ program, selected, recover, recoveredRoot, onRefresh }) {
    const state = (recover && recover.state) || "";
    const files = (recover && recover.files) || [];
    const summary = (recover && recover.summary)
      || (recoveredRoot ? "A recovered source directory is set." : "No recovered source yet.");
    return html`<div className="wb-re-pane" id="wb-recover-pane">
      <p className="wb-hint">${program ? ("Program " + program) : "Pick a program in Explorer."}
        ${selected ? (" · " + (selected.name || selected.addr)) : ""}</p>
      <div id="wb-recover-status" className=${"wb-bsim-state st-" + (state || "none")}>
        <strong>Source</strong>
        <p>${summary}</p>
        ${recover && recover.path ? html`<p className="wb-hint"><code>${recover.path}</code></p>` : null}
      </div>
      <p className="wb-hint">The pipeline recovers, places and ingests source automatically.</p>
      <div className="wb-fn-tools" role="toolbar" aria-label="Recover">
        <button type="button" className="wb-btn" onClick=${onRefresh}>Refresh</button>
      </div>
      ${((recover && recover.leftoverCount) || 0) > 0 ? html`<p className="wb-hint">Leftover functions are pending. The pipeline recovers them automatically.</p>` : html`<p className="wb-hint">No leftover functions right now.</p>`}
      ${files.length ? html`<ul className="wb-recover-files">
        ${files.map(function (name) {
          return html`<li key=${name}><code>${name}</code></li>`;
        })}
      </ul>` : html`<p className="wb-hint">The pipeline writes compiling C here automatically.</p>`}
    </div>`;
  }

  function HtmlIsland({ url, refreshKey, className, compact }) {
    const ref = useRef(null);
    const [manualKey, setManualKey] = useState(0);
    useEffect(function () {
      function bump() { setManualKey(function (n) { return n + 1; }); }
      ISLAND_BUS.subs.push(bump);
      return function () {
        const at = ISLAND_BUS.subs.indexOf(bump);
        if (at >= 0) ISLAND_BUS.subs.splice(at, 1);
      };
    }, []);
    useEffect(function () {
      if (!url) return undefined;
      let dead = false;
      let timer = null;

      function stillPending() {
        return Boolean(ref.current && ref.current.querySelector('[data-pending="1"]'));
      }

      function announce(waiting, attempt) {
        if (!ref.current) return;
        const old = ref.current.querySelector(".wb-island-pending");
        if (old) old.remove();
        const bar = document.createElement("p");
        bar.className = "wb-island-pending" + (waiting ? "" : " stalled");
        const note = document.createElement("span");
        note.textContent = waiting
          ? "Still reading the store (" + attempt + ")…"
          : "The store read has not finished yet.";
        bar.appendChild(note);
        const again = document.createElement("button");
        again.type = "button";
        again.className = "wb-btn";
        again.textContent = "Refresh";
        again.addEventListener("click", function () { setManualKey(function (n) { return n + 1; }); });
        bar.appendChild(again);
        ref.current.insertBefore(bar, ref.current.firstChild);
      }

      function load(attempt) {
        fetch(url, { cache: "no-store" }).then(function (res) {
          return res.text().then(function (text) {
            return { ok: res.ok, status: res.status, text: text };
          });
        }).then(function (payload) {
          if (dead || !ref.current) return;
          if (!payload.ok) {
            const atlas = /\/atlas/.test(url);
            const report = /\/report/.test(url);
            if (payload.status === 404 && (atlas || report)) {
              ref.current.innerHTML = '<p class="wb-hint">' + (atlas ? "Atlas" : "Report")
                + " is not on this process. Open the full HTTP app, or stay on Overview.</p>";
              return;
            }
            ref.current.innerHTML = '<p class="wb-hint">Panel failed (' + payload.status + ").</p>";
            return;
          }
          if (!(payload.text || "").trim()) {
            ref.current.innerHTML = '<p class="wb-hint">This panel returned no HTML.</p>';
            return;
          }
          ref.current.innerHTML = '<div class="wb-legacy' + (compact ? " wb-legacy-compact" : "") + '">' + payload.text + "</div>";
          sanitizeLegacy(ref.current);
          wireStepActions(ref.current);
          wireMatchDecide(ref.current);
          runScripts(ref.current);
          if (!stillPending()) return;
          const wait = PENDING_DELAYS[attempt];
          announce(Boolean(wait), attempt + 1);
          if (!wait) return;
          timer = window.setTimeout(function () { if (!dead) load(attempt + 1); }, wait);
        }).catch(function (err) {
          if (!dead && ref.current) {
            ref.current.innerHTML = '<p class="wb-hint">' + String(err.message || err) + "</p>";
          }
        });
      }

      load(0);
      return function () {
        dead = true;
        if (timer) window.clearTimeout(timer);
      };
    }, [url, refreshKey, compact, manualKey]);
    return html`<div ref=${ref} className=${className || "wb-island"}><p className="wb-hint">Loading panel…</p></div>`;
  }

  function DockPanel({ id, title, children, className, actions }) {
    return html`<section id=${id} className=${"wb-dock" + (className ? " " + className : "")} aria-labelledby=${id + "-title"}>
      <header className="wb-dock-title">
        <span id=${id + "-title"}>${title}</span>
        ${actions || null}
      </header>
      <div className="wb-dock-body">${children}</div>
    </section>`;
  }

  function TabBar({ tabs, active, onSelect, id }) {
    return html`<div id=${id || "wb-tabbar"} className="wb-tabbar" role="tablist">
      ${tabs.map(function (tab) {
        return html`<button key=${tab.id} type="button" role="tab" aria-selected=${active === tab.id}
          className=${active === tab.id ? "on" : ""}
          onClick=${function () { onSelect(tab.id); }}>${tab.label}</button>`;
      })}
    </div>`;
  }

  const BOTTOM_TABS = [
    { id: "pipeline", label: "Pipeline" },
    { id: "atlas", label: "Atlas" },
    { id: "report", label: "Report" },
    { id: "tools", label: "Tools" },
    { id: "output", label: "Output" }
  ];

  const CENTER_TABS = [
    { id: "decompile", label: "Listing" },
    { id: "graph", label: "Call trees" }
  ];

  const QUICK_ACTION_SETS = {
    home: [
      { id: "mcp.status", label: "Status" },
      { id: "mcp.list-functions", label: "List functions" }
    ],
    atlas: [
      { id: "mcp.decompile-function", label: "Decompile", needsFunction: true },
      { id: "mcp.get-function", label: "Get function", needsFunction: true }
    ],
    functions: [
      { id: "mcp.list-functions", label: "List functions" },
      { id: "mcp.search-symbols", label: "Search symbols" }
    ],
    explorer: [
      { ui: "upload", label: "Add files…" },
      { ui: "import", label: "Open…" },
      { id: "corpus.init-store", label: "Init store" },
      { id: "corpus.init", label: "Init corpus", needsProject: true, mutating: true }
    ],
    project: [],
    pipeline: [],
    function: [
      { id: "mcp.decompile-function", label: "Decompile", needsFunction: true },
      { id: "mcp.get-references", label: "Xrefs", needsFunction: true },
      { id: "mcp.analyze-data-flow", label: "Data flow", needsFunction: true }
    ],
    binary: [
      { id: "recover.inspect", label: "Inspect", needsSlug: true }
    ],
    report: [
      { id: "corpus.export-run-report", label: "Export report" }
    ],
    stabs: []
  };

  function quickActionDisabled(item, flags) {
    if (item.needsFunction && flags.needsFunction) return true;
    if (item.needsSlug && flags.needsSlug) return true;
    if (item.needsProject && flags.needsProject) return true;
    return false;
  }

  function quickActionUnavailable(item, catalog, flags) {
    const act = item.id ? catalog.find(function (row) { return row.id === item.id; }) : null;
    return quickActionDisabled(item, flags) || (item.requiresCatalog && !act);
  }

  function QuickActions({ items, catalog, onPress, flags }) {
    if (!items || !items.length) return null;
    const gate = flags || {};
    return html`<div className="wb-quick-actions" role="toolbar" aria-label="Quick actions">
      ${items.map(function (item, index) {
        const act = item.id ? catalog.find(function (row) { return row.id === item.id; }) : null;
        const label = item.label || (act && act.title) || item.id || "Action";
        const off = quickActionUnavailable(item, catalog, gate);
        return html`<button key=${item.id || item.ui || String(index)} type="button"
          className=${"wb-qact" + (item.danger ? " danger" : "") + (off ? " off" : "")}
          disabled=${off}
          title=${act && act.summary ? act.summary : label}
          onClick=${function () { if (!off) onPress(item); }}>${label}</button>`;
      })}
    </div>`;
  }

  function Surface({ id, title, children, compact, actions }) {
    return html`<section id=${id} className=${"wb-surface" + (compact ? " wb-surface-compact" : "")} aria-labelledby=${id + "-title"}>
      <header className=${"wb-surface-head" + (actions ? " has-actions" : "")}>
        <h2 id=${id + "-title"}>${title}</h2>
        ${actions || null}
      </header>
      ${children}
    </section>`;
  }

  function PanelLayoutDialog({ open, onClose, workspaceId, menuInvokerRef }) {
    const [, refresh] = useState(0);
    const [panelState, setPanelState] = useState(null);
    useEffect(function () {
      if (!open) return;
      setPanelState(null);
      function update(event) {
        if (!event.detail || event.detail.id !== workspaceId) return;
        const current = window.AgentDecompileDockControls && window.AgentDecompileDockControls.get(workspaceId);
        if (current) setPanelState(current.panels);
        refresh(function (n) { return n + 1; });
      }
      window.addEventListener("agentdecompile:dock-controls", update);
      return function () { window.removeEventListener("agentdecompile:dock-controls", update); };
    }, [open, workspaceId]);
    const registry = window.AgentDecompileDockControls;
    const workspace = registry && registry.get(workspaceId);
    function change(action, patch) {
      if (patch && workspace) setPanelState(function (previous) { return (previous || workspace.panels).map(function (panel) { return panel.id === patch.id ? Object.assign({}, panel, patch) : panel; }); });
      action();
    }
    return html`<${Modal} open=${open} title="Arrange panels" onClose=${onClose} menuInvokerRef=${menuInvokerRef}
      footer=${html`<button type="button" className="wb-btn" disabled=${!workspace} onClick=${function () { if (workspace) change(workspace.reset); }}>Restore default layout</button><button type="button" className="wb-btn wb-btn-primary" onClick=${onClose}>Done</button>`}>
      ${workspace ? html`<p>Drag a panel title to move it, or set its position here. Right-click a title for the same controls.</p><div className="wb-panel-layout-list">${(panelState || workspace.panels).map(function (panel) {
        return html`<div key=${panel.id}><label><input type="checkbox" checked=${!panel.hidden} onChange=${function (event) { const checked = event.target.checked; change(function () { checked ? workspace.show(panel.id) : workspace.hide(panel.id); }, {id:panel.id,hidden:!checked}); }}/><span>${panel.title}</span></label><label>Position<select aria-label=${"Position " + panel.title} value=${panel.zone} onChange=${function (event) { const zone = event.target.value; change(function () { workspace.dock(panel.id, zone); }, {id:panel.id,zone:zone}); }}>${["left", "center", "right", "bottom", "floating"].map(function (zone) { return html`<option value=${zone} key=${zone}>${zone === "floating" ? "Floating" : zone.charAt(0).toUpperCase() + zone.slice(1)}</option>`; })}</select></label></div>`;
      })}</div>` : html`<p>Open Compare, Recover or Work to arrange its panels.</p>`}
    </${Modal}>`;
  }

  function SaveAsDialog({ open, onClose, onSubmit, error, menuInvokerRef, locator, project, projectTitle, workDir, target, setTarget, name, setName, destination, setDestination }) {
    const [busy,setBusy]=useState(false),[localError,setLocalError]=useState(""),[picker,setPicker]=useState(null),[reading,setReading]=useState(false);
    const browseSequence=useRef(0),active=useRef(open);
    active.current=open;
    useEffect(function(){browseSequence.current++;setReading(false);if(open){setBusy(false);setLocalError("");setPicker(null);}},[open]);
    const stem=(name||"").trim().replace(/[^\p{L}\p{N}_-]/gu,"_")||"Project";
    const source=project&&project.ok&&(!project.locator||project.locator===locator||project.canonical===locator)?project:null;
    const count=source&&Number.isSafeInteger(source.program_count)?source.program_count:source&&Array.isArray(source.programs)?source.programs.length:null;
    const sourceName=source&&source.slug||String(projectTitle||"Project").replace(/^[^:]+:\s*/,"");
    const remote=target==="shared-project",local=target==="ghidra-project";
    const requested=(destination||"").trim(),base=String(workDir||"").replace(/\/$/,"");
    const folder=requested||(base?(local?base+"/ghidra-projects":base+"/shared-exports/"+stem):"");
    const path=remote?"Native server publication is not available in this adapter.":folder?(local?/\.gpr$/i.test(folder)?folder:folder.replace(/\/$/,"")+"/"+stem+".gpr":folder.replace(/\/$/,"")+"/_"+stem):"The server's configured work directory will determine the destination.";
    const unsupported=source&&!["ghidra-project","shared-fs"].includes(source.kind);
    async function browseFolder(next) {
      const seq=++browseSequence.current;setReading(true);setLocalError("");
      try {
        const response=await fetch(API.browse+"?path="+encodeURIComponent(next||""),{cache:"no-store",signal:AbortSignal.timeout(12000)});
        const packet=await response.json();
        if(seq!==browseSequence.current||!active.current)return;
        if(!response.ok||packet.ok===false)throw new Error(packet.error||"Could not read destination folders.");
        setPicker(packet);
      }catch(reason){if(seq===browseSequence.current&&active.current)setLocalError(String(reason.message||reason));}
      finally{if(seq===browseSequence.current&&active.current)setReading(false);}
    }
    async function submit(event) {
      event.preventDefault();if(busy||remote||unsupported||!locator||!name.trim())return;
      if(requested&&!/^(\/|~\/)/.test(requested)){setLocalError("Use an absolute server path (or ~/…) so the destination does not depend on the server's working directory.");return;}
      setBusy(true);setLocalError("");
      try{await onSubmit(event);}catch(reason){if(active.current)setLocalError(String(reason.message||reason));}
      finally{if(active.current)setBusy(false);}
    }
    return html`<${Modal} open=${open} title="Save project copy" onClose=${function(){if(!busy)onClose();}} error=${localError||error} menuInvokerRef=${menuInvokerRef}
      footer=${html`<button type="button" className="wb-btn" disabled=${busy} onClick=${onClose}>Cancel</button><button type="submit" form="wb-save-as-form" className="wb-btn wb-btn-primary" disabled=${busy||remote||unsupported||!locator||!name.trim()}>${busy?"Copying…":"Save copy and open"}</button>`}>
      <form id="wb-save-as-form" className="wb-save-project-form" onSubmit=${submit} aria-busy=${busy}>
        <section className="wb-save-source" aria-label="Source project"><strong>${sourceName}</strong><span>${count==null?"Program count not recorded":count+" recorded "+(count===1?"program":"programs")}${source&&source.kind?" · "+kindTitle(source.kind):""}</span><code>${locator||"No source project open"}</code></section>
        <div className="wb-save-fields"><label htmlFor="wb-save-name">New project name<input id="wb-save-name" type="text" value=${name} required disabled=${busy} autoComplete="off" onInput=${event=>setName(event.target.value)} aria-describedby="wb-save-name-note"/><small id="wb-save-name-note">${stem===name.trim()?"Names the copied project, not the selected binary.":"Filesystem name: "+stem}</small></label>
        <label htmlFor="wb-save-format">Destination format<select id="wb-save-format" value=${target} disabled=${busy} onChange=${event=>{browseSequence.current++;setReading(false);setTarget(event.target.value);setPicker(null);}}><option value="ghidra-project">Local Ghidra project (.gpr + .rep)</option><option value="shared-fs">Shared repository folder (offline)</option><option value="shared-project" disabled>Ghidra Server publication — unavailable</option></select></label></div>
        <p className="wb-save-format-note">${remote?"This adapter cannot publish a project to a live server. Opening a server URL is not a saved project copy.":local?"Copies program databases and stored version history into a local .gpr project with its .rep directory.":"Copies program databases and stored version history into a server-shaped repository on disk. This does not connect to or publish on a live Ghidra Server."}</p>
        ${!remote?html`<label className="wb-save-destination" htmlFor="wb-save-folder">${local?"Destination folder or .gpr path":"Destination repository root"}<div className="wb-save-path-control"><input id="wb-save-folder" type="text" value=${destination} disabled=${busy} placeholder=${base?(local?base+"/ghidra-projects":base+"/shared-exports/"+stem):"Use configured work directory"} onInput=${event=>setDestination(event.target.value)} aria-describedby="wb-save-destination-note"/><button type="button" className="wb-btn" disabled=${busy||reading} aria-expanded=${Boolean(picker)} onClick=${()=>{if(picker){browseSequence.current++;setPicker(null);}else browseFolder(/\.gpr$/i.test(requested)?requested.slice(0,requested.lastIndexOf("/")):requested||workDir||"");}}>Browse…</button></div><small id="wb-save-destination-note">Server-visible storage only. Leave blank to use the configured work directory.</small></label>`:null}
        ${reading?html`<p role="status">Reading destination folders…</p>`:null}
        ${picker&&!remote?html`<section className="wb-save-folder-picker" aria-label="Choose destination folder"><header><code>${picker.path||"Available storage roots"}</code><button type="button" className="wb-btn" disabled=${busy||reading} onClick=${()=>{browseSequence.current++;setPicker(null);}}>Close browser</button></header><div className="wb-save-folder-actions">${picker.parent?html`<button type="button" className="wb-btn" disabled=${reading} onClick=${()=>browseFolder(picker.parent)}>Parent folder</button>`:null}${picker.path&&picker.kind!=="ghidra-project"?html`<button type="button" className="wb-btn" disabled=${reading} onClick=${()=>{setDestination(picker.path);setPicker(null);}}>Use this folder</button>`:null}</div><ul>${(picker.entries||[]).filter(entry=>["dir","project-dir","shared-fs"].includes(entry.kind)).map(entry=>html`<li key=${entry.path}><button type="button" disabled=${reading} onClick=${()=>browseFolder(entry.path)}><span aria-hidden="true">▱</span> ${entry.name}</button></li>`)}</ul>${!(picker.entries||[]).some(entry=>["dir","project-dir","shared-fs"].includes(entry.kind))?html`<p>No subfolders listed. You can use this folder or enter a new destination path.</p>`:null}</section>`:null}
        <section className="wb-save-output" aria-label="Requested destination"><span>Requested ${local?"project path":"repository path"}</span><output>${path}</output>${!remote?html`<small>${local&&/\.gpr$/i.test(folder)?"Explicit path: existing destination storage is not overwritten. Saving to the source path uses native Save instead of creating a copy.":"The server chooses a numbered suffix if that project already exists; the final path is confirmed after copying."}</small>`:null}</section>
        ${unsupported?html`<p className="wb-dialog-error" role="status">This source does not expose program databases to the copy adapter. Open a local .gpr or a shared repository folder first.</p>`:null}
        <p className="wb-save-scope-note">The source stays in place. The saved destination opens when the copy succeeds. This saves project databases, not a recovered-source export or a byte-verification receipt.</p>
        ${busy?html`<p role="status">Copying the project databases; waiting for the server to confirm the destination. No byte progress is available.</p>`:null}
      </form>
    </${Modal}>`;
  }

  function Modal({ open, title, onClose, children, footer, error, menuInvokerRef }) {
    const boxRef = useRef(null);
    const capturedInvokerRef = useRef(null);
    const moveRef = useRef(null);
    const [position, setPosition] = useState({ x: 0, y: 0 });
    useEffect(function () { if (open) setPosition({ x: 0, y: 0 }); moveRef.current = null; }, [open]);
    function moveBy(dx, dy) {
      if (!boxRef.current) return;
      const r = boxRef.current.getBoundingClientRect();
      setPosition(old => ({ x: old.x + Math.min(innerWidth - r.right - 8, Math.max(8 - r.left, dx)), y: old.y + Math.min(innerHeight - r.bottom - 8, Math.max(8 - r.top, dy)) }));
    }
    function startMove(event) {
      if (event.button !== 0 || event.target.closest("button, input, select")) return;
      event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
      moveRef.current = { x: event.clientX, y: event.clientY };
    }
    function continueMove(event) {
      const start = moveRef.current;
      if (!start) return;
      moveBy(event.clientX - start.x, event.clientY - start.y);
      moveRef.current = { x: event.clientX, y: event.clientY };
    }
    useEffect(function () {
      if (!open || !boxRef.current) return;
      /* A2: remember what had focus before the modal opened, so closing it
         (Escape, backdrop click, or the × button) can put focus back there
         instead of dropping it to <body>. Dialogs opened from a menu item
         are a special case: the item itself unmounts (its menu closes) in
         the same render that opens the dialog, so document.activeElement
         is already <body> by the time this effect runs. menuInvokerRef is
         the surviving menu-trigger button captured at click time, before
         that unmount -- prefer it when present. */
      const menuInvoker = menuInvokerRef && menuInvokerRef.current;
      capturedInvokerRef.current = (menuInvoker && document.contains(menuInvoker))
        ? menuInvoker
        : document.activeElement;
      if (menuInvokerRef) menuInvokerRef.current = null;
      const first = boxRef.current.querySelector("input, select, textarea, button.wb-btn-primary") || boxRef.current.querySelector("button");
      if (first && typeof first.focus === "function") first.focus();
      return function () {
        const invoker = capturedInvokerRef.current;
        if (invoker && typeof invoker.focus === "function" && document.contains(invoker)) {
          invoker.focus();
        }
        capturedInvokerRef.current = null;
      };
    }, [open]);
    if (!open) return null;
    /* Tab stays inside the dialog, the way a modal window behaves on a desktop. */
    function onKeyDown(ev) {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); onClose(); return; }
      if (ev.key !== "Tab" || !boxRef.current) return;
      const focusable = Array.prototype.filter.call(
        boxRef.current.querySelectorAll("a[href], button, input, select, textarea, [tabindex]"),
        function (node) { return !node.disabled && node.offsetParent !== null; }
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    }
    return html`<div className="wb-modal-backdrop" onClick=${onClose}>
      <div className="wb-modal" role="dialog" aria-modal="true" aria-labelledby="wb-modal-title"
        ref=${boxRef}
        style=${{ transform: "translate(" + position.x + "px," + position.y + "px)" }}
        onKeyDown=${onKeyDown}
        onClick=${function (ev) { ev.stopPropagation(); }}>
        <header className="wb-modal-head" tabIndex="0" aria-label=${title + "; drag to move, Alt and arrow keys to move, double-click to center"}
          onPointerDown=${startMove} onPointerMove=${continueMove} onPointerUp=${function () { moveRef.current = null; }} onPointerCancel=${function () { moveRef.current = null; }}
          onDoubleClick=${function (event) { if (!event.target.closest("button")) setPosition({ x: 0, y: 0 }); }}
          onKeyDown=${function (event) { if (event.altKey && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); moveBy(event.key === "ArrowLeft" ? -20 : event.key === "ArrowRight" ? 20 : 0, event.key === "ArrowUp" ? -20 : event.key === "ArrowDown" ? 20 : 0); } }}>
          <h2 id="wb-modal-title">${title}</h2>
          <button type="button" className="wb-modal-close" aria-label="Close" onClick=${onClose}>×</button>
        </header>
        <div className="wb-modal-body">
          ${error ? html`<p className="wb-dialog-error" role="alert">${error}</p>` : null}
          ${children}
        </div>
        ${footer ? html`<footer className="wb-modal-foot">${footer}</footer>` : null}
      </div>
    </div>`;
  }

  const MORE_SURFACE_IDS = new Set([
    "wb-overview", "wb-atlas", "wb-report", "wb-pipeline",
    "wb-jobs", "wb-stabs", "wb-knowledge",
    "wb-roundtrip", "wb-processes", "wb-mission", "wb-corpus", "wb-review",
    "wb-logical", "wb-artifacts", "wb-evidence", "wb-tools"
  ]);


  const CORPUS_NAV = [
    { id: "wb-guide", title: "Reversing guide", more: true },
    { id: "wb-tools", title: "Commands", more: true }
  ];

  /* Guide rail (slice 5). Titles and guide-anchor labels are reused verbatim
     from the Vite frontend's GuideWorkflows.tsx (8 chapters, same order) so the
     static dashboard doesn't grow a second guide taxonomy. GuideWorkflows.tsx
     has no per-chapter URL (only a short "N · Section name" label) so a rail
     click only focuses the mapped pane -- it never opens a tab and never calls
     executeAction. `target` is the closest existing surface/centerTab id;
     several chapters share one because the corresponding first-class surface
     (Symbol Tree, Types/Structures/Vtables dock) doesn't exist yet -- see
     docs/dashboard-design/2026-09-28-static-codebrowser-guide-redesign.md §2.3. */
  const GUIDE_CHAPTERS = [
    { title: "Orient to the project", guide: "2–3 · Projects and code browser", target: "wb-sidebar" },
    { title: "Find symbols and types", guide: "4–5 · Symbol tree and data type manager", target: "wb-fnbrowse" },
    { title: "Read bytes and reconstructed code", guide: "6–7 · Listing and decompile view", target: "decompile" },
    { title: "Trace relationships and keep notes", guide: "8 · Call trees, memory map, and bookmarks", target: "graph" },
    { title: "Check function signatures and ABI", guide: "9–11 · Functions, conventions, and return storage", target: "wb-fnbrowse" },
    { title: "Recover structures and virtual dispatch", guide: "12–13 · Structures and vtables", target: "wb-tools" },
    { title: "Compare template instantiations", guide: "14 · Template classes", target: "wb-tools" },
    { title: "Diagnose decompiler inconsistencies", guide: "15–16 · Common issues and next steps", target: "decompile" }
  ];

  const EDITOR_TABS = EDITOR_PRIMARY.concat(CORPUS_NAV);

  /* The browse page's old anchors and query keys still arrive from bookmarks,
     redirects and other panels, so they select a window instead of a second page. */
  const BROWSE_ANCHOR_WINDOW = {
    functions: "wb-fnbrowse",
    logical: "wb-logical",
    review: "wb-review",
    graph: "graph",
    builds: "wb-corpus"
  };

  function bootWindow() {
    const hash = String((window.location.hash || "").replace(/^#/, "")).toLowerCase();
    if (BROWSE_ANCHOR_WINDOW[hash]) return editorTabFor(BROWSE_ANCHOR_WINDOW[hash]);
    const want = String(params().get("window") || "").trim();
    if (!want) return "wb-overview";
    if (BROWSE_ANCHOR_WINDOW[want.toLowerCase()]) {
      return editorTabFor(BROWSE_ANCHOR_WINDOW[want.toLowerCase()]);
    }
    return editorTabFor(want);
  }

  function editorTabFor(id) {
    if (["wb-tools", "wb-guide"].includes(id)) return id;
    if (["wb-artifacts", "wb-roundtrip", "wb-recovery", "recover", "recovery", "artifact", "artifacts", "wb-evidence", "evidence"].includes(id)) return "wb-artifacts";
    if (["wb-pipeline", "wb-processes", "wb-jobs", "wb-activity"].includes(id)) return "wb-pipeline";
    return "wb-overview";
  }

  const RECENT_ACTIONS_KEY = "wb-recent-actions";

  function readRecentActionIds() {
    try {
      const raw = localStorage.getItem(RECENT_ACTIONS_KEY);
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list.filter(function (item) { return typeof item === "string"; }) : [];
    } catch (_err) {
      return [];
    }
  }

  function pushRecentActionId(actionId) {
    if (!actionId) return;
    try {
      const next = [actionId].concat(readRecentActionIds().filter(function (item) {
        return item !== actionId;
      })).slice(0, 8);
      localStorage.setItem(RECENT_ACTIONS_KEY, JSON.stringify(next));
    } catch (_err) { /* private mode */ }
  }

  function readUiPref(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value != null && value !== "" ? value : fallback;
    } catch (_err) {
      return fallback;
    }
  }

  function writeUiPref(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_err) { /* private mode */ }
  }

  function scrollToSurface(surfaceId) {
    const aliases = {
      decompile: "wb-comparison-evidence", "wb-inspect": "wb-comparison-evidence",
      inspect: "wb-comparison-evidence", graph: "wb-comparison-evidence", "wb-graph": "wb-comparison-evidence",
      "wb-fnbrowse": "wb-q", "wb-functions": "wb-q"
    };
    window.requestAnimationFrame(function () {
      const node = document.getElementById(aliases[surfaceId] || surfaceId);
      if (!node) return;
      node.scrollIntoView({ block: "nearest" });
      if (node.id === "wb-q" || node.hasAttribute("tabindex")) node.focus({ preventScroll: true });
    });
  }

  function readActionParams(form, action, ctx) {
    if (!form || !action) return {};
    const params = {};
    (action.fields || []).forEach(function (field) {
      const el = form.elements.namedItem(field.name);
      if (!el) return;
      let value;
      if (field.kind === "bool") {
        value = el.checked;
        if (!value && !field.required) return;
      } else {
        value = el.value;
        if (value === "" || value == null) return;
      }
      const def = defaultToolValue(field, ctx);
      if (field.kind === "bool") {
        if (Boolean(value) === Boolean(def === true || def === "true")) return;
      } else if (String(value) === String(def || "")) return;
      params[field.name] = value;
    });
    return params;
  }

  function actionTitle(id, catalog) {
    const key = String(id || "");
    if (!key) return "";
    const known = {
      "corpus.add-binary": "Opened project",
      "corpus.remove-binary": "Removed program",
      "corpus.edit-binary": "Edited program",
      "corpus.extract-stabs": "Extract STABS",
      "corpus.bsim-ingest": "BSim ingest",
      "corpus.bsim-report": "BSim report",
      "corpus.cross-place": "Cross-place",
      "corpus.match-pair": "Match pair",
      "corpus.apply-stabs": "Apply STABS",
      "corpus.logical-build": "Logical build",
      "corpus.merge-parts": "Merge parts",
      "corpus.propagate-source": "Propagate source",
      "corpus.export-c": "Export C",
      "mcp.analyze-program": "Analyze program",
      "mcp.match-function": "Match function",
      "mcp.decompile-function": "Decompile",
      "reconstruct.one-shot": "Dump source"
    };
    if (known[key]) return known[key];
    const act = (catalog || []).find(function (item) { return item.id === key; });
    if (act && act.title) return act.title;
    return key.split(".").pop().replace(/-/g, " ");
  }

  function formatJobSummary(data, catalog) {
    if (!data) return "";
    if (data.job) {
      const job = data.job;
      const title = actionTitle(job.actionId, catalog);
      return "Job " + job.id + " — " + (job.status || "started")
        + (title ? " (" + title + ")" : "");
    }
    if (data.ok === false && data.error) return String(data.error);
    if (data.argv && data.argv.length) return "Dry run: " + data.argv.slice(0, 8).join(" ");
    return "";
  }

  function actionUsesAddr(act) {
    if (!act) return false;
    if ((act.fields || []).some(function (field) {
      return ADDR_FIELD_NAMES.has(normFieldName(field.name)) || field.from_context === "addr";
    })) return true;
    const id = String(act.id || "");
    return /function|rename-variable|get-references|analyze-data-flow|match-function/.test(id);
  }

  function toggleAddrList(list, addr) {
    const next = (list || []).slice();
    const i = next.indexOf(addr);
    if (i >= 0) next.splice(i, 1);
    else if (addr) next.push(addr);
    return next;
  }

  function rangeAddrList(rows, fromAddr, toAddr) {
    const addrs = (rows || []).map(function (row) { return row.addr; });
    const a = addrs.indexOf(fromAddr);
    const b = addrs.indexOf(toAddr);
    if (a < 0 && b < 0) return [];
    if (a < 0) return toAddr ? [toAddr] : [];
    if (b < 0) return fromAddr ? [fromAddr] : [];
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    return addrs.slice(lo, hi + 1);
  }

  function mergeAddrLists(base, extra) {
    const seen = {};
    const out = [];
    (base || []).concat(extra || []).forEach(function (addr) {
      if (!addr || seen[addr]) return;
      seen[addr] = true;
      out.push(addr);
    });
    return out;
  }

  function jobLiveAnnouncement(prevList, nextList) {
    const prev = {};
    (prevList || []).forEach(function (job) { prev[job.id] = job.status; });
    const parts = [];
    (nextList || []).forEach(function (job) {
      const was = prev[job.id];
      if (was === job.status) return;
      const id = String(job.id || "unknown").slice(0, 80);
      if (!was && (job.status === "running" || job.status === "queued")) {
        parts.push("Job " + id + " started");
      } else if (was && (job.status === "error" || job.status === "failed")) {
        parts.push("Job " + id + " failed");
      } else if (was && (job.status === "done" || job.status === "finished" || job.status === "ok" || job.status === "completed")) {
        parts.push("Job " + id + " finished. A finished job is not a match.");
      } else if (was && (job.status === "cancelled" || job.status === "canceled")) {
        parts.push("Job " + id + " cancelled");
      }
    });
    const shown = parts.slice(0, 3);
    if (parts.length > shown.length) shown.push("and " + (parts.length - shown.length) + " more job updates");
    return shown.join(". ");
  }

  function measuredJobPercent(job) {
    const progress = job && job.workProgress;
    if (!progress) return null;
    const completed = progress.completed;
    const total = progress.total;
    if (typeof completed !== "number" || typeof total !== "number") return null;
    if (!Number.isFinite(completed) || !Number.isFinite(total) || total <= 0 || completed < 0 || completed > total) return null;
    return Math.round(100 * completed / total);
  }

  function JobLiveRegion({ text }) {
    return html`<div id="wb-job-live" className="sr-only" aria-live="polite" aria-atomic="true">${text || ""}</div>`;
  }

  /* Accelerators are stored as specs and rendered per platform, so a Linux menu never
     promises "⌘". Ctrl+N / Ctrl+T / Ctrl+W / Ctrl+J / Ctrl+digit belong to the browser and
     cannot be intercepted by a page, so tab and window verbs ride Alt instead. */
  const IS_MAC = /mac|iphone|ipad/i.test(
    (window.navigator && (window.navigator.platform || window.navigator.userAgent)) || ""
  );

  function accelLabel(spec) {
    if (!spec) return "";
    if (IS_MAC) {
      return spec.replace(/mod\+/g, "⌘").replace(/alt\+/g, "⌥").replace(/shift\+/g, "⇧");
    }
    return spec.replace(/mod\+/g, "Ctrl+").replace(/alt\+/g, "Alt+").replace(/shift\+/g, "Shift+");
  }

  const WORKBENCH_COMMANDS = [
    { id: "file.new-project", title: "New Project…", accel: "alt+N", group: "File" },
    { id: "file.new-tab", title: "New Tab", accel: "alt+T", group: "File" },
    { id: "file.open", title: "Open…", accel: "mod+O", group: "File" },
    { id: "file.open-url", title: "Open from URL…", accel: "mod+shift+U", group: "File" },
    { id: "file.save", title: "Save", accel: "mod+S", group: "File" },
    { id: "file.save-as", title: "Save As…", accel: "mod+shift+S", group: "File" },
    { id: "file.download-source", title: "Download project source", group: "File" },
    { id: "file.checkin", title: "Check in to Ghidra server", group: "File" },
    { id: "file.open-program", title: "Open selected program in Ghidra", group: "File" },
    { id: "file.add-binaries", title: "Add to project…", accel: "mod+I", group: "File" },
    { id: "file.remove-binary", title: "Remove from project", accel: "Del", group: "File" },
    { id: "file.reload", title: "Reload from disk", accel: "alt+R", group: "File" },
    { id: "file.close-tab", title: "Close Tab", accel: "alt+W", group: "File" },
    { id: "edit.rename-tab", title: "Rename Tab", accel: "F2", group: "Edit" },
    { id: "view.palette", title: "Command palette", accel: "mod+K", group: "View" },
    { id: "view.explorer", title: "Explorer", accel: "mod+shift+E", group: "View" },
    { id: "view.panels", title: "Arrange panels…", group: "View" },
    { id: "view.match-receipts", title: "Matching receipts…", group: "View" },
    { id: "view.listing", title: "Listing", accel: "alt+1", group: "View" },
    { id: "view.browse", title: "Functions", accel: "alt+F", group: "View" },
    { id: "view.graph", title: "Call trees", accel: "alt+2", group: "View" },
    { id: "view.artifacts", title: "Artifacts", group: "View" },
    { id: "view.evidence", title: "Database evidence", group: "View" },
    { id: "view.logical", title: "Logical identities", accel: "alt+L", group: "View" },
    { id: "view.overview", title: "Overview", accel: "alt+3", group: "View" },
    { id: "view.atlas", title: "Atlas", accel: "alt+4", group: "View" },
    { id: "view.cross-match", title: "Cross-build", accel: "alt+5", group: "View" },
    { id: "view.inspect", title: "Inspector", accel: "alt+6", group: "View" },
    { id: "view.tools", title: "Commands", accel: "alt+7", group: "View" },
    { id: "view.jobs", title: "Jobs", accel: "alt+J", group: "View" },
    { id: "view.pipeline", title: "Pipeline", group: "View" },
    { id: "view.report", title: "Report", group: "View" },
    { id: "view.recovery", title: "Recover", group: "View" },
    { id: "view.stabs", title: "STABS", group: "View" },
    { id: "view.knowledge", title: "Knowledge", group: "View" },
    { id: "view.review", title: "Review", group: "View" },
    { id: "view.corpus", title: "Corpus table", group: "View" },
    { id: "view.density-compact", title: "Use compact layout", group: "View" },
    { id: "view.density-comfortable", title: "Use roomy layout", group: "View" },
    { id: "view.jobs-rail", title: "Dock jobs on the side", group: "View" },
    { id: "view.jobs-bottom", title: "Dock jobs at the bottom", group: "View" },
    { id: "view.classic-layout", title: "Use classic layout", group: "View" },
    { id: "run.last", title: "Run last action", accel: "Enter", group: "Run" },
    { id: "help.access", title: "Shortcuts and menus…", accel: "shift+?", group: "Help" },
    { id: "help.overview", title: "Overview", group: "Help" }
  ];

  const COMMAND_BY_ID = {};
  WORKBENCH_COMMANDS.forEach(function (cmd) { COMMAND_BY_ID[cmd.id] = cmd; });

  const COMMAND_ACCEL = {};
  WORKBENCH_COMMANDS.forEach(function (cmd) {
    if (cmd.accel) COMMAND_ACCEL[cmd.title] = accelLabel(cmd.accel);
  });

  /* Context menus quote the catalog so a shortcut only ever has to be spelled once. */
  function decorateCommandItem(item) {
    if (typeof item === "string") return item;
    const cmd = COMMAND_BY_ID[item.id];
    if (!cmd) return item;
    return Object.assign({}, item, {
      title: item.title || cmd.title,
      accel: item.accel || accelLabel(cmd.accel)
    });
  }

  function surfaceTitle(id) {
    const hit = EDITOR_TABS.concat(SURFACES).find(function (item) {
      return item.id === id || item.id === editorTabFor(id);
    });
    return (hit && hit.title) || id;
  }

  function ContextMenu({ menu, onPick, onClose }) {
    if (!menu || !menu.items || !menu.items.length) return null;
    return html`<div className="wb-ctx-backdrop" onClick=${onClose}
      onContextMenu=${function (ev) { ev.preventDefault(); onClose(); }}>
      <ul className="wb-ctx-menu" role="menu" style=${{ left: menu.x + "px", top: menu.y + "px" }}>
        ${menu.items.map(function (item, index) {
          if (item === "—") return html`<li key=${"s" + index} className="wb-ctx-sep" role="separator" />`;
          return html`<li key=${item.id || item.title} role="none">
            <button type="button" className=${"wb-ctx-item" + (item.danger ? " danger" : "")} role="menuitem"
              data-cmd=${item.id || ""}
              onClick=${function () { onPick(item); }}>
              <span>${item.title}</span>
              ${item.accel ? html`<span className="wb-accel">${item.accel}</span>` : null}
            </button>
          </li>`;
        })}
      </ul>
    </div>`;
  }

  function ConfirmDialog({ open, title, message, confirmLabel, danger, onConfirm, onCancel }) {
    const goRef = useRef(null);
    useEffect(function () {
      if (open && goRef.current) goRef.current.focus();
    }, [open]);
    if (!open) return null;
    return html`<div className="wb-modal-backdrop wb-confirm-backdrop" onClick=${onCancel}>
      <div className="wb-modal wb-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="wb-confirm-title"
        onClick=${function (ev) { ev.stopPropagation(); }}
        onKeyDown=${function (ev) {
          if (ev.key === "Enter") { ev.preventDefault(); if (onConfirm) onConfirm(); }
          if (ev.key === "Escape") { ev.preventDefault(); if (onCancel) onCancel(); }
        }}>
        <header className="wb-modal-head">
          <h2 id="wb-confirm-title">${title || "Confirm"}</h2>
        </header>
        <div className="wb-modal-body">
          ${message ? html`<p>${message}</p>` : null}
        </div>
        <footer className="wb-modal-foot wb-confirm">
          <button type="button" className="wb-btn" onClick=${onCancel}>Cancel</button>
          <button type="button" className=${"wb-btn wb-btn-primary" + (danger ? " danger" : "")}
            ref=${goRef} onClick=${onConfirm}>${confirmLabel || "Confirm"}</button>
        </footer>
      </div>
    </div>`;
  }

  /* Guide rail (slice 5, §5.3): state is derived only from data already in
     scope, never invented. `reachable`/`evidence` are booleans the caller
     computes from real app state (program selection, loaded rows/detail/
     graph); this component only renders them. Clicking a step focuses its
     mapped pane through the existing jumpTo mechanism -- it never runs an
     action and never opens a network request. */
  function GuideRail({ chapters, centerTab, reachable, evidence, onJump }) {
    return html`<nav className="wb-guide-rail" aria-label="Guide">
      <ol className="wb-guide-list">
        ${chapters.map(function (chapter, i) {
          const isReachable = Boolean(reachable[i]);
          const inView = isReachable && centerTab === chapter.target;
          const hasEvidence = isReachable && Boolean(evidence[i]);
          const state = !isReachable ? "partial" : inView ? "active" : hasEvidence ? "proven" : "default";
          const stateText = !isReachable ? "not reachable yet"
            : inView ? "in view"
              : hasEvidence ? "has evidence"
                : "not started";
          const label = (i + 1) + ". " + chapter.title + " (" + chapter.guide + ") — " + stateText;
          return html`<li key=${chapter.title}>
            <button type="button" className="wb-guide-step" data-state=${state}
              title=${chapter.title}
              aria-label=${label}
              aria-current=${inView ? "step" : undefined}
              onClick=${function () { onJump(chapter.target); }}>
              <span className="wb-guide-dot" aria-hidden="true">${String(i + 1).padStart(2, "0")}</span>
              <span className="sr-only">${label}</span>
            </button>
          </li>`;
        })}
      </ol>
    </nav>`;
  }

  /* Symbol Tree (slice 1, redesign §5.1/§6 row 1). Lives under Explorer in the
     left column. Every node is fetched lazily, through `runReadAction`
     (same POST-then-poll idiom `executeAction` and `loadFunctionEvidence`
     already use), and only the read-only catalog actions confirmed
     `danger:false, mutating:false, long_running:false`:
     mcp.search-symbols, mcp.list-imports, mcp.list-exports,
     mcp.get-current-program. Nothing here ever calls a mutating action.

     Classes and Namespaces both derive from one cached mcp.search-symbols
     sweep, grouped client-side by the `namespace` field each symbol already
     carries -- the action has no dedicated class-vs-namespace filter, so
     "Classes" narrows that same grouping to namespaces that look like real
     C++ types (not an import DLL, not the external/global bucket). This is
     a heuristic, not a guarantee, and is called out as such in the slice
     report.

     The Functions node never renders its own rows (FRONTEND_INTENT §4.2 /
     §9 -- two Functions surfaces are banned): clicking it only calls
     onOpenFunctions(), which switches the existing wb-fnbrowse tab. */
  const SYMTREE_PAGE = 200;

  function looksLikeClassNamespace(name) {
    if (!name) return false;
    if (name === "Global" || name === "<EXTERNAL>") return false;
    if (/\.(DLL|dll|EXE|exe)$/.test(name)) return false;
    return true;
  }

  function SymbolTreeNode({ id, title, depth, expanded, loading, error, onToggle, children, isLeaf, onActivate, hint }) {
    const indent = { paddingLeft: (depth * 14) + "px" };
    return html`<li className="wb-symtree-li" role="treeitem" aria-expanded=${isLeaf ? undefined : Boolean(expanded)}>
      <button type="button" className=${"wb-symtree-row wb-text-action" + (isLeaf ? " wb-symtree-leaf" : "")}
        style=${indent}
        title=${hint || title}
        onClick=${function () { (isLeaf ? onActivate : onToggle)(id); }}>
        ${!isLeaf ? html`<span className="wb-symtree-caret" aria-hidden="true">${expanded ? "▾" : "▸"}</span>` : null}
        <span className="wb-symtree-label">${title}</span>
        ${loading ? html`<span className="wb-hint wb-symtree-loading">loading…</span>` : null}
      </button>
      ${error ? html`<p className="wb-hint wb-symtree-error" style=${{ paddingLeft: ((depth + 1) * 14) + "px" }}>${error}</p>` : null}
      ${expanded && children ? html`<ul className="wb-symtree-children" role="group">${children}</ul>` : null}
    </li>`;
  }

  function SymbolTree({ program, scopeKey, hint, runReadAction, onOpenFunctions, onSelectFunction }) {
    const [expanded, setExpanded] = useState({});
    const [nodes, setNodes] = useState({}); // key -> { items, error, offset, hasMore, loading }
    const [symbolSweep, setSymbolSweep] = useState(null); // shared cache for classes/namespaces

    useEffect(function () {
      setExpanded({});
      setNodes({});
      setSymbolSweep(null);
    }, [program]);

    function patchNode(key, patch) {
      setNodes(function (prev) {
        return Object.assign({}, prev, { [key]: Object.assign({}, prev[key], patch) });
      });
    }

    async function ensureSymbolSweep() {
      if (symbolSweep) return symbolSweep;
      const pending = { loading: true };
      setSymbolSweep(pending);
      const result = await runReadAction("mcp.search-symbols", {
        query: "", includeExternal: false, limit: 500
      }, { timeoutMs: 8000 });
      const next = result.ok
        ? { scopeKey: scopeKey, items: (result.data && result.data.results) || [] }
        : { error: result.error || "Could not read symbols." };
      setSymbolSweep(next);
      return next;
    }

    async function loadNamespaceGroup(key, filterFn) {
      patchNode(key, { loading: true, error: "" });
      const sweep = await ensureSymbolSweep();
      if (sweep.error) { patchNode(key, { loading: false, error: sweep.error }); return; }
      const seen = new Set();
      const names = [];
      (sweep.items || []).forEach(function (sym) {
        const ns = sym.namespace || "";
        if (!ns || seen.has(ns) || !filterFn(ns)) return;
        seen.add(ns);
        names.push(ns);
      });
      names.sort();
      patchNode(key, { loading: false, items: names.slice(0, SYMTREE_PAGE), hasMore: names.length > SYMTREE_PAGE, allNames: names, offset: SYMTREE_PAGE });
    }

    async function loadNamespaceMembers(nsKey, namespace) {
      patchNode(nsKey, { loading: true, error: "" });
      const sweep = await ensureSymbolSweep();
      if (sweep.error) { patchNode(nsKey, { loading: false, error: sweep.error }); return; }
      const members = (sweep.items || []).filter(function (sym) { return sym.namespace === namespace; });
      patchNode(nsKey, { scopeKey: sweep.scopeKey, loading: false, items: members.slice(0, SYMTREE_PAGE), hasMore: members.length > SYMTREE_PAGE });
    }

    async function loadFlatAction(key, actionId, offset) {
      patchNode(key, { loading: true, error: "" });
      const result = await runReadAction(actionId, { limit: SYMTREE_PAGE, offset: offset || 0 }, { timeoutMs: 8000 });
      if (!result.ok) { patchNode(key, { loading: false, error: result.error || "Could not load this list." }); return; }
      const results = (result.data && result.data.results) || [];
      const hasMore = Boolean(result.data && result.data.hasMore);
      setNodes(function (prev) {
        const prior = (offset && prev[key] && prev[key].items) || [];
        const priorScope = offset && prev[key] ? prev[key].scopeKey : scopeKey;
        return Object.assign({}, prev, {
          [key]: { scopeKey: priorScope === scopeKey ? scopeKey : null, loading: false, error: "", items: prior.concat(results), hasMore: hasMore, offset: (offset || 0) + results.length }
        });
      });
    }

    function toggle(key, loader) {
      setExpanded(function (prev) {
        const next = Object.assign({}, prev, { [key]: !prev[key] });
        if (next[key] && !nodes[key]) loader();
        return next;
      });
    }

    function activateFunction(name, addr, scope) {
      onSelectFunction({ name: name, addr: addr }, scope);
    }

    if (!program) {
      return html`<div id="wb-symtree" className="wb-sidebar-section wb-symbol-tree">
        <header className="wb-sidebar-head"><h3>Symbol Tree</h3></header>
        <p className="wb-hint">Pick a program in Explorer to browse its symbols.</p>
      </div>`;
    }
    if (hint) {
      return html`<div id="wb-symtree" className="wb-sidebar-section wb-symbol-tree">
        <header className="wb-sidebar-head"><h3>Symbol Tree</h3></header>
        <p className="wb-hint">${hint}</p>
      </div>`;
    }

    function namespaceChildren(key) {
      const node = nodes[key];
      if (!node || !node.items) return null;
      return node.items.map(function (ns) {
        const nsKey = key + ":" + ns;
        const nsNode = nodes[nsKey];
        return html`<${SymbolTreeNode} key=${nsKey} id=${nsKey} title=${ns} depth=${1}
          expanded=${Boolean(expanded[nsKey])} loading=${nsNode && nsNode.loading} error=${nsNode && nsNode.error}
          onToggle=${function () { toggle(nsKey, function () { loadNamespaceMembers(nsKey, ns); }); }}
          isLeaf=${false}
          children=${expanded[nsKey] && nsNode && nsNode.items ? nsNode.items.map(function (sym) {
            return html`<${SymbolTreeNode} key=${nsKey + "#" + sym.address} id=${nsKey + "#" + sym.address}
              title=${(sym.name || sym.address) + " " + (sym.address || "")} depth=${2}
              isLeaf=${true}
              onActivate=${function () { activateFunction(sym.name, sym.address, nsNode.scopeKey); }} />`;
          }).concat(nsNode.hasMore ? [html`<li key=${nsKey + "-more"} className="wb-symtree-li" style=${{ paddingLeft: "28px" }}>
            <span className="wb-hint">${nsNode.items.length} shown, more available</span>
          </li>`] : []) : null} />`;
      }).concat(node.hasMore ? [html`<li key=${key + "-more"} className="wb-symtree-li">
        <button type="button" className="wb-text-action wb-symtree-more" style=${{ paddingLeft: "14px" }}
          onClick=${function () {
            const shown = node.items.length;
            patchNode(key, { items: node.allNames.slice(0, shown + SYMTREE_PAGE), hasMore: node.allNames.length > shown + SYMTREE_PAGE });
          }}>Show more…</button>
      </li>`] : []);
    }

    function flatChildren(key) {
      const node = nodes[key];
      if (!node || !node.items) return null;
      const items = node.items.map(function (item, i) {
        const label = (item.name || "") + "  " + (item.address || "") + (item.library ? "  (" + item.library + ")" : "");
        return html`<${SymbolTreeNode} key=${key + "#" + i + "#" + item.address} id=${key + "#" + i}
          title=${label} depth=${1} isLeaf=${true}
          onActivate=${function () { activateFunction(item.name, item.address, node.scopeKey); }} />`;
      });
      if (node.hasMore) {
        items.push(html`<li key=${key + "-more"} className="wb-symtree-li">
          <button type="button" className="wb-text-action wb-symtree-more" style=${{ paddingLeft: "14px" }}
            onClick=${function () { loadFlatAction(key, key === "imports" ? "mcp.list-imports" : "mcp.list-exports", node.offset); }}>Show more…</button>
        </li>`);
      }
      return items;
    }

    return html`<div id="wb-symtree" className="wb-sidebar-section wb-symbol-tree">
      <header className="wb-sidebar-head"><h3>Symbol Tree</h3></header>
      <ul className="wb-symtree-root" role="tree" aria-label="Symbol tree">
        <${SymbolTreeNode} key="classes" id="classes" title="Classes" depth=${0}
          expanded=${Boolean(expanded.classes)} loading=${nodes.classes && nodes.classes.loading} error=${nodes.classes && nodes.classes.error}
          onToggle=${function () { toggle("classes", function () { loadNamespaceGroup("classes", looksLikeClassNamespace); }); }}
          isLeaf=${false}
          children=${expanded.classes ? namespaceChildren("classes") : null} />
        <${SymbolTreeNode} key="namespaces" id="namespaces" title="Namespaces" depth=${0}
          expanded=${Boolean(expanded.namespaces)} loading=${nodes.namespaces && nodes.namespaces.loading} error=${nodes.namespaces && nodes.namespaces.error}
          onToggle=${function () { toggle("namespaces", function () { loadNamespaceGroup("namespaces", function () { return true; }); }); }}
          isLeaf=${false}
          children=${expanded.namespaces ? namespaceChildren("namespaces") : null} />
        <${SymbolTreeNode} key="imports" id="imports" title="Imports" depth=${0}
          expanded=${Boolean(expanded.imports)} loading=${nodes.imports && nodes.imports.loading} error=${nodes.imports && nodes.imports.error}
          onToggle=${function () { toggle("imports", function () { loadFlatAction("imports", "mcp.list-imports", 0); }); }}
          isLeaf=${false}
          children=${expanded.imports ? flatChildren("imports") : null} />
        <${SymbolTreeNode} key="exports" id="exports" title="Exports" depth=${0}
          expanded=${Boolean(expanded.exports)} loading=${nodes.exports && nodes.exports.loading} error=${nodes.exports && nodes.exports.error}
          onToggle=${function () { toggle("exports", function () { loadFlatAction("exports", "mcp.list-exports", 0); }); }}
          isLeaf=${false}
          children=${expanded.exports ? flatChildren("exports") : null} />
        <li className="wb-symtree-li" role="treeitem">
          <button type="button" className="wb-symtree-row wb-text-action" style=${{ paddingLeft: "0" }}
            title="Open the Functions tab"
            onClick=${onOpenFunctions}>
            <span className="wb-symtree-caret" aria-hidden="true">▸</span>
            <span className="wb-symtree-label">Functions</span>
          </button>
        </li>
      </ul>
    </div>`;
  }

  /* Continuous Listing rows (slice 2, redesign §5.1/§6 row 2). Replaces the
     #wb-listing-preview text blob with an address/bytes/mnemonic/operands/
     xref row table, backed by mcp.inspect-memory (mode: "instruction",
     chained through each row's own fallThrough address) plus one
     mcp.get-references call (mode: "to") for the function entry. Both are
     confirmed danger:false/mutating:false/long_running:false in the catalog
     -- same runReadAction reader the Symbol Tree uses.

     Each inspect-memory round trip on this backend is a real Ghidra bridge
     call, not a local computation -- measured against repos-local.gpr /
     DragonAge2.exe it runs ~1.1s per instruction (see slice report). A
     continuous table of any real size will blow past a 5s budget, so this
     component fetches what it can inside `budgetMs` and falls back to the
     existing detail.preview text -- with the measured elapsed time shown --
     rather than pretend a partial or synthetic result is the whole listing. */
  // "00b411a0  b6 f1   MOV DH,0xf1" lines from get-function's disassembly.
  function parseAssemblyRows(text, addr) {
    if (!text) return null;
    const want = parseInt(String(addr || "").replace(/^0x/i, ""), 16);
    const rows = [];
    let found = false;
    String(text).split("\n").forEach(function (line) {
      const m = /^\s*([0-9a-fA-F]{6,16})\s+((?:[0-9a-fA-F]{2} )*[0-9a-fA-F]{2})\s+((?:(?:REP[A-Z]*|LOCK)\s+)?\S+)\s*(.*)$/i.exec(line);
      if (!m) return;
      const at = parseInt(m[1], 16);
      if (at === want) found = true;
      const targets = (m[4].match(/0x[0-9a-fA-F]{6,16}/g) || []);
      const branch = /^(CALL|J[A-Z]{1,3}|LOOP[A-Z]*)$/i.test(m[3].split(/\s+/).pop());
      rows.push({
        addr: "0x" + m[1].toLowerCase(),
        bytes: m[2],
        mnemonic: m[3],
        operands: m[4].trim(),
        flows: branch ? targets : []
      });
    });
    return rows.length && found ? rows : null;
  }

  function ListingRows({ addr, name, program, runReadAction, fallbackText, onJumpAddr, budgetMs, assemblyText }) {
    const [state, setState] = useState({ status: "idle" });
    const [requestedScope, setRequestedScope] = useState("");
    const listingScope = JSON.stringify([program, addr]);
    const [focusIdx, setFocusIdx] = useState(0);
    const seqRef = useRef(0);
    const rowRefs = useRef([]);

    useEffect(function () {
      let cancelled = false;
      const seq = ++seqRef.current;
      // Address/target changes remount this component; evidence refresh retains focus.
      if (!addr || !program) { setState({ status: "idle" }); return undefined; }
      // The function read already carries its whole disassembly; use it rather
      // than one inspect-memory round trip per instruction.
      const parsed = parseAssemblyRows(assemblyText, addr);
      if (parsed) {
        setState({ status: "ok", rows: parsed, elapsedMs: 0, budgetHit: false, inboundCount: null });
        return undefined;
      }
      // Viewing an uncached listing is not permission to queue an instruction
      // walk. The operator explicitly acquires it; browsing stays read-only.
      if (requestedScope !== listingScope) { setState({ status: "idle" }); return undefined; }
      setState({ status: "loading" });
      const t0 = (window.performance && performance.now) ? performance.now() : Date.now();
      const now = function () { return (window.performance && performance.now) ? performance.now() : Date.now(); };
      const budget = budgetMs || 5000;
      const maxRows = 64;

      async function run() {
        const rows = [];
        let cur = addr;
        let inboundCount = null;
        const refResult = await runReadAction("mcp.get-references", { target: addr, mode: "to", limit: 200 }, { timeoutMs: Math.max(1000, budget - (now() - t0)) });
        if (cancelled || seq !== seqRef.current) return;
        if (refResult.ok && refResult.data) inboundCount = refResult.data.count != null ? refResult.data.count : (refResult.data.references || []).length;
        while (rows.length < maxRows) {
          const elapsed = now() - t0;
          if (elapsed >= budget) {
            if (cancelled || seq !== seqRef.current) return;
            if (rows.length) {
              setState({ status: "ok", rows: rows, elapsedMs: elapsed, budgetHit: true, inboundCount: inboundCount });
            } else {
              setState({ status: "fallback", reason: "5s budget exceeded before the first row loaded", elapsedMs: elapsed });
            }
            return;
          }
          const result = await runReadAction("mcp.inspect-memory", { mode: "instruction", address: cur }, { timeoutMs: Math.max(500, budget - elapsed) });
          if (cancelled || seq !== seqRef.current) return;
          if (!result.ok) {
            if (rows.length) {
              setState({ status: "ok", rows: rows, elapsedMs: now() - t0, budgetHit: true, inboundCount: inboundCount });
            } else {
              setState({ status: "fallback", reason: result.error || "inspect-memory failed", elapsedMs: result.elapsedMs || (now() - t0) });
            }
            return;
          }
          const d = result.data || {};
          const flows = (d.flows || []).map(function (f) { return typeof f === "string" ? f : (f && (f.address || f.target || f.to)); }).filter(Boolean);
          rows.push({
            addr: d.address || cur,
            bytes: d.bytes || "",
            mnemonic: d.mnemonic || "",
            operands: (d.operands || []).map(function (o) { return o && o.text; }).filter(Boolean).join(", "),
            flows: flows
          });
          if (!d.fallThrough || d.fallThrough === d.address) break;
          cur = d.fallThrough;
        }
        if (cancelled || seq !== seqRef.current) return;
        setState({ status: "ok", rows: rows, elapsedMs: now() - t0, budgetHit: false, inboundCount: inboundCount });
      }
      run();
      return function () { cancelled = true; };
    }, [addr, program, assemblyText, requestedScope]);

    function onRowKeyDown(ev, idx, row) {
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        const next = Math.min(idx + 1, state.rows.length - 1);
        setFocusIdx(next);
        const el = rowRefs.current[next];
        if (el) el.focus();
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        const prev = Math.max(idx - 1, 0);
        setFocusIdx(prev);
        const el = rowRefs.current[prev];
        if (el) el.focus();
      } else if ((ev.key === "Enter" || ev.key === " ") && row.flows && row.flows.length) {
        ev.preventDefault();
        onJumpAddr(row.flows[0]);
      }
    }

    if (state.status === "ok" && state.rows && state.rows.length) {
      return html`<div className="wb-listing-rows-wrap">
        <table id="wb-listing-rows" className="wb-listing-rows" role="table" aria-label=${"Listing for " + (name || addr)}>
          <thead>
            <tr><th scope="col">Address</th><th scope="col">Bytes</th><th scope="col">Mnemonic</th><th scope="col">Operands</th><th scope="col">Xref</th></tr>
          </thead>
          <tbody>
            ${state.rows.map(function (row, idx) {
              return html`<tr key=${row.addr} ref=${function (el) { rowRefs.current[idx] = el; }}
                tabIndex=${idx === focusIdx ? 0 : -1}
                className="wb-listing-row"
                onFocus=${function () { setFocusIdx(idx); }}
                onKeyDown=${function (ev) { onRowKeyDown(ev, idx, row); }}>
                <td><code>${row.addr}</code></td>
                <td><code className="wb-hint">${row.bytes}</code></td>
                <td>${row.mnemonic}</td>
                <td>${row.operands}</td>
                <td>${row.flows.map(function (target) {
                  return html`<button key=${target} type="button" className="wb-text-action wb-listing-xref"
                    title=${"Jump to " + target}
                    onClick=${function (ev) { ev.stopPropagation(); onJumpAddr(target); }}>→${target}</button>`;
                })}</td>
              </tr>`;
            })}
          </tbody>
        </table>
        <p className="wb-hint">${state.rows.length} instructions${state.budgetHit ? ", stopped at the " + Math.round((budgetMs || 5000) / 1000) + "s read budget" : ""}${state.inboundCount != null ? " · " + state.inboundCount + " inbound reference" + (state.inboundCount === 1 ? "" : "s") : ""} (${Math.round(state.elapsedMs)}ms)</p>
      </div>`;
    }
    return html`<div>
      ${state.status === "fallback" ? html`<p className="wb-hint">Structured listing unavailable here (${state.reason}, ${Math.round(state.elapsedMs || 0)}ms) -- showing the text preview.</p>` : null}
      ${state.status === "loading" ? html`<p className="wb-hint">Reading instructions…</p>` : null}
      ${state.status === "idle" && program && addr ? html`<button type="button" className="wb-btn" onClick=${function () { setRequestedScope(listingScope); }}>Read uncached instructions from Ghidra</button>` : null}
      <pre className="wb-preview" id="wb-listing-preview">${fallbackText}</pre>
    </div>`;
  }

  function CorpusNavBar({ active, onJump }) {
    return html`<nav id="wb-corpus-nav" className="wb-corpus-nav wb-editor-tabs" aria-label="Workspace destinations">
      ${EDITOR_PRIMARY.map(function (item) {
        const isActive = editorTabFor(active) === item.id;
        return html`<button type="button" key=${item.id} className=${"wb-corpus-nav-item" + (isActive ? " on" : "")}
          data-surface=${item.id} aria-current=${isActive ? "page" : undefined}
          onClick=${function () { onJump(item.id); }}>${item.title}</button>`;
      })}
      <button type="button" className="wb-text-action wb-files-access" onClick=${function () { onJump("wb-sidebar"); }}>Project files</button>
    </nav>`;
  }

  function CommandPalette({ open, query, onQuery, actions, surfaces, jobs, recentActionIds, commands, onPickAction, onPickSurface, onPickJob, onPickCommand, onClose, menuInvokerRef }) {
    const inputRef = useRef(null);
    const capturedInvokerRef = useRef(null);
    const [activeIdx, setActiveIdx] = useState(0);
    useEffect(function () {
      if (!open) return;
      /* A2: same invoker-focus contract as Modal -- remember what triggered
         the palette (Ctrl+K, a menu item, …) and give it focus back on close.
         menuInvokerRef covers the "View > Command palette" menu-item case,
         where the item unmounts before this effect can see it as active. */
      const menuInvoker = menuInvokerRef && menuInvokerRef.current;
      capturedInvokerRef.current = (menuInvoker && document.contains(menuInvoker))
        ? menuInvoker
        : document.activeElement;
      if (menuInvokerRef) menuInvokerRef.current = null;
      if (inputRef.current) inputRef.current.focus();
      return function () {
        const invoker = capturedInvokerRef.current;
        if (invoker && typeof invoker.focus === "function" && document.contains(invoker)) {
          invoker.focus();
        }
        capturedInvokerRef.current = null;
      };
    }, [open]);
    useEffect(function () {
      if (open) setActiveIdx(0);
    }, [open, query]);
    if (!open) return null;
    const needle = (query || "").trim().toLowerCase();
    function matchText(text) {
      if (!needle) return true;
      return String(text || "").toLowerCase().indexOf(needle) >= 0;
    }
    const actionHits = (actions || []).filter(function (act) {
      return matchText(act.title) || matchText(act.id) || matchText(act.summary);
    }).slice(0, 12);
    const recentHits = (recentActionIds || []).map(function (actionId) {
      return (actions || []).find(function (act) { return act.id === actionId; });
    }).filter(Boolean).filter(function (act) {
      if (needle) {
        return matchText(act.title) || matchText(act.id) || matchText(act.summary);
      }
      return true;
    }).slice(0, 6);
    const recentIds = new Set(recentHits.map(function (act) { return act.id; }));
    const filteredActionHits = actionHits.filter(function (act) { return !recentIds.has(act.id); });
    const surfaceHits = (surfaces || []).filter(function (item) {
      return matchText(item.title) || matchText(item.id)
        || (item.keys || []).some(function (key) { return matchText(key); });
    }).slice(0, 14);
    const jobHits = (jobs || []).filter(function (job) {
      return matchText(job.id) || matchText(job.actionId) || matchText(job.status);
    }).slice(0, 8);
    const commandHits = (commands || []).filter(function (cmd) {
      return matchText(cmd.title) || matchText(cmd.id) || matchText(cmd.group);
    }).slice(0, 10);
    const picks = [];
    commandHits.forEach(function (cmd) {
      picks.push({ kind: "command", key: "cmd-" + cmd.id, id: cmd.id, title: cmd.title, meta: accelLabel(cmd.accel) || cmd.group });
    });
    recentHits.forEach(function (act) {
      picks.push({ kind: "action", key: "recent-" + act.id, id: act.id, title: act.title || act.id, meta: "recent" });
    });
    filteredActionHits.forEach(function (act) {
      picks.push({ kind: "action", key: "action-" + act.id, id: act.id, title: act.title || act.id, meta: act.id });
    });
    surfaceHits.forEach(function (item) {
      picks.push({ kind: "surface", key: "surface-" + item.id, id: item.id, title: item.title, meta: item.id });
    });
    jobHits.forEach(function (job) {
      picks.push({
        kind: "job",
        key: "job-" + job.id,
        id: job.id,
        title: job.actionId || job.id,
        meta: job.status
      });
    });
    const safeIdx = picks.length ? Math.min(activeIdx, picks.length - 1) : 0;
    function activatePick(idx) {
      const pick = picks[idx];
      if (!pick) return;
      if (pick.kind === "command") onPickCommand(pick.id);
      else if (pick.kind === "action") onPickAction(pick.id);
      else if (pick.kind === "surface") onPickSurface(pick.id);
      else onPickJob(pick.id);
    }
    function onPaletteInputKey(ev) {
      if (ev.key === "Escape") {
        onClose();
        return;
      }
      if (!picks.length) return;
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        setActiveIdx(function (prev) { return Math.min(prev + 1, picks.length - 1); });
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        setActiveIdx(function (prev) { return Math.max(prev - 1, 0); });
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        activatePick(safeIdx);
      }
    }
    let pickCursor = 0;
    function itemClass(idx) {
      return "wb-palette-item" + (idx === safeIdx ? " active" : "");
    }
    return html`<div className="wb-palette-backdrop" onClick=${onClose}>
      <div className="wb-palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick=${function (ev) { ev.stopPropagation(); }}>
        <input ref=${inputRef} type="search" className="wb-palette-input" placeholder="Run an action or go to a surface…"
          value=${query} onInput=${function (ev) { onQuery(ev.target.value); }}
          onKeyDown=${onPaletteInputKey} autocomplete="off"
          role="combobox" aria-expanded="true" aria-controls="wb-palette-results"
          aria-activedescendant=${picks.length ? "wb-palette-pick-" + safeIdx : undefined} />
        <div id="wb-palette-results" role="listbox" aria-label="Command palette results">
        ${commandHits.length ? html`<section className="wb-palette-section">
          <h3>Workbench</h3>
          <ul>${commandHits.map(function (cmd) {
            const idx = pickCursor++;
            return html`<li key=${"cmd-" + cmd.id}>
              <button type="button" id=${"wb-palette-pick-" + idx} className=${itemClass(idx)}
                role="option" aria-selected=${idx === safeIdx}
                data-cmd=${cmd.id}
                onMouseEnter=${function () { setActiveIdx(idx); }}
                onClick=${function () { onPickCommand(cmd.id); }}>
                <strong>${cmd.title}</strong>
                <span>${accelLabel(cmd.accel) || cmd.group}</span>
              </button>
            </li>`;
          })}</ul>
        </section>` : null}
        ${recentHits.length ? html`<section className="wb-palette-section">
          <h3>Recent actions</h3>
          <ul>${recentHits.map(function (act) {
            const idx = pickCursor++;
            return html`<li key=${"recent-" + act.id}>
              <button type="button" id=${"wb-palette-pick-" + idx} className=${itemClass(idx)}
                role="option" aria-selected=${idx === safeIdx}
                onMouseEnter=${function () { setActiveIdx(idx); }}
                onClick=${function () { onPickAction(act.id); }}>
                <strong>${act.title || act.id}</strong>
                <span>recent</span>
              </button>
            </li>`;
          })}</ul>
        </section>` : null}
        ${filteredActionHits.length ? html`<section className="wb-palette-section">
          <h3>Actions</h3>
          <ul>${filteredActionHits.map(function (act) {
            const idx = pickCursor++;
            return html`<li key=${act.id}>
              <button type="button" id=${"wb-palette-pick-" + idx} className=${itemClass(idx)}
                role="option" aria-selected=${idx === safeIdx}
                onMouseEnter=${function () { setActiveIdx(idx); }}
                onClick=${function () { onPickAction(act.id); }}>
                <strong>${act.title || act.id}</strong>
                <span>${act.id}</span>
              </button>
            </li>`;
          })}</ul>
        </section>` : null}
        ${surfaceHits.length ? html`<section className="wb-palette-section">
          <h3>Go to</h3>
          <ul>${surfaceHits.map(function (item) {
            const idx = pickCursor++;
            return html`<li key=${item.id}>
              <button type="button" id=${"wb-palette-pick-" + idx} className=${itemClass(idx)}
                role="option" aria-selected=${idx === safeIdx}
                onMouseEnter=${function () { setActiveIdx(idx); }}
                onClick=${function () { onPickSurface(item.id); }}>
                <strong>${item.title}</strong>
                <span>${item.id}</span>
              </button>
            </li>`;
          })}</ul>
        </section>` : null}
        ${jobHits.length ? html`<section className="wb-palette-section">
          <h3>Recent jobs</h3>
          <ul>${jobHits.map(function (job) {
            const idx = pickCursor++;
            return html`<li key=${job.id}>
              <button type="button" id=${"wb-palette-pick-" + idx} className=${itemClass(idx)}
                role="option" aria-selected=${idx === safeIdx}
                onMouseEnter=${function () { setActiveIdx(idx); }}
                onClick=${function () { onPickJob(job.id); }}>
                <strong>${job.actionId || job.id}</strong>
                <span>${job.status}${job.resourceDisposition === "quarantined" || job.ownershipUnresolved === true ? " · ownership unresolved" : ""}</span>
              </button>
            </li>`;
          })}</ul>
        </section>` : null}
        </div>
        ${!picks.length
          ? html`<p className="wb-hint">No matches. Try “ghidra”, “cross-match”, or “jobs”.</p>`
          : html`<p className="wb-hint wb-palette-kbd">↑↓ to move · Enter to select · Esc to close</p>`}
      </div>
    </div>`;
  }

  function ActionStrip({ action, ctx, expanded, onToggleExpand, onRun, onClose, formRef, danger, checkedCount }) {
    if (!action) return null;
    const fields = action.fields || [];
    const batch = Number(checkedCount || 0) > 1 && actionUsesAddr(action);
    const title = action.title || action.id;
    const summary = action.summary && action.summary !== action.id && action.summary !== title
      ? action.summary : "";
    return html`<div id="wb-action-strip" className=${"wb-action-strip" + (danger ? " danger" : "")}>
      <div className="wb-action-strip-head">
        <strong>${title}</strong>
        ${summary ? html`<span className="wb-hint">${summary}</span>` : null}
        ${batch ? html`<span className="wb-sel-chip">${checkedCount} selected</span>` : null}
        <div className="wb-action-strip-btns">
          <button type="button" className="wb-btn wb-btn-primary" onClick=${onRun}>${batch ? "Run " + checkedCount : "Run"}</button>
          ${fields.length ? html`<button type="button" className="wb-btn" onClick=${onToggleExpand}>
            ${expanded ? "Hide fields" : "Fields…"}</button>` : null}
          <button type="button" className="wb-btn" onClick=${onClose} aria-label="Close action strip">×</button>
        </div>
      </div>
      ${expanded && fields.length ? html`<form ref=${formRef} className="wb-tool-form wb-tools-layout" onSubmit=${function (ev) { ev.preventDefault(); onRun(); }}>
        ${fields.map(function (field) {
          return html`<${ToolField} key=${field.name} field=${field} ctx=${ctx} listPrefix=${action.id} />`;
        })}
      </form>` : null}
    </div>`;
  }

  function SplitHandle({ axis, label, onDrag, value, min, max, step, onStep }) {
    const orientation = axis === "x" ? "vertical" : "horizontal";
    const stepSize = step || 16;
    function onKeyDown(ev) {
      if (!onStep) return;
      let delta = 0;
      if (orientation === "vertical") {
        if (ev.key === "ArrowLeft") delta = -stepSize;
        else if (ev.key === "ArrowRight") delta = stepSize;
      } else {
        if (ev.key === "ArrowUp") delta = stepSize;
        else if (ev.key === "ArrowDown") delta = -stepSize;
      }
      if (!delta) return;
      ev.preventDefault();
      onStep(delta);
    }
    return html`<div className=${"wb-split wb-split-" + axis} role="separator"
      tabIndex="0"
      aria-orientation=${orientation}
      aria-label=${label}
      aria-valuenow=${value != null ? Math.round(value) : undefined}
      aria-valuemin=${min != null ? min : undefined}
      aria-valuemax=${max != null ? max : undefined}
      onMouseDown=${onDrag}
      onKeyDown=${onKeyDown}></div>`;
  }

  function clampResize(next, min, max, setter, key) {
    const clamped = Math.round(Math.min(max, Math.max(min, next)));
    setter(clamped);
    writeUiPref(key, String(clamped));
  }

  function beginResize(ev, startPx, setter, key, axis, min, max, invert) {
    ev.preventDefault();
    const origin = axis === "x" ? ev.clientX : ev.clientY;
    document.body.classList.add(axis === "x" ? "wb-resizing-x" : "wb-resizing-y");
    function move(e) {
      const delta = (axis === "x" ? e.clientX : e.clientY) - origin;
      clampResize(startPx + (invert ? -delta : delta), min, max, setter, key);
    }
    function up() {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.classList.remove("wb-resizing-x", "wb-resizing-y");
    }
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  }

  function JobAdmissionSummary({ admission, onSelectJob }) {
    if (!admission) return null;
    const holders = Array.isArray(admission.holders) ? admission.holders : [];
    const pausedScopes = Object.keys(admission.pausedScopes || {});
    return html`<section className="wb-admission-summary" aria-label="Scheduler resource ownership">
      <p className="wb-hint">Scheduler: ${admission.running}/${admission.maxConcurrent} worker slots · ${admission.identityLocksHeld} identity locks · ${admission.ghidraLocksHeld} Ghidra locks · ${admission.pausedScopeCount} paused scopes</p>
      ${pausedScopes.length ? html`<p className="wb-hint">Paused: ${pausedScopes.join(", ")}. Jobs in these scopes wait until explicitly resumed.</p>` : null}
      ${holders.length ? html`<div className="wb-admission-holders">
        <h4>${holders.length} retained resource reservation${holders.length === 1 ? "" : "s"}</h4>
        <ul className="wb-job-list">
          ${holders.map(function (holder, index) {
            const jobId = String(holder.jobId || "");
            const status = String(holder.status || "unknown");
            const disposition = String(holder.resourceDisposition || "");
            const receipt = holder.retainedReceipt;
            const displayedStatus = holder.liveRecordPresent === false && receipt
              ? String(receipt.status || "unknown") + " receipt" : status;
            const extra = holder.liveRecordPresent === false && receipt
              ? "live owner unregistered · clearance " + (receipt.clearanceRecorded ? "recorded, not reconciled" : "unconfirmed")
              : disposition && disposition !== "unknown"
              ? disposition
              : holder.historyOnly === true ? "history only" : "";
            return html`<li key=${String(holder.resource || "resource") + ":" + jobId + ":" + index}>
              ${jobId ? html`<button type="button" className="wb-job-row" onClick=${function () { onSelectJob(jobId); }}>
                <code>${jobId}</code>
                <span>${String(holder.resource || "resource")} · ${String(holder.actionId || "unknown action")}</span>
                <span>${displayedStatus}${extra ? " · " + extra : ""}</span>
              </button>` : html`<p className="wb-hint">${String(holder.resource || "resource")} · owner ID unavailable · ${status}</p>`}
            </li>`;
          })}
        </ul>
      </div>` : html`<p className="wb-hint">No retained resource owners reported.</p>`}
    </section>`;
  }

  function LogDock({
    entries, tab, onTab, open, onToggle, selectedId, onSelect,
    jobs, selectedJobId, jobDetail, jobDetailLoading, jobDetailError,
    onSelectJob, onRetryJobDetail, onCancel, onRefreshJobs, onLoadJobHistory,
    jobsRefreshedAt, jobsRefreshing, jobsVisibleCount, onShowMoreJobs,
    jobsScope, jobsLoadingScope, jobAdmission, actions, height, onResize, onKeyResize
  }) {
    const list = jobs || [];
    const running = list.filter(function (job) { return job.status === "running"; }).length;
    const queued = list.filter(function (job) { return job.status === "queued"; }).length;
    const visibleJobs = list.slice(0, jobsVisibleCount || JOB_PAGE_SIZE);
    const detail = jobDetail || null;
    const logText = detail && detail.log ? String(detail.log).slice(-12000) : "";
    const rows = (entries || []).slice().reverse();
    return html`<aside id="wb-log-dock" className=${"wb-log-dock" + (open ? " open" : "")}
      style=${open ? { height: height + "px" } : undefined}>
      <${SplitHandle} axis="y" label="Resize log"
        value=${height} min=${72} max=${640}
        onDrag=${onResize} onStep=${onKeyResize} />
      <header className="wb-log-dock-head">
        <button type="button" className=${"wb-log-tab" + (tab === "log" ? " on" : "")}
          onClick=${function () { onTab("log"); if (!open) onToggle(true); }}>Log</button>
        <button type="button" className=${"wb-log-tab" + (tab === "jobs" ? " on" : "")}
          onClick=${function () { onTab("jobs"); if (!open) onToggle(true); }}>
          Jobs${jobsRefreshedAt ? " · " + running + " running" + (queued ? " · " + queued + " queued" : "") : jobs.length ? " · new job" : " · not checked"}
        </button>
        ${tab === "jobs" ? html`<button type="button" className="wb-btn wb-btn-mini" disabled=${Boolean(jobsRefreshing)}
          onClick=${function () { onRefreshJobs("current"); }}>${jobsLoadingScope === "current" ? "Refreshing status…" : "Refresh live status"}</button>
          <button type="button" className="wb-btn wb-btn-mini" disabled=${Boolean(jobsRefreshing)}
            onClick=${function () { onLoadJobHistory(); }}>${jobsLoadingScope === "history" ? "Loading history…" : "Load retained history"}</button>` : null}
        <span className="wb-hint">A finished job is not a match.</span>
        <button type="button" className="wb-log-toggle" onClick=${function () { onToggle(!open); }}>
          ${open ? "Hide" : "Show"}
        </button>
      </header>
      ${open ? html`<div className="wb-log-body">
        ${tab === "log" ? html`<ul className="wb-log-list" id="wb-log-list">
          ${rows.length ? rows.map(function (item) {
            const on = item.id === selectedId;
            const preview = item.text.length > 140 && !on ? item.text.slice(0, 137) + "…" : item.text;
            return html`<li key=${item.id} className=${"wb-log-item kind-" + (item.kind || "info") + (on ? " on" : "")}>
              <button type="button" className="wb-log-row" onClick=${function () { onSelect(on ? "" : item.id); }}>
                <span className="wb-log-kind">${item.kind || "note"}</span>
                <span className="wb-log-text">${preview}</span>
              </button>
            </li>`;
          }) : html`<li className="wb-hint">No log lines yet.</li>`}
        </ul>` : html`<div className="wb-jobs-dock-body">
          <p className="wb-hint">${jobsRefreshedAt
            ? "Showing " + visibleJobs.length + " of " + jobs.length + (jobsScope === "current-process" ? " current-process jobs" : " retained jobs") + " · " + running + " running · " + queued + " queued · refreshed " + new Date(jobsRefreshedAt).toLocaleTimeString()
            : jobs.length ? "Refresh live status for this server, or load retained history when you need older receipts." : "Live status and retained history are separate; history is only read when requested."}</p>
          <${JobAdmissionSummary} admission=${jobAdmission} onSelectJob=${onSelectJob} />
          <ul className="wb-job-list">
            ${visibleJobs.length ? visibleJobs.map(function (job) {
              const on = job.id === selectedJobId;
              const live = job.status === "running" || job.status === "queued";
              return html`<li key=${job.id} className=${on ? "on" : ""}>
                <button type="button" className="wb-job-row" onClick=${function () { onSelectJob(job.id); }}>
                  <code>${job.id}</code>
                  <span>${actionTitle(job.actionId, actions)}</span>
                  <span className=${"st-" + (job.status || "unknown")}>${job.status}${job.resourceDisposition === "quarantined" || job.ownershipUnresolved === true ? " · ownership unresolved" : ""}</span>
                </button>
                ${live ? html`<button type="button" className="wb-btn danger wb-job-cancel"
                  onClick=${function (ev) { ev.stopPropagation(); onCancel(job.id); }}>Cancel</button>` : null}
              </li>`;
            }) : html`<li className="wb-hint">${jobsRefreshedAt ? "No jobs were returned by the last refresh." : "No job history loaded."}</li>`}
          </ul>
          ${visibleJobs.length < list.length ? html`<button type="button" className="wb-btn wb-btn-mini" onClick=${onShowMoreJobs}>Show ${Math.min(JOB_PAGE_SIZE, list.length - visibleJobs.length)} older jobs</button>` : null}
          ${selectedJobId && logText ? html`<pre className="wb-job-log">${logText}</pre>`
            : selectedJobId && jobDetailLoading ? html`<p className="wb-hint" role="status">Loading job detail…</p>`
              : selectedJobId && jobDetailError ? html`<p className="wb-status-error" role="alert">${jobDetailError}
                <button type="button" className="wb-btn wb-btn-mini" onClick=${onRetryJobDetail}>Retry</button></p>`
                : selectedJobId ? html`<p className="wb-hint">No retained log is available for this job.</p>` : null}
        </div>`}
      </div>` : null}
    </aside>`;
  }

  const LIST_LIMITS = ["all", 10, 20, 50, 100, 200];

  function FuncPager({ limit, shown, total, onLimit, compact }) {
    const clipped = limit !== "all" && shown && total && shown < total;
    return html`<div className=${"wb-pager" + (compact ? " wb-pager-compact" : "")}>
      <span className="wb-pager-count">${clipped ? shown + " of " + total : (total || shown || 0) + " functions"}</span>
      <label className="wb-pager-size">
        <span className="sr-only">How many functions to show</span>
        <select value=${String(limit)} onChange=${function (ev) { onLimit(ev.target.value); }}>
          ${LIST_LIMITS.map(function (size) {
            return html`<option key=${String(size)} value=${String(size)}>${size === "all" ? "All" : size}</option>`;
          })}
        </select>
      </label>
    </div>`;
  }

  function shortPath(text) {
    const value = String(text || "");
    if (value.length <= 56) return value;
    return "…" + value.slice(-53);
  }

  function staticMatrixCell(body, expected) {
    const p = body && body.matrix_projection, b = p && p.binary;
    const fail = function (reason) { return { verified: "Unavailable · " + reason, advisory: "Unavailable · " + reason, unclassified: "Unavailable · " + reason }; };
    const validHash = function (value) { return typeof value === "string" && value.length === 64 && /^[0-9a-f]{64}$/.test(value); };
    if (!/^[1-9][0-9]*$/.test(expected.logicalId) || !Number.isSafeInteger(Number(expected.logicalId)) || String(Number(expected.logicalId)) !== expected.logicalId || !expected.corpusIdentity || !expected.slug || !validHash(expected.version)) return fail("Exact selection and content-hash version are required.");
    if (!p) return fail(body && body.error || "Tier report unavailable.");
    if (body.ok !== true || body.status !== "available") return fail(body.error || "Tier report failed.");
    const scopeMatches = function (scope) { return scope && scope.kind === "logical_function" && Number.isSafeInteger(scope.logical_id) && scope.logical_id === Number(expected.logicalId) && Object.keys(scope).length === 2; };
    if (!scopeMatches(p.selection_scope) || !scopeMatches(body.report && body.report.selection_scope)) return fail("Report scope does not match the selected logical entity.");
    if (p.unbound !== null || p.unbound_status !== "not_requested") return fail("Scoped report supplied global unbound counts.");
    if (p.corpus_identity !== expected.corpusIdentity || !p.freshness || p.freshness.status !== "current") return fail("Stale or different corpus report.");
    if (!b || b.slug !== expected.slug || b.content_sha256 !== expected.version || b.version !== expected.version || !validHash(b.report_sha256)) return fail("Exact build/version basis mismatch.");
    const reportBinary = body.report && body.report.binary;
    if (!reportBinary || reportBinary.slug !== b.slug || reportBinary.content_sha256 !== b.content_sha256 || reportBinary.version !== b.version) return fail("Report and projection build bases differ.");
    if (!body.report || body.report.report_sha256 !== b.report_sha256) return fail("Report and projection digests differ.");
    if (!Array.isArray(p.rows) || p.rows.length !== 1) return fail("Scoped report must contain exactly one logical tier row.");
    const row = p.rows[0];
    if (!row || !Number.isSafeInteger(row.logical_id) || row.logical_id !== Number(expected.logicalId)) return fail("No authoritative row for this identity.");
    const names = ["verified", "advisory", "unclassified"], all = [];
    const validKey = function (key) { return typeof key === "string" && key.length > 0; };
    if (!Array.isArray(row.member_keys) || !row.member_keys.every(validKey) || new Set(row.member_keys).size !== row.member_keys.length || !Number.isSafeInteger(row.physical_members) || row.physical_members < 0 || row.member_keys.length !== row.physical_members) return fail("Physical member set mismatch.");
    const rowKeys = new Set(row.member_keys);
    for (const name of names) {
      const tier = row[name];
      if (!tier || !Array.isArray(tier.member_keys) || !tier.member_keys.every(validKey) || new Set(tier.member_keys).size !== tier.member_keys.length) return fail(name + " member set malformed.");
      if (tier.member_keys.some(function (key) { return !rowKeys.has(key); })) return fail(name + " tier names members outside this logical identity.");
      if (name === "verified" && tier.status === "unavailable") { if (tier.functions !== null || tier.bytes !== null) return fail("Unavailable verified tier supplied progress."); }
      else if (!Number.isSafeInteger(tier.functions) || tier.functions < 0 || tier.member_keys.length !== tier.functions) return fail(name + " count mismatch.");
      all.push.apply(all, tier.member_keys);
    }
    if (new Set(all).size !== all.length || all.length !== row.member_keys.length) return fail("Tier sets overlap or do not reconcile.");
    if (row.verified.status === "available" && (!p.provider || p.provider.status !== "connected")) return fail("Verified tier conflicts with disconnected acceptance provider.");
    return { verified: row.verified.status === "available" ? String(row.verified.functions) : "Unavailable · " + ((p.provider && p.provider.reason) || "acceptance provider unavailable"), advisory: String(row.advisory.functions), unclassified: String(row.unclassified.functions), basis: b.report_sha256 };
  }

  function logicalBrowseUrl(corpusIdentity, search, cursor) {
    return "/dashboard/browse-block?" + new URLSearchParams({
      block: "logical", limit: "50", lq: search || "",
      logical_after: String(cursor || 0), corpus_identity: corpusIdentity || ""
    });
  }

  function staticSelectionKey(corpusIdentity, revision, logicalId, binaries) {
    const basis = (binaries || []).map(function (binary) {
      return (binary.slug || "") + ":" + (binary.content_sha256 || binary.contentSha256 || binary.sha256 || "");
    }).join("|");
    return [corpusIdentity || "", revision, logicalId || "", basis].join(":");
  }

  function LogicalMatrix({ binaries, corpusIdentity, revision }) {
    const corpus = corpusIdentity || "";
    const [list, setList] = useState([]);
    const [filter, setFilter] = useState("");
    const [search, setSearch] = useState("");
    const [pages, setPages] = useState([0]);
    const [more, setMore] = useState(false);
    const [chosen, setChosen] = useState("");
    const [detailState, setDetailState] = useState({ key: "", data: null });
    const [reportState, setReportState] = useState({ key: "", data: {} });
    const [state, setState] = useState("Loading logical identities…");
    useEffect(function () { setChosen(""); setPages([0]); }, [corpus, revision]);
    useEffect(function () {
      const c = new AbortController();
      if (!corpus) { setList([]); setMore(false); setState("Current corpus identity unavailable."); return function () { c.abort(); }; }
      const cursor = pages[pages.length - 1] || 0;
      const url = logicalBrowseUrl(corpus, search, cursor);
      fetch(url, { cache: "no-store", signal: c.signal }).then(function (r) { return r.json(); })
        .then(function (body) { if (!c.signal.aborted) { if (!body.corpus || body.corpus.identity !== corpus) { setList([]); setMore(false); throw new Error("Logical list lacks the exact current corpus identity."); } setList(body.rows || []); setMore(Boolean(body.more)); setState("Select a logical identity."); } })
        .catch(function (err) { if (!c.signal.aborted) setState(String(err && err.message || err)); });
      return function () { c.abort(); };
    }, [search, corpus, revision, pages]);
    // Content-derived key: an equal-content binaries refresh (job poll) must not restart the fan-out.
    // The effect below may read only slug and content hash from binaries; those are exactly what the key covers.
    const key = staticSelectionKey(corpus, revision, chosen, binaries);
    useEffect(function () {
      const c = new AbortController();
      setDetailState({ key: key, data: null });
      setReportState({ key: key, data: {} });
      if(!chosen||!corpus)return function(){c.abort();};
      setState("Reading logical members and exact tier reports…");
      fetch("/dashboard/api/workbench/logical/"+encodeURIComponent(chosen)+"?corpus_identity="+encodeURIComponent(corpus),{cache:"no-store",signal:c.signal}).then(function(r){return r.json();}).then(async function(body){
        if(c.signal.aborted)return;
        if(!body.corpus||body.corpus.identity!==corpus){setState(body.error||"Logical detail lacks the exact current corpus identity.");return;}
        setDetailState({ key: key, data: body });
        const queue=(binaries||[]).filter(function(b){return b.slug&&(b.content_sha256||b.contentSha256||b.sha256);}), found={};let next=0;
        async function worker(){while(next<queue.length&&!c.signal.aborted){const b=queue[next++],version=String(b.content_sha256||b.contentSha256||b.sha256),q=new URLSearchParams({slug:String(b.slug),version:version,corpusIdentity:corpus,logicalId:chosen});try{found[b.slug]=await fetch(API.progressReport+"?"+q,{cache:"no-store",signal:AbortSignal.any([c.signal,AbortSignal.timeout(15000)])}).then(function(r){return r.json();});}catch(err){if(!c.signal.aborted)found[b.slug]={error:String(err)};}if(!c.signal.aborted)setReportState({key:key,data:Object.assign({},found)});}}
        await Promise.all([worker(),worker()]);if(!c.signal.aborted){setReportState({ key: key, data: found });setState("");}
      }).catch(function(err){if(!c.signal.aborted)setState(String(err&&err.message||err));});
      return function(){c.abort();};
    }, [key]);
    const detail = detailState.key === key ? detailState.data : null;
    const reports = reportState.key === key ? reportState.data : {};
    const members=detail&&detail.members||[];
    return html`<section aria-label="Logical entity coverage matrix">
      <form onSubmit=${function (ev) { ev.preventDefault(); setPages([0]); setSearch(filter); }}><label>Find a logical entity <input value=${filter} onInput=${function (ev) { setFilter(ev.target.value); }}/></label><button type="submit">Search</button></form>
      <label>Logical entity <select value=${chosen} onChange=${function(ev){setChosen(ev.target.value);}}><option value="">Choose an identity</option>${list.map(function(row){return html`<option key=${row.id} value=${String(row.id)}>${row.name||"Identity "+row.id} · ${row.members==null?"?":row.members} members</option>`;})}</select></label>
      <div><button type="button" disabled=${pages.length===1} onClick=${function(){setChosen("");setPages(function(old){return old.slice(0,-1);});}}>Previous identities</button><button type="button" disabled=${!more||!list.length} onClick=${function(){setChosen("");setPages(function(old){return old.concat(Number(list[list.length-1].id)||0);});}}>Next identities</button></div>
      ${state?html`<p role="status">${state}</p>`:null}
      ${chosen&&detail?html`<table className="wb-fnb-table"><thead><tr><th>Build</th><th>Corpus matches</th><th>Verified</th><th>Advisory</th><th>Unclassified</th></tr></thead><tbody>${(binaries||[]).map(function(b){const version=String(b.content_sha256||b.contentSha256||b.sha256||""),cell=staticMatrixCell(reports[b.slug],{logicalId:chosen,corpusIdentity:corpus,slug:String(b.slug||""),version:version}),count=members.filter(function(m){return m.slug===b.slug||(b.aliasSlugs||[]).includes(m.slug);}).length;return html`<tr key=${b.slug}><td>${b.name||b.slug}</td><td>${count}</td><td>${cell.verified}</td><td>${cell.advisory}</td><td>${cell.unclassified}</td></tr>`;})}</tbody></table>`:null}
    </section>`;
  }

  // Corpus status and corpus-db identity settle independently: a failed identity read
  // must not discard healthy status (it only clears identity), and vice versa.
  async function readCorpusStatus(fetchImpl, api) {
    const read = async function (url) {
      const res = await fetchImpl(url, { cache: "no-store" });
      let body;
      try { body = await res.json(); } catch (_err) { throw new Error(url + " returned a non-JSON response (HTTP " + res.status + ")."); }
      return { ok: Boolean(res.ok), body: body };
    };
    const reason = function (err) { return String(err && err.message || err); };
    const settled = await Promise.allSettled([read(api.corpusStatus), read(api.corpusDb)]);
    const statusResult = settled[0], dbResult = settled[1];
    const status = statusResult.status === "fulfilled" && statusResult.value.body && typeof statusResult.value.body === "object"
      ? statusResult.value.body
      : { ok: false, error: statusResult.status === "rejected" ? reason(statusResult.reason) : "Corpus status response is malformed." };
    const db = dbResult.status === "fulfilled" && dbResult.value.ok ? dbResult.value.body : null;
    const identity = status.scope === "projects" ? status.corpusIdentity || "" : db && db.corpus && typeof db.corpus.identity === "string" ? db.corpus.identity : "";
    return { status: status, identity: identity };
  }

  function App() {
    const start = params();
    const [binaries, setBinaries] = useState([]);
    const binaryInventoryRef = useRef(binaries);
    const [slug, setSlugState] = useState(start.get("slug") || start.get("binary") || "");
    const [rowPacket, setRowPacket] = useState(null);
    const [total, setTotal] = useState(0);
    const [query, setQuery] = useState(start.get("q") || "");
    const [selectionPacket, setSelectionPacket] = useState(null);
    const [evidencePacket, setEvidencePacket] = useState(null);
    const [corpusStatus, setCorpusStatus] = useState(null);
    const [projectQuery, setProjectQuery] = useState("");
    const [projectBusy, setProjectBusy] = useState(false);
    const [cohortIds, setCohortIds] = useState(null);
    const [functionBuildFilter, setFunctionBuildFilter] = useState("");
    const [functionBrowseIds, setFunctionBrowseIds] = useState(null);
    const [acrossProjects, setAcrossProjects] = useState(false);
    const [functionRequest, setFunctionRequest] = useState({ q: "", offset: 0, limit: 100 });
    const [functionRefresh, setFunctionRefresh] = useState(0);
    const [functionPacket, setFunctionPacket] = useState(null);
    const [functionBusy, setFunctionBusy] = useState(false);
    const [functionError, setFunctionError] = useState("");
    const functionSequence = useRef(0);
    const projectPageRef = useRef({ q: "", offset: 0, limit: 100 });
    const sessionsWriteSequence = useRef(0);
    const sessionsWriteQueue = useRef(Promise.resolve());
    const openSequence = useRef(0);
    const projectOperationSequence = useRef(0);
    const [focusLocator, setFocusLocator] = useState("");
    const [addBusy, setAddBusy] = useState(false);
    const addDialogSequence = useRef(0);
    const [projectControls, setProjectControls] = useState({});
    const projectControlBusy = useRef(new Set());
    const [projectAvailability, setProjectAvailability] = useState({});
    const availabilitySequence = useRef(0);
    const availabilityScopeRef = useRef("");
    const projectPipelineSnapshot = useRef(null);
    const [outputBuilds, setOutputBuilds] = useState({});
    const [reviewAnchor, setReviewAnchor] = useState(null);
    const [memberLimit, setMemberLimit] = useState(48);
    const [peerLimits, setPeerLimits] = useState({});
    const [receiptLimits, setReceiptLimits] = useState({});
    const [runLimit, setRunLimit] = useState(12);
    const [inspectedMember, setInspectedMember] = useState("");
    const [inspectedOutput, setInspectedOutput] = useState("");
    const [inspectedStages, setInspectedStages] = useState({});
    const [filesOpen, setFilesOpen] = useState(false);
    const [comparisonMode, setComparisonMode] = useState(function () {
      return /graph/.test(start.get("window") || window.location.hash) ? "calls" : "code";
    });
    const [corpusIdentity, setCorpusIdentity] = useState("");
    const [corpusRevision, setCorpusRevision] = useState(0);
    const [preparationRuns, setPreparationRuns] = useState([]);
    const [preparationFeed, setPreparationFeed] = useState({ receivedAt: 0, error: "" });
    const [preparationNow, setPreparationNow] = useState(Date.now());
    const [preparationRefreshing, setPreparationRefreshing] = useState(false);
    const preparationSequence = useRef(0);
    const preparationInFlight = useRef(false);
    useEffect(function () {
      const timer = setInterval(function () { setPreparationNow(Date.now()); }, 1000);
      return function () { clearInterval(timer); };
    }, []);
    const [actions, setActions] = useState([]);
    const [jobs, setJobs] = useState([]);
    const [jobsVisibleCount, setJobsVisibleCount] = useState(JOB_PAGE_SIZE);
    const [jobAdmission, setJobAdmission] = useState(null);
    const readActionJobs = useRef(new Map());
    const projectSourceRequests = useRef(new Map());
    const [projectSourceState, setProjectSourceState] = useState(null);
    const [jobsRefreshedAt, setJobsRefreshedAt] = useState(0);
    const [jobsScope, setJobsScope] = useState("");
    const [jobsLoadingScope, setJobsLoadingScope] = useState("");
    const [jobsRefreshing, setJobsRefreshing] = useState(false);
    const jobsRefreshInFlight = useRef(false);
    const [reaction, setReaction] = useState(null);
    const [path, setPath] = useState("");
    const [newSlug, setNewSlug] = useState("");
    const [role, setRole] = useState("member");
    const [label, setLabel] = useState("");
    const [browse, setBrowse] = useState({ path: "", parent: "", entries: [] });
    const [browseBusy, setBrowseBusy] = useState(false);
    const [browseOpening, setBrowseOpening] = useState(false);
    const browseReadSequence = useRef(0);
    const browseReadController = useRef(null);
    const browseOpenSequence = useRef(0);
    const browseDialogEpoch = useRef(0);
    const renderedBrowseDialogEpoch = browseDialogEpoch.current;
    const [preview, setPreview] = useState(null);
    const [sharedHost, setSharedHost] = useState("127.0.0.1");
    const [sharedPort, setSharedPort] = useState("13100");
    const [sharedRepo, setSharedRepo] = useState("");
    const [sharedProgram, setSharedProgram] = useState("");
    const [sharedUrl, setSharedUrl] = useState("");
    const [sharedUser, setSharedUser] = useState("");
    const [artifactPath, setArtifactPath] = useState(start.get("p") || "");
    const [ingestNote, setIngestNote] = useState("");
    const [logEntries, setLogEntries] = useState([]);
    const [openLogId, setOpenLogId] = useState("");
    const [lastNote, setLastNote] = useState("Ready");
    const [statusError, setStatusError] = useState("");
    const [dialogError, setDialogError] = useState("");
    const [ctxMenu, setCtxMenu] = useState(null);
    const [dialog, setDialog] = useState("");
    /* A2: when a dialog is opened from a menu item, the item itself is
       unmounted (its menu closes) in the same render that opens the dialog,
       so by the time Modal's own effect runs document.activeElement is
       already <body>. The stable ~menu trigger~ button survives that
       unmount, so it's captured here and handed to Modal as the fallback
       invoker to restore focus to. */
    const dialogInvokerRef = useRef(null);
    const [openTab, setOpenTab] = useState("local");
    const [openPaste, setOpenPaste] = useState("");
    const [funcNote, setFuncNote] = useState("");
    const [program, setProgramState] = useState(start.get("program") || "");
    const [sessions, setSessions] = useState([]);
    const [activeSession, setActiveSessionState] = useState("");
    const [sessionRevision, setSessionRevision] = useState(0);
    const [dossier, setDossierState] = useState(null);
    const [editingTab, setEditingTab] = useState("");
    const [menu, setMenu] = useState("");
    const [saveAsTarget, setSaveAsTarget] = useState("ghidra-project");
    const [saveAsName, setSaveAsName] = useState("");
    const [saveAsDest, setSaveAsDest] = useState("");
    const [saveAsUrl, setSaveAsUrl] = useState("");
    const [addPath, setAddPath] = useState("");
    const [addFileName, setAddFileName] = useState("");
    const [editRole, setEditRole] = useState("member");
    const [editLabel, setEditLabel] = useState("");
    const [probes, setProbes] = useState([]);
    const [centerTab, setCenterTab] = useState(function () { return bootWindow(); });
    const [bottomTab, setBottomTab] = useState("pipeline");
    const [dropCandidates, setDropCandidates] = useState([]);
    const [treeExpanded, setTreeExpanded] = useState(true);
    const [envDefaults, setEnvDefaults] = useState({ db: "", work_dir: "", kb: "", mcp_url: "" });
    const [pipelineStages, setPipelineStages] = useState([]);
    const [recoveredRoot, setRecoveredRoot] = useState("");
    const [bsimStatus, setBsimStatus] = useState(null);
    const [recoverInfo, setRecoverInfo] = useState(null);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [paletteQuery, setPaletteQuery] = useState("");
    const [commandFilter, setCommandFilter] = useState("");
    const [funcOffset, setFuncOffset] = useState(0);
    const [funcLimit, setFuncLimit] = useState("all");
    const DEFAULT_FUNCTION_ACTION = "mcp.decompile-function";
    const [pendingActionId, setPendingActionId] = useState("");
    const [pendingActionParams, setPendingActionParams] = useState({});
    const [lastActionId, setLastActionId] = useState(DEFAULT_FUNCTION_ACTION);
    const [actionExpanded, setActionExpanded] = useState(false);
    const [confirmDialog, setConfirmDialog] = useState(null);
    const [logOpen, setLogOpen] = useState(false);
    const [logTab, setLogTab] = useState("log");
    const [selectedJobId, setSelectedJobId] = useState("");
    const [jobDetail, setJobDetail] = useState(null);
    const [jobDetailLoading, setJobDetailLoading] = useState(false);
    const [jobDetailError, setJobDetailError] = useState("");
    const [jobDetailReload, setJobDetailReload] = useState(0);
    const [sideW, setSideW] = useState(function () { return Number(readUiPref("wb-side-w", "360")) || 360; });
    const [explorerH, setExplorerH] = useState(function () { return Number(readUiPref("wb-explorer-h", "240")) || 240; });
    const [logH, setLogH] = useState(function () { return Number(readUiPref("wb-log-h", "180")) || 180; });
    const [moreOpen, setMoreOpen] = useState(false);
    const [density, setDensity] = useState(function () { return readUiPref("wb-density", "compact"); });
    const [jobsRail, setJobsRail] = useState(function () { return readUiPref("wb-jobs-rail", "0") === "1"; });
    const [classicLayout, setClassicLayout] = useState(function () { return readUiPref("wb-classic-layout", "0") === "1"; });
    const [decompileOpenNarrow, setDecompileOpenNarrow] = useState(function () { return readUiPref("wb-decompile-open", "0") === "1"; });
    const [lastDecompilePacket, setLastDecompile] = useState(null);
    const [recentActionIds, setRecentActionIds] = useState(readRecentActionIds);
    const [checkedAddrs, setCheckedAddrs] = useState([]);
    const [checkAnchor, setCheckAnchor] = useState("");
    const [jobLiveText, setJobLiveText] = useState("");
    const jobsSnapshotRef = useRef(null);
    const ensureSeqRef = useRef(0);
    const funcSeqRef = useRef(0);
    const intentRef = useRef(null);
    const primaryRowRef = useRef(null);
    const intentGeneration = useRef(0);
    const navigationGeneration = useRef(0);
    const evidenceTimer = useRef(null);
    const selectionMounted = useRef(true);
    const targetRef = useRef(null);
    const funcSlugRef = useRef(slug);
    const fileRef = useRef(null);
    const addFileRef = useRef(null);
    const folderRef = useRef(null);
    const dropRef = useRef(null);
    const actionFormRef = useRef(null);

    const current = useMemo(function () {
      return binaries.find(function (row) { return row.slug === slug; }) || {};
    }, [binaries, slug]);

    const running = jobs.filter(function (job) {
      return job.status === "running" || job.status === "queued";
    });

    const currentSession = useMemo(function () {
      return sessions.find(function (item) { return item.id === activeSession; }) || sessions[0] || null;
    }, [sessions, activeSession]);

    function canonicalLocator(value) { return String(value || "").trim().replace(/\/+$/, ""); }
    function canonicalProgram(value) { return String(value || "").trim().replace(/^\/+/, ""); }
    function targetIdentity(fields) {
      return JSON.stringify([fields.session, fields.locator, fields.program, fields.slug,
        fields.corpus, fields.content]);
    }
    function targetFields(nextSlug, nextProgram, nextSession, nextLocator) {
      const binary = binaries.find(function (item) { return item.slug === nextSlug; }) || {};
      return { session: nextSession || "", locator: canonicalLocator(nextLocator),
        program: canonicalProgram(nextProgram), slug: nextSlug || "", corpus: corpusIdentity || "",
        // Only use identity supplied by the inventory. UI counters are not revisions.
        content: binary.content_sha256 || binary.contentSha256 || binary.sha256 || binary.binary_hash || binary.hash || "", repo: binary.repo || "" };
    }
    // An explicit pending/empty dossier owns the locator even before inspection.
    // Falling back to the previous session here would resurrect its target on render.
    const renderedTarget = targetFields(slug, program, activeSession,
      focusLocator || (currentSession && currentSession.locator) || "");
    const targetKey = targetIdentity(renderedTarget);

    function writePageContext(row, target) {
      const node = document.getElementById("page-context");
      if (!node) return;
      node.setAttribute("data-page", row ? "function" : "home");
      node.setAttribute("data-slug", target.slug || "");
      node.setAttribute("data-program", target.program || "");
      node.setAttribute("data-repo", target.repo || "");
      node.setAttribute("data-addr", row && row.addr || "");
      node.setAttribute("data-name", row && row.name || "");
      node.setAttribute("data-logical-id", row && row.logicalId ? String(row.logicalId) : "");
    }
    function retireSelection(identityRefresh) {
      intentRef.current = null;
      primaryRowRef.current = null;
      intentGeneration.current += 1;
      // Identity discovery still retires evidence, but is not a new navigation.
      if (!identityRefresh) navigationGeneration.current += 1;
      clearTimeout(evidenceTimer.current);
      writePageContext(null, targetRef.current || renderedTarget);
    }
    // Setters retire synchronously, before React commits or a promise can settle.
    // The render comparison also masks identity changes supplied by inventory/session refresh.
    if (!targetRef.current || targetIdentity(targetRef.current) !== targetKey) {
      retireSelection(true);
      targetRef.current = renderedTarget;
      writePageContext(null, renderedTarget);
    }
    function changeTarget(patch) {
      const next = Object.assign({}, targetRef.current, patch);
      if (targetIdentity(next) !== targetIdentity(targetRef.current)) {
        retireSelection();
        targetRef.current = next;
        writePageContext(null, next);
      }
    }
    const setSlug = useCallback(function (value) {
      const next = typeof value === "function" ? value(targetRef.current.slug) : value;
      // Bootstrap retains this callback across inventory discovery. Capture the
      // latest admitted inventory identity before creating its preview intent.
      const binary = binaryInventoryRef.current.find(function (item) { return item.slug === next; }) || {};
      changeTarget({ slug: next || "", content: binary.content_sha256 || binary.contentSha256 || binary.sha256 || binary.binary_hash || binary.hash || "", repo: binary.repo || "" });
      setSlugState(next);
    }, []);
    const setProgram = useCallback(function (value) {
      changeTarget({ program: canonicalProgram(value) });
      setProgramState(value);
    }, []);
    const setActiveSession = useCallback(function (value) {
      changeTarget({ session: value || "" });
      setActiveSessionState(value);
    }, []);
    const setDossier = useCallback(function (value) {
      if (value && Object.prototype.hasOwnProperty.call(value, "locator")) changeTarget({ locator: canonicalLocator(value.locator) });
      setDossierState(value);
    }, []);
    function beginSelection(row) {
      retireSelection();
      const target = Object.freeze(Object.assign({}, targetRef.current));
      const intent = Object.freeze({ generation: intentGeneration.current, target: target,
        targetKey: targetIdentity(target), row: row ? Object.freeze(Object.assign({}, row)) : null,
        requestedAddr: row && row.addr || "" });
      intentRef.current = intent;
      primaryRowRef.current = intent.row;
      setSelectionPacket({ intent: intent, row: intent.row });
      writePageContext(intent.row, target);
      return intent;
    }
    function isCurrentIntent(intent) {
      return selectionMounted.current && Boolean(intent) && intentRef.current === intent
        && intent.targetKey === targetIdentity(targetRef.current);
    }
    function responseMatches(intent, data) {
      return isCurrentIntent(intent) && Boolean(data)
        && (!data.locator || canonicalLocator(data.locator) === intent.target.locator)
        && (!data.program || canonicalProgram(data.program) === intent.target.program);
    }
    const renderIntent = intentRef.current;
    const selected = selectionPacket && selectionPacket.intent === renderIntent
      && isCurrentIntent(renderIntent) ? selectionPacket.row : null;
    const admittedPacket = evidencePacket && evidencePacket.intent === renderIntent
      && isCurrentIntent(renderIntent) ? evidencePacket : null;
    const detail = admittedPacket && admittedPacket.detail;
    const graph = admittedPacket && (!detail.resolvedFunction || !selected || sameFunctionAddress(detail.resolvedFunction.addr, selected.addr))
      ? admittedPacket.graph : null;
    const overview = admittedPacket && admittedPacket.overview;
    const lastDecompile = lastDecompilePacket && lastDecompilePacket.targetKey === targetKey
      && (!detail || !detail.resolvedSlug || !lastDecompilePacket.resolvedSlug || detail.resolvedSlug === lastDecompilePacket.resolvedSlug)
      ? lastDecompilePacket : null;
    const rows = rowPacket && rowPacket.targetKey === targetKey ? rowPacket.rows : [];
    function setRows(value) { setRowPacket({ targetKey: targetIdentity(targetRef.current), rows: value }); }
    const selectionKey = targetKey + "\0" + (selected && selected.addr || "");

    const reactJob = useCallback(function (id, data) {
      setReaction({ id: id, data: data });
    }, []);

    const loadBinaries = useCallback(async function () {
      const res = await fetch(API.binaries, { cache: "no-store" });
      const data = await res.json();
      const list = data.binaries || [];
      binaryInventoryRef.current = list;
      setBinaries(list);
      setRecoveredRoot(data.recovered || "");
    }, []);

    const corpusStatusSequence = useRef(0);
    const loadCorpusStatus = useCallback(async function (page) {
      if (page && !page.nativeEvent) projectPageRef.current = Object.assign({}, projectPageRef.current, page);
      const scope = projectPageRef.current;
      const sequence = ++corpusStatusSequence.current;
      const writeSequence = sessionsWriteSequence.current;
      setProjectBusy(true);
      await sessionsWriteQueue.current.catch(function () {});
      if (sequence !== corpusStatusSequence.current || writeSequence !== sessionsWriteSequence.current) {
        if (sequence === corpusStatusSequence.current) setProjectBusy(false);
        return;
      }
      const scopedApi = Object.assign({}, API, { corpusStatus: API.corpusStatus + "?scope=projects&q=" + encodeURIComponent(scope.q) + "&offset=" + scope.offset + "&limit=" + scope.limit });
      const result = await readCorpusStatus(function (url, init) { return fetch(url, init); }, scopedApi);
      if (sequence !== corpusStatusSequence.current) return;
      setCorpusStatus(function (previous) {
        if (result.status && result.status.scope === "projects") return result.status;
        return previous && previous.scope === "projects"
          ? Object.assign({}, previous, { staleError: result.status && result.status.error || "Refresh failed; showing the last project snapshot." })
          : result.status;
      });
      setCorpusIdentity(result.identity);
      setCorpusRevision(function (value) { return value + 1; });
      setProjectBusy(false);
    }, []);

    const loadPreparations = useCallback(async function () {
      if (preparationInFlight.current) return;
      preparationInFlight.current = true;
      setPreparationRefreshing(true);
      const sequence = ++preparationSequence.current;
      try {
        const res = await fetch(API.preparations, { cache: "no-store", signal: AbortSignal.timeout(10000) });
        if (!res.ok) throw new Error("Preparation request failed (" + res.status + ")");
        const data = await res.json();
        const received = preparationResponse(data);
        if (sequence !== preparationSequence.current) return;
        setPreparationRuns(received);
        setPreparationFeed({ receivedAt: Date.now(), error: "" });
      } catch (err) {
        if (sequence !== preparationSequence.current) return;
        setPreparationFeed(function (previous) { return { receivedAt: previous.receivedAt, error: String(err && err.message || err) }; });
      } finally {
        preparationInFlight.current = false;
        setPreparationRefreshing(false);
      }
    }, []);

    const loadJobs = useCallback(async function (requestedScope) {
      if (jobsRefreshInFlight.current) return;
      const scope = requestedScope === "history" ? "history" : "current";
      jobsRefreshInFlight.current = true;
      setJobsLoadingScope(scope);
      setJobsRefreshing(true);
      try {
        const url = scope === "current" ? API.jobsCurrent : API.jobsHistory;
        const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(30000) });
        if (!res.ok) throw new Error((scope === "current" ? "Live job status" : "Job history") + " request failed (" + res.status + ")");
        const data = await res.json();
        const list = Array.isArray(data.jobs) ? data.jobs : [];
        const note = jobsSnapshotRef.current === null ? "" : jobLiveAnnouncement(jobsSnapshotRef.current, list);
        jobsSnapshotRef.current = list;
        setJobs(list);
        setJobsScope(data.scope || (scope === "current" ? "current-process" : "retained-history"));
        setJobsVisibleCount(JOB_PAGE_SIZE);
        setJobAdmission(data.admission && typeof data.admission === "object" ? data.admission : null);
        setJobsRefreshedAt(Date.now());
        if (note) {
          setJobLiveText(note);
          showToast(note, /failed|cancelled/.test(note) ? "error" : "info");
        }
      } catch (err) {
        showToast("Could not refresh " + (scope === "current" ? "live job status" : "job history") + ": " + String(err && err.message || err), "error");
      } finally {
        jobsRefreshInFlight.current = false;
        setJobsLoadingScope("");
        setJobsRefreshing(false);
      }
    }, []);

    const loadFuncs = useCallback(async function (nextSlug, nextQuery, intent) {
      const scope = targetIdentity(targetRef.current);
      const target = intent ? intent.target : Object.assign({}, targetRef.current);
      const currentRead = function () { return scope === targetIdentity(targetRef.current) && (!intent || isCurrentIntent(intent)); };
      if (!currentRead()) return;
      const seq = funcSeqRef.current + 1;
      funcSeqRef.current = seq;
      const useSlug = nextSlug !== undefined ? nextSlug : target.slug;
      if (!useSlug && !target.program) {
        setRows([]);
        setTotal(0);
        setFuncNote("");
        return;
      }
      const loc = target.locator;
      const url = API.functions + "?slug=" + encodeURIComponent(useSlug)
        + "&q=" + encodeURIComponent(nextQuery !== undefined ? nextQuery : query)
        + "&offset=" + Math.max(0, funcOffset) + "&limit=" + funcLimit
        + (target.program ? "&program=" + encodeURIComponent(target.program) : "")
        + (loc ? "&locator=" + encodeURIComponent(loc) : "");
      const res = await fetch(url, { cache: "no-store" });
      if (!currentRead() || seq !== funcSeqRef.current) return;
      const data = await res.json();
      if (!currentRead() || seq !== funcSeqRef.current) return;
      if (res.ok && data.ok === true && data.queued === true) {
        setRows([]);
        setTotal(0);
        setFuncNote("Live function read queued. " + (data.sessionReason || "Waiting for the current Ghidra reader or writer."));
        return;
      }
      setRows(data.results || []);
      setTotal(data.total || 0);
      if (!data.ok && data.error) setFuncNote(humanError(data.error));
      else if (!(data.results || []).length) {
        setFuncNote(humanError(data.error) || (program
          ? (program + " has no functions yet. The pipeline analyzes it automatically.")
          : (funcOffset ? "Past the end of this build. Go back a page." : "Pick a program in Explorer.")));
      } else setFuncNote("");
    }, [slug, query, program, funcOffset, funcLimit, targetKey]);

    function commitEvidence(intent, data, row, merge) {
      if (!responseMatches(intent, data)) return null;
      const listing = data.listing || data;
      const center = data.selected || (listing.addr ? { addr: listing.addr, name: listing.name } : row) || intent.row;
      const detailValue = Object.assign({}, listing, data.decompile ? { decompile: data.decompile } : {},
        { resolvedFunction: center || null, resolvedSlug: data.slug || "", requestedAddr: intent.requestedAddr });
      if (data.error && !data.ok) detailValue.preview = "// Could not open listing\n// " + humanError(data.error);
      setEvidencePacket(function (previous) {
        if (!isCurrentIntent(intent)) return previous;
        const prior = merge && previous && previous.intent === intent ? previous : null;
        return { intent: intent,
          detail: Object.assign({}, prior && prior.detail || {}, detailValue),
          graph: data.graph || (prior && prior.graph) || null,
          overview: data.overview || (prior && prior.overview) || null };
      });
      // A backend center is evidence metadata, not permission to navigate from a data address.
      const pick = intent.row || center;
      if (pick && pick.addr) {
        primaryRowRef.current = pick;
        setSelectionPacket({ intent: intent, row: pick });
        writePageContext(pick, intent.target);
      }
      const decompile = detailValue.decompile;
      if (decompile && decompile.text && center && center.addr) {
        setLastDecompile({ targetKey: intent.targetKey, resolvedSlug: data.slug || "", text: decompile.text,
          name: center.name || "", addr: center.addr, source: decompile.source || "" });
      }
      return data;
    }

    async function loadWorkspace(intent, row) {
      if (!isCurrentIntent(intent)) return null;
      const target = intent.target;
      if (!target.locator || !target.program) return null;
      const addr = intent.requestedAddr || (row && row.addr) || "";
      const url = API.workspace + "?locator=" + encodeURIComponent(target.locator)
        + "&program=" + encodeURIComponent(target.program) + "&slug=" + encodeURIComponent(target.slug)
        + (addr ? "&addr=" + encodeURIComponent(addr) : "");
      const res = await fetch(url, { cache: "no-store" });
      if (!isCurrentIntent(intent)) return null;
      const data = await res.json();
      return commitEvidence(intent, data, row, false);
    }

    // Every evidence retry carries the original intent, including diagnostic lookup.
    async function loadFunctionEvidence(intent, row, evidenceSlug, attempt) {
      if (!isCurrentIntent(intent)) return;
      let data = null;
      try {
        const res = await fetch(API.detail + "?slug=" + encodeURIComponent(evidenceSlug || "")
          + "&addr=" + encodeURIComponent(row.addr)
          + "&locator=" + encodeURIComponent(intent.target.locator)
          + "&program=" + encodeURIComponent(intent.target.program), { cache: "no-store" });
        if (!isCurrentIntent(intent)) return;
        data = await res.json();
      } catch (err) { return; }
      if (!responseMatches(intent, data)) return;
      const request = data.evidenceRequest || null;
      let cause = "";
      if (request && request.status === "failed" && request.jobId) {
        try {
          const res = await fetch(API.jobs + "/" + encodeURIComponent(request.jobId), { cache: "no-store" });
          if (!isCurrentIntent(intent)) return;
          const job = await res.json();
          if (!isCurrentIntent(intent)) return;
          const record = (job && (job.job || job)) || {};
          const output = String(record.log || record.output || "");
          const state = /\*\*State:\*\* `([^`]+)`/.exec(output) || /"state":\s*"([^"]+)"/.exec(output);
          cause = state ? state[1] : "";
        } catch (err) { cause = ""; }
        if (!isCurrentIntent(intent)) return;
      }
      commitEvidence(intent, Object.assign({ slug: evidenceSlug || "" }, data, {
        evidenceRequest: request ? Object.assign({}, request, { cause: cause }) : null
      }), row, true);
      const pending = request && ["running", "queued", "admitted"].indexOf(request.status) >= 0;
      if (isCurrentIntent(intent) && pending && (attempt || 0) < 40) {
        evidenceTimer.current = setTimeout(function () {
          if (isCurrentIntent(intent)) loadFunctionEvidence(intent, row, evidenceSlug, (attempt || 0) + 1);
        }, 3000);
      }
    }

    async function readSelection(intent) {
      if (!isCurrentIntent(intent) || !intent.row) return;
      const row = intent.row;
      const target = intent.target;
      try {
        if (target.locator && target.program) {
          const ws = await loadWorkspace(intent, row);
          if (!isCurrentIntent(intent)) return;
          if (ws && ws.ok) {
            if (!(ws.decompile && ws.decompile.text)) {
              loadFunctionEvidence(intent, ws.selected || row, ws.slug || target.slug, 0);
            }
            return;
          }
          // Null denotes an ignored response, never permission to start a fallback.
          if (!ws) return;
        }
        const res = await fetch(API.detail + "?slug=" + encodeURIComponent(target.slug)
          + "&addr=" + encodeURIComponent(row.addr)
          + (target.locator ? "&locator=" + encodeURIComponent(target.locator) : "")
          + (target.program ? "&program=" + encodeURIComponent(target.program) : ""), { cache: "no-store" });
        if (!isCurrentIntent(intent)) return;
        const data = await res.json();
        commitEvidence(intent, data, row, false);
      } catch (err) {
        if (isCurrentIntent(intent)) commitEvidence(intent, { ok: false, error: String(err && err.message || err) }, row, false);
      }
    }
    const selectRow = useCallback(function (row) {
      // Retained callbacks from another concrete target cannot mint a fresh intent.
      if (targetKey !== targetIdentity(targetRef.current) || !selectionMounted.current) return Promise.resolve(null);
      const intent = beginSelection(row);
      return readSelection(intent);
    }, [targetKey]);

    function onFuncRowClick(ev, row) {
      if (!row) return;
      if (ev.shiftKey) {
        const from = checkAnchor || (selected && selected.addr) || row.addr;
        setCheckedAddrs(function (prev) {
          return mergeAddrLists(prev, rangeAddrList(rows, from, row.addr));
        });
        setCheckAnchor(row.addr);
        selectRow(row);
        return;
      }
      if (ev.ctrlKey || ev.metaKey) {
        setCheckedAddrs(function (prev) { return toggleAddrList(prev, row.addr); });
        setCheckAnchor(row.addr);
        selectRow(row);
        return;
      }
      selectRow(row);
    }

    function onFuncCheck(ev, row) {
      ev.preventDefault();
      ev.stopPropagation();
      if (!row) return;
      if (ev.shiftKey) {
        const from = checkAnchor || (selected && selected.addr) || row.addr;
        setCheckedAddrs(function (prev) {
          return mergeAddrLists(prev, rangeAddrList(rows, from, row.addr));
        });
      } else {
        setCheckedAddrs(function (prev) { return toggleAddrList(prev, row.addr); });
      }
      setCheckAnchor(row.addr);
    }

    const loadContext = useCallback(async function () {
      const generation = intentGeneration.current;
      try {
        const query = "?slug=" + encodeURIComponent(slug || "")
          + "&program=" + encodeURIComponent(program || "");
        const res = await fetch(API.context + query, { cache: "no-store" });
        const data = await res.json();
        if (data.defaults) setEnvDefaults(data.defaults);
        if (Array.isArray(data.pipelineStages)) setPipelineStages(data.pipelineStages);
        if (generation !== intentGeneration.current) return;
        const session = data.session || {};
        if (!program && session.program) setProgram(session.program);
        if (!slug && session.slug) setSlug(session.slug);
      } catch (_err) { /* optional */ }
    }, [program, slug]);

    const loadActions = useCallback(async function () {
      const res = await fetch(API.actions, { cache: "no-store" });
      const data = await res.json();
      const list = data.actions || [];
      setActions(list);
      if (data.context && data.context.defaults) setEnvDefaults(data.context.defaults);
      if (data.context && Array.isArray(data.context.pipelineStages)) setPipelineStages(data.context.pipelineStages);
    }, []);

    const loadMatchStatus = useCallback(async function () {
      try {
        const res = await fetch(API.matchStatus, { cache: "no-store" });
        const data = await res.json();
        setBsimStatus(data);
        return data;
      } catch (_err) {
        setBsimStatus({ ok: true, state: "database_unreachable", summary: "Could not read BSim status." });
        return null;
      }
    }, []);

    const loadRecoverStatus = useCallback(async function () {
      try {
        const url = API.recoverStatus
          + "?program=" + encodeURIComponent(program || "")
          + "&slug=" + encodeURIComponent(slug || "");
        const res = await fetch(url, { cache: "no-store" });
        const data = await res.json();
        setRecoverInfo(data);
        if (data.path) setRecoveredRoot(data.path);
        return data;
      } catch (_err) {
        setRecoverInfo({ ok: true, state: "none", summary: "Could not read recovered source." });
        return null;
      }
    }, [program, slug]);

    const loadBrowse = useCallback(async function (nextPath) {
      const requested = typeof nextPath === "string" ? nextPath.trim() : "";
      const sequence = ++browseReadSequence.current;
      if (browseReadController.current) browseReadController.current.abort();
      const controller = new AbortController();
      browseReadController.current = controller;
      setBrowseBusy(true);
      try {
        const res = await fetch(API.browse + "?path=" + encodeURIComponent(requested), {
          cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12000)])
        });
        const data = await res.json();
        if (controller.signal.aborted || sequence !== browseReadSequence.current) return null;
        if (!res.ok || !data || data.ok === false) throw new Error(data && data.error || "Could not read this folder.");
        setBrowse(data);
        setDialogError("");
        return data;
      } catch (error) {
        if (!controller.signal.aborted && sequence === browseReadSequence.current) {
          setDialogError("Could not browse " + (requested || "project locations") + ": " + String(error.message || error));
        }
        return null;
      } finally {
        if (sequence === browseReadSequence.current) setBrowseBusy(false);
      }
    }, []);

    useEffect(function () {
      // A delayed close effect must not cancel a newer Open project request.
      if (dialog === "open" || renderedBrowseDialogEpoch !== browseDialogEpoch.current) return;
      ++browseReadSequence.current;
      ++browseOpenSequence.current;
      if (browseReadController.current) browseReadController.current.abort();
      setBrowseBusy(false);
      setBrowseOpening(false);
    }, [dialog]);

    async function openBrowseEntry(entry) {
      if (!entry || !entry.path || browseOpening) return null;
      const value = String(entry.path);
      setOpenPaste(value);
      setDialogError("");
      if (["gpr", "ghidra-project", "project-dir", "shared-fs", "shared-project", "project-collection", "binary", "packed-program"].includes(entry.kind)) {
        const opening = ++browseOpenSequence.current;
        ++browseReadSequence.current;
        if (browseReadController.current) browseReadController.current.abort();
        setBrowseBusy(false);
        setBrowseOpening(true);
        try { return await openLocator(value); }
        finally { if (opening === browseOpenSequence.current) setBrowseOpening(false); }
      }
      const observed = await loadBrowse(value);
      if (observed && ["ghidra-project", "shared-fs", "shared-project", "binary", "packed-program"].includes(observed.kind)) {
        const opening = ++browseOpenSequence.current;
        setBrowseOpening(true);
        try { return await openLocator(observed.path || value); }
        finally { if (opening === browseOpenSequence.current) setBrowseOpening(false); }
      }
      return observed;
    }

    const loadPreview = useCallback(async function (locator) {
      /* Project inspection is scoped to the locator, not the selected function.
         Function-selection churn must not strand the project panel in “Reading…”. */
      const currentRead = function () {
        return selectionMounted.current
          && currentLocator() === canonicalLocator(locator);
      };
      if (!locator) {
        setPreview(null);
        setDossier(null);
        return;
      }
      try {
        const res = await fetch(API.inspect + "?locator=" + encodeURIComponent(locator), {
          cache: "no-store",
          signal: AbortSignal.timeout(10000)
        });
        if (!currentRead()) return;
        let data = null;
        try { data = await res.json(); } catch (_parseError) { data = null; }
        if (!currentRead()) return;
        if (!res.ok || !data || typeof data !== "object") {
          data = Object.assign({}, data || {}, {
            ok: false,
            locator: locator,
            error: (data && data.error) || ("Project inspection returned HTTP " + res.status + ".")
          });
        }
        setPreview(data);
        setDossier(data);
      } catch (error) {
        if (!currentRead()) return;
        const message = error && error.name === "TimeoutError"
          ? "Project inspection timed out after 10 seconds."
          : String(error && error.message || error || "Project inspection failed.");
        setPreview({ ok: false, locator: locator, error: message });
        setDossier({ ok: false, locator: locator, error: message });
      }
    }, []);

    function showToast(message, kind) {
      const text = String(message || "");
      if (!text) return;
      const tone = kind || "info";
      const entry = {
        id: "log-" + Date.now() + "-" + Math.random().toString(16).slice(2, 8),
        at: Date.now(),
        kind: tone,
        text: text
      };
      setLogEntries(function (prev) {
        const next = prev.concat(entry);
        return next.length > 200 ? next.slice(-200) : next;
      });
      setLogTab("log");
      if (tone === "error") setOpenLogId(entry.id);
      setIngestNote(text);
      window.clearTimeout(showToast._errTimer);
      if (tone === "error") {
        setStatusError(text);
        showToast._errTimer = window.setTimeout(function () { setStatusError(""); }, 20000);
      } else {
        setStatusError("");
        setLastNote(text);
      }
    }

    function openLogJobs() {
      setLogTab("jobs");
      setLogOpen(true);
    }

    const putSessions = useCallback(async function (nextActive, nextSessions, revision, options) {
      const write = ++sessionsWriteSequence.current;
      ++corpusStatusSequence.current;
      setProjectBusy(true);
      setCorpusStatus(null);
      const generation = intentGeneration.current;
      const persist = async function () {
      if (write !== sessionsWriteSequence.current) return { ok: false, ignored: true };
      const rev = sessionRevisionRef.current;
      try {
        const res = await fetch(API.sessions, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ active: nextActive, sessions: nextSessions, revision: rev, admitOpen: Boolean(options && options.admitOpen) }),
          signal: AbortSignal.timeout(45000)
        });
        const data = await res.json();
        if (!res.ok || data.ok === false) {
          showToast(data.error || "Could not save tab state.", "error");
          return Object.assign({}, data, { ok: false });
        }
        if (data.revision != null) { sessionRevisionRef.current = data.revision; setSessionRevision(data.revision); }
        if (data.sessions && write === sessionsWriteSequence.current && generation === intentGeneration.current) {
          sessionsRef.current = data.sessions;
          setSessions(data.sessions);
          if (data.active) setActiveSession(data.active);
        }
        if (data.merged) showToast("Tab state merged", "success");
        return data;
      } catch (error) {
        const message = error && error.name === "TimeoutError"
          ? "Could not confirm the tab save after 45 seconds. The server may have saved it; retry to reconcile the existing tab."
          : "Could not confirm the tab save. Retry to reconcile the existing tab.";
        showToast(message, "error");
        return { ok: false, error: message };
      }
      };
      const queued = sessionsWriteQueue.current.catch(function () {}).then(persist);
      sessionsWriteQueue.current = queued;
      const saved = await queued;
      if (write === sessionsWriteSequence.current) {
        if (saved && saved.ok !== false) loadCorpusStatus({ offset: 0 });
        else setProjectBusy(false);
      }
      return saved;
    }, [loadCorpusStatus]);

    const sessionsRef = useRef([]);
    const activeSessionRef = useRef("");
    const sessionRevisionRef = useRef(0);
    useEffect(function () { sessionsRef.current = sessions; }, [sessions]);
    useEffect(function () { activeSessionRef.current = activeSession; }, [activeSession]);
    useEffect(function () { sessionRevisionRef.current = sessionRevision; }, [sessionRevision]);
    // Every session mutation enters the serialized writer. An extra unload PUT
    // could overtake that queue with an older snapshot and resurrect closed tabs.

    const persistSessions = useCallback(async function (nextSessions, nextActive) {
      sessionsRef.current = nextSessions;
      activeSessionRef.current = nextActive;
      setSessions(nextSessions);
      setActiveSession(nextActive);
      return await putSessions(nextActive, nextSessions);
    }, [putSessions]);

    const patchActiveSession = useCallback(async function (patch) {
      const owner = activeSessionRef.current;
      const list = sessionsRef.current.map(function (item) {
        return item.id === owner ? Object.assign({}, item, patch) : item;
      });
      sessionsRef.current = list;
      setSessions(list);
      await putSessions(owner, list);
    }, [putSessions]);

    function closeDialog() {
      ++projectOperationSequence.current;
      ++addDialogSequence.current;
      ++openSequence.current;
      setAddBusy(false);
      setDialog("");
      setDialogError("");
      setMenu("");
    }

    function beginProjectOperation() {
      return { id: ++projectOperationSequence.current, generation: intentGeneration.current };
    }

    function projectOperationCurrent(operation) {
      return Boolean(operation) && selectionMounted.current
        && operation.id === projectOperationSequence.current
        && operation.generation === intentGeneration.current;
    }

    function resetTabState(nextLocator, operation, keepDialog) {
      if (operation && !projectOperationCurrent(operation)) return false;
      if (!operation) ++projectOperationSequence.current;
      if (!keepDialog) {
        ++openSequence.current;
        ++addDialogSequence.current;
        setAddBusy(false);
      }
      setFocusLocator("");
      retireSelection();
      setDossier({ locator: canonicalLocator(nextLocator) });
      ensureSeqRef.current += 1;
      funcSeqRef.current += 1;
      setSlug("");
      setProgram("");
      beginSelection(null);
      setEvidencePacket(null);
      setPreview(null);
      setQuery("");
      setIngestNote("");
      if (!keepDialog) setDialog("");
      setRows([]);
      setTotal(0);
      setCheckedAddrs([]);
      setCheckAnchor("");
      // Only this synchronous, already-authorized transition may rebase focus.
      if (operation) operation.generation = intentGeneration.current;
      return true;
    }

    function restoreTabSession(item) {
      resetTabState(item && item.locator);
      if (!item || !item.locator) return;
      setSlug("");
      setProgram("");
      changeTarget({ locator: canonicalLocator(item.locator) });
      loadPreview(item.locator);
    }

    function selectProgram(name) {
      setFocusLocator("");
      changeTarget({ locator: currentLocator() });
      const picked = (name || "").trim();
      ensureSeqRef.current += 1;
      funcSeqRef.current += 1;
      setProgram(picked);
      patchActiveSession({ program: picked });
      if (currentSession && currentSession.projectSlug) setSlug(currentSession.projectSlug);
      const intent = beginSelection(null);
      if (picked && intent.target.locator) {
        loadWorkspace(intent, null).catch(function () { /* unavailable until next current read */ });
        ensureGhidraProgram(picked, { intent: intent, quiet: true });
      }
    }

    async function ensureGhidraProgram(name, options) {
      const opts = options || {};
      // Only a synchronous UI entry may create this token. Async callers pass theirs.
      const intent = opts.intent || beginSelection(null);
      const target = canonicalProgram(name || intent.target.program);
      const locator = canonicalLocator(opts.locator || intent.target.locator);
      if (!target || !locator || target !== intent.target.program || locator !== intent.target.locator
          || !isCurrentIntent(intent)) return null;
      const seq = ++ensureSeqRef.current;
      const currentEnsure = function () { return seq === ensureSeqRef.current && isCurrentIntent(intent); };
      if (!opts.quiet) showToast("Opening " + target + "…");
      try {
        let res, data;
        for (let attempt = 0; attempt < 6; attempt += 1) {
          if (!currentEnsure()) return null;
          res = await fetch(API.ensureProgram, {
            method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ locator: locator, program: target })
          });
          if (!currentEnsure()) return null;
          data = await res.json();
          if (!currentEnsure() || !responseMatches(intent, data)) return null;
          if (!res.ok || data.ok !== true || data.queued !== true) break;
          setFuncNote("Live read queued for " + target + ". " + (data.sessionReason || "Waiting for the current Ghidra reader or writer."));
          if (attempt === 5) return data;
          const retryMs = Math.min(2000, Math.max(250, Number(data.retryAfterMs) || 500));
          await new Promise(function (resolve) { window.setTimeout(resolve, retryMs); });
          if (!currentEnsure()) return null;
        }
        if (!currentEnsure()) return null;
        if (!res.ok || data.ok !== true || data.ensured !== true) {
          if (!opts.quiet || opts.reportFailure) showToast(data.error || ("Could not open " + target + " in Ghidra."), "error");
          return null;
        }
        if (data.results && data.results.length) {
          setRows(data.results);
          setTotal(data.total || data.results.length);
          setFuncNote("");
          const first = data.results[0];
          commitEvidence(intent, { ok: true, selected: first,
            overview: { program: target, functionCount: data.total || data.results.length,
              namedCount: data.named || 0, path: data.program_path || target },
            listing: { name: first.name, addr: first.addr,
              preview: "// " + target + "\n// " + (data.total || data.results.length)
                + " functions from the Ghidra project\n" + (first.name || "") + "  @ " + (first.addr || "") }
          }, first, true);
          await loadWorkspace(intent, first);
          if (!currentEnsure()) return null;
          if (!opts.quiet) showToast(target + " — " + (data.total || data.results.length) + " functions", "success");
          return data;
        }
        await loadFuncs(intent.target.slug, undefined, intent);
        if (!currentEnsure()) return null;
        if (data.error && !opts.quiet) showToast(data.error, data.next === "analyze-program" ? "" : "error");
        return data;
      } catch (err) {
        if (!currentEnsure()) return null;
        if (!opts.quiet || opts.reportFailure) showToast("Could not open " + target + " in Ghidra: " + String((err && err.message) || err), "error");
        return null;
      }
    }

    const sessionOverviewSlugs = useMemo(function () {
      const slugs = [];
      const seen = new Set();
      function addName(name) {
        if (!name || seen.has(name)) return;
        seen.add(name);
        slugs.push(name);
      }
      if (currentSession) {
        addName(currentSession.projectSlug);
        sessionImportSlugs(currentSession).forEach(addName);
      }
      return slugs;
    }, [currentSession]);

    const overviewUrl = useMemo(function () {
      let url = "/dashboard/overview-fragment?embed=1";
      sessionOverviewSlugs.forEach(function (name) {
        url += "&slug=" + encodeURIComponent(name);
      });
      const programNames = [];
      const seenPrograms = new Set();
      function addProgram(name) {
        if (!name || seenPrograms.has(name)) return;
        seenPrograms.add(name);
        programNames.push(name);
      }
      if (currentSession && currentSession.program) addProgram(currentSession.program);
      ((dossier && dossier.ok ? (dossier.programs || []) : []).map(programName).filter(Boolean)).forEach(addProgram);
      programNames.forEach(function (name) {
        url += "&program=" + encodeURIComponent(name);
      });
      return url;
    }, [sessionOverviewSlugs, dossier, currentSession]);

    useEffect(function bootstrapWorkbench() {
      selectionMounted.current = true;
      const bootNavigation = navigationGeneration.current;
      const bootSessionWrite = sessionsWriteSequence.current;
      const bootProjectOperation = projectOperationSequence.current;
      window.AgentDecompileUI = {
        announce: function (msg) {
          const pulse = document.getElementById("job-pulse");
          if (pulse) pulse.title = msg;
        }
      };
      window.KotorXidUI = window.AgentDecompileUI;
      loadBinaries();
      loadActions();
      loadBrowse("");
      fetch(API.sessions, { cache: "no-store" }).then(function (res) { return res.json(); }).then(function (data) {
        // Context/default discovery can change the function target while this
        // read is pending. That must not discard the persisted project tabs.
        // Actual project operations or tab writes still supersede restoration.
        if (!selectionMounted.current || bootSessionWrite !== sessionsWriteSequence.current
          || bootProjectOperation !== projectOperationSequence.current) return;
        const restoreFocus = bootNavigation === navigationGeneration.current;
        const list = data.sessions || [];
        sessionsRef.current = list;
        setSessions(list);
        const activeId = data.active || (list[0] && list[0].id) || "";
        activeSessionRef.current = activeId;
        setActiveSession(activeId);
        if (data.revision != null) { sessionRevisionRef.current = data.revision; setSessionRevision(data.revision); }
        const cur = list.find(function (item) { return item.id === activeId; }) || list[0];
        /* A deep link that names a build wins over the restored tab, otherwise
           /dashboard?window=…&binary=X silently shows a different build. */
        const pinned = start.get("slug") || start.get("binary") || "";
        const pinnedProgram = start.get("program") || "";
        if (cur && cur.locator && restoreFocus) {
          if (!pinned) setSlug("");
          if (!pinnedProgram) setProgram("");
          setDossier({ locator: canonicalLocator(cur.locator) });
          beginSelection(null);
          loadPreview(cur.locator);
        }
      }).catch(function () { /* next write creates a draft */ });
      fetch(API.ghidraDefaults, { cache: "no-store" }).then(function (res) { return res.json(); }).then(function (data) {
        if (data.host) setSharedHost(String(data.host));
        if (data.port) setSharedPort(String(data.port));
        if (data.repository) setSharedRepo(String(data.repository));
        if (data.user) setSharedUser(String(data.user));
      }).catch(function () { /* keep defaults */ });
      function loadProbes() {
        fetch("/dashboard/healthz", { cache: "no-store" }).then(function (res) { return res.json(); }).then(function (data) {
          if (Array.isArray(data.probes)) setProbes(data.probes);
        }).catch(function () { /* optional */ });
      }
      loadProbes();
      const probeTimer = window.setInterval(loadProbes, 15000);
      function onKey(ev) {
        const mod = ev.ctrlKey || ev.metaKey;
        if (!mod) return;
        const key = (ev.key || "").toLowerCase();
        if (key === "s" && ev.shiftKey) {
          ev.preventDefault();
          openSaveAsDialog();
        } else if (key === "s") {
          ev.preventDefault();
          saveProject();
        } else if (key === "o" && ev.shiftKey) {
          ev.preventDefault();
          openProjectDialog("remote");
        } else if (key === "o") {
          ev.preventDefault();
          openProjectDialog();
        } else if (key === "n") {
          ev.preventDefault();
          createProject();
        } else if (key === "w") {
          ev.preventDefault();
          runCommand("file.close-tab");
        } else if (key === "i") {
          ev.preventDefault();
          runCommand("file.add-binaries");
        } else if (key === "j") {
          ev.preventDefault();
          runCommand("view.jobs");
        }
      }
      window.addEventListener("keydown", onKey);
      return function () {
        selectionMounted.current = false;
        retireSelection();
        ensureSeqRef.current += 1;
        funcSeqRef.current += 1;
        window.clearInterval(probeTimer);
        window.removeEventListener("keydown", onKey);
      };
    }, [loadBinaries, loadActions, loadBrowse, loadPreview]);

    useEffect(function () {
      loadContext();
    }, [loadContext]);

    // Opening a project leaves focus empty, including single-program projects.

    useEffect(function () {
      /* Reset paging on the same tick as the slug change so we do not fetch the
         old offset against the new build and then overwrite the first page. */
      if (funcSlugRef.current !== slug + "\0" + (program || "")) {
        funcSlugRef.current = slug + "\0" + (program || "");
        if (funcOffset !== 0) {
          setFuncOffset(0);
          return;
        }
      }
      loadFuncs(slug, query);
    }, [slug, program, query, funcOffset, funcLimit, loadFuncs]);

    useEffect(function () {
      if (editorTabFor(centerTab) === "wb-pipeline") loadPreparations();
      if (centerTab === "wb-recovery") loadRecoverStatus();
    }, [centerTab, loadPreparations, loadRecoverStatus]);

    /* A deep link from the old browse page names an address; land on that row so
       the link means the same thing it used to. Disarm after the first page so
       a later build cannot steal the selection. */
    const bootAddrRef = useRef(start.get("addr") || "");
    useEffect(function () {
      const want = bootAddrRef.current;
      if (!want || !rows.length) return;
      const hit = rows.find(function (row) {
        return row.addr === want || String(row.address) === String(parseInt(want, 16));
      });
      bootAddrRef.current = "";
      if (hit) selectRow(hit);
    }, [rows, selectRow]);

    useEffect(function () {
      if (!current.slug) return;
      setEditRole(current.role || "member");
      setEditLabel(current.label || "");
    }, [current.slug, current.role, current.label]);

    useEffect(function () {
      if (!menu) return undefined;
      function onDoc(ev) {
        const bar = document.getElementById("wb-menubar");
        if (bar && !bar.contains(ev.target)) setMenu("");
      }
      document.addEventListener("mousedown", onDoc);
      return function () { document.removeEventListener("mousedown", onDoc); };
    }, [menu]);

    useEffect(function () {
      if (!moreOpen) return undefined;
      function onDoc(ev) {
        const nav = document.getElementById("wb-corpus-nav");
        const more = nav && nav.querySelector(".wb-editor-more");
        if (more && !more.contains(ev.target)) setMoreOpen(false);
      }
      document.addEventListener("mousedown", onDoc);
      return function () { document.removeEventListener("mousedown", onDoc); };
    }, [moreOpen]);

    useEffect(function () {
      const tool = params().get("tool") || params().get("focus") || params().get("window") || "";
      if (!tool) return;
      const hit = SURFACES.find(function (item) {
        return item.id === tool || item.id === "wb-" + tool || item.keys.indexOf(tool) >= 0;
      });
      if (hit) {
        setCenterTab(editorTabFor(hit.id));
        if (MORE_SURFACE_IDS.has(hit.id)) setMoreOpen(true);
        scrollToSurface(hit.id);
      }
    }, [binaries]);

    useEffect(function () {
      if (!selectedJobId) {
        setJobDetail(null);
        setJobDetailLoading(false);
        setJobDetailError("");
        return undefined;
      }
      let dead = false;
      setJobDetail(null);
      setJobDetailLoading(true);
      setJobDetailError("");
      fetch(API.jobs + "/" + encodeURIComponent(selectedJobId), {
        cache: "no-store", signal: AbortSignal.timeout(15000)
      })
        .then(function (res) {
          if (!res.ok) throw new Error("Job detail request failed (" + res.status + ")");
          return res.json();
        })
        .then(function (data) {
          if (dead) return;
          const job = data.job || null;
          setJobDetail(job);
          if (!job) setJobDetailError("No retained detail was returned for this job.");
        })
        .catch(function (err) {
          if (dead) return;
          setJobDetailError(err && err.name === "TimeoutError"
            ? "Job detail request timed out after 15 seconds."
            : "Could not load job detail: " + String(err && err.message || err));
        })
        .finally(function () { if (!dead) setJobDetailLoading(false); });
      return function () { dead = true; };
    }, [selectedJobId, jobs, jobDetailReload]);

    useEffect(function () {
      function onPaletteKey(ev) {
        const mod = ev.ctrlKey || ev.metaKey;
        if (mod && (ev.key || "").toLowerCase() === "k") {
          ev.preventDefault();
          setPaletteOpen(function (prev) { return !prev; });
          setPaletteQuery("");
          setMenu("");
        }
        if (ev.key === "Escape") {
          setPaletteOpen(false);
          setConfirmDialog(null);
          setCtxMenu(null);
        }
      }
      window.addEventListener("keydown", onPaletteKey);
      return function () { window.removeEventListener("keydown", onPaletteKey); };
    }, []);

    useEffect(function () {
      function editingTarget(target) {
        if (!target) return false;
        const tag = (target.tagName || "").toUpperCase();
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
        return Boolean(target.isContentEditable);
      }
      function scrollSelectedFunc() {
        window.requestAnimationFrame(function () {
          const el = document.querySelector("#wb-func-window .wb-func-row.on");
          if (el) el.scrollIntoView({ block: "nearest" });
        });
      }
      function onFuncNav(ev) {
        if (paletteOpen || dialog || confirmDialog) return;
        if (editingTarget(ev.target)) return;
        if (!rows.length) return;
        const key = ev.key || "";
        if (key === "j" || key === "k") {
          ev.preventDefault();
          const idx = selected
            ? rows.findIndex(function (row) { return row.addr === selected.addr; })
            : -1;
          const next = key === "j"
            ? (idx < 0 ? 0 : Math.min(idx + 1, rows.length - 1))
            : (idx < 0 ? rows.length - 1 : Math.max(idx - 1, 0));
          const dest = rows[next];
          selectRow(dest);
          if (ev.shiftKey && dest) {
            const from = checkAnchor || (selected && selected.addr) || dest.addr;
            setCheckedAddrs(function (prev) {
              return mergeAddrLists(prev, rangeAddrList(rows, from, dest.addr));
            });
          }
          scrollSelectedFunc();
          return;
        }
        if ((key === "x" || key === "X" || key === " ") && selected) {
          ev.preventDefault();
          setCheckedAddrs(function (prev) { return toggleAddrList(prev, selected.addr); });
          setCheckAnchor(selected.addr);
          return;
        }
        if (key === "Escape" && checkedAddrs.length) {
          ev.preventDefault();
          setCheckedAddrs([]);
          setCheckAnchor("");
          return;
        }
        if (key === "Enter" && selected && lastActionId && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
          if (editingTarget(document.activeElement)) return;
          const act = actions.find(function (item) { return item.id === lastActionId; });
          if (!act) return;
          ev.preventDefault();
          openActionStrip(lastActionId);
        }
      }
      window.addEventListener("keydown", onFuncNav);
      return function () { window.removeEventListener("keydown", onFuncNav); };
    }, [paletteOpen, dialog, confirmDialog, rows, selected, lastActionId, actions, selectRow, checkAnchor, checkedAddrs]);

    useEffect(function () {
      setCheckedAddrs([]);
      setCheckAnchor("");
    }, [slug, program]);

    useEffect(function () {
      const live = {};
      rows.forEach(function (row) { live[row.addr] = true; });
      setCheckedAddrs(function (prev) {
        const next = prev.filter(function (addr) { return live[addr]; });
        return next.length === prev.length ? prev : next;
      });
    }, [rows]);

    useEffect(function () {
      document.body.classList.toggle("wb-density-compact", density === "compact");
      writeUiPref("wb-density", density);
    }, [density]);

    useEffect(function () {
      /* Decompile owns the right edge in the CodeBrowser grid, so the side rail
         only applies in classic layout. The command and pref still work either way. */
      document.body.classList.toggle("wb-jobs-rail", jobsRail && classicLayout);
      writeUiPref("wb-jobs-rail", jobsRail ? "1" : "0");
    }, [jobsRail, classicLayout]);

    useEffect(function () {
      document.body.classList.toggle("wb-classic-layout", classicLayout);
      writeUiPref("wb-classic-layout", classicLayout ? "1" : "0");
    }, [classicLayout]);

    useEffect(function () {
      writeUiPref("wb-decompile-open", decompileOpenNarrow ? "1" : "0");
    }, [decompileOpenNarrow]);

    async function registerLocator(locator, extraSlug, options) {
      let operationGeneration = intentGeneration.current;
      const operationCurrent = function () { return selectionMounted.current && operationGeneration === intentGeneration.current; };
      const value = (locator || "").trim();
      if (!value) return { ok: false, error: "locator is required" };
      const shared = /^(ghidra:\/\/|https?:\/\/)/i.test(value);
      const res = await fetch(API.binaries, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          path: shared ? "" : value,
          url: shared ? value : "",
          slug: extraSlug || newSlug,
          role: role,
          label: (options && options.label) || label
        })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!options || !options.quiet) {
        setIngestNote(data.ok ? "Registered " + (data.binary && data.binary.slug) : (data.error || "register failed"));
        if (data.ok && data.binary && !(options && options.intoProject)) {
          setSlug(data.binary.slug);
          const programs = data.binary.programs || [];
          if (programs.length) selectProgram(programs[0]);
        }
      }
      await loadBinaries();
      return data;
    }

    function triggerFileUpload() {
      if (!fileRef.current) return;
      fileRef.current.value = "";
      fileRef.current.click();
    }

    function triggerAddFileUpload() {
      if (!addFileRef.current) return;
      addFileRef.current.value = "";
      addFileRef.current.click();
    }

    async function stageAddFile(file) {
      if (!file) return;
      const sequence = ++addDialogSequence.current;
      const generation = intentGeneration.current;
      const owner = currentLocator();
      const currentUpload = function () { return sequence === addDialogSequence.current && generation === intentGeneration.current && owner === currentLocator() && selectionMounted.current; };
      setAddBusy(true);
      setDialogError("");
      try {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("paths", JSON.stringify([file.name]));
      const res = await fetch(API.stageDrop, { method: "POST", body: form });
      if (!currentUpload()) return;
      const data = await res.json();
      if (!currentUpload()) return;
      if (!res.ok || !data.ok || !data.root || !data.relative_paths || !data.relative_paths[0]) {
        failDialog(data.error || "Could not stage the selected file.");
        return;
      }
      const stagedPath = data.root.replace(/[\\/]+$/, "") + "/" + data.relative_paths[0];
      setAddPath(stagedPath);
      setAddFileName(file.name);
      setDialogError("");
      } catch (error) {
        if (currentUpload()) failDialog("Could not stage file: " + String(error.message || error));
      } finally {
        if (sequence === addDialogSequence.current) setAddBusy(false);
      }
    }

    function triggerFolderUpload() {
      if (!folderRef.current) return;
      folderRef.current.value = "";
      folderRef.current.click();
    }

    async function importIntoTab(binarySlug) {
      const generation = intentGeneration.current;
      const name = (binarySlug || "").trim();
      if (!name || !activeSession) return;
      let base = sessions;
      try {
        const res = await fetch(API.sessions, { cache: "no-store" });
        const data = await res.json();
        if (data.sessions && data.sessions.length) base = data.sessions;
      } catch (_err) { /* use in-memory copy */ }
      if (generation !== intentGeneration.current || !selectionMounted.current) return;
      const list = base.map(function (item) {
        if (item.id !== activeSession) return item;
        return Object.assign({}, item, {
          imports: mergeImportSlugs(sessionImportSlugs(item), [name], item.projectSlug || "")
        });
      });
      await persistSessions(list, activeSession);
    }

    async function createTabProject(preferredName, operation) {
      if (!projectOperationCurrent(operation)) return null;
      const operationCurrent = function () { return projectOperationCurrent(operation); };
      const session = sessions.find(function (item) { return item.id === activeSession; }) || currentSession;
      if (tabHasRealProject(session)) {
        return { ok: true, list: sessions, id: activeSession, projectSlug: session.projectSlug || "" };
      }
      const projectName = tabProjectName(session, preferredName);
      const res = await fetch(API.projects, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: projectName })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!data.ok) {
        showToast(data.error || "Could not create a project.", "error");
        return null;
      }
      return openLocator(data.locator || data.gpr, data.slug || projectName, { operation: operation, keepDialog: true });
    }

    async function openLocator(locator, title, options) {
      const opts = options || {};
      const operation = opts.operation || beginProjectOperation();
      if (!projectOperationCurrent(operation)) return null;
      const value = (locator || "").trim();
      if (!value) return null;
      const request = ++openSequence.current;
      const isCurrent = function () { return request === openSequence.current && projectOperationCurrent(operation); };
      try {
      const inspectedRes = await fetch(API.inspect + "?locator=" + encodeURIComponent(value), { cache: "no-store", signal: AbortSignal.timeout(15000) });
      if (!isCurrent()) return null;
      const inspected = await inspectedRes.json();
      if (!isCurrent()) return null;
      if (!inspectedRes.ok || !inspected.ok) {
        showToast(inspected.error || "Could not load that project.", "error");
        setDialogError(inspected.error || "Could not load that project.");
        return null;
      }
      if (inspected.kind === "project-collection" && Array.isArray(inspected.projects)) {
        // A folder containing several .gpr files is a chooser, not a project.
        // Opening it must not silently select a sibling or create a fake tab.
        const collection = String(inspected.canonical || inspected.locator || value);
        ++browseReadSequence.current;
        if (browseReadController.current) browseReadController.current.abort();
        setBrowseBusy(false);
        setOpenPaste(collection);
        setOpenTab("local");
        ++browseDialogEpoch.current;
        setDialog("open");
        setBrowse({ ok: true, path: collection,
          parent: collection.replace(/\/+$/, "").replace(/\/[^/]*$/, "") || "/",
          kind: "project-collection", entries: inspected.projects.filter(function (project) { return project && project.locator; }).map(function (project) {
            return { name: project.name || project.locator, path: project.locator, kind: "ghidra-project", programs: project.programs || [] };
          }) });
        setDialogError("");
        return { ok: false, requiresSelection: true, inspected: inspected };
      }
      if (!["ghidra-project", "shared-fs", "shared-project", "project-collection"].includes(inspected.kind)) {
        if (!["binary", "packed-program"].includes(inspected.kind)) {
          failDialog("This item is not an openable project or importable binary (" + String(inspected.kind || "unknown") + ").");
          return null;
        }
        openAddToProjectDialog();
        setAddPath(value);
        setAddFileName(value.split(/[/\\]/).pop());
        return null;
      }
      const canonical = canonicalLocator(inspected.canonical || inspected.gpr || inspected.locator || value);
      let list = sessionsRef.current.slice();
      const existing = list.find(function (item) { return canonicalLocator(item.locator) === canonical; });
      const draft = list.find(function (item) { return item.id === activeSessionRef.current && item.kind === "draft" && !item.locator && !sessionImportSlugs(item).length && !item.program && !item.projectSlug; });
      const id = existing ? existing.id : draft ? draft.id : "s" + Date.now() + Math.random().toString(16).slice(2, 6);
      const nextTitle = existing && existing.title || title || inspected.slug || "Project";
      const projectSlug = existing && existing.projectSlug || "";
      const opened = Object.assign({}, existing || draft || {}, { id: id, title: nextTitle,
        kind: inspected.kind, locator: canonical, projectSlug: projectSlug,
        imports: existing && existing.imports || [], program: "", created: existing && existing.created || Date.now() });
      if (existing || draft) list = list.map(function (item) { return item.id === id ? opened : item; });
      else list.push(opened);
      // Keep this open request alive while its project-tab selection is saved.
      // Closing/resetting the dialog here invalidates openSequence, making the
      // successful persistence response look stale before it can finish.
      if (!resetTabState(canonical, operation, true)) return null;
      setDossier(inspected);
      setPreview(inspected);
      sessionsRef.current = list;
      activeSessionRef.current = id;
      setSessions(list);
      setActiveSession(id);
      setCenterTab("wb-overview");
      const openIntent = beginSelection(null);
      operation.generation = intentGeneration.current;
      const saved = await putSessions(id, list, undefined, { admitOpen: false });
      if (!projectOperationCurrent(operation) || !isCurrentIntent(openIntent)) return null;
      if (!saved || saved.ok === false) {
        if (!saved || !saved.ignored) {
          setDialogError(saved && saved.error || "The project was read, but its tab could not be saved. Retry opening it.");
        }
        return null;
      }
      const admission = saved && saved.preparation;
      setIngestNote("Loaded " + nextTitle + (admission
        ? " · Recovery " + admission.status + " · run " + (admission.id || "unavailable")
          + " · generation " + (admission.generation || "not recorded")
          + " · queue " + (admission.queuePosition == null ? (admission.admissionPending ? "position pending" : "not queued") : admission.queuePosition)
          + (admission.reason ? " · " + admission.reason : "") : ""));
      if (!opts.keepDialog) closeDialog();
      return { ok: true, list: list, id: id, projectSlug: projectSlug || "", inspected: inspected, intent: openIntent };
      } catch (error) {
        if (isCurrent()) failDialog("Could not open project: " + String(error.message || error));
        return null;
      }
    }

    function builtSharedUrl() {
      if (sharedUrl.trim()) return sharedUrl.trim();
      const host = sharedHost.trim() || "127.0.0.1";
      const portNum = parseInt(sharedPort.trim() || "13100", 10);
      const repo = sharedRepo.trim();
      const prog = sharedProgram.trim();
      if (!repo) return "";
      const portBit = (!portNum || portNum === 13100) ? "" : (":" + portNum);
      return "ghidra://" + host + portBit + "/" + repo + (prog ? "/" + prog.replace(/^\/+/, "") : "");
    }

    async function registerShared(ev) {
      if (ev) ev.preventDefault();
      const locator = builtSharedUrl();
      if (!locator) {
        showToast("Enter a repository name or a ghidra:// URL.", "error");
        setDialogError("Enter a repository name or a ghidra:// URL.");
        return;
      }
      await openLocator(locator, sharedRepo || sharedProgram || "shared");
    }

    async function newTab() {
      const id = "s" + Date.now();
      const item = {
        id: id,
        title: "Untitled",
        kind: "draft",
        locator: "",
        projectSlug: "",
        imports: [],
        program: "",
        created: Date.now()
      };
      resetTabState();
      await persistSessions(sessionsRef.current.concat([item]), id);
    }

    async function closeTab(id) {
      const remain = sessionsRef.current.filter(function (item) { return item.id !== id; });
      if (!remain.length) {
        const fresh = {
          id: "s" + Date.now(),
          title: "Untitled",
          kind: "draft",
          locator: "",
          projectSlug: "",
          imports: [],
          program: "",
          created: Date.now()
        };
        resetTabState();
        await persistSessions([fresh], fresh.id);
        return;
      }
      const next = id === activeSession ? remain[remain.length - 1].id : activeSession;
      if (id === activeSession) {
        const chosen = remain.find(function (item) { return item.id === next; });
        setActiveSession(next);
        restoreTabSession(chosen);
      }
      await persistSessions(remain, next);
    }

    async function renameTab(id, title) {
      const name = (title || "").trim() || "Untitled";
      const list = sessionsRef.current.map(function (item) {
        return item.id === id ? Object.assign({}, item, { title: name }) : item;
      });
      await persistSessions(list, activeSession);
      setEditingTab("");
    }

    async function createProject() {
      const operation = beginProjectOperation();
      const res = await fetch(API.projects, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: (currentSession && currentSession.title) || "Project" })
      });
      const data = await res.json();
      if (!projectOperationCurrent(operation)) return;
      if (!data.ok) {
        const err = data.error || "Could not create a local project.";
        setIngestNote(err);
        showToast(err, "error");
        return;
      }
      await openLocator(data.locator || data.gpr, data.slug, { operation: operation });
    }

    function currentLocator() {
      const owner = sessionsRef.current.find(function (item) { return item.id === activeSessionRef.current; });
      return canonicalLocator(owner && owner.locator || "");
    }

    /* Reload answers "did my change on disk land?" without losing the tab layout: it
       re-reads the store, the project dossier, the function list and every legacy panel,
       and keeps the current slug/program selection. */
    async function reloadProject() {
      setMenu("");
      setStatusError("");
      const intent = beginSelection(selected);
      const locator = intent.target.locator;
      if (!locator) { showToast("This tab has no project to reload."); return; }
      showToast("Reloading…");
      try {
        await loadBinaries();
        if (!isCurrentIntent(intent)) return;
        await loadActions();
        if (!isCurrentIntent(intent)) return;
        await loadPreview(locator);
        if (!isCurrentIntent(intent)) return;
        await loadFuncs(intent.target.slug, query, intent);
        if (!isCurrentIntent(intent)) return;
        if (intent.row) await readSelection(intent);
        else await loadWorkspace(intent, null);
        if (!isCurrentIntent(intent)) return;
        reloadIslands();
        showToast("Reloaded " + locator, "success");
      } catch (err) {
        if (isCurrentIntent(intent)) showToast("Reload failed: " + String((err && err.message) || err), "error");
      }
    }

    async function saveProject() {
      let operationGeneration = intentGeneration.current;
      const operationCurrent = function () { return selectionMounted.current && operationGeneration === intentGeneration.current; };
      const locator = currentLocator();
      if (!locator) { showToast("Open or create a project before saving.", "warning"); return null; }
      const prevSlug = slug;
      const prevProgram = program;
      const res = await fetch(API.save, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ locator: locator })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!data.ok) {
        showToast(data.error || "Save failed.", "error");
        return data;
      }
      const nextLoc = data.locator || data.gpr || locator;
      const title = (currentSession && currentSession.title) || data.slug || "Project";
      setDossier(data);
      setPreview(data);
      const list = sessions.map(function (item) {
        if (item.id !== activeSession) return item;
        return Object.assign({}, item, {
          kind: data.kind || item.kind,
          locator: nextLoc || item.locator,
          projectSlug: item.projectSlug || data.slug || "",
          title: item.title || title
        });
      });
      operationGeneration = intentGeneration.current;
      await persistSessions(list, activeSession);
      if (!operationCurrent()) return null;
      if (prevSlug) setSlug(prevSlug);
      if (prevProgram) setProgram(prevProgram);
      showToast(data.state === "partial" || data.saved === false
        ? (data.message || "Program changes persisted; complete project save is not yet confirmed.")
        : "Saved " + title, data.state === "partial" || data.saved === false ? "warning" : "success");
      setMenu("");
      return data;
    }

    function openSaveAsDialog() {
      ++projectOperationSequence.current;
      ++openSequence.current;
      ++addDialogSequence.current;
      setAddBusy(false);
      setDialogError("");
      setSaveAsTarget("ghidra-project");
      const sourceName = dossier && dossier.slug || String(currentSession && currentSession.locator || "").replace(/\\/g, "/").split("/").pop();
      setSaveAsName(String(sourceName || currentSession && currentSession.title || "Project").replace(/\.gpr$/i, "").replace(/^[^:]+:\s*/, ""));
      setSaveAsDest("");
      setSaveAsUrl(sharedUrl || builtSharedUrl() || "");
      setDialog("save-as");
      setMenu("");
    }

    async function submitSaveAs(ev) {
      const operation = beginProjectOperation();
      const operationCurrent = function () { return projectOperationCurrent(operation); };
      if (ev) ev.preventDefault();
      setDialogError("");
      if (!(saveAsName || "").trim()) {
        failDialog("Give the project a name before saving.");
        return null;
      }
      if (saveAsTarget === "shared-project" && !(saveAsUrl || "").trim()) {
        failDialog("A shared project needs a ghidra:// server URL.");
        return null;
      }
      const res = await fetch(API.saveAs, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          locator: currentLocator(),
          target: saveAsTarget,
          name: saveAsName,
          dest: saveAsDest,
          url: saveAsUrl
        })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!data.ok) {
        failDialog(data.error || "Save As failed.");
        return data;
      }
      if (data.saved === false || data.project_metadata_saved === false || data.state === "partial") {
        failDialog(data.reason || data.origin_note || "The server did not confirm a complete project save. No successful copy is being claimed.");
        return data;
      }
      const next = saveAsTarget === "shared-project"
        ? (data.http_locator || data.locator || data.local_checkout || data.gpr)
        : (data.locator || data.local_checkout || data.gpr);
      if (next && next !== currentLocator()) {
        const carryImports = sessionImportSlugs(currentSession);
        const opened = await openLocator(next, data.slug || saveAsName, { operation: operation });
        if (!opened || !opened.ok) return null;
        if (opened && opened.ok && isCurrentIntent(opened.intent) && carryImports.length) {
          const list = opened.list.map(function (item) {
            if (item.id !== opened.id) return item;
            return Object.assign({}, item, {
              imports: mergeImportSlugs(sessionImportSlugs(item), carryImports, item.projectSlug || "")
            });
          });
          await persistSessions(list, opened.id);
        }
      } else if (next) {
        setDossier(data);
        setPreview(data);
        closeDialog();
      }
      showToast("Saved as " + kindTitle(data.kind || saveAsTarget) + (data.origin_note ? ". " + data.origin_note : ""), "success");
      if (data.origin_note) setIngestNote(data.origin_note);
      return data;
    }

    function openProjectDialog(tab) {
      ++browseDialogEpoch.current;
      ++projectOperationSequence.current;
      ++openSequence.current;
      ++addDialogSequence.current;
      setAddBusy(false);
      setOpenTab(tab === "remote" ? "remote" : "local");
      setDialogError("");
      setDialog("open");
      setMenu("");
      if (tab !== "remote") loadBrowse("");
    }

    /* A dialog reports its own failure next to the field that caused it; the toast alone
       leaves the operator staring at an unchanged form wondering what happened. */
    function failDialog(message) {
      setDialogError(String(message || ""));
      showToast(message, "error");
    }

    async function openPastedPath() {
      if (browseOpening) return;
      const value = (openPaste || "").trim();
      setDialogError("");
      if (!value) {
        failDialog("Paste a folder, .gpr, binary, or ghidra:// URL.");
        return;
      }
      // One inspect/router and one operation token cover every locator kind.
      await openBrowseEntry({ path: value, kind: "project-collection" });
    }

    /* Navigating closes the overflow menu the way a desktop menu closes on pick; the
       chosen window stays visible because CorpusNavBar promotes it into the tab strip. */
    function jumpTo(id) {
      setMenu("");
      setMoreOpen(false);
      if (id !== "wb-sidebar") setFilesOpen(false);
      if (id === "wb-sidebar") {
        setFilesOpen(true);
        return;
      }
      if (id === "wb-jobs") {
        openLogJobs();
        return;
      }
      const tab = editorTabFor(id);
      if (["graph", "wb-graph"].includes(id)) setComparisonMode("calls");
      if (["decompile", "wb-inspect", "inspect"].includes(id)) setComparisonMode("code");
      if (id === "listing") setComparisonMode("listing");
      setCenterTab(tab);
      if (["wb-match", "wb-review"].includes(id)) { scrollToSurface("wb-match-analysis"); return; }
      const contextual = ["wb-fnbrowse", "wb-functions", "decompile", "inspect", "wb-inspect", "graph", "wb-graph"].includes(id);
      scrollToSurface(contextual ? id : tab);
    }

    function jumpToCorpus(surfaceId) {
      jumpTo(surfaceId);
    }

    function askConfirm(opts) {
      setConfirmDialog({
        title: opts.title,
        message: opts.message || "",
        confirmLabel: opts.confirmLabel || "Confirm",
        danger: Boolean(opts.danger),
        onConfirm: function () {
          setConfirmDialog(null);
          if (opts.onConfirm) opts.onConfirm();
        }
      });
    }

    function closeConfirm() {
      setConfirmDialog(null);
    }

    function openActionStrip(actionId, initialParameters) {
      if (actionId) setLastActionId(actionId);
      setPendingActionId(actionId || "");
      setPendingActionParams(initialParameters || {});
      setActionExpanded(Boolean(initialParameters && Object.keys(initialParameters).length));
    }

    function openCtx(ev, items) {
      if (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      }
      setMenu("");
      setCtxMenu({ x: ev.clientX, y: ev.clientY, items: items || [] });
    }

    function copyText(text, label) {
      const value = String(text || "");
      if (!value) {
        showToast("Nothing to copy.", "error");
        return;
      }
      const clip = window.navigator && window.navigator.clipboard;
      if (clip && clip.writeText) {
        clip.writeText(value).then(function () {
          showToast("Copied " + (label || "value"), "success");
        }).catch(function () {
          showToast("The browser refused clipboard access.", "error");
        });
        return;
      }
      showToast("This browser exposes no clipboard API.", "error");
    }

    /* Right-click menus are built from the thing that was clicked. A menu that offers the
       same File verbs everywhere teaches the operator that right-click is not worth using. */
    function importCtxItems(row) {
      const name = (row && row.slug) || "";
      return [
        { title: "Open in Functions", run: function () { selectImportBinary(row); } },
        { title: "Listing", id: "view.listing" },
        "—",
        { title: "Copy name", run: function () { copyText(name, "name"); } },
        { title: "Copy path", run: function () { copyText((row && (row.locator || row.repo)) || "", "path"); } },
        "—",
        { title: "Remove " + name, danger: true, accel: "Del", run: function () { removeSlug(name); } }
      ].map(decorateCommandItem);
    }

    function programCtxItems(name) {
      return [
        { title: "Select program", run: function () { selectProgram(name); } },
        { title: "Open in Ghidra", run: function () { setProgram(name); ensureGhidraProgram(name, { locator: currentLocator() }); } },
        { title: "Listing", id: "view.listing" },
        { title: "Match", id: "view.cross-match" },
        { title: "Recover", id: "view.recovery" },
        { title: "Call Graph", id: "view.graph" },
        "—",
        { title: "Check in", id: "file.checkin" },
        "—",
        { title: "Copy program name", run: function () { copyText(name, "program name"); } },
        "—",
        { title: "Remove from project", danger: true, accel: "Del", run: function () { removeProgramFromProject(name); } }
      ].map(decorateCommandItem);
    }

    function projectCtxItems() {
      return [
        { id: "file.add-binaries" },
        { id: "file.reload" },
        "—",
        { id: "file.save" },
        { id: "file.save-as" },
        { id: "file.download-source" },
        "—",
        { title: "Copy project path", run: function () { copyText(currentLocator(), "project path"); } },
        "—",
        { id: "file.close-tab", danger: true }
      ].map(decorateCommandItem);
    }

    function functionCtxItems(row) {
      function runTool(actionId, extras) {
        if (row) selectRow(row);
        executeAction(actionId, extras || { addr: row && row.addr, name: row && row.name }, { skipConfirm: true });
      }
      return [
        { title: "Listing", id: "view.listing" },
        { title: "Call Graph", id: "view.graph" },
        { title: "Match", id: "view.cross-match" },
        { title: "Recover", id: "view.recovery" },
        { title: "Inspector", id: "view.inspect" },
        "—",
        { title: "Decompile", run: function () { runTool("mcp.decompile-function"); } },
        { title: "Add comment…", run: function () { if (row) selectRow(row); openActionStrip("mcp.manage-comments"); } },
        { title: "Create label…", run: function () { if (row) selectRow(row); openActionStrip("mcp.create-label"); } },
        { title: "Cross-references", run: function () { runTool("mcp.get-references"); } },
        { title: "Data flow", run: function () { runTool("mcp.analyze-data-flow"); } },
        { title: "Bookmark…", run: function () { if (row) selectRow(row); openActionStrip("mcp.manage-bookmarks"); } },
        { title: "Rename / manage function…", run: function () { if (row) selectRow(row); openActionStrip("mcp.manage-function"); } },
        "—",
        { title: "Run last action", id: "run.last" },
        "—",
        { title: "Copy address", run: function () { copyText(row && row.addr, "address"); } },
        { title: "Copy name", run: function () { copyText((row && row.name) || (row && row.addr), "name"); } }
      ].map(decorateCommandItem);
    }

    function runCommand(id, extra) {
      extra = extra || {};
      if (id !== "view.explorer") setFilesOpen(false);
      setCtxMenu(null);
      setMenu("");
      if (id === "file.new-project") { createProject(); showToast("New project"); return; }
      if (id === "file.new-tab") { newTab(); showToast("New tab"); return; }
      if (id === "file.open") { openProjectDialog(); showToast("Open…"); return; }
      if (id === "file.open-url") { openProjectDialog("remote"); showToast("Open from URL…"); return; }
      if (id === "file.save") { saveProject(); return; }
      if (id === "file.save-as") { openSaveAsDialog(); showToast("Save As…"); return; }
      if (id === "file.download-source") { downloadProjectSource(); return; }
      if (id === "view.panels") { setDialog("panels"); return; }
      if (id === "view.match-receipts") { setDialog("match-receipts"); return; }
      if (id === "file.checkin") {
        if (focusLocator && canonicalLocator(focusLocator) !== currentLocator()) {
          showToast("Choose a program in the active project before checking it in. The compared function belongs to another project.", "warning");
          return;
        }
        const kind = (dossier && dossier.kind) || (currentSession && currentSession.kind) || "";
        const loc = currentLocator();
        const isServer = kind === "shared-project" || String(loc).indexOf("ghidra://") === 0;
        if (!isServer) {
          showToast("Check in needs a Ghidra Server project, not a local .gpr.", "error");
          return;
        }
        if (!program) {
          showToast("Select a program to check in.", "error");
          return;
        }
        if (dossier && dossier.reachable === false && !dossier.mirror_available) {
          showToast("Lost connection to Ghidra Server.", "error");
          return;
        }
        const programPath = (dossier && dossier.program_paths && dossier.program_paths[program]) || program;
        executeAction("mcp.checkin-program", { program: programPath }, { skipConfirm: true });
        showToast("Check in queued");
        return;
      }
      if (id === "file.open-program") {
        if (focusLocator && canonicalLocator(focusLocator) !== currentLocator()) { showToast("Choose a program in the active project first.", "warning"); return; }
        if (!program) { showToast("Select a program first", "error"); return; }
        ensureGhidraProgram(program, { locator: currentLocator() });
        return;
      }
      if (id === "file.add-binaries") { openAddToProjectDialog(); return; }
      if (id === "file.reload") { reloadProject(); return; }
      if (id === "file.close-tab") {
        if (!currentSession) return;
        const dirty = currentSession.kind !== "draft" || currentSession.locator || sessionImportSlugs(currentSession).length;
        if (dirty) {
          askConfirm({
            title: "Close " + (currentSession.title || "tab") + "?",
            message: "This closes the project tab. File → Open reopens it. New tab only creates a draft.",
            confirmLabel: "Close tab",
            danger: true,
            onConfirm: function () { closeTab(currentSession.id); }
          });
          return;
        }
        closeTab(currentSession.id);
        showToast("Closed tab");
        return;
      }
      if (id === "file.remove-binary") {
        if (program) { removeProgramFromProject(program); return; }
        if (extra.program) { removeProgramFromProject(extra.program); return; }
        if (extra.slug) removeSlug(extra.slug);
        else if (slug && slug !== (currentSession && currentSession.projectSlug)) removeSlug(slug);
        return;
      }
      if (id === "edit.rename-tab") {
        if (currentSession) setEditingTab(currentSession.id);
        showToast("Rename tab");
        return;
      }
      /* Navigation is its own feedback: the tab highlights and the body changes.
         Toasting it as well buries the notifications that report real outcomes. */
      if (id === "view.palette") { setPaletteOpen(true); setPaletteQuery(""); return; }
      if (id === "view.jobs") { jumpTo("wb-jobs"); return; }
      if (id === "view.listing") { jumpTo("listing"); return; }
      if (id === "view.browse") { jumpTo("wb-fnbrowse"); return; }
      if (id === "view.logical") { jumpTo("wb-logical"); return; }
      if (id === "view.inspect") { jumpTo("wb-inspect"); return; }
      if (id === "view.graph") { jumpTo("wb-graph"); return; }
      if (id === "view.artifacts") { jumpTo("wb-artifacts"); return; }
      if (id === "view.evidence") { jumpTo("wb-evidence"); return; }
      if (id === "view.overview") { jumpTo("wb-overview"); return; }
      if (id === "view.atlas") { jumpTo("wb-atlas"); return; }
      if (id === "view.pipeline") { jumpTo("wb-pipeline"); return; }
      if (id === "view.report") { jumpTo("wb-report"); return; }
      if (id === "view.cross-match") { jumpTo("wb-match"); return; }
      if (id === "view.recovery") { jumpTo("wb-recovery"); return; }
      if (id === "view.stabs") { jumpTo("wb-stabs"); return; }
      if (id === "view.knowledge") { jumpTo("wb-knowledge"); return; }
      if (id === "view.review") { jumpTo("wb-review"); return; }
      if (id === "view.corpus") { jumpTo("wb-corpus"); return; }
      if (id === "view.tools") { jumpTo("wb-tools"); return; }
      if (id === "view.explorer") { jumpTo("wb-sidebar"); return; }
      if (id === "view.density-compact") { setDensity("compact"); return; }
      if (id === "view.density-comfortable") { setDensity("comfortable"); return; }
      if (id === "view.jobs-rail") { setJobsRail(true); return; }
      if (id === "view.jobs-bottom") { setJobsRail(false); return; }
      if (id === "view.classic-layout") {
        setClassicLayout(function (v) {
          const next = !v;
          showToast(next ? "Classic layout on" : "Classic layout off");
          return next;
        });
        return;
      }
      if (id === "run.last") {
        if (lastActionId) { openActionStrip(lastActionId); showToast("Last action " + lastActionId); }
        else showToast("No last action yet.", "error");
        return;
      }
      if (id === "help.access") { setDialog("access"); showToast("Shortcuts and menus"); return; }
      if (id === "help.overview") { jumpTo("wb-overview"); return; }
      showToast("Unknown command " + id, "error");
    }

    useEffect(function () {
      function typingTarget(el) {
        if (!el) return false;
        const tag = (el.tagName || "").toLowerCase();
        return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
      }
      function onCmd(ev) {
        if (typingTarget(ev.target) && ev.key !== "Escape") return;
        const mod = ev.ctrlKey || ev.metaKey;
        const key = (ev.key || "").toLowerCase();
        if (ev.key === "Escape") {
          if (paletteOpen) { ev.preventDefault(); setPaletteOpen(false); return; }
          if (confirmDialog) { ev.preventDefault(); closeConfirm(); return; }
          if (ctxMenu) { ev.preventDefault(); setCtxMenu(null); return; }
          if (dialog) { ev.preventDefault(); closeDialog(); return; }
          if (menu) { ev.preventDefault(); setMenu(""); return; }
          if (moreOpen) { ev.preventDefault(); setMoreOpen(false); return; }
          return;
        }
        if (ev.key === "F2") { ev.preventDefault(); runCommand("edit.rename-tab"); return; }
        if (ev.key === "Delete") {
          if (slug && currentSession && slug !== currentSession.projectSlug) {
            ev.preventDefault();
            runCommand("file.remove-binary", { slug: slug });
          }
          return;
        }
        if (ev.key === "?" && ev.shiftKey && !mod) { ev.preventDefault(); runCommand("help.access"); return; }
        if (ev.altKey && !mod) {
          const altMap = {
            n: "file.new-project",
            t: "file.new-tab",
            w: "file.close-tab",
            r: "file.reload",
            f: "view.browse",
            l: "view.logical",
            j: "view.jobs",
            1: "view.listing",
            2: "view.graph",
            3: "view.overview",
            4: "view.atlas",
            5: "view.cross-match",
            6: "view.inspect",
            7: "view.tools"
          };
          const altCmd = altMap[key];
          if (altCmd) { ev.preventDefault(); runCommand(altCmd); }
          return;
        }
        if (!mod) return;
        if (key === "k") { return; }
        else if (key === "u" && ev.shiftKey) { ev.preventDefault(); runCommand("file.open-url"); }
        else if (key === "o") { ev.preventDefault(); runCommand("file.open"); }
        else if (key === "s" && ev.shiftKey) { ev.preventDefault(); runCommand("file.save-as"); }
        else if (key === "s") { ev.preventDefault(); runCommand("file.save"); }
        else if (key === "i") { ev.preventDefault(); runCommand("file.add-binaries"); }
        else if (key === "e" && ev.shiftKey) { ev.preventDefault(); runCommand("view.explorer"); }
        else if (key === "w") { ev.preventDefault(); runCommand("file.close-tab"); }
      }
      window.addEventListener("keydown", onCmd);
      return function () { window.removeEventListener("keydown", onCmd); };
    });

    async function selectJobInDock(jobId) {
      setSelectedJobId(jobId || "");
      openLogJobs();
    }

    function retryJobDetail() {
      setJobDetailReload(function (value) { return value + 1; });
    }

    async function cancelJob(jobId) {
      if (!jobId) return;
      try {
        await fetch(API.jobs + "/" + encodeURIComponent(jobId) + "/cancel", { method: "POST" });
        showToast("Cancel requested for " + jobId, "info");
      } catch (_err) {
        showToast("Could not cancel job.", "error");
      }
    }

    const toolContext = useMemo(function () {
      const tabSlugs = [];
      const seen = new Set();
      function addSlug(name) {
        if (!name || seen.has(name)) return;
        seen.add(name);
        tabSlugs.push(name);
      }
      if (currentSession && currentSession.projectSlug && slug === currentSession.projectSlug) {
        addSlug(currentSession.projectSlug);
      }
      sessionImportSlugs(currentSession).forEach(addSlug);
      if (slug) addSlug(slug);
      const tabRows = tabSlugs.map(function (name) {
        return binaries.find(function (row) { return row.slug === name; });
      }).filter(Boolean);
      const projectNames = (dossier && dossier.ok ? (dossier.programs || []) : []).map(programName).filter(Boolean);
      const activeRow = binaries.find(function (row) { return row.slug === slug; }) || tabRows[0] || {};
      return {
        slug: slug || (currentSession && currentSession.projectSlug) || "",
        program: program || "",
        repo: activeRow.repo || "",
        addr: selected && selected.addr ? selected.addr : "",
        name: selected && selected.name ? selected.name : "",
        db: envDefaults.db || "",
        work_dir: envDefaults.work_dir || "",
        kb: envDefaults.kb || "",
        recovered: recoveredRoot || "",
        tabSlugs: tabSlugs,
        tabRows: (corpusStatus && corpusStatus.builds || []).filter(function (row) { return row.slug && row.bindingState !== "ambiguous" && row.repositoryBindingState !== "unresolved"; }).map(function (row) { return binaries.find(function (b) { return b.slug === row.slug; }); }).filter(Boolean),
        allBinaries: binaries.filter(function (b) { return (corpusStatus && corpusStatus.builds || []).some(function (row) { return row.slug === b.slug; }); }),
        programs: projectNames,
        functions: rows
      };
    }, [binaries, slug, program, selected, rows, currentSession, dossier, envDefaults, recoveredRoot, corpusStatus]);

    function liveToolContext() {
      const target = targetRef.current;
      const row = isCurrentIntent(intentRef.current) ? primaryRowRef.current : null;
      return Object.assign({}, toolContext, { slug: target.slug, program: target.program,
        locator: target.locator, repo: target.repo || "", addr: row && row.addr || "", name: row && row.name || "",
        functions: targetKey === targetIdentity(target) ? rows : [] });
    }

    const programProgress = useMemo(function () {
      const locator = currentLocator();
      if (!locator) return {};
      const projection = {};
      jobs.forEach(function (job) {
        const params = job.params || {};
        const jobLocator = String(params.locator || "").trim();
        const jobProgram = String(params.program || params.programPath || "").trim();
        if (jobLocator !== locator || !jobProgram) return;
        const active = job.status === "running" || job.status === "queued";
        const previous = projection[jobProgram];
        if (previous && (previous.active || !active)) return;
        projection[jobProgram] = {
          active: active,
          pct: measuredJobPercent(job),
          tool: job.actionId || "",
          status: job.status
        };
      });
      return projection;
    }, [jobs, dossier, currentSession]);

    async function executeAction(actionId, paramOverrides, options) {
      const opts = options || {};
      if (!actionId) return null;
      if (!opts.targetContext && targetKey !== targetIdentity(targetRef.current)) return null;
      const actionIntent = intentRef.current;
      const currentContext = liveToolContext();
      setLastActionId(actionId);
      const act = actions.find(function (item) { return item.id === actionId; });
      if (!act) {
        showToast("Unknown action " + actionId, "error");
        return null;
      }
      const params = paramOverrides || {};
      if ((act.mutating || act.danger) && actionId.indexOf("mcp.") === 0) {
        const nativeContext = opts.targetContext || currentContext;
        const nativeProgram = canonicalProgram(params.program || nativeContext.program);
        const nativeLocator = canonicalLocator(params.locator || nativeContext.locator);
        const bindings = projectBuilds.filter(function (build) { return canonicalLocator(build.locator) === nativeLocator && canonicalProgram(build.program) === nativeProgram; });
        if (bindings.length !== 1 || bindings[0].bindingState === "ambiguous" || bindings[0].repositoryBindingState === "unresolved") {
          showToast("Native changes require one unambiguous project/program binding. Review the project membership before running this command.", "warning");
          return null;
        }
      }
      const checkedRows = rows.filter(function (row) { return checkedAddrs.indexOf(row.addr) >= 0; });
      const batchTargets = opts.batch === false
        ? []
        : (checkedRows.length > 1 && actionUsesAddr(act) ? checkedRows : []);
      const needsConfirm = !opts.skipConfirm && (
        opts.danger || act.danger || opts.mutating || act.mutating
      );
      if (needsConfirm) {
        askConfirm({
          title: batchTargets.length > 1
            ? "Run " + (act.title || actionId) + " on " + batchTargets.length + " functions?"
            : "Run " + (act.title || actionId) + "?",
          message: act.summary || "",
          danger: act.danger || opts.danger,
          onConfirm: function () {
            executeAction(actionId, paramOverrides, Object.assign({}, opts, { skipConfirm: true }));
          }
        });
        return null;
      }
      if (batchTargets.length > 1) {
        showToast("Starting " + (act.title || actionId) + " on " + batchTargets.length + " functions…", "info");
        let ok = 0;
        for (let i = 0; i < batchTargets.length; i += 1) {
          const row = batchTargets[i];
          const result = await executeAction(
            actionId,
            Object.assign({}, params, { addr: row.addr, name: row.name }),
            { skipConfirm: true, batch: false, quiet: true, targetRow: row }
          );
          if (result) ok += 1;
        }
        showToast("Queued " + ok + " of " + batchTargets.length + " — " + (act.title || actionId), ok ? "info" : "error");
        return ok;
      }
      const row = opts.targetRow;
      const targetContext = opts.targetContext || {};
      const captured = function (key, fallback) {
        return Object.prototype.hasOwnProperty.call(targetContext, key) ? targetContext[key] : fallback;
      };
      const ctx = {
        slug: captured("slug", currentContext.slug) || "",
        program: captured("program", currentContext.program) || "",
        repo: captured("repo", currentContext.repo) || "",
        locator: captured("locator", currentContext.locator) || "",
        addr: (row && row.addr) || params.addr || currentContext.addr || "",
        name: (row && row.name) || params.name || currentContext.name || "",
        db: currentContext.db || "",
        work_dir: currentContext.work_dir || "",
        kb: currentContext.kb || ""
      };
      if (!opts.quiet) showToast("Starting " + (act.title || actionId) + "…", "info");
      const body = Object.assign({}, params, { confirm: true, context: ctx });
      let res;
      let data;
      try {
        res = await fetch("/api/v1/actions/" + actionId.replace(/\./g, "/"), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body)
        });
        data = await res.json();
        // Some hot-reloaded catalog actions are newer than the action-specific
        // routes mounted when the server started. Keep them on the same job
        // runner and admission path through the stable dashboard endpoint.
        if (res.status === 404) {
          res = await fetch("/dashboard/api/jobs", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ action: actionId, params: params, context: ctx, confirm: true })
          });
          data = await res.json();
        }
      } catch (err) {
        const message = "Action request failed: " + String((err && err.message) || err);
        if (!opts.quiet) showToast(message, "error");
        reactJob(actionId, { error: message });
        return null;
      }
      if (!res.ok) {
        if (!opts.quiet) showToast(data.error || "Action failed", "error");
        reactJob(actionId, data);
        return null;
      }
      reactJob(actionId, data);
      pushRecentActionId(actionId);
      setRecentActionIds(readRecentActionIds());
      if (data.job && data.job.id) {
        setJobs(function (previous) {
          return [Object.assign({ actionId: actionId }, data.job), ...previous.filter(function (job) { return job.id !== data.job.id; })];
        });
        openLogJobs();
        setSelectedJobId(data.job.id);
        if (!opts.quiet) showToast("Job " + data.job.id + " — " + (act.title || actionId), "info");
      } else if (data.argv && !opts.quiet) {
        showToast("Dry run: " + data.argv.join(" "), "success");
      }
      if (!data.job && !data.argv) loadCorpusStatus();
      if (String(actionId).indexOf("decompile") >= 0 || String(actionId).indexOf("rename") >= 0) {
        loadBinaries();
        if (isCurrentIntent(actionIntent)) {
          const refreshed = beginSelection(primaryRowRef.current);
          loadFuncs(refreshed.target.slug, undefined, refreshed);
          if (refreshed.row) readSelection(refreshed);
        }
      }
      return data;
    }

    async function downloadProjectSource() {
      const owner = currentSession;
      const identity = projectUniverse && projectUniverse.corpusIdentity;
      if (!owner || !owner.locator || !identity) {
        showToast("Load project facts before downloading its source. No export was started.", "warning");
        return;
      }
      const actionId = "workbench.export-project-source-zip";
      if (!actions.some(function (action) { return action.id === actionId; })) {
        await loadActions();
        showToast("Project source export is not in the loaded catalog yet. The catalog was refreshed; try again.", "warning");
        return;
      }
      const key = JSON.stringify([owner.id, owner.locator, identity]);
      let entry = projectSourceRequests.current.get(key);
      if (entry && entry.waiting) return;
      const context = liveToolContext();
      const current = function () {
        const session = sessionsRef.current.find(function (item) { return item.id === activeSessionRef.current; });
        return selectionMounted.current && session && session.id === owner.id && session.locator === owner.locator && liveToolContext().db === context.db;
      };
      if (!entry) {
        entry = { waiting: true, jobId: null, result: null, uncertain: false };
        projectSourceRequests.current.set(key, entry);
        setProjectSourceState({ owner: owner.id, status: "waiting" });
        try {
          const admission = await executeAction(actionId, { project_id: owner.id, corpus_identity: identity, locator: owner.locator }, { skipConfirm: true, batch: false, quiet: true, targetContext: context });
          if (!admission) { entry.uncertain = true; throw new Error("Export admission could not be confirmed. Check Activity before trying another export."); }
          entry.jobId = admission.job && admission.job.id;
          if (!entry.jobId) entry.result = admission;
        } catch (error) {
          entry.waiting = false;
          setProjectSourceState(function (state) {
            return state && state.owner === owner.id ? { owner: owner.id, status: "uncertain" } : state;
          });
          if (current()) showToast(String(error.message || error), "error");
          return;
        }
      }
      if (entry.uncertain) {
        if (current()) showToast("The previous admission is uncertain. Check Activity; no duplicate export was submitted.", "warning");
        return;
      }
      entry.waiting = true;
      if (current()) setProjectSourceState({ owner: owner.id, status: "waiting" });
      try {
        const deadline = Date.now() + 60000;
        while (!entry.result && Date.now() < deadline && current()) {
          const response = await fetch(API.jobs + "/" + encodeURIComponent(entry.jobId), { cache: "no-store", signal: AbortSignal.timeout(10000) });
          if (!response.ok) throw new Error("Could not inspect source export " + entry.jobId + ". Check the existing export; no duplicate will be submitted.");
          const packet = await response.json(), job = packet.job;
          if (!job || job.id !== entry.jobId) throw new Error("Source export job identity did not match.");
          if (job.status === "ok") {
            const log = String(job.log || ""), newline = log.indexOf("\n");
            entry.result = JSON.parse(newline >= 0 ? log.slice(newline + 1) : log);
          } else if (["error", "failed", "cancelled", "canceled"].includes(job.status)) {
            throw new Error(job.error || "Source export " + job.status + ". Inspect Activity for its recorded error.");
          } else await new Promise(function (resolve) { window.setTimeout(resolve, 750); });
        }
        if (!current()) return;
        if (!entry.result) {
          setProjectSourceState({ owner: owner.id, status: "pending" });
          showToast("The source export is still queued or preparing. Check source download to reconnect to the same job.", "info");
          return;
        }
        const result = entry.result;
        if (!result.ok || result.scope !== "project" || !result.project || result.project.id !== owner.id || !/^\/dashboard\/api\/workbench\/source-archives\/[a-f0-9]{32}\/download$/.test(result.downloadUrl || "")) throw new Error(result.error || "The source export did not return a project-bound download.");
        const link = document.createElement("a");
        link.href = result.downloadUrl; link.download = result.filename || "project-source.zip";
        document.body.appendChild(link); link.click(); link.remove();
        setProjectSourceState({ owner: owner.id, status: "ready" });
        showToast(result.partial ? "Project source snapshot downloaded. Its manifest lists missing source; this is not a complete matching-C build." : "Project source snapshot downloaded. Compilation and byte parity are not established by this export.", result.partial ? "warning" : "success");
      } catch (error) {
        if (current()) { setProjectSourceState({ owner: owner.id, status: "pending" }); showToast(String(error.message || error), "error"); }
      } finally {
        entry.waiting = false;
        // Leaving a tab stops observation, not its admitted export. Allow the
        // same project to reconnect when revisited without admitting a duplicate.
        setProjectSourceState(function (state) {
          return state && state.owner === owner.id && state.status === "waiting"
            ? { owner: owner.id, status: "pending" } : state;
        });
      }
    }

    /* Pause, resume and stop are the only workflow controls (R4). They post the
       same workbench.workflow-control action explorer-page.js already uses,
       scoped to the run in view via preparation_id. */
    function controlPreparation(preparationId, operation) {
      if (["pause", "resume", "stop"].indexOf(operation) === -1) return Promise.resolve(null);
      if (!preparationId || !operation) return Promise.resolve(null);
      return executeAction("workbench.workflow-control", {
        preparation_id: preparationId,
        operation: operation
      }, { skipConfirm: true, quiet: true }).then(function (data) {
        loadPreparations();
        return data;
      });
    }

    /* Quiet, budget-bounded reader for catalog actions the Symbol Tree (slice 1)
       and the continuous Listing rows (slice 2) use. Same POST-then-poll idiom
       as executeAction/loadFunctionEvidence above, but: (1) refuses to run
       anything the catalog doesn't mark danger:false, mutating:false --
       belt-and-suspenders on top of these call sites only ever naming
       read-only ids; (2) never opens the Jobs dock or shows a toast --
       these fire on every tree expand / row scroll, which would otherwise
       spam both; (3) gives up at `timeoutMs` (default 5000ms, per the
       redesign spec's "too slow" escape hatch for listing rows) and reports
       how long it actually waited so the caller can fall back to text and
       say why. */
    async function runReadAction(actionId, params, options) {
      const opts = options || {};
      const readScope = targetKey;
      const readGeneration = intentGeneration.current;
      const readCurrent = function () { return selectionMounted.current && readScope === targetIdentity(targetRef.current)
        && readGeneration === intentGeneration.current
        && (!opts.selectionIntent || isCurrentIntent(opts.selectionIntent)) && !(opts.signal && opts.signal.aborted); };
      const ignored = { ok: false, ignored: true, error: "Selection target changed.", elapsedMs: 0 };
      if (!readCurrent()) return ignored;
      const readContext = liveToolContext();
      const t0 = (window.performance && performance.now) ? performance.now() : Date.now();
      const elapsed = function () { return ((window.performance && performance.now) ? performance.now() : Date.now()) - t0; };
      const timeoutMs = Number.isFinite(opts.timeoutMs) && opts.timeoutMs > 0 ? Math.max(1,Math.floor(Math.min(opts.timeoutMs,2147483647))) : 5000;
      const deadline = AbortSignal.timeout(timeoutMs);
      const readSignal = opts.signal ? AbortSignal.any([opts.signal, deadline]) : deadline;
      const act = actions.find(function (item) { return item.id === actionId; });
      if (!act) return { ok: false, error: "Unknown action " + actionId, elapsedMs: elapsed() };
      if (act.danger || act.mutating || act.long_running) {
        return { ok: false, error: actionId + " is not a confirmed read-only action; refusing to auto-run it.", elapsedMs: elapsed() };
      }
      const parameters = params || {};
      const loc = readContext.locator || "";
      const ctx = {
        slug: readContext.slug || "",
        program: readContext.program || "",
        repo: readContext.repo || "",
        addr: parameters.addr ?? readContext.addr ?? "",
        name: parameters.name ?? readContext.name ?? "",
        db: readContext.db || "",
        work_dir: readContext.work_dir || "",
        kb: readContext.kb || ""
      };
      const body = Object.assign({ confirm: true, context: ctx, locator: loc, program: readContext.program || "" }, parameters);
      let key, encoded;
      try {
        /* Key the effective request, not option spelling/order or the wait budget. */
        encoded = JSON.stringify(body,function(_key,value){return value&&typeof value==="object"&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(function(name){return [name,value[name]];})):value;});
        key = JSON.stringify([readScope,actionId,encoded]);
      } catch (err) { return {ok:false,error:"Read parameters cannot be serialized: "+String(err.message||err),elapsedMs:elapsed()}; }
      let entry = readActionJobs.current.get(key);
      const reused = Boolean(entry);
      if (!entry) {
        if (readActionJobs.current.size >= 128) return {ok:false,error:"128 read admissions are still pending or uncertain. Check existing jobs before admitting another read; none were discarded.",elapsedMs:elapsed()};
        entry = {jobId:null,job:null,admission:null,outcome:null};
        /* Reserve synchronously, before fetch or any await: double clicks share admission. */
        readActionJobs.current.set(key,entry);
        entry.admission = (async function () {
          try {
            /* A caller stops waiting, not a shared admission. Retain its response even
               after a tab/target change so a later exact request can recover the job ID. */
            const res = await fetch("/api/v1/actions/"+actionId.replace(/\./g,"/"), {
              method:"POST",headers:{"content-type":"application/json"},body:encoded
            });
            const data = await res.json();
            if (data&&data.job&&data.job.id) {
              entry.jobId=data.job.id;entry.job=data.job;
            } else if (!res.ok || !data || data.ok===false) {
              entry.outcome = {ok:false,error:data&&data.error||"Action admission failed",admissionUncertain:res.status>=500};
            } else entry.outcome={ok:true,data:data};
          } catch (err) {
            /* Losing the response does not prove the server failed to admit work. */
            entry.outcome={ok:false,admissionUncertain:true,error:"The read admission response was lost; no duplicate was submitted. "+String(err.message||err)};
          }
          if (entry.outcome&&!entry.outcome.admissionUncertain&&readActionJobs.current.get(key)===entry)readActionJobs.current.delete(key);
        })();
      }
      function interrupted() {
        const stopped=Boolean(opts.signal&&opts.signal.aborted);
        return {ok:false,ignored:!readCurrent(),aborted:stopped,timedOut:deadline.aborted||elapsed()>=timeoutMs,jobId:entry.jobId,
          admissionPending:!entry.jobId&&!entry.outcome,reused:reused,elapsedMs:elapsed(),
          error:stopped?"Stopped waiting; the read job was not cancelled.":!readCurrent()?"Selection target changed; its read job was retained.":"Timed out waiting for "+actionId+"; repeat this read to check the existing admission, not submit another job."};
      }
      const admitted=await new Promise(function(resolve){
        const stop=function(){readSignal.removeEventListener("abort",stop);resolve(false);};
        readSignal.addEventListener("abort",stop,{once:true});
        entry.admission.then(function(){readSignal.removeEventListener("abort",stop);resolve(true);});
        if(readSignal.aborted)stop();
      });
      if(!admitted||!readCurrent()||deadline.aborted)return interrupted();
      if(entry.outcome)return Object.assign({},entry.outcome,{elapsedMs:elapsed(),reused:reused,jobId:entry.jobId});
      const jobId = entry.jobId;
      let job = entry.job, firstCheck = true;
      while (job.status === "running" || job.status === "queued" || job.status === "admitted" || !job.status) {
        if (elapsed() >= timeoutMs || deadline.aborted || !readCurrent()) return interrupted();
        /* Reconnecting starts with GET immediately; later checks retain the bounded wait. */
        if(!firstCheck)await new Promise(function(resolve){
          const wake=function(){clearTimeout(timer);readSignal.removeEventListener("abort",wake);resolve();};
          const timer=setTimeout(wake,Math.max(0,Math.min(250,timeoutMs-elapsed())));
          readSignal.addEventListener("abort",wake,{once:true});if(readSignal.aborted)wake();
        });
        firstCheck=false;
        if (!readCurrent()||deadline.aborted) return interrupted();
        try {
          const jres = await fetch(API.jobs + "/" + encodeURIComponent(jobId), { cache: "no-store", signal: readSignal });
          if (!readCurrent()||deadline.aborted) return interrupted();
          const jdata = await jres.json();
          if (!readCurrent()||deadline.aborted) return interrupted();
          if(jres.ok&&jdata&&jdata.job&&jdata.job.id===jobId){job=jdata.job;entry.job=job;}
        } catch (err) {
          // Keep polling until the deadline; a transient fetch error isn't fatal.
        }
      }
      if (!readCurrent()||deadline.aborted) return interrupted();
      if(readActionJobs.current.get(key)===entry)readActionJobs.current.delete(key);
      if (job.status !== "ok") {
        const log = String(job.log || "");
        const stateMatch = /\*\*State:\*\* `([^`]+)`/.exec(log) || /"state":\s*"([^"]+)"/.exec(log) || /"cause":\s*"([^"]+)"/.exec(log);
        const cause = stateMatch ? stateMatch[1] : "";
        const friendly = cause === "authentication-failed"
          ? "The Ghidra server refused the login for this repository."
          : (job.error || cause || "Action failed");
        return { ok: false, error: friendly, cause: cause, elapsedMs: elapsed(), jobId:jobId,reused:reused };
      }
      const log = String(job.log || "");
      const nl = log.indexOf("\n");
      const jsonText = nl >= 0 ? log.slice(nl + 1) : log;
      let parsed = null;
      try {
        parsed = JSON.parse(jsonText);
      } catch (err) {
        return { ok: false, error: "Could not parse the response for " + actionId, elapsedMs: elapsed(),jobId:jobId,reused:reused };
      }
      return { ok: true, data: parsed, elapsedMs: elapsed(),jobId:jobId,reused:reused };
    }

    useEffect(function () {
      window.AgentDecompileUI = Object.assign(window.AgentDecompileUI || {}, {
        getToolContext: function () { return liveToolContext(); },
        getEnvDefaults: function () { return envDefaults; },
        getBinaries: function () { return toolContext.allBinaries || []; },
        getSiblings: function () { return isCurrentIntent(renderIntent) && admittedPacket ? ((admittedPacket.detail && admittedPacket.detail.siblings) || []).filter(function (peer) { return (toolContext.allBinaries || []).some(function (binary) { return binary.slug === peer.slug; }); }) : []; },
        runCatalogAction: function (actionId, params) {
          if (!actionId) return null;
          openActionStrip(actionId);
          const filled = catalogParamsFor(actionId, params && Object.keys(params).length ? params : {});
          return executeAction(actionId, filled, {});
        },
        showToast: showToast
      });
      window.KotorXidUI = window.AgentDecompileUI;
    }, [toolContext, envDefaults, binaries, detail]);

    function runFromActionStrip() {
      const act = pendingAction;
      if (!act) return;
      const params = readActionParams(actionFormRef.current, act, toolContext);
      executeAction(pendingActionId, params, { danger: act.danger, mutating: act.mutating });
    }

    function onPaletteAction(actionId) {
      setPaletteOpen(false);
      setPaletteQuery("");
      openActionStrip(actionId);
    }

    function onPaletteSurface(surfaceId) {
      setPaletteOpen(false);
      setPaletteQuery("");
      if (MORE_SURFACE_IDS.has(surfaceId)) setMoreOpen(true);
      jumpTo(surfaceId);
    }

    function onPaletteJob(jobId) {
      setPaletteOpen(false);
      setPaletteQuery("");
      selectJobInDock(jobId);
    }

    async function applyProjectInspect(inspected) {
      if (inspected && inspected.ok) {
        setDossier(inspected);
        setPreview(inspected);
      }
      return inspected;
    }

    function openAddToProjectDialog() {
      ++projectOperationSequence.current;
      ++openSequence.current;
      ++addDialogSequence.current;
      setAddBusy(false);
      setDialogError("");
      setAddPath("");
      setAddFileName("");
      setDialog("add-binary");
      setMenu("");
      showToast(currentLocator() ? "Add a binary into this project" : "Add creates a project, then imports into it");
    }

    async function submitAddToProject(ev) {
      if (ev) ev.preventDefault();
      if (addBusy) return null;
      const field = document.getElementById("wb-add-path");
      const path = ((addPath || "").trim() || (field && field.value) || "").trim();
      if (!path) {
        failDialog("Paste a binary path, or choose a file.");
        return null;
      }
      setAddBusy(true);
      const sequence = addDialogSequence.current;
      try {
        const data = await importPathIntoProject(path, path.split(/[/\\]/).pop() || "binary");
        if (sequence === addDialogSequence.current && data && data.ok) closeDialog();
        return data;
      } catch (error) {
        if (sequence === addDialogSequence.current) failDialog(String(error.message || error));
        return null;
      } finally {
        if (sequence === addDialogSequence.current) setAddBusy(false);
      }
    }

    async function importPathIntoProject(filePath, preferredName, sourceProgram, capturedOperation) {
      const operation = capturedOperation || beginProjectOperation();
      const operationCurrent = function () { return projectOperationCurrent(operation); };
      if (!operationCurrent()) return null;
      const path = (filePath || "").trim();
      if (!path) return null;
      const baseName = (preferredName || path.split(/[/\\]/).pop() || "binary").trim();
      let locator = currentLocator();
      if (!locator) {
        const opened = await createTabProject(baseName, operation);
        if (!operationCurrent()) return null;
        if (!opened || !opened.ok || (opened.intent && !isCurrentIntent(opened.intent))) {
          showToast("Open a project first, then add binaries into it.", "error");
          return null;
        }
        locator = (opened.inspected && opened.inspected.locator) || currentLocator();
      }
      if (!locator) {
        showToast("The project tab has no locator yet.", "error");
        return null;
      }
      if (!operationCurrent()) return null;
      showToast("Importing " + baseName + " into the project…");
      const res = await fetch(API.programs, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          locator: locator,
          path: path,
          program: sourceProgram || "",
          name: baseName,
          analyze: false
        })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!data.ok) {
        const message = data.error || "Could not import into the project.";
        setIngestNote(message);
        showToast(message, "error");
        return data;
      }
      if (data.inspect) await applyProjectInspect(data.inspect);
      else await loadPreview(locator);
      if (!operationCurrent()) return null;
      const prog = data.program || baseName;
      if (currentSession && currentSession.projectSlug) setSlug(currentSession.projectSlug);
      if (prog) {
        setProgram(prog);
        patchActiveSession({ program: prog });
        beginSelection(null);
        setEvidencePacket(null);
      }
      setIngestNote("Imported " + prog + " into the project");
      showToast("Imported " + prog + " into the project", "success");
      operation.generation = intentGeneration.current;
      loadCorpusStatus({ offset: 0 });
      return Object.assign({}, data, { selectionIntent: intentRef.current });
    }

    async function removeProgramFromProject(name) {
      if (focusLocator && canonicalLocator(focusLocator) !== currentLocator() && (!name || name === program)) { showToast("Choose a program in the active project before removing it.", "warning"); return; }
      const target = (name || program || "").trim();
      const locator = currentLocator();
      if (!target || !locator) {
        showToast("Select a program in this project first.", "error");
        return;
      }
      askConfirm({
        title: "Remove " + target + " from the project?",
        message: "This deletes the program from the open Ghidra project.",
        danger: true,
        confirmLabel: "Remove from project",
        onConfirm: function () { removeProgramConfirmed(locator, target); }
      });
    }

    async function removeProgramConfirmed(locator, target) {
      let operationGeneration = intentGeneration.current;
      const operationCurrent = function () { return selectionMounted.current && operationGeneration === intentGeneration.current; };
      const res = await fetch(API.programs, {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ locator: locator, program: target, confirm: true })
      });
      if (!operationCurrent()) return null;
      const data = await res.json();
      if (!operationCurrent()) return null;
      if (!data.ok) {
        showToast(data.error || "Could not remove that program.", "error");
        return;
      }
      if (data.inspect) await applyProjectInspect(data.inspect);
      else await loadPreview(locator);
      if (!operationCurrent()) return null;
      if (program === target) {
        const next = ((data.inspect && data.inspect.programs) || []).map(programName).filter(Boolean)[0] || "";
        setProgram(next);
        patchActiveSession({ program: next });
        beginSelection(null);
        setEvidencePacket(null);
        setRows([]);
        setTotal(0);
        if (next) ensureGhidraProgram(next, { quiet: true, locator: locator, intent: intentRef.current });
      }
      showToast("Removed " + target + " from the project", "success");
    }

    async function openBinaryPath(filePath, preferredName) {
      const path = (filePath || "").trim();
      if (!path) return;
      const baseName = (preferredName || path.split(/[/\\]/).pop() || "binary").trim();
      return openLocator(path, baseName);
    }

    async function selectImportBinary(row) {
      let operationGeneration = intentGeneration.current;
      const operationCurrent = function () { return selectionMounted.current && operationGeneration === intentGeneration.current; };
      if (!row || !row.slug) return;
      if (tabHasRealProject(currentSession) && !importsContain(currentSession, row.slug)) {
        await importIntoTab(row.slug);
        if (!operationCurrent()) return null;
      }
      setSlug(row.slug);
      setProgram("");
      patchActiveSession({ program: "" });
      beginSelection(null);
      setEvidencePacket(null);
    }

    async function uploadFiles(fileList) {
      if (dialog === "add-binary") closeDialog();
      const operation = beginProjectOperation();
      const operationCurrent = function () { return projectOperationCurrent(operation); };
      const files = Array.from(fileList || []);
      const rels = files.map(function (file) { return file.webkitRelativePath || file.name; });
      const gprs = files.filter(function (file) { return /\.gpr$/i.test(file.name); });
      const looksShared = rels.some(function (rel) {
        return rel === "users" || rel.indexOf("~index.dat") >= 0 || /(^|\/)users$/.test(rel);
      });
      const looksRep = rels.some(function (rel) { return /\.rep(\/|$)/i.test(rel); });
      if (gprs.length || looksShared || looksRep) {
        const repRel = rels.find(function (rel) { return /\.rep(\/|$)/i.test(rel); }) || "";
        const dropName = (gprs[0] && gprs[0].name) || (repRel ? repRel.split("/")[0] : files[0].name);
        const form = new FormData();
        files.forEach(function (file) {
          form.append("file", file, file.name);
        });
        form.append("paths", JSON.stringify(rels));
        const stageRes = await fetch(API.stageDrop, { method: "POST", body: form });
        if (!operationCurrent()) return null;
        const stageData = await stageRes.json();
        if (!operationCurrent()) return null;
        if (!stageRes.ok || stageData.ok === false || !stageData.staging_id) {
          setIngestNote(stageData.error || "Could not stage dropped files.");
          return;
        }
        const res = await fetch(API.resolveDrop, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            name: dropName,
            relativePaths: rels,
            staging_id: stageData.staging_id
          })
        });
        if (!operationCurrent()) return null;
        const data = await res.json();
        if (!operationCurrent()) return null;
        if (data.ok && data.locator) {
          await openLocator(data.locator, data.slug, { operation: operation });
          return;
        }
        if (data.candidates && data.candidates.length) {
          setIngestNote("Several matches. Pick one in the folder list.");
          return;
        }
        setIngestNote(data.error || "Could not resolve that drop to a project on disk.");
        return;
      }
      for (const file of files) {
        if (!operationCurrent()) return null;
        const body = new FormData();
        body.append("file", file, file.name);
        body.append("role", role || "member");
        const res = await fetch(API.binaries, { method: "POST", body: body });
        if (!operationCurrent()) return null;
        const data = await res.json();
        if (!operationCurrent()) return null;
        // source_path is the immutable staged upload. binary.repo can be a
        // reused virtual Ghidra row and binary.locator a project locator;
        // neither is a file the project import can read.
        const staged = data.source_path || "";
        if (!staged) {
          setIngestNote(data.error || "upload failed");
          showToast(data.error || "Could not stage " + file.name, "error");
          continue;
        }
        if (!data.ok) showToast("Staged " + file.name + ", but the corpus did not record it: " + (data.error || "unknown reason"), "error");
        const imported = await importPathIntoProject(staged, file.name, "", operation);
        if (!operationCurrent() || !imported || !imported.selectionIntent || !isCurrentIntent(imported.selectionIntent)) return;
      }
    }

    async function removeSlug(target) {
      if (!target) return;
      askConfirm({
        title: "Remove " + target + "?",
        message: "Remove this leftover corpus row. Prefer Remove on a program in the open project.",
        danger: true,
        confirmLabel: "Remove",
        onConfirm: function () { removeSlugConfirmed(target); }
      });
    }

    async function removeSlugConfirmed(target) {
      const generation = intentGeneration.current;
      const res = await fetch(API.binaries + "/" + encodeURIComponent(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ confirm: true })
      });
      const data = await res.json();
      if (generation !== intentGeneration.current || !selectionMounted.current) return null;
      reactJob("corpus.remove-binary", data);
      if (slug === target) {
        setSlug(currentSession && currentSession.projectSlug ? currentSession.projectSlug : "");
        beginSelection(null);
        setEvidencePacket(null);
      }

      if (currentSession && currentSession.projectSlug === target) {
        resetTabState();
        const cleared = sessions.map(function (item) {
          if (item.id !== activeSession) return item;
          return Object.assign({}, item, {
            kind: "draft",
            locator: "",
            projectSlug: "",
            imports: [],
            program: ""
          });
        });
        await persistSessions(cleared, activeSession);
      } else if (currentSession && importsContain(currentSession, target)) {
        const trimmed = sessions.map(function (item) {
          if (item.id !== activeSession) return item;
          return Object.assign({}, item, {
            imports: sessionImportSlugs(item).filter(function (slug) { return slug !== target; })
          });
        });
        await persistSessions(trimmed, activeSession);
      }
      await loadBinaries();
    }

    async function saveMeta(ev) {
      if (ev) ev.preventDefault();
      if (!slug) return;
      const res = await fetch(API.binaries + "/" + encodeURIComponent(slug), {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role: editRole, label: editLabel })
      });
      reactJob("corpus.edit-binary", await res.json());
      await loadBinaries();
    }

    async function runQuickAction(spec) {
      if (!spec) return;
      if (spec.ui === "upload") {
        triggerFileUpload();
        return;
      }
      if (spec.ui === "import") {
        openProjectDialog();
        return;
      }
      if (spec.ui === "new-project") {
        createProject();
        return;
      }
      if (!spec.id) return;
      openActionStrip(spec.id);
      const act = actions.find(function (item) { return item.id === spec.id; });
      const mutating = spec.mutating || (act && act.mutating);
      const danger = spec.danger || (act && act.danger);
      executeAction(
        spec.id,
        catalogParamsFor(spec.id, {}),
        { skipConfirm: !mutating && !danger, danger: danger, mutating: mutating }
      );
    }

    async function shutdownServer() {
      askConfirm({
        title: "Shut down server?",
        message: "Stop the AgentDecompile HTTP server on this port.",
        danger: true,
        confirmLabel: "Shutdown",
        onConfirm: async function () {
          showToast("Shutting down server…", "success");
          try {
            await fetch(API.serverShutdown, { method: "POST" });
          } catch (_err) { /* connection will drop */ }
        }
      });
    }

    async function restartServer() {
      askConfirm({
        title: "Restart server?",
        message: "Restart the AgentDecompile HTTP server. Open tabs reconnect when it is back.",
        confirmLabel: "Restart",
        onConfirm: async function () {
          showToast("Restarting server…", "success");
          try {
            await fetch(API.serverRestart, { method: "POST" });
          } catch (_err) { /* connection may drop while restarting */ }
          window.setTimeout(function () {
            window.location.reload();
          }, 2500);
        }
      });
    }

    function quickActionFlags() {
      return {
        needsFunction: !selected && checkedAddrs.length === 0,
        needsSlug: !slug,
        needsProject: !tabHasRealProject(currentSession)
      };
    }

    function quickBar(setName) {
      const items = QUICK_ACTION_SETS[setName] || [];
      return html`<${QuickActions}
        items=${items}
        catalog=${actions}
        onPress=${runQuickAction}
        flags=${quickActionFlags()} />`;
    }

    function onSearch(value) {
      setQuery(value);
      setFuncOffset(0);
    }

    /* Symbol Tree function leaves (and Listing xref jumps) select through the
       existing wb-fnbrowse path, never a second row list: switch to the
       Functions tab, narrow its own search so the row loads into view, then
       reuse selectRow -- the same click handler the table itself uses. */
    function selectFunctionLeaf(name, addr, scope) {
      if (scope && scope !== targetIdentity(targetRef.current)) return;
      jumpTo("wb-fnbrowse");
      onSearch(name || addr || "");
      selectRow({ name: name || "", addr: addr || "" });
    }

    function onIngestDragOver(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      ev.currentTarget.classList.add("on");
    }

    function onIngestDragLeave(ev) {
      ev.currentTarget.classList.remove("on");
    }

    function onDrop(ev) {
      ev.preventDefault();
      if (ev.currentTarget && ev.currentTarget.classList) ev.currentTarget.classList.remove("on");
      if (dropRef.current) dropRef.current.classList.remove("on");
      uploadFiles(ev.dataTransfer && ev.dataTransfer.files);
    }

    const projectLocator = canonicalLocator(currentSession && currentSession.locator);
    const projectNames = (dossier && dossier.ok ? (dossier.programs || []) : []).map(programName).filter(Boolean);
    const tabImports = sessionImportSlugs(currentSession);
    const activeProjectSlug = (currentSession && currentSession.projectSlug) || slug;
    const projectRow = dossier && dossier.ok ? binaries.find(function (row) {
      return row.slug === activeProjectSlug
        || row.locator === projectLocator
        || row.repo === projectLocator
        || row.slug === dossier.slug;
    }) : null;
    const importItems = [];
    tabImports.forEach(function (name) {
      if (!name) return;
      if (projectRow && name === projectRow.slug) return;
      const row = binaries.find(function (item) { return item.slug === name; }) || { slug: name, kind: "binary" };
      importItems.push({
        key: "import-" + name,
        name: row.slug || name,
        kind: kindLabel(row),
        row: row
      });
    });
    let projectCard = null;
    if (dossier && dossier.ok) {
      projectCard = {
        key: "project-" + (projectLocator || dossier.slug || "project"),
        name: (currentSession && currentSession.title) || dossier.slug || "Project",
        kind: styleKind(dossier.kind),
        row: projectRow,
        programs: projectNames,
        imports: importItems
      };
    } else if (currentSession && currentSession.projectSlug) {
      const row = binaries.find(function (item) { return item.slug === currentSession.projectSlug; });
      projectCard = {
        key: "project-" + currentSession.projectSlug,
        name: currentSession.title || currentSession.projectSlug,
        kind: styleKind(currentSession.kind || (row && row.kind) || "draft"),
        row: row,
        programs: projectNames,
        imports: importItems
      };
    }

    const graphUrl = selected
      ? "/dashboard/function/" + encodeURIComponent(slug) + "/" + encodeURIComponent(selected.addr)
      : "";
    const panelUrl = function (id) { return API.panel + "?id=" + id + "&embed=1"; };
    /* One block of the retired browse page, mounted as its own window. */
    const blockUrl = function (block) {
      let url = "/dashboard/browse-block?block=" + encodeURIComponent(block);
      if (slug) url += "&binary=" + encodeURIComponent(slug);
      ["lq", "logical_q", "logical_after", "q", "addr", "logical_id"].forEach(function (key) {
        const val = start.get(key);
        if (val) url += "&" + encodeURIComponent(key) + "=" + encodeURIComponent(val);
      });
      return url;
    };

    function openLogicalId(logicalId) {
      if (!logicalId) return;
      jumpToCorpus("wb-logical");
      showToast("Logical #" + logicalId + " — see Logical identities");
    }

    const pendingCatalogAction = pendingActionId
      ? actions.find(function (item) { return item.id === pendingActionId; })
      : null;
    const pendingAction = pendingCatalogAction ? Object.assign({}, pendingCatalogAction, { fields: (pendingCatalogAction.fields || []).map(function (field) {
      return Object.prototype.hasOwnProperty.call(pendingActionParams, field.name) ? Object.assign({}, field, { default: pendingActionParams[field.name] }) : field;
    }) }) : null;

    /* Refresh controls are explicit to the data they refresh; avoid a generic
       button that reloads unrelated hidden HTML panels. */
    function panelActions(extras) {
      return extras ? html`<div className="wb-surface-actions">${extras}</div>` : null;
    }

    function runActionButton(actionId, label) {
      const known = actions.some(function (item) { return item.id === actionId; });
      if (!known) return null;
      return html`<button type="button" className="wb-btn wb-btn-mini"
        onClick=${function () { openActionStrip(actionId); }}>${label}</button>`;
    }

    function runActionButtonRun(actionId, label, options) {
      const known = actions.some(function (item) { return item.id === actionId; });
      if (!known) return null;
      return html`<button type="button" className="wb-btn wb-btn-mini"
        onClick=${function () {
          executeAction(actionId, catalogParamsFor(actionId, options), { skipConfirm: true });
        }}>${label}</button>`;
    }

    const projectUniverse = corpusStatus && corpusStatus.scope === "projects" ? corpusStatus : null;
    const allOpenProjects = projectUniverse && projectUniverse.projects || [];
    const openProjects = acrossProjects ? allOpenProjects : allOpenProjects.filter(function (project) { return project.id === activeSession; });
    const projectOwners = new Set(openProjects.map(function (project) { return project.id; }));
    const projectBuilds = (projectUniverse && projectUniverse.builds || []).filter(function (build) { return (build.projectIds || []).some(function (owner) { return projectOwners.has(owner); }); });
    const cohortBuilds = cohortIds === null ? projectBuilds : projectBuilds.filter(function (build) { return cohortIds.includes(build.id); });
    const cohortBinaryIds = Array.from(new Set(cohortBuilds.flatMap(function (build) { return build.binaryIds || []; }))).sort(function (a,b) { return a-b; });
    const functionBrowseBuilds = projectBuilds;
    const functionBrowseSelection = functionBrowseIds === null ? functionBrowseBuilds.map(function (build) { return build.id; }) : functionBrowseIds;
    const functionBinaryIds = Array.from(new Set(functionBrowseBuilds.filter(function (build) { return functionBrowseSelection.includes(build.id); }).flatMap(function (build) { return build.binaryIds || []; }))).sort(function (a,b) { return a-b; });
    const functionScope = JSON.stringify([activeSession, acrossProjects, projectUniverse && projectUniverse.corpusIdentity, corpusRevision, functionBinaryIds, functionRequest, functionRefresh]);
    const functionOwner = useRef(activeSession);
    useEffect(function () {
      if (functionOwner.current === activeSession) return;
      functionOwner.current = activeSession;
      setCohortIds(null); setFunctionBrowseIds(null); setAcrossProjects(false); setFunctionBuildFilter(""); setProjectQuery(""); setReviewAnchor(null);
      setFunctionRequest(function (old) { return Object.assign({}, old, { q: "", offset: 0 }); });
    }, [activeSession]);
    const emptyFunctions = { results: [], total: null, offset: functionRequest.offset, limit: functionRequest.limit, hasMore: false };
    const projectFunctions = functionPacket && functionPacket.key === functionScope ? functionPacket.functions : emptyFunctions;
    useEffect(function () {
      const sequence = ++functionSequence.current;
      const controller = new AbortController();
      setFunctionError("");
      if (!projectUniverse || !projectUniverse.corpusIdentity || !functionBinaryIds.length) { setFunctionBusy(false); return; }
      setFunctionBusy(true);
      const timer = setTimeout(async function () {
        try {
          const request = new URLSearchParams({ binary_ids: functionBinaryIds.join(","), corpus_identity: projectUniverse.corpusIdentity,
            q: functionRequest.q, offset: String(functionRequest.offset), limit: String(functionRequest.limit) });
          const response = await fetch("/api/v1/projects/functions?" + request, {cache:"no-store",signal:AbortSignal.any([controller.signal,AbortSignal.timeout(12000)])});
          const result = await response.json();
          if (!response.ok || !result.ok || result.corpusIdentity !== projectUniverse.corpusIdentity || JSON.stringify(result.binaryIds) !== JSON.stringify(functionBinaryIds) || !result.functions || result.functions.query !== functionRequest.q.trim() || result.functions.offset !== functionRequest.offset || result.functions.limit !== functionRequest.limit) throw new Error(result.error || "The selected project evidence changed. Refresh project facts.");
          if (sequence === functionSequence.current) setFunctionPacket({key:functionScope,functions:result.functions});
        } catch (error) { if (!controller.signal.aborted && sequence === functionSequence.current) setFunctionError(String(error.message || error)); }
        finally { if (sequence === functionSequence.current && !controller.signal.aborted) setFunctionBusy(false); }
      }, 200);
      return function () { controller.abort(); clearTimeout(timer); };
    }, [functionScope]);
    function loadFunctionPage(update) {
      setFunctionRequest(function (previous) { return Object.assign({}, previous, update); });
    }
    const availabilityScope = JSON.stringify(openProjects.map(function (project) { return [project.id, project.locator]; }));
    availabilityScopeRef.current = availabilityScope;
    projectPipelineSnapshot.current = { projects: openProjects, runs: preparationRuns, feed: preparationFeed, availability: projectAvailability };
    useEffect(function () {
      if (editorTabFor(centerTab) === "wb-pipeline") loadProjectAvailability();
      return function () { ++availabilitySequence.current; };
    }, [centerTab, availabilityScope]);

    async function loadProjectAvailability() {
      const request = ++availabilitySequence.current;
      const scope = availabilityScopeRef.current;
      const projects = (projectPipelineSnapshot.current && projectPipelineSnapshot.current.projects || []).slice();
      const pending = {};
      projects.forEach(function (project) { pending[project.id] = { locator: project.locator, state: "unknown", reason: "Reading project inventory…" }; });
      setProjectAvailability(pending);
      const observed = {};
      let index = 0;
      async function worker() {
        while (index < projects.length && request === availabilitySequence.current && scope === availabilityScopeRef.current) {
          const project = projects[index++];
          const entry = { locator: project.locator, state: "unavailable", reason: "This retained record has no project locator." };
          if (project.locator) {
            try {
              const response = await fetch(API.inspect + "?locator=" + encodeURIComponent(project.locator), { cache: "no-store", signal: AbortSignal.timeout(15000) });
              const data = await response.json();
              if (!response.ok || !data.ok) entry.reason = data.error || "Project inventory is unavailable.";
              else if (!["ghidra-project", "shared-project", "shared-fs", "project-collection"].includes(data.kind)) entry.reason = "The locator does not identify an openable project.";
              else if (data.reachable === false && !data.mirror_available) entry.reason = "The project is unreachable and no readable mirror was reported.";
              else if (!(data.programs || []).length) entry.reason = "No program inventory was reported. Add or resolve project members before starting.";
              else { entry.state = "available"; entry.reason = "Project inventory is readable; native execution and recovery eligibility are checked by the pipeline."; }
            } catch (error) { entry.reason = "Project inventory read failed: " + String(error.message || error); }
          }
          entry.observedAt = Date.now();
          observed[project.id] = entry;
        }
      }
      await Promise.all([worker(), worker(), worker(), worker()]);
      if (request === availabilitySequence.current && scope === availabilityScopeRef.current && selectionMounted.current) setProjectAvailability(observed);
    }

    function projectPipelineState(project, now) {
      const snapshot = projectPipelineSnapshot.current || {};
      const currentProject = (snapshot.projects || []).find(function (item) { return item.id === project.id && item.locator === project.locator; });
      const locator = canonicalLocator(project.locator);
      const allRuns = (snapshot.runs || []).filter(function (run) { return locator && canonicalLocator(run.locator) === locator && !run.supersededBy; });
      const projectRuns = allRuns.filter(function (run) { return run.scope === "project" && !String(run.program || "").trim(); });
      const otherRuns = allRuns.filter(function (run) { return !projectRuns.includes(run); });
      const run = projectRuns.length === 1 ? projectRuns[0] : null;
      const state = { run: run, projectRuns: projectRuns, otherRuns: otherRuns, operation: "", reason: "", label: "Start project" };
      if (run && PREPARATION_PAUSABLE[run.status]) { state.operation = "pause"; state.label = "Pause project"; }
      else if (run && run.status === "paused") { state.operation = "resume"; state.label = "Resume project"; }
      else if (!run || run.status === "completed") state.operation = "start";
      const feed = snapshot.feed || {};
      const available = (snapshot.availability || {})[project.id];
      if (!currentProject || !locator) state.reason = "Open a project with a locator before controlling its pipeline.";
      else if (!feed.receivedAt || feed.error || now - feed.receivedAt > 10000) state.reason = "Pipeline status is unavailable or older than ten seconds. Refresh status before controlling it.";
      else if (projectRuns.length > 1) state.reason = "Multiple project-scoped runs are recorded. No authoritative project run is identified; no run was chosen automatically.";
      else if (otherRuns.some(function (item) { return item.scope !== "binary" || !String(item.program || "").trim(); })) state.reason = "A recorded run has unknown or inconsistent scope. Project control is unavailable until its ownership is resolved.";
      else if (otherRuns.some(function (item) { return ["queued", "running", "waiting", "paused", "cancelling", "disconnected", "resync"].includes(item.status); })) state.reason = "A program-scoped or unknown-scope run is active for this locator. Project-wide control is unavailable until its ownership is resolved.";
      else if (run && ["blocked", "failed", "cancelled", "interrupted", "partial", "cancelling", "disconnected", "resync"].includes(run.status)) state.reason = "Recorded project run is " + run.status + ": " + (run.error || "Resolve its recorded prerequisites before starting another run.");
      else if (!state.operation) state.reason = "The recorded run state does not authorize a project control.";
      else if (state.operation === "resume" && !Object.prototype.hasOwnProperty.call(run, "deadline")) state.reason = "The paused run's execution deadline is unknown; refresh or resolve its recorded state.";
      else if (state.operation === "resume" && run.deadline != null && (!Number.isFinite(run.deadline) || run.deadline * 1000 <= now)) state.reason = "The paused run's execution deadline has expired or is invalid; resume is unavailable.";
      else if (state.operation === "resume" && Object.values(run.retryDecisions || {}).some(function (decision) { return decision && decision.nextAction && decision.nextAction !== "dispatch"; })) state.reason = "The paused run has an unresolved recorded retry prerequisite. Review its observation details before resuming.";
      else if (state.operation !== "pause" && (!available || available.locator !== project.locator || available.state !== "available" || now - available.observedAt > 60000)) state.reason = available && available.locator === project.locator && available.state !== "available" ? available.reason : "Project inventory availability is unknown or stale. Refresh status before starting or resuming.";
      return state;
    }
    const memberSlugs = new Set(projectBuilds.map(function (build) { return build.slug; }).filter(Boolean));
    const scopedBinaries = binaries.filter(function (binary) { return memberSlugs.has(binary.slug); });
    function projectTitles(ids) {
      return openProjects.filter(function (project) { return (ids || []).includes(project.id); }).map(function (project) { return project.title; }).join(", ");
    }
    function focusProjectFunction(row, keepReference) {
      const memberships = projectBuilds.filter(function (build) { return row.binaryId != null ? (build.binaryIds || []).includes(Number(row.binaryId)) : build.slug === row.slug; });
      const choices = memberships.filter(function (build) { return build.bindingState !== "ambiguous" && build.repositoryBindingState !== "unresolved" && build.locator && build.program; });
      const ownedChoices = choices.filter(function (build) { return (build.projectIds || []).includes(activeSession); });
      const exact = row.buildId ? choices.find(function (build) { return build.id === row.buildId; }) : ownedChoices.length === 1 ? ownedChoices[0] : choices.length === 1 ? choices[0] : null;
      if (!exact) { showToast("This function has no unambiguous project/program binding. Review its recorded membership before opening native evidence.", "warning"); return; }
      if (!keepReference) setReviewAnchor(null);
      setFocusLocator(exact.locator);
      changeTarget({ locator: canonicalLocator(exact.locator) });
      setSlug(row.slug);
      setProgram(exact.program);
      const intent = beginSelection(Object.assign({}, row, { logicalId: row.logicalId == null ? row.logical_id : row.logicalId }));
      readSelection(intent);
    }
    function inspectMatchEndpoint(info) {
      const match = info.row.match;
      setReviewAnchor({ binaryId: match.src_binary, addr: match.src_addr });
      const functionRecord = info.row.functions && info.row.functions[info.side] || {};
      focusProjectFunction({ binaryId: info.binaryId, slug: info.slug,
        addr: "0x" + Number(info.addr).toString(16), name: info.name || functionRecord.name || "0x" + Number(info.addr).toString(16) }, true);
      scrollToSurface("wb-comparison-evidence");
    }
    function projectScopeNotice() {
      return html`<div className="wb-project-scope"><strong>${acrossProjects ? "Across open projects" : currentSession && currentSession.title || "Current project"}</strong>
        <label className="wb-project-scope-choice"><input type="checkbox" checked=${acrossProjects} onChange=${function (event) { setAcrossProjects(event.target.checked); setCohortIds(null); setFunctionBrowseIds(null); setReviewAnchor(null); loadFunctionPage({ offset: 0 }); }}/>Compare across open projects</label>
        <span>${projectUniverse
          ? "Recorded project snapshot" + (projectUniverse.staleError ? " · stale" : "")
          : "Project-wide inventory and function aggregation is loaded only when requested."}</span>
        ${projectBusy ? html`<span>Reading recorded facts…</span>` : null}
        <button type="button" className="wb-btn wb-btn-mini" disabled=${projectBusy} onClick=${function () { loadBinaries().catch(function (error) { showToast("Build relationships could not refresh: " + String(error.message || error)); }); loadCorpusStatus(); }}>${projectUniverse ? "Refresh project facts" : "Load project facts"}</button>
      </div>`;
    }
    function projectErrors() {
      return html`<div>${(corpusStatus && corpusStatus.errors || []).map(function (error, index) { return html`<p key=${index} className="wb-hint" role="status">${error}</p>`; })}${corpusStatus && (corpusStatus.error || corpusStatus.staleError) ? html`<p role="alert">${corpusStatus.error || corpusStatus.staleError}</p>` : null}</div>`;
    }
    function memberTable() {
      return html`<div className="wb-project-table-scroll"><table className="wb-fnb-table"><thead><tr><th>Project</th><th>Build / program</th><th>Functions</th><th>Named</th><th>Recorded identities</th><th>Binding</th></tr></thead><tbody>
        ${projectBuilds.map(function (build) { return html`<tr key=${build.id}><td>${projectTitles(build.projectIds)}</td><td><strong>${build.slug || build.name}</strong><br/><code>${build.program}</code></td><td>${build.funcs == null ? "Unknown" : build.funcs.toLocaleString()}</td><td>${build.named == null ? "Unknown" : build.named.toLocaleString()}</td><td>${build.bound == null ? "Unknown" : build.bound.toLocaleString()}</td><td>${build.repositoryBindingState === "unresolved" ? "Unresolved repository" : build.bindingState}<br/><small>${build.bindingReason || build.inventoryState || ""}</small></td></tr>`; })}
      </tbody></table></div>`;
    }
    function projectFunctionFilter() {
      return html`<form className="wb-project-filter" onSubmit=${function (ev) { ev.preventDefault(); loadFunctionPage({ q: projectQuery, offset: 0 }); setFunctionRefresh(function (n) { return n+1; }); scrollToSurface("wb-function-results-heading"); }}>
        <label>Find a function <input id="wb-q" type="search" value=${projectQuery} onInput=${function (ev) { const value = ev.target.value; setProjectQuery(value); loadFunctionPage({q:value,offset:0}); }} placeholder="Name or address across selected binaries" /></label>
        <button type="submit" className="wb-btn">Find</button>
        <button type="button" className="wb-btn" disabled=${!projectQuery} onClick=${function () { setProjectQuery(""); loadFunctionPage({ q: "", offset: 0 }); }}>Clear filter</button>
        ${functionBusy ? html`<span role="status">Searching stored functions in the selected binaries…</span>` : null}
        ${functionError ? html`<p role="alert">${functionError}</p>` : null}
      </form>`;
    }
    function projectPager() {
      return html`<div className="wb-project-pager"><span>${projectFunctions.results.length ? projectFunctions.offset + 1 : 0}–${projectFunctions.offset + projectFunctions.results.length}${projectFunctions.total == null ? " recorded functions in this page" : " of " + projectFunctions.total + " recorded functions"}</span>
        <button type="button" className="wb-btn" disabled=${functionBusy || !functionRequest.offset} onClick=${function () { loadFunctionPage({ offset: Math.max(0, functionRequest.offset - functionRequest.limit) }); }}>Previous</button>
        <button type="button" className="wb-btn" disabled=${functionBusy || !projectFunctions.hasMore} onClick=${function () { loadFunctionPage({ offset: functionRequest.offset + functionRequest.limit }); }}>Next</button>
        <label>Page size <select value=${functionRequest.limit} onChange=${function (ev) { loadFunctionPage({ limit: Number(ev.target.value), offset: 0 }); }}>${[50, 100, 250, 500].map(function (n) { return html`<option key=${n} value=${n}>${n}</option>`; })}</select></label>
      </div>`;
    }
    function focusedComparison() {
      const scopedDetail = Object.assign({}, detail || {}, { siblings: (detail && detail.siblings || []).filter(function (peer) { return memberSlugs.has(peer.slug); }) });
      const comparisonBinaries = scopedBinaries.map(function (binary) {
        const group = binary.variant_group || binary.variantGroup;
        if (!group) return binary;
        const scopedGroup = Object.assign({}, group, { evidence: (group.evidence || []).filter(function (receipt) { return memberSlugs.has(receipt.source) && memberSlugs.has(receipt.target); }) });
        return Object.assign({}, binary, { variant_group: scopedGroup, variantGroup: scopedGroup });
      });
      return html`<${LogicalCounterparts} slug=${slug} selected=${selected} detail=${scopedDetail} binaries=${comparisonBinaries} onPick=${focusProjectFunction}/>
        <p className="wb-hint">${selected ? "Focus: " + slug + " · " + selected.addr + ". Project ownership and the all-project scope remain unchanged." : "Choose a function in Functions to compare code and calls across its recorded peers."}</p>`;
    }
    async function projectPipelineControl(project, run) {
      if (projectControlBusy.current.has(project.id)) return;
      const state = projectPipelineState(project, Date.now());
      if (state.reason || (state.run && state.run.id || "") !== (run && run.id || "")) {
        setProjectControls(function (old) { return Object.assign({}, old, { [project.id]: state.reason || "Project run selection changed. Refresh and review its scope before controlling it." }); });
        return;
      }
      projectControlBusy.current.add(project.id);
      setProjectControls(function (old) { return Object.assign({}, old, { [project.id]: "Submitting…" }); });
      try {
        let data;
        if (state.operation === "pause" || state.operation === "resume") {
          data = await controlPreparation(state.run.id, state.operation);
        } else {
          const response = await fetch("/dashboard/api/workbench/prepare", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ locator: project.locator, program: "", slug: "", resume: false }) });
          data = await response.json();
          if (!response.ok) throw new Error(data.error || "Pipeline request failed");
        }
        if (!data || data.ok === false || data.error) throw new Error(data && data.error || "Pipeline request failed");
        setProjectControls(function (old) { return Object.assign({}, old, { [project.id]: "Request recorded. Refresh status for progress." }); });
        await loadPreparations();
        loadCorpusStatus();
      } catch (error) { setProjectControls(function (old) { return Object.assign({}, old, { [project.id]: String(error.message || error) }); }); }
      finally { projectControlBusy.current.delete(project.id); }
    }
    function evidenceMark(state) {
      const shapes = { accepted: html`<path d="M5 12l5 5 9-11" />`, candidate: html`<path d="M12 3l10 18H2z" />`, divergent: html`<path d="M5 5l14 14M19 5L5 19" />`, selected: html`<circle cx="12" cy="12" r="8" />`, unknown: html`<circle cx="12" cy="12" r="8" strokeDasharray="3 3" />` };
      return html`<svg className=${"wb-evidence-mark is-" + state} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7">${shapes[state] || shapes.unknown}</svg>`;
    }
    function peersForBuild(build) {
      if (!selected) return [];
      const records = (detail && detail.siblings || []).filter(function (peer) { return peer.slug === build.slug && peer.addr && memberSlugs.has(peer.slug); });
      if (build.slug === slug) records.unshift(Object.assign({}, selected, { slug: slug, selected: true }));
      const identities = new Map();
      records.forEach(function (peer) {
        const key = JSON.stringify([peer.binaryId ?? peer.binary_id ?? null, peer.slug, peer.addr, peer.logicalId ?? peer.logical_id ?? null]);
        if (!identities.has(key)) identities.set(key, []);
        identities.get(key).push(peer);
      });
      return Array.from(identities.values());
    }
    function counterpartCard(records, build) {
      const peer = records[0];
      const cardKey = JSON.stringify([slug, selected && selected.addr, build.id, peer.binaryId ?? peer.binary_id ?? null, peer.slug, peer.addr, peer.logicalId ?? peer.logical_id ?? null]);
      const receiptLimit = receiptLimits[cardKey] || 3;
      return html`<div className="wb-counterpart-card" key=${cardKey}><button type="button" className="wb-counterpart-open" onClick=${function () { focusProjectFunction(Object.assign({}, peer, { buildId: build.id })); }}>
        <strong>${peer.name || "Unnamed counterpart"}</strong><code>${peer.addr}</code><span>Read recorded function</span>
      </button>${records.slice(0, receiptLimit).map(function (record, index) {
        const state = peerState(record);
        return html`<div className=${"wb-peer-receipt is-" + state} key=${index}>${evidenceMark(state)}<span>${record.selected ? "Selected function" : "Recorded counterpart · " + state}</span>
          <${IdentityReceiptDetails} record=${record} label=${"Identity receipt" + (records.length > 1 ? " " + (index + 1) : "")} /></div>`;
      })}${records.length > receiptLimit ? html`<button type="button" className="wb-btn wb-peer-expansion" onClick=${function () { setReceiptLimits(function (old) { return Object.assign({}, old, { [cardKey]: receiptLimit + 12 }); }); }}>Show ${Math.min(12, records.length - receiptLimit)} more identity receipts (${receiptLimit} of ${records.length} shown)</button>` : null}</div>`;
    }
    function counterpartRow(build, project) {
      const peers = peersForBuild(build);
      const states = Array.from(new Set(peers.reduce(function (all, records) { return all.concat(records.map(peerState)); }, [])));
      const name = memberPath(build).name;
      const relationLabel = peers.length ? peers.length + " recorded address" + (peers.length === 1 ? "" : "es") : "No recorded counterpart";
      return html`<tr className=${peers.length ? "wb-counterpart-row has-peer" : "wb-counterpart-row is-unknown"} key=${project.id + ":" + build.id}>
        <td className="wb-counterpart-project">${project.title}</td>
        <th scope="row"><button type="button" className="wb-counterpart-binary" aria-pressed=${inspectedMember === build.id} onClick=${function () { setInspectedMember(inspectedMember === build.id ? "" : build.id); }}><strong>${name}</strong><small>${build.slug || "Build identity not bound"}</small></button></th>
        <td><div className="wb-matrix-peers">${peers.length ? peers.map(function (records) { return counterpartCard(records, build); }) : html`<span className="wb-matrix-unknown">${evidenceMark("unknown")}<span><strong>${relationLabel}</strong><small>Not recorded here; absence is not established.</small></span></span>`}</div></td>
        <td className="wb-counterpart-state">${states.length ? states.map(function (state) { return html`<span className=${"wb-peer-state is-" + state} key=${state}>${evidenceMark(state)}${state === "unknown" ? "Recorded; state unknown" : state === "selected" ? "Selected" : state}</span>`; }) : html`<span className="wb-peer-state is-unknown">${evidenceMark("unknown")}Unknown</span>`}</td>
      </tr>`;
    }
    function peerState(peer) {
      if (!peer) return "unknown";
      if (peer.selected) return "selected";
      const state = String(peer.status || peer.decision || "").toLowerCase();
      if (["accepted", "candidate", "divergent"].includes(state)) return state;
      return "unknown";
    }
    function memberLimitControl() {
      return projectBuilds.length > memberLimit ? html`<button type="button" className="wb-btn" onClick=${function () { setMemberLimit(function (n) { return n + 48; }); }}>Show ${Math.min(48, projectBuilds.length - memberLimit)} more members (${memberLimit} of ${projectBuilds.length} drawn)</button>` : null;
    }
    function memberPath(build) {
      const path = String(build.program || "").replace(/\\/g, "/");
      const slash = path.lastIndexOf("/");
      return { name: path.slice(slash + 1) || build.name || build.slug || "Unnamed member", directory: path ? path.slice(0, slash + 1) || "/" : "Path not recorded" };
    }
    function binaryInventoryCard(build) {
      const path = memberPath(build);
      const binding = build.repositoryBindingState === "unresolved" ? "Unresolved repository" : build.bindingState || "Binding unknown";
      const total = Number.isFinite(build.funcs) && build.funcs >= 0 ? build.funcs : null;
      const named = Number.isFinite(build.named) && build.named >= 0 ? Math.min(build.named, total == null ? build.named : total) : null;
      const namedWidth = total > 0 && named != null ? Math.round(named * 100 / total) : 0;
      return html`<button type="button" className=${"wb-binary-inventory" + (/unresolved|ambiguous|unbound/.test(binding) ? " has-binding-warning" : "") + (inspectedMember === build.id ? " is-inspected" : "")} key=${build.id} aria-pressed=${inspectedMember === build.id} aria-label=${path.name + " · " + (total == null ? "function inventory unavailable" : total.toLocaleString() + " functions") + " · " + binding} onClick=${function () { setInspectedMember(inspectedMember === build.id ? "" : build.id); }}>
        <span className="wb-binary-inventory-head"><svg viewBox="0 0 18 18" aria-hidden="true" className="wb-member-glyph"><rect x="2" y="2" width="13" height="13" rx="1" /><path d="M5 6h7M5 9h7M5 12h4" /></svg><strong>${path.name}</strong></span>
        ${total == null ? html`<span className="wb-binary-inventory-unknown">Function inventory not recorded</span>` : named == null ? html`<span className="wb-inventory-track is-unknown" role="img" aria-label="Function count recorded; naming breakdown unknown"></span>` : html`<span className="wb-inventory-track" role="img" aria-label=${named.toLocaleString() + " named and " + Math.max(0, total - named).toLocaleString() + " unnamed or generated functions"}><span className="is-named" style=${{ width: namedWidth + "%" }}></span><span className="is-generated" style=${{ width: Math.max(0, 100 - namedWidth) + "%" }}></span></span>`}
        <span className="wb-inventory-counts">${total == null ? "Function count unknown" : total.toLocaleString() + " functions"}<span>${named == null ? "Named count unknown" : named.toLocaleString() + " named"}</span><span>${Number.isFinite(build.bound) ? build.bound.toLocaleString() + " identity records" : "Identity count unknown"}</span></span>
        <span className=${"wb-inventory-binding" + (/unresolved|ambiguous|unbound/.test(binding) ? " is-warning" : "")}>${binding}</span>
      </button>`;
    }
    function projectMap() {
      const logical = selected && (selected.logicalId || selected.logical_id) || detail && detail.function && (detail.function.logicalId || detail.function.logical_id);
      const inspected = projectBuilds.find(function (build) { return build.id === inspectedMember; });
      return html`<section className="wb-build-map wb-membership-map" aria-label="Project membership and recorded function counterparts">
        <header className="wb-map-heading"><div><span className="wb-map-kicker">Open project map</span><h3 id="wb-map-heading" tabIndex="-1">${selected ? selected.name || selected.addr : "Binaries by project"}</h3></div>
          ${selected ? html`<div className="wb-alignment-anchor"><code>${logical == null ? "Identity not recorded" : "Logical identity #" + logical}</code><span>Correspondence is not byte equivalence.</span></div>` : html`<p>Select any combination of project builds; functions and correspondence follow that selection.</p>`}</header>
        ${window.AgentDecompileFamilyMap ? html`<${window.AgentDecompileFamilyMap} builds=${projectBuilds} binaries=${binaries} relationships=${projectUniverse && projectUniverse.relationships}
          selectedIds=${cohortIds === null ? projectBuilds.map(function (build) { return build.id; }) : cohortIds}
          onSelection=${function (ids) { setCohortIds(ids); setReviewAnchor(null); loadFunctionPage({offset:0}); }}
          onFocus=${function (build) { setInspectedMember(build.id); }}/>` : null}
        ${inspected ? html`<aside className="wb-member-inspection" aria-label="Selected member details"><header><strong>${memberPath(inspected).name}</strong><button type="button" className="wb-text-action" onClick=${function () { setInspectedMember(""); }}>Close details</button></header><code>${inspected.program || inspected.slug}</code><span>${inspected.slug} · ${inspected.repositoryBindingState === "unresolved" ? "Unresolved repository" : inspected.bindingState || "Binding unknown"}</span><p>${inspected.bindingReason || inspected.inventoryState || "No binding explanation supplied."}</p>
        </aside>` : null}
        <div className="wb-map-foot"><details><summary>Inspect project membership and inventory records</summary>${memberTable()}</details></div>
      </section>`;
    }
    function comparisonWorkspace() {
      const selectedIds = cohortBinaryIds;
      const focusedBuilds = projectBuilds.filter(function (build) { return build.slug === slug; });
      const focusedIds = Array.from(new Set(focusedBuilds.flatMap(function (build) { return build.binaryIds || []; })));
      const focus = reviewAnchor && selectedIds.includes(reviewAnchor.binaryId) ? reviewAnchor :
        selected && focusedIds.length === 1 && selectedIds.includes(focusedIds[0]) ? { binaryId: focusedIds[0], addr: Number(selected.addr) } : null;
      function followCall(node) { setReviewAnchor(null); const hit = rows.find(function (row) { return row.addr === node.addr; }); selectRow(hit || node); }
      const functionsPanel = html`<div className="wb-function-results">
          <fieldset className="wb-functions-cohort"><legend>Browse binaries</legend>
            <p className="wb-functions-cohort-context">${acrossProjects ? "Across open projects" : "Current project tab"} · ${functionBrowseSelection.length} selected project members</p>
            <label className="wb-functions-cohort-filter"><span>Find a binary</span><input type="search" value=${functionBuildFilter} placeholder="Name or program path" onInput=${function (event) { setFunctionBuildFilter(event.target.value); }}/></label>
            <div className="wb-functions-cohort-actions"><button type="button" className="wb-btn wb-btn-mini" onClick=${function () { setFunctionBrowseIds(null); setReviewAnchor(null); loadFunctionPage({offset:0}); }}>Select all</button><button type="button" className="wb-btn wb-btn-mini" disabled=${!functionBrowseSelection.length} onClick=${function () { setFunctionBrowseIds([]); setReviewAnchor(null); loadFunctionPage({offset:0}); }}>Clear</button></div>
            <div className="wb-functions-cohort-options" aria-label="Binary browsing selection">${openProjects.map(function (project) {
              const members = functionBrowseBuilds.filter(function (build) { return (build.projectIds || []).includes(project.id) && (!functionBuildFilter.trim() || [build.name,build.slug,build.program].join(" ").toLowerCase().includes(functionBuildFilter.trim().toLowerCase())); });
              if (!members.length) return null;
              return html`<fieldset className="wb-functions-cohort-project" key=${project.id}><legend>${project.title || project.locator || "Project"}</legend>${members.map(function (build) {
                const checked = functionBrowseSelection.includes(build.id);
                return html`<div className=${"wb-functions-cohort-member" + (checked ? " is-selected" : "")} key=${build.id}><label><input type="checkbox" checked=${checked} onChange=${function (event) {
                  const next = event.target.checked ? Array.from(new Set(functionBrowseSelection.concat(build.id))) : functionBrowseSelection.filter(function (id) { return id !== build.id; });
                  setFunctionBrowseIds(next); setReviewAnchor(null); loadFunctionPage({offset:0});
                }}/><span><strong>${build.name || build.slug || "Unnamed binary"}</strong><small title=${build.program || build.slug}>${build.program || build.slug || "Program path not recorded"}</small>${!(build.binaryIds || []).length ? html`<small className="wb-functions-cohort-unbound">No recorded function binding</small>` : null}</span></label><button type="button" className="wb-text-action" title=${"Browse only " + (build.name || build.slug || "this binary")} aria-label=${"Browse only " + (build.name || build.slug || "this binary")} onClick=${function () { setFunctionBrowseIds([build.id]); setReviewAnchor(null); loadFunctionPage({offset:0}); }}>Only</button></div>`;
              })}</fieldset>`;
            })}
            ${!functionBrowseBuilds.length ? html`<p>No binaries recorded for this browsing scope. Refresh project facts to inspect its inventory.</p>` : functionBuildFilter.trim() && !functionBrowseBuilds.some(function (build) { return [build.name,build.slug,build.program].join(" ").toLowerCase().includes(functionBuildFilter.trim().toLowerCase()); }) ? html`<p>No binaries match this filter. <button type="button" className="wb-text-action" onClick=${function () { setFunctionBuildFilter(""); }}>Clear binary filter</button></p>` : null}
            </div><small className="wb-functions-cohort-hint">Browsing selection filters this function list; it does not remove comparison peers.</small>
          </fieldset><h3 id="wb-function-results-heading" tabIndex="-1">Functions in browsing selection</h3>${projectPager()}
          <div className="wb-function-list" aria-label="Recorded function page">${projectFunctions.results.map(function (row) { return html`<button type="button" key=${row.binaryId + ":" + row.addr} className=${"wb-function-result" + (selected && slug === row.slug && selected.addr === row.addr ? " on" : "")} onClick=${function () { focusProjectFunction(row); }}>
            <strong>${row.name || "Unnamed function"}</strong><code>${row.addr}</code><span>${row.slug}</span>${row.recordedName && row.recordedName !== row.name ? html`<small>Recorded name: ${row.recordedName}</small>` : null}${(row.matchedNames || []).filter(function (name) { return name !== row.name && name !== row.recordedName; }).map(function (name) { return html`<small key=${name}>Matched identity label: ${name}</small>`; })}<small>${row.logicalId == null ? "Identity not recorded" : "Identity #" + row.logicalId}</small></button>`; })}</div>
          ${!projectFunctions.results.length ? html`<p>${functionBusy ? "Reading function page…" : !functionBrowseSelection.length ? "Select a binary above to browse its functions." : "No recorded functions returned for this selection. Clear the function filter or inspect the project bindings."}</p>` : null}
        </div>`;
      const matchesPanel = html`<section id="wb-match-analysis" tabIndex="-1" aria-label="Correspondence analysis">
            ${reviewAnchor && focus === reviewAnchor ? html`<p className="wb-match-reference">Reference pinned at <code>${"0x" + reviewAnchor.addr.toString(16)}</code> while inspecting counterparts. <button type="button" className="wb-btn wb-btn-mini" onClick=${function () { setReviewAnchor(null); }}>Follow current function</button></p>` : null}
            ${selectedIds.length && projectUniverse && projectUniverse.corpusIdentity ? html`<${ReviewReact} binaryIds=${selectedIds} corpusIdentity=${projectUniverse.corpusIdentity} focus=${focus} onInspect=${inspectMatchEndpoint} onRefresh=${loadCorpusStatus}/>` : html`<p>Load project facts to inspect recorded correspondences alongside the code.</p>`}
          </section>`;
      const sourcePanel = html`<section className="wb-function-analysis" aria-label="Focused source and instructions">
          ${selected ? html`<p><code>${slug} · ${selected.addr}</code></p>${focusedIds.length === 1 && !selectedIds.includes(focusedIds[0]) ? html`<p className="wb-hint">This inspected function is outside the selected binary cohort. The correspondence area follows the selected cohort, not this excluded build.</p>` : null}<div className="wb-context-modes" role="group" aria-label="Function evidence">
            ${["code", "calls", "listing"].map(function (mode) { return html`<button type="button" className="wb-btn" key=${mode} aria-pressed=${comparisonMode === mode} onClick=${function () { setComparisonMode(mode); }}>${mode.charAt(0).toUpperCase() + mode.slice(1)}</button>`; })}</div>
            ${comparisonMode === "calls" ? html`<section className="wb-matching-call-context" aria-label="Call neighborhood of the focused member"><h4>Focused call neighborhood</h4><${CallGraphView} graph=${graph} compact=${true} onPick=${followCall}/></section>` : comparisonMode === "listing" ? renderFocusedListing() : decompileDockBody()}
            ` : html`<div className="wb-map-gap">Select a recorded function to inspect code, calls and member correspondence here.</div>`}
          </section>`;
      return html`<${window.AgentDecompileDockWorkspace} id="compare" onContextMenu=${openCtx} panels=${[
        { id: "wb-builds-dock", title: "Project builds", zone: "left", weight: .8, content: projectMap() },
        { id: "wb-functions-dock", title: "Functions", zone: "left", weight: 1.4, content: functionsPanel },
        { id: "wb-comparison-evidence", title: selected ? (selected.name || selected.addr) + " · " + selected.addr : "Code / listing", zone: "center", content: sourcePanel },
        { id: "wb-correspondence-dock", title: "Correspondence / call graph", zone: "right", content: matchesPanel },
        { id: "wb-selection-inspector-dock", title: "References / types / memory", zone: "bottom", content: html`<${window.AgentDecompileGhidraInspector} program=${program} addr=${selected && selected.addr} selectionKey=${selectionKey} actions=${actions} runReadAction=${runReadAction} onOpenAction=${openActionStrip}/>` }
      ]}/>`;
    }
    function recoveryPaths() {
      function shortPathLabel(value) {
        const parts = String(value || "").replace(/\\/g, "/").split("/").filter(Boolean);
        return parts[parts.length - 1] || "/";
      }
      return html`<section className="wb-recovery-paths" aria-label="Independent source and proof evidence"><header className="wb-map-heading"><div><span className="wb-map-kicker">Evidence overview</span><h3>Source and proof by binary</h3></div></header>
        <p className="wb-evidence-note">Independent evidence columns, not a progression. ● Witness on the explicitly loaded inventory snapshot page; ? unknown in that snapshot. Search does not recompute recovery evidence. Fresh whole-image proof is not supplied here.</p>
        <p className="wb-evidence-key"><b>C</b> readable source · <b>Comp.</b> compiled · <b>Hist.</b> historical exact · <b>Image</b> fresh whole-image proof</p>
        <div className="wb-evidence-scroll"><table className="wb-evidence-grid"><thead><tr><th scope="col">Binary</th><th scope="col" aria-label="Readable C">C</th><th scope="col" aria-label="Compiled">Comp.</th><th scope="col" aria-label="Historical exact">Hist.</th><th scope="col" aria-label="Fresh whole-image proof">Image</th></tr></thead><tbody>
          ${projectBuilds.slice(0, memberLimit).map(function (build) {
            const witnesses = (projectUniverse && projectUniverse.functions.results || []).filter(function (row) { return (build.binaryIds || []).includes(row.binaryId) && row.recordedRecovery && (row.recordedRecovery.records || []).length; });
            const tiers = [["Readable C", witnesses.some(function (row) { return row.recordedRecovery.readable === true; })], ["Compiled", witnesses.some(function (row) { return row.recordedRecovery.compiled === true; })], ["Historical exact", witnesses.some(function (row) { return row.recordedRecovery.historicalExact === true; })], ["Fresh image", false]];
            const path = memberPath(build);
            const owningProjects = openProjects.filter(function (project) { return (build.projectIds || []).includes(project.id); });
            const projectLabel = owningProjects.map(function (project) { return shortPathLabel(project.title || project.locator); }).join(", ");
            return html`<${React.Fragment} key=${build.id}><tr className=${inspectedOutput === build.id ? "is-inspected" : ""}><th scope="row"><button type="button" aria-expanded=${inspectedOutput === build.id} aria-label=${path.name + " · " + projectTitles(build.projectIds) + " · " + path.directory + " · show member details"} className="wb-evidence-member" onClick=${function () { setInspectedOutput(inspectedOutput === build.id ? "" : build.id); }}><strong>${path.name}</strong><small>${projectLabel} · ${shortPathLabel(path.directory)}</small></button></th>
              ${tiers.map(function (tier) { return html`<td key=${tier[0]}><span className=${"wb-tier-dot " + (tier[1] ? "has-witness" : "is-unknown")} aria-label=${tier[0] + ": " + (tier[1] ? "witness on this page" : "unknown in this view")}>${tier[1] ? "●" : "?"}</span></td>`; })}</tr>
              ${inspectedOutput === build.id ? html`<tr className="wb-evidence-detail"><td colSpan="5"><strong>${build.slug || path.name}</strong><p><code>${build.program || "Program path not recorded"}</code></p>
                ${owningProjects.map(function (project) { return html`<p key=${project.id}>Project: ${project.title}<br/><code>${project.locator || "Project locator not recorded"}</code></p>`; })}
                ${!witnesses.length ? html`<p>No source witness on this page. Find additional functions in Compare.</p>` : witnesses.map(function (row) { return html`<section key=${row.binaryId + ":" + row.addr}><h4>${row.name} <code>${row.addr}</code></h4>${row.recordedRecovery.records.map(function (record, index) { return html`<div key=${index}><code>${record.path}</code><pre>${record.evidence || "No evidence reference recorded"}</pre></div>`; })}${row.recordedRecovery.witnessesPartial ? html`<p>Witness list is partial.</p>` : null}</section>`; })}
                ${build.slug ? html`<details onToggle=${function (ev) { if (ev.currentTarget.open) setOutputBuilds(function (old) { return Object.assign({}, old, { [build.id]: true }); }); }}><summary>Inspect exports and WASM / hook / runtime readiness</summary>${outputBuilds[build.id] ? html`<${ExportBundles} slug=${build.slug} locator="" />` : null}</details>` : html`<p>Resolve this member’s binding to inspect exports.</p>`}
              </td></tr>` : null}</${React.Fragment}>`;
          })}</tbody></table></div>${memberLimitControl()}${projectPager()}<button type="button" className="wb-btn" onClick=${function () { jumpTo("wb-fnbrowse"); }}>Find source functions in Compare</button>
      </section>`;
    }
    function measuredStageProgress(value, unit) {
      if (!value || !Number.isFinite(value.total) || value.total <= 0 || !Number.isFinite(value.completed) || value.completed < 0 || value.completed > value.total) return null;
      return { completed: value.completed, total: value.total, unit: value.unit || unit || "items", currentTarget: value.currentTarget || "" };
    }
    function workRunLane(run) {
      const stages = Array.isArray(run.stages) ? run.stages : [];
      const displayed = stages.slice(0, 32);
      const current = stages.find(function (stage) { return stage.key === run.currentStage; });
      const selectedStage = stages.find(function (stage) { return stage.key === inspectedStages[run.id]; }) || current || stages.find(function (stage) { return /failed|blocked|queued|waiting/.test(stage.status); }) || stages[0];
      const defaultUnits = { matching: "comparisons", analysis: "programs", facts: "programs", bsim: "programs" };
      function progressFor(stage) { return { primary: measuredStageProgress(stage, defaultUnits[stage.key]), secondary: measuredStageProgress(stage.workProgress) }; }
      function counter(progress) { return progress.completed + " / " + progress.total + " " + progress.unit; }
      function stageFacts(stage) {
        const progress = progressFor(stage);
        const job = jobs.find(function (item) { return item.id === stage.jobId; });
        const startKnown = job && Object.prototype.hasOwnProperty.call(job, "startedAt");
        const boundary = !job ? "Job execution receipt not loaded" : job.startedAt ? "Execution start recorded" : startKnown ? job.status === "cancelled" && !job.workerPid ? "Cancelled · no start or worker receipt" : "No execution start recorded" : "Execution start unknown";
        return html`<div className="wb-stage-inspection"><div className="wb-stage-actual"><strong>${stage.title || stage.key}</strong><span>Stage: ${stage.status || "unknown"}</span><span>Child job in stage receipt: ${stage.jobStatus || "unknown"}</span>${job ? html`<span>Job snapshot: ${job.status || "unknown"}</span>` : null}</div>
          <div className="wb-stage-target">${stage.currentTarget || stage.currentProgram ? html`<span>Target <code>${stage.currentTarget || stage.currentProgram}</code></span>` : html`<span>Current target not recorded</span>`}${stage.currentAction ? html`<span>Action <code>${stage.currentAction}</code></span>` : null}</div>
          ${progress.primary ? html`<div className="wb-measured-line"><span>Stage ${counter(progress.primary)}</span><progress max=${progress.primary.total} value=${progress.primary.completed} aria-label="Measured stage progress"></progress></div>` : null}
          ${progress.secondary ? html`<div className="wb-measured-line"><span>Sub-work ${counter(progress.secondary)}</span><progress max=${progress.secondary.total} value=${progress.secondary.completed} aria-label="Measured sub-work progress"></progress></div>` : null}
          ${stage.workProgress && stage.workProgress.currentTarget ? html`<p className="wb-stage-subtarget">Sub-work target <code>${stage.workProgress.currentTarget}</code></p>` : null}
          <p className="wb-execution-boundary">${boundary}${job && job.resourceDisposition ? " · Resources: " + job.resourceDisposition : ""}</p>
          ${stage.reason ? html`<p className="wb-stage-boundary">${stage.reason}</p>` : null}
          <details><summary>Stage evidence and resource details</summary>${job && job.resourceKeys ? html`<p>Recorded resource keys</p><pre>${JSON.stringify(job.resourceKeys, null, 2)}</pre>` : null}<p>A stage message is not a fresh byte inspection. Queue time is not execution time.</p><pre>${JSON.stringify(stage, null, 2)}</pre>${stage.jobId ? html`<button type="button" className="wb-btn" onClick=${function () { selectJobInDock(stage.jobId); }}>Inspect job details</button>` : null}</details>
        </div>`;
      }
      return html`<section key=${run.id} className="wb-run-lane wb-compact-run"><header><strong>${run.scope === "project" ? "Project run" : run.scope === "binary" ? "Program run" : "Unknown scope"} · ${run.status || "unknown"}</strong><code>${run.program || run.id}</code></header>
        <ol className="wb-stage-path" aria-label="Ordered recorded stages">${displayed.map(function (stage, index) {
          const progress = progressFor(stage); const shown = progress.primary || progress.secondary;
          const job = jobs.find(function (item) { return item.id === stage.jobId; });
          return html`<li key=${stage.key || index} className=${(stage.key === run.currentStage ? "is-current " : "") + (/failed|blocked/.test(stage.status) ? "is-failed" : "")}><button type="button" aria-pressed=${stage === selectedStage} onClick=${function () { setInspectedStages(function (old) { return Object.assign({}, old, { [run.id]: stage.key }); }); }}><span className="wb-path-pin" aria-hidden="true"></span><strong>${stage.title || stage.key || "Unnamed stage"}</strong><span>${stage.status || "unknown"}${stage.key === run.currentStage ? " · current receipt" : ""}</span>${stage.jobStatus || job ? html`<small>Child: ${stage.jobStatus || job.status || "unknown"}</small>` : null}${shown ? html`<small>${progress.primary ? "" : "Sub-work: "}${counter(shown)}</small>` : null}</button></li>`;
        })}</ol>${selectedStage ? stageFacts(selectedStage) : html`<p className="wb-membership-gap">No stage list recorded.</p>`}
        ${stages.length > 32 ? html`<p>First 32 of ${stages.length} stages drawn; full record below.</p>` : null}
        <details><summary>Run observation and complete stage record</summary><${PreparationObservation} run=${run} feed=${preparationFeed} now=${preparationNow} /><pre>${JSON.stringify(stages, null, 2)}</pre></details>
      </section>`;
    }
    function workPaths() {
      return html`<section className="wb-work-paths" aria-label="Recorded project work"><header className="wb-map-heading"><div><span className="wb-map-kicker">Recorded work</span><h3>Where each run stopped</h3></div><button type="button" className="wb-btn" disabled=${preparationRefreshing} onClick=${function () { loadPreparations(); loadProjectAvailability(); loadJobs("current"); }}>Refresh work status</button></header>
        <p className="wb-hint">${preparationFeed.receivedAt ? "Snapshot received " + new Date(preparationFeed.receivedAt).toLocaleString() + (preparationNow - preparationFeed.receivedAt > 10000 ? " · stale for controls" : "") : "Work snapshot not loaded"}${preparationFeed.error ? " · Refresh failed: " + preparationFeed.error : ""}. Queue time is not execution time.</p>
        ${openProjects.map(function (project) { const state = projectPipelineState(project, preparationNow); return html`<article key=${project.id} className="wb-project-boundary"><header><h4>${project.title}</h4><button type="button" className="wb-btn" disabled=${Boolean(state.reason) || projectControlBusy.current.has(project.id)} onClick=${function () { projectPipelineControl(project, state.run); }}>${state.label}</button></header>
          ${state.reason ? html`<p role="status">${state.reason}</p>` : null}${projectControls[project.id] ? html`<p role="status">${projectControls[project.id]}</p>` : null}
          ${state.projectRuns.length > 1 ? html`<p>Multiple project runs · ownership unresolved. Each is shown separately.</p>` : null}
          ${state.projectRuns.concat(state.otherRuns).slice(0, runLimit).map(workRunLane)}${!state.projectRuns.length && !state.otherRuns.length ? html`<p className="wb-map-gap">No preparation runs recorded for this project. Execution elsewhere is unknown.</p>` : null}
          ${state.projectRuns.length + state.otherRuns.length > runLimit ? html`<button type="button" className="wb-btn" onClick=${function () { setRunLimit(function (n) { return n + 12; }); }}>Show more runs (${runLimit} of ${state.projectRuns.length + state.otherRuns.length} drawn)</button>` : null}
          <details><summary>Project availability</summary><p>${projectAvailability[project.id] && projectAvailability[project.id].reason || "Inventory not yet inspected."}</p></details>
        </article>`; })}
        <div className="wb-work-activity"><button type="button" className="wb-btn" onClick=${openLogJobs}>Inspect job activity</button><button type="button" className="wb-btn" onClick=${function () { setLogTab("log"); setLogOpen(true); }}>Session log</button><span>Job details open on request.</span></div>
      </section>`;
    }
    function renderProjectSurface(tab) {
      const titles = { "wb-overview": "Compare", "wb-artifacts": "Recover", "wb-pipeline": "Work" };
      if (!titles[tab]) return null;
      return html`<${Surface} id=${tab} title=${titles[tab]}>
        ${projectScopeNotice()}${projectErrors()}
        ${!openProjects.length ? html`<p>Open a project to inspect its binaries and recorded work.</p><button type="button" className="wb-btn" onClick=${openProjectDialog}>Open project…</button>` : null}
        ${tab === "wb-overview" ? comparisonWorkspace() : html`<${window.AgentDecompileDockWorkspace} id=${tab} onContextMenu=${openCtx} panels=${[{ id: tab + "-dock", title: titles[tab] === "Recover" ? "Source / build artifacts" : "Pipeline / activity", zone: "center", content: tab === "wb-artifacts" ? recoveryPaths() : workPaths() }]}/>`}
      </${Surface}>`;
    }

    function renderEditorBody() {
      const tab = editorTabFor(centerTab);
      const projectSurface = renderProjectSurface(tab);
      if (projectSurface) return projectSurface;
      if (tab === "wb-guide") {
        return html`<${Surface} id="wb-guide" title="Ghidra reversing guide">
          ${projectScopeNotice()}
          <p className="wb-hint">Navigate the existing workspace using the guide’s Code Browser concepts. A guide step is orientation, not a completion score.</p>
          <${GuideRail} chapters=${GUIDE_CHAPTERS} centerTab=${centerTab}
            reachable=${GUIDE_CHAPTERS.map(function (chapter) {
              return chapter.target === "wb-sidebar" ? Boolean(dossier && dossier.ok) : Boolean(program);
            })}
            evidence=${[
              Boolean(dossier && dossier.ok && (dossier.programs || []).length > 0),
              rows.length > 0,
              Boolean(detail && (detail.preview || (detail.decompile && detail.decompile.text))),
              Boolean(graph && (graph.center || (graph.callers && graph.callers.length) || (graph.callees && graph.callees.length))),
              Boolean(selected && selected.addr),
              false,
              false,
              Boolean(detail && detail.decompile && detail.decompile.text)
            ]}
            onJump=${jumpTo} />
        </${Surface}>`;
      }

      if (tab === "wb-tools") {
        const needle = (commandFilter || "").trim().toLowerCase();
        const matches = actions.filter(function (item) {
          if (!needle) return true;
          return (item.id + " " + (item.title || "") + " " + (item.group || "") + " " + (item.summary || ""))
            .toLowerCase().indexOf(needle) >= 0;
        });
        const groups = [];
        const byGroup = {};
        matches.forEach(function (item) {
          const key = item.group || "Other";
          if (!byGroup[key]) { byGroup[key] = []; groups.push(key); }
          byGroup[key].push(item);
        });
        return html`<${Surface} id="wb-tools" title="Commands" actions=${html`<div className="wb-surface-actions">
          <a className="wb-btn wb-btn-mini" href="/docs" target="_blank" rel="noreferrer">HTTP API</a>
          <button type="button" className="wb-btn wb-btn-mini"
            onClick=${function () { setPaletteOpen(true); setPaletteQuery(""); }}>Palette ${accelLabel("mod+K")}</button>
        </div>`}>
          ${projectScopeNotice()}
          <p className="wb-hint">Expert commands retain their explicit parameters. Review source and target when several project members are suitable; no arbitrary global binary is selected.</p>
          <label className="wb-cmd-filter">
            <span className="sr-only">Filter commands</span>
            <input type="search" id="wb-cmd-filter" placeholder=${"Filter " + actions.length + " commands…"}
              value=${commandFilter} onInput=${function (ev) { setCommandFilter(ev.target.value); }} />
          </label>
          <p className="wb-hint">${matches.length} of ${actions.length} commands. Click a command to load it.</p>
          ${recentActionIds.length && !needle ? html`<section className="wb-cmd-group">
            <h3>Recent</h3>
            <ul className="wb-cmd-list">
              ${recentActionIds.map(function (id) {
                const item = actions.find(function (row) { return row.id === id; });
                if (!item) return null;
                return html`<li key=${"recent-" + id}>
                  <button type="button" className="wb-cmd-entry" onClick=${function () { openActionStrip(item.id); }}>
                    <span className="wb-cmd-title">${item.title || item.id}</span>
                    <code className="wb-cmd-id">${item.id}</code>
                  </button>
                </li>`;
              })}
            </ul>
          </section>` : null}
          ${groups.map(function (name) {
            return html`<section key=${name} className="wb-cmd-group">
              <h3>${name}</h3>
              <ul className="wb-cmd-list">
                ${byGroup[name].map(function (item) {
                  return html`<li key=${item.id}>
                    <button type="button" className=${"wb-cmd-entry" + (item.danger || item.mutating ? " danger" : "")}
                      data-action=${item.id}
                      onClick=${function () { openActionStrip(item.id); }}>
                      <span className="wb-cmd-title">${item.title || item.id}</span>
                      <code className="wb-cmd-id">${item.id}</code>
                      ${item.summary ? html`<span className="wb-cmd-summary">${item.summary}</span>` : null}
                      ${item.danger || item.mutating ? html`<span className="wb-cmd-flag">writes</span>` : null}
                    </button>
                  </li>`;
                })}
              </ul>
            </section>`;
          })}
          ${!matches.length ? html`<p className="wb-empty">No command matches “${commandFilter}”.</p>` : null}
        </${Surface}>`;
      }

      return renderProjectSurface("wb-overview");
    }

    function renderFocusedListing() {
      return html`<section id="wb-inspect" aria-label="Selected function listing">
        <div className="wb-fn-tools" role="toolbar" aria-label="Listing tools">
          <button type="button" id="wb-listing-decompile" className="wb-btn" onClick=${function () { if (selected && selected.addr) executeAction("mcp.decompile-function", { addr: selected.addr, name: selected.name || "", program: program || "" }, { skipConfirm: true }); }}>Decompile</button>
          <button type="button" className="wb-btn" onClick=${function () { jumpTo("wb-recovery"); }}>Recover</button>
          <button type="button" className="wb-btn" onClick=${function () { openActionStrip("mcp.manage-function"); }}>Function fields…</button>
        </div>
        <${ListingRows} key=${selectionKey} addr=${selected.addr} name=${selected.name} program=${program}
          runReadAction=${function (id, parameters, options) {
            if (!isCurrentIntent(renderIntent)) return Promise.resolve({ ok: false, ignored: true, error: "Selection changed." });
            return runReadAction(id, parameters, Object.assign({}, options, { selectionIntent: renderIntent }));
          }}
          assemblyText=${detail && detail.resolvedFunction && sameFunctionAddress(detail.resolvedFunction.addr, selected.addr) && detail.assembly && detail.assembly.text}
          fallbackText=${detail && detail.resolvedFunction && sameFunctionAddress(detail.resolvedFunction.addr, selected.addr) && detail.preview || "No captured listing available for this selection."}
          onJumpAddr=${function (target) { selectRow({ addr: target, name: target }); }} />
      </section>`;
    }

    /* Persistent Decompile dock (CodeBrowser layout only). Shows the selected
       function's decompile from whichever center tab is active, not only
       Listing. When nothing is selected, it keeps the last function that had
       a decompile, per the guide's "connected views" behavior. */
    function decompileDockBody() {
      const liveText = detail && detail.resolvedFunction && selected && sameFunctionAddress(detail.resolvedFunction.addr, selected.addr)
        && detail.decompile && detail.decompile.text;
      const text = liveText || (lastDecompile && lastDecompile.text) || "";
      const request = detail && detail.evidenceRequest;
      let status = "";
      if (!liveText && request) {
        if (request.status === "running" || request.status === "queued" || request.status === "admitted") {
          status = "Reading this function from Ghidra…";
        } else if (request.status === "failed") {
          status = request.cause === "authentication-failed"
            ? "The Ghidra server refused the login, so this function could not be read. Open a local copy of the project to read it."
            : "Ghidra could not read this function." + (request.cause ? " (" + request.cause + ")" : "");
        }
      }
      if (!text) {
        const assembly=detail&&detail.resolvedFunction&&selected&&sameFunctionAddress(detail.resolvedFunction.addr,selected.addr)&&detail.assembly&&detail.assembly.text;
        if(assembly)return html`<div className="wb-decompile-pane"><${SourcePreview} text=${assembly} language="assembly-listing" name=${selected.name||"function"} addr=${selected.addr} slug=${detail.resolvedSlug||slug} source=${detail.source||"recorded instruction evidence"} truncated=${detail.assembly.truncated} status=${status} reason=${detail.decompile&&detail.decompile.reason}/></div>`;
        return html`<div className="wb-decompile-pane wb-decompile-empty">
          <h3>Decompile</h3>
          <p className="wb-hint" role="status">${status || "Pick a function to see its decompiled C."}</p>
        </div>`;
      }
      const name = (liveText && detail.resolvedFunction && detail.resolvedFunction.name)
        || (lastDecompile && lastDecompile.name)
        || (selected && selected.name)
        || "function";
      const source = (liveText && detail.decompile && detail.decompile.source)
        || (lastDecompile && lastDecompile.source)
        || (liveText&&detail.source)
        || "";
      return html`<div className="wb-decompile-pane">
        <${SourcePreview} text=${text} name=${name} addr=${liveText?detail.resolvedFunction.addr:lastDecompile&&lastDecompile.addr} slug=${liveText?detail.resolvedSlug||slug:lastDecompile&&lastDecompile.resolvedSlug||slug} source=${source} path=${liveText&&detail.decompile.path||""} truncated=${liveText?detail.decompile.truncated:undefined} previous=${!liveText} status=${status
          ? status + " Showing the last function read."
          : (!liveText ? "Showing the previous function read; the current address has no decompile evidence. This download belongs to the displayed previous function, not the current cursor." : "")}/>
      </div>`;
    }


    return html`<div className="wb">
      <a className="skip-link" href="#wb-q" onClick=${function (ev) { ev.preventDefault(); jumpTo("wb-fnbrowse"); }}>Skip to function search</a>
      <div className="wb-chrome">
      <header className="wb-toolbar">
        <div className="wb-brand">
          <span className="wb-mark" aria-hidden="true">AD</span>
          <strong>AgentDecompile</strong>
        </div>
        <button type="button" className="wb-btn wb-project-source-download" data-cmd="file.download-source" disabled=${!currentSession || !currentSession.locator || projectSourceState && projectSourceState.owner === activeSession && projectSourceState.status === "waiting"} onClick=${downloadProjectSource} title="Download recorded source and assembly artifacts for every member of the active project; includes a coverage manifest">${projectSourceState && projectSourceState.owner === activeSession && projectSourceState.status === "waiting" ? "Collecting project source…" : projectSourceState && projectSourceState.owner === activeSession && projectSourceState.status === "pending" ? "Check source download" : "Download project source"}</button>
        <p className="wb-status-line">
          <button type="button" className="wb-server-btn" data-cmd="view.palette"
            onClick=${function () { setPaletteOpen(true); setPaletteQuery(""); }}
            title=${"Command palette (" + accelLabel("mod+K") + ")"}>${accelLabel("mod+K")}</button>
          <span id="job-pulse" title=${jobsRefreshedAt ? "Last checked " + new Date(jobsRefreshedAt).toLocaleString() : "Job status has not been checked"}>${jobsRefreshedAt
            ? (running.length ? running.length + " active" : "No active jobs · checked")
            : jobs.length ? "New job · refresh for status" : "Jobs not checked"}</span>
        </p>
      </header>
      <${RepoStatus} dossier=${dossier} user=${sharedUser} session=${currentSession} program=${program} slug=${slug}
        onRetry=${function () { if (currentSession && currentSession.locator) loadPreview(currentSession.locator); }} />
      <nav id="wb-menubar" className="wb-menubar" aria-label="Application">
        ${[
          ["file", "File", [
            ["New Project…", "file.new-project"],
            ["New Tab", "file.new-tab"],
            ["Open…", "file.open"],
            ["Open from URL…", "file.open-url"],
            ["Add to project…", "file.add-binaries"],
            ["—"],
            ["Reload from disk", "file.reload"],
            ["Save", "file.save"],
            ["Save As…", "file.save-as"],
            ["Download project source", "file.download-source"],
            ["Check in to Ghidra server", "file.checkin"],
            ["Open selected program in Ghidra", "file.open-program"],
            ["—"],
            ["Close Tab", "file.close-tab"]
          ]],
          ["edit", "Edit", [
            ["Rename Tab", "edit.rename-tab"]
          ]],
          ["view", "View", [
            ["Command palette", "view.palette"],
            ["Explorer", "view.explorer"],
            ["Arrange panels…", "view.panels"],
            ["—"],
            ["Compare", "view.overview"],
            ["Recover", "view.artifacts"],
            ["Work", "view.pipeline"],
            ["Job activity…", "view.jobs"],
            ["Matching receipts…", "view.match-receipts"],
            ["—"],
            ["Commands", "view.tools"],
            ["—"],
            ["Use compact layout", "view.density-compact"],
            ["Use roomy layout", "view.density-comfortable"],
            ["Dock jobs on the side", "view.jobs-rail"],
            ["Dock jobs at the bottom", "view.jobs-bottom"],
            [classicLayout ? "Use new layout" : "Use classic layout", "view.classic-layout"]
          ]],
          ["server", "Server", [
            ["Targeted AI settings…", null, function () { window.location.href = "/dashboard/settings/ai"; }],
            ["—"],
            ["Restart server", null, restartServer],
            ["Shut down server", null, shutdownServer]
          ]],
          ["help", "Help", [
            ["Shortcuts and menus…", "help.access"],
            ["Ghidra reversing guide", null, function () { setCenterTab("wb-guide"); }],
            ["Open all commands", null, function () { window.location.href = "/docs"; }],
            ["Overview", "help.overview"]
          ]]
        ].map(function (entry) {
          const id = entry[0];
          const label = entry[1];
          const items = entry[2];
          return html`<div key=${id} className=${"wb-menu" + (menu === id ? " on" : "")}
            onMouseEnter=${function () { if (menu) setMenu(id); }}>
            <button type="button" className="wb-menu-btn" aria-haspopup="true" aria-expanded=${menu === id}
              onClick=${function (ev) { dialogInvokerRef.current = ev.currentTarget; setMenu(menu === id ? "" : id); }}>${label}</button>
            ${menu === id ? html`<ul className="wb-menu-list">${items.map(function (item, index) {
              if (item[0] === "—") return html`<li key=${id + "-s" + index} className="wb-menu-sep" />`;
              const cmdId = item[1];
              const accel = (cmdId && COMMAND_BY_ID[cmdId] && accelLabel(COMMAND_BY_ID[cmdId].accel))
                || COMMAND_ACCEL[item[0]] || "";
              return html`<li key=${id + "-" + item[0]}>
                <button type="button" className="wb-menu-item" data-cmd=${cmdId || ""}
                  onClick=${function () {
                    setMenu("");
                    if (cmdId) runCommand(cmdId);
                    else if (item[2]) item[2]();
                  }}>
                  <span>${item[0]}</span>
                  ${accel ? html`<span className="wb-accel">${accel}</span>` : null}
                </button>
              </li>`;
            })}</ul>` : null}
          </div>`;
        })}
      </nav>
      <div id="wb-sessions" className="wb-sessions" role="tablist" aria-label="Open projects"
        onContextMenu=${function (ev) {
          openCtx(ev, [
            { id: "file.new-tab" },
            { id: "file.new-project" },
            "—",
            { id: "file.open" },
            { id: "file.open-url" }
          ].map(decorateCommandItem));
        }}>
        ${sessions.map(function (item) {
          const on = item.id === activeSession;
          return html`<div key=${item.id} className=${"wb-tab kind-" + styleKind(item.kind) + (on ? " on" : "")} role="tab" aria-selected=${on}
            onContextMenu=${function (ev) {
              if (item.id !== activeSession) {
                setActiveSession(item.id);
                persistSessions(sessions, item.id);
                restoreTabSession(item);
              }
              openCtx(ev, [
                { title: "Rename “" + (item.title || "tab") + "”", run: function () { setEditingTab(item.id); }, accel: "F2" },
                { id: "file.reload" },
                "—",
                { id: "file.save" },
                { id: "file.save-as" },
                "—",
                { title: "Copy project path", run: function () { copyText(item.locator || "", "project path"); } },
                "—",
                { title: "Close “" + (item.title || "tab") + "”", danger: true, accel: accelLabel("alt+W"),
                  run: function () { runCommand("file.close-tab"); } }
              ].map(decorateCommandItem));
            }}>
            <span className=${"wb-tab-chip kind-" + styleKind(item.kind)} title=${kindTitle(item.kind) + " · " + sessionKindLabel(item)}>${sessionKindLabel(item)}</span>
            ${editingTab === item.id
              ? html`<input className="wb-tab-rename" value=${item.title} autofocus
                  onBlur=${function (ev) { renameTab(item.id, ev.target.value); }}
                  onKeyDown=${function (ev) { if (ev.key === "Enter") renameTab(item.id, ev.target.value); }} />`
              : html`<button type="button" className="wb-tab-name" title="Double-click to rename"
                  onClick=${function () {
                    if (item.id === activeSession) return;
                    setActiveSession(item.id);
                    persistSessions(sessions, item.id);
                    restoreTabSession(item);
                  }}
                  onDblClick=${function () { setEditingTab(item.id); }}>${item.title}</button>`}
            <button type="button" className="wb-tab-close" aria-label=${"Close " + item.title}
              onClick=${function () {
                const dirty = item.kind !== "draft" || item.locator || sessionImportSlugs(item).length;
                if (dirty) {
                  askConfirm({
                    title: "Close " + (item.title || "tab") + "?",
                    message: "This closes the project tab. File → Open reopens it.",
                    confirmLabel: "Close tab",
                    danger: true,
                    onConfirm: function () { closeTab(item.id); }
                  });
                  return;
                }
                closeTab(item.id);
              }}>×</button>
          </div>`;
        })}
        <button type="button" id="wb-tab-new" className="wb-tab-new" data-cmd="file.new-tab"
          onClick=${function () { runCommand("file.new-tab"); }}
          title=${"New tab (" + accelLabel("alt+T") + ")"}>+</button>
      </div>
      ${pendingAction ? html`<${ActionStrip}
        key=${pendingAction.id + ":" + JSON.stringify(pendingActionParams)}
        action=${pendingAction}
        ctx=${toolContext}
        expanded=${actionExpanded}
        danger=${pendingAction.danger || pendingAction.mutating}
        checkedCount=${checkedAddrs.length}
        formRef=${actionFormRef}
        onToggleExpand=${function () { setActionExpanded(function (v) { return !v; }); }}
        onRun=${runFromActionStrip}
        onClose=${function () { setPendingActionId(""); setActionExpanded(false); }} />` : null}
      <${JobLiveRegion} text=${jobLiveText} />
      </div>
      <${CommandPalette}
        open=${paletteOpen}
        query=${paletteQuery}
        onQuery=${setPaletteQuery}
        actions=${actions}
        surfaces=${SURFACES}
        jobs=${jobs}
        recentActionIds=${recentActionIds}
        commands=${WORKBENCH_COMMANDS}
        onPickAction=${onPaletteAction}
        onPickSurface=${onPaletteSurface}
        onPickJob=${onPaletteJob}
        onPickCommand=${function (id) { setPaletteOpen(false); setPaletteQuery(""); runCommand(id); }}
        onClose=${function () { setPaletteOpen(false); setPaletteQuery(""); }}
        menuInvokerRef=${dialogInvokerRef} />
      <${ContextMenu} menu=${ctxMenu} onClose=${function () { setCtxMenu(null); }}
        onPick=${function (item) {
          setCtxMenu(null);
          if (typeof item.run === "function") item.run();
          else runCommand(item.id, item.extra);
        }} />
      <${PanelLayoutDialog} open=${dialog === "panels"} onClose=${closeDialog} workspaceId=${editorTabFor(centerTab) === "wb-overview" ? "compare" : editorTabFor(centerTab)} menuInvokerRef=${dialogInvokerRef}/>
      <${Modal} open=${dialog === "match-receipts"} title="Recorded matching evidence" onClose=${closeDialog} menuInvokerRef=${dialogInvokerRef} footer=${html`<button type="button" className="wb-btn" onClick=${loadMatchStatus}>Read matching methods</button><button type="button" className="wb-btn wb-btn-primary" onClick=${closeDialog}>Close</button>`}>
        <table><thead><tr><th>Build pair</th><th>Accepted correspondences</th><th>Receipt</th></tr></thead><tbody>${scopedBinaries.flatMap(function (binary) { const group = binary.variant_group || binary.variantGroup; return (group && group.evidence || []).filter(function (receipt) { return memberSlugs.has(receipt.source) && memberSlugs.has(receipt.target); }); }).map(function (receipt, index) { return html`<tr key=${index}><td>${receipt.source} ↔ ${receipt.target}</td><td>${receipt.acceptedMatches == null ? "Not recorded" : receipt.acceptedMatches}</td><td><code>${receipt.receipt || "Not supplied"}</code></td></tr>`; })}</tbody></table>
        ${bsimStatus ? html`<p>${bsimStatus.summary}</p><table><thead><tr><th>Recorded method</th><th>Bindings</th><th>Scope</th></tr></thead><tbody>${(bsimStatus.methods || []).map(function (method, index) { return html`<tr key=${index}><td>${method.method}</td><td>${method.bindings}</td><td>${method.scope}</td></tr>`; })}</tbody></table>${(bsimStatus.errors || []).map(function (error, index) { return html`<p role="status" key=${index}>${error}</p>`; })}` : html`<p>Read methods on demand. Missing BSim does not block other matching methods.</p>`}
        <p>Recorded correspondence is not byte-equality proof. Detailed pair evidence remains alongside the code in Correspondence.</p>
      </${Modal}>
      <${ConfirmDialog}
        open=${Boolean(confirmDialog)}
        title=${confirmDialog && confirmDialog.title}
        message=${confirmDialog && confirmDialog.message}
        confirmLabel=${confirmDialog && confirmDialog.confirmLabel}
        danger=${confirmDialog && confirmDialog.danger}
        onConfirm=${confirmDialog && confirmDialog.onConfirm}
        onCancel=${closeConfirm} />
      <main id="app">
      <input id="wb-bin-file-global" type="file" multiple hidden ref=${fileRef}
        onChange=${function (ev) { if (ev.target.files && ev.target.files.length) uploadFiles(ev.target.files); }} />
      <input id="wb-add-file" type="file" hidden ref=${addFileRef}
        onChange=${function (ev) { if (ev.target.files && ev.target.files.length) stageAddFile(ev.target.files[0]); }} />
      <input id="wb-bin-folder-global" type="file" webkitdirectory="true" hidden ref=${folderRef}
        onChange=${function (ev) { if (ev.target.files && ev.target.files.length) uploadFiles(ev.target.files); }} />
      <${Modal} open=${dialog === "open"} title="Open project" onClose=${closeDialog} error=${dialogError} menuInvokerRef=${dialogInvokerRef} footer=${html`
        <button type="button" className="wb-btn" onClick=${closeDialog}>Cancel</button>
        <button type="button" className="wb-btn wb-btn-primary" id="wb-open-paste-go" disabled=${browseOpening || !openPaste.trim()} onClick=${openPastedPath}>${browseOpening ? "Opening project…" : "Open path"}</button>
      `}>
        <label className="wb-open-paste">Path or URL
          <input id="wb-open-paste" value=${openPaste} disabled=${browseOpening} placeholder="/home/…/repos · Name.gpr · ghidra://host:port/repo · /path/to/binary"
            onInput=${function (ev) { setOpenPaste(ev.target.value); }}
            onKeyDown=${function (ev) { if (ev.key === "Enter") { ev.preventDefault(); openPastedPath(); } }} />
        </label>
        <div className="wb-dialog-tabs">
          <button type="button" className=${openTab === "local" ? "on" : ""} onClick=${function () { setOpenTab("local"); }}>This computer</button>
          <button type="button" className=${openTab === "remote" ? "on" : ""} onClick=${function () { setOpenTab("remote"); }}>Ghidra Server</button>
        </div>
        ${openTab === "local" ? html`<div>
          <div id="wb-drop" className="wb-drop wb-drop-compact" tabindex="0" ref=${dropRef}
            onClick=${triggerFileUpload}
            onDragOver=${function (ev) { ev.preventDefault(); ev.currentTarget.classList.add("on"); }}
            onDragLeave=${function (ev) { ev.currentTarget.classList.remove("on"); }}
            onDrop=${onDrop}>
            Drop a .gpr, repos folder, or binary
          </div>
          <p className="wb-dialog-actions">
            <button type="button" className="wb-btn" onClick=${triggerFolderUpload}>Choose folder…</button>
            <button type="button" className="wb-btn wb-btn-primary" onClick=${createProject}>Create empty project</button>
          </p>
          <div id="wb-browse" className="wb-browse">
            <p className="wb-browse-path">
              ${browse.path ? html`<button type="button" className="wb-text-action" disabled=${browseBusy || browseOpening} onClick=${function () { loadBrowse(""); }}>Locations</button>` : null}
              ${browse.parent ? html`<button type="button" className="wb-text-action" disabled=${browseBusy || browseOpening} onClick=${function () { loadBrowse(browse.parent); }}>Up</button>` : null}
              <code>${browse.path || "roots"}</code>
              ${browse.path && ["ghidra-project", "shared-fs", "shared-project"].includes(browse.kind) ? html`<button type="button" className="wb-btn wb-btn-primary" disabled=${browseBusy || browseOpening} onClick=${function () { openBrowseEntry({path:browse.path,kind:browse.kind}); }}>Open this project</button>` : null}
            </p>
            ${browseBusy ? html`<p role="status">Reading project locations…</p>` : browseOpening ? html`<p role="status">Opening the selected project and retaining existing analysis…</p>` : browse.kind === "project-collection" ? html`<p>Select the .gpr project to open. This folder contains multiple projects.</p>` : null}
            <ul className="wb-browse-list" aria-busy=${browseBusy || browseOpening}>
              ${(browse.entries || []).map(function (entry) {
                return html`<li key=${entry.path} className=${"kind-" + styleKind(entry.kind)}>
                  <button type="button" className="wb-browse-item" data-kind=${entry.kind} disabled=${browseBusy || browseOpening} title=${entry.path}
                    onClick=${function () { openBrowseEntry(entry); }}>
                    <strong>${entry.name}</strong>
                    <span>${["gpr", "ghidra-project", "project-dir", "shared-fs", "shared-project"].includes(entry.kind) ? "Open project" : ["binary", "packed-program"].includes(entry.kind) ? "Add binary to project" : entry.kind === "file" ? "Inspect file" : "Browse folder"} · ${kindTitle(entry.kind)}${entry.programs && entry.programs.length ? " · " + entry.programs.length + " programs" : ""}</span>
                  </button>
                </li>`;
              })}
            </ul>
          </div>
        </div>` : html`<form id="wb-shared-form" className="wb-bin-form" onSubmit=${registerShared}>
          <label>URL
            <input id="wb-shared-url" placeholder="ghidra://127.0.0.1/Repo/Game.exe"
              value=${sharedUrl} onInput=${function (ev) { setSharedUrl(ev.target.value); }} />
          </label>
          <p className="wb-hint">Ghidra Server uses RMI. The user is not part of the URL.</p>
          <label>Server Name<input id="wb-shared-host" value=${sharedHost} onInput=${function (ev) { setSharedHost(ev.target.value); }} /></label>
          <label>Port Number<input id="wb-shared-port" value=${sharedPort} onInput=${function (ev) { setSharedPort(ev.target.value); }} /></label>
          <label>Repository Name<input id="wb-shared-repo" value=${sharedRepo} onInput=${function (ev) { setSharedRepo(ev.target.value); }} /></label>
          <label>User<input id="wb-shared-user" value=${sharedUser} onInput=${function (ev) { setSharedUser(ev.target.value); }} /></label>
          <label>Program<input id="wb-shared-program" value=${sharedProgram} onInput=${function (ev) { setSharedProgram(ev.target.value); }} /></label>
          <p className="wb-hint"><code>${builtSharedUrl() || "ghidra://host/repository"}</code></p>
          <button type="submit" id="wb-shared-add" className="wb-btn wb-btn-primary">Open</button>
        </form>`}
      </${Modal}>

      <${SaveAsDialog} open=${dialog === "save-as"} onClose=${closeDialog} onSubmit=${submitSaveAs} error=${dialogError} menuInvokerRef=${dialogInvokerRef}
        locator=${currentLocator()} project=${dossier} projectTitle=${currentSession&&currentSession.title} workDir=${envDefaults.work_dir}
        target=${saveAsTarget} setTarget=${setSaveAsTarget} name=${saveAsName} setName=${setSaveAsName} destination=${saveAsDest} setDestination=${setSaveAsDest}/>

      <${Modal} open=${dialog === "add-binary"} title="Add binary to this project" onClose=${closeDialog} error=${dialogError} menuInvokerRef=${dialogInvokerRef}
        footer=${html`
          <button type="button" className="wb-btn" onClick=${closeDialog}>Cancel</button>
          <button type="button" className="wb-btn" disabled=${addBusy} onClick=${triggerAddFileUpload}>Choose file…</button>
          <button type="submit" form="wb-add-binary-form" className="wb-btn wb-btn-primary" disabled=${addBusy || !addPath.trim()}>${addBusy ? "Working…" : "Add to project"}</button>
        `}>
        <form id="wb-add-binary-form" onSubmit=${submitAddToProject}>
          ${addBusy ? html`<p role="status">Staging or importing the file…</p>` : null}
          <p className="wb-hint">${currentLocator()
            ? "The file is imported into the open Ghidra project."
            : "This tab has no project yet. Add creates one, then imports the binary."}</p>
          <label>${addFileName ? "Selected file · " + addFileName : "Binary path"}
            <input id="wb-add-path" value=${addPath} disabled=${addBusy} placeholder="Choose a file or enter a server-visible path"
              onInput=${function (ev) { setAddPath(ev.target.value); setAddFileName(""); }}
              onKeyDown=${function (ev) { if (ev.key === "Enter") { ev.preventDefault(); submitAddToProject(ev); } }} />
          </label>
        </form>
      </${Modal}>

      <${Modal} open=${dialog === "access"} title="Shortcuts and menus" onClose=${closeDialog} menuInvokerRef=${dialogInvokerRef}
        footer=${html`<button type="button" className="wb-btn wb-btn-primary" onClick=${closeDialog}>Close</button>`}>
        <p className="wb-hint">Use the menu, the command palette, a right-click, a shortcut, or a button.</p>
        <table className="wb-access-table">
          <thead><tr><th>Command</th><th>Menu</th><th>Palette</th><th>Context</th><th>Key</th></tr></thead>
          <tbody>
            ${WORKBENCH_COMMANDS.map(function (cmd) {
              return html`<tr key=${cmd.id}>
                <td>${cmd.title}</td>
                <td>${cmd.group}</td>
                <td>${accelLabel("mod+K")}</td>
                <td>Right-click</td>
                <td><code>${accelLabel(cmd.accel) || "—"}</code></td>
              </tr>`;
            })}
          </tbody>
        </table>
      </${Modal}>

      <div className="wb-app-shell wb-project-workspace">
        <${Modal} open=${filesOpen} title="Project files" onClose=${function () { setFilesOpen(false); }}>
        <aside id="wb-sidebar" className="wb-sidebar wb-files-drawer"
          onContextMenu=${function (ev) {
            const items = [
              { id: "file.open", title: "Open…" },
              { id: "file.add-binaries", title: "Add to project…" },
              "—",
              { id: "file.save", title: "Save" },
              { id: "file.save-as", title: "Save As…" },
              "—",
              { id: "file.reload", title: "Reload" }
            ].map(decorateCommandItem);
            openCtx(ev, items);
          }}>
          <div id="wb-sources" className="wb-sidebar-section" style=${{ flex: "0 0 " + explorerH + "px", height: explorerH + "px" }}>
            <header className="wb-sidebar-head">
              <h3>Project files</h3>
              <button type="button" className="wb-text-action" data-cmd="file.add-binaries"
                title="Add a binary or program to the open project"
                onClick=${function () { runCommand("file.add-binaries"); }}>Add files</button>
            </header>
            <ul id="wb-binary-list" className="wb-source-tree">
              ${projectCard ? html`<li key=${projectCard.key}
                className=${((activeProjectSlug && slug === activeProjectSlug && !program) ? "on " : "") + "kind-" + projectCard.kind + " wb-source-project"}>
                <button type="button" className="wb-bin" data-slug=${(projectCard.row && projectCard.row.slug) || activeProjectSlug || projectCard.name}
                  onContextMenu=${function (ev) { openCtx(ev, projectCtxItems()); }}
                  onClick=${function () {
                    if (activeProjectSlug) {
                      setSlug(activeProjectSlug);
                      setProgram("");
                      patchActiveSession({ program: "" });
                      beginSelection(null);
                      setEvidencePacket(null);
                    }
                  }}>
                  ${projectCard.name}
                </button>
                ${((projectCard.programs || []).length) ? html`<ul className="wb-programs">
                  ${(projectCard.programs || []).map(function (name) {
                    const meter = programProgress[name] || null;
                    const live = meter && meter.active;
                    const measured = live && Number.isFinite(meter.pct);
                    return html`<li key=${"prog-" + name} className=${"wb-program" + (program === name && slug === activeProjectSlug ? " on" : "") + (live ? " live" : "")}
                      onContextMenu=${function (ev) { openCtx(ev, programCtxItems(name)); }}>
                      <button type="button" className="wb-text-action"
                        title=${name}
                        onClick=${function (ev) {
                          ev.stopPropagation();
                          if (activeProjectSlug) setSlug(activeProjectSlug);
                          selectProgram(name);
                        }}
                        onDoubleClick=${function (ev) {
                          ev.stopPropagation();
                          if (activeProjectSlug) setSlug(activeProjectSlug);
                          selectProgram(name);
                          jumpTo("decompile");
                        }}>${name}</button>
                      <button type="button" className="wb-text-action wb-remove"
                        title=${"Remove " + name + " from this project"}
                        onClick=${function (ev) {
                          ev.stopPropagation();
                          removeProgramFromProject(name);
                        }}>Remove</button>
                      ${live ? html`<span className="wb-prog-pct" title=${meter.tool || ""}>${measured ? meter.pct + "%" : meter.status}</span>` : null}
                      ${measured ? html`<span className="wb-prog-meter" aria-hidden="true"><i style=${{ transform: "scaleX(" + (meter.pct / 100) + ")" }}></i></span>` : null}
                    </li>`;
                  })}
                </ul>` : html`<ul className="wb-programs">
                  <li className="wb-empty" role="status">No program entries are visible in this project yet.</li>
                </ul>`}
              </li>` : null}
              ${!projectCard ? html`<li className="wb-empty" role="status">${currentSession && currentSession.locator
                ? (dossier && dossier.error
                  ? "This tab’s saved project path cannot be read: " + dossier.error
                  : "Reading the saved project for this workspace…")
                : currentSession && currentSession.projectSlug
                  ? "Workspace build: " + currentSession.projectSlug + ". Open a project to browse its program files."
                  : "No project is loaded in this workspace. Use File → Open project."}</li>` : null}
            </ul>
          </div>
          <${SplitHandle} axis="y" label="Resize explorer"
            onDrag=${function (ev) { beginResize(ev, explorerH, setExplorerH, "wb-explorer-h", "y", 80, 720, false); }} />
          <${SymbolTree} program=${program} scopeKey=${targetKey}
            hint=${dossier && dossier.error ? "Symbols need a readable project. " + dossier.error : ""}
            runReadAction=${runReadAction}
            onOpenFunctions=${function () { jumpTo("wb-fnbrowse"); }}
            onSelectFunction=${function (fn, scope) {
              if (scope && scope === targetKey && scope === targetIdentity(targetRef.current)) selectFunctionLeaf(fn.name, fn.addr, scope);
            }} />
        </aside>
        </${Modal}>

      <div className="wb-editor"
        onContextMenu=${function (ev) {
          openCtx(ev, [
            { title: "Refresh this panel", run: function () { reloadIslands(); showToast("Panels refreshed", "success"); } },
            "—",
            { id: "view.palette" },
            { id: "view.cross-match" },
            "—",
            { id: "file.open" },
            { id: "file.add-binaries" }
          ].map(decorateCommandItem));
        }}>
        <${CorpusNavBar} active=${centerTab} moreOpen=${moreOpen}
          onMoreToggle=${setMoreOpen} onJump=${jumpToCorpus} />
        ${editorTabFor(centerTab) === "wb-overview" ? html`<div className="wb-workspace-search">${projectFunctionFilter()}</div>` : null}
        <div className="wb-editor-body" onDragOver=${onIngestDragOver} onDragLeave=${onIngestDragLeave} onDrop=${onDrop}>
          ${renderEditorBody()}
        </div>
      </div>
      </div>
      ${logOpen ? html`<${LogDock}
        entries=${logEntries}
        tab=${logTab}
        onTab=${setLogTab}
        open=${logOpen}
        onToggle=${setLogOpen}
        selectedId=${openLogId}
        onSelect=${setOpenLogId}
        jobs=${jobs}
        selectedJobId=${selectedJobId}
        jobDetail=${jobDetail}
        jobDetailLoading=${jobDetailLoading}
        jobDetailError=${jobDetailError}
        onSelectJob=${selectJobInDock}
        onRetryJobDetail=${retryJobDetail}
        onCancel=${cancelJob}
        onRefreshJobs=${loadJobs}
        onLoadJobHistory=${function () { loadJobs("history"); }}
        jobsRefreshedAt=${jobsRefreshedAt}
        jobsRefreshing=${jobsRefreshing}
        jobsVisibleCount=${jobsVisibleCount}
        jobsScope=${jobsScope}
        jobsLoadingScope=${jobsLoadingScope}
        onShowMoreJobs=${function () { setJobsVisibleCount(function (count) { return Math.min(jobs.length, count + JOB_PAGE_SIZE); }); }}
        jobAdmission=${jobAdmission}
        actions=${actions}
        height=${logH}
        onResize=${function (ev) { beginResize(ev, logH, setLogH, "wb-log-h", "y", 72, 640, true); }}
        onKeyResize=${function (delta) { clampResize(logH + delta, 72, 640, setLogH, "wb-log-h"); }} />` : null}
        <input id="wb-bin-slug" type="hidden" value=${newSlug} />
        <input id="wb-bin-role" type="hidden" value=${role} />
        <input id="wb-bin-label" type="hidden" value=${label} />
      </main>

      <footer className="wb-status" id="wb-status">
        <span id="wb-status-source">${(currentSession && currentSession.title) || "No project"}</span>
        <span id="wb-status-program">${program || "No program"}</span>
        <span id="wb-status-selection">${selected
          ? ((selected.name || selected.addr) + " " + (selected.addr || ""))
          : (total ? total + " functions" : "No function")}</span>
        <span id="job-status" title=${jobsRefreshedAt ? "Last checked " + new Date(jobsRefreshedAt).toLocaleString() : "Job status has not been checked"}>${jobsRefreshedAt
          ? (running.length ? running.length + " active" : "No active jobs · checked")
          : jobs.length ? "New job · refresh for status" : "Jobs not checked"}</span>
        ${statusError
          ? html`<span id="wb-status-error" className="wb-status-error" role="alert">${statusError}
              <button type="button" className="wb-status-dismiss" aria-label="Dismiss error"
                onClick=${function () { setStatusError(""); }}>×</button></span>`
          : html`<span id="wb-last-action" className="wb-hint" aria-live="polite" aria-atomic="true">${lastNote}</span>`}
      </footer>
    </div>`;
  }

  const root = document.getElementById("wb-root");
  if (root && window.ReactDOM) {
    ReactDOM.createRoot(root).render(e(App));
  }
})();
