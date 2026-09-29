// Static cockpit: the no-build twin of /react/#cockpit. Same contract (docs/cockpit/API.md),
// same deep-link hash (#cockpit?program=<id>&fn=<index>). Every value comes from the API.
(function () {
  "use strict";

  var API = "/dashboard/api/cockpit";
  var COLORS = {
    0: ["#2e333d", "#474e5c"],
    1: ["#28446f", "#4a78bb"],
    2: ["#7fd6a4", "#b1f0cc"]
  };
  var DIM = "#1d2027";
  var SEL = "#f2f4f7";
  var TIERS = { 0: "No name", 1: "Human", 2: "Debug info", 3: "Symbols", 4: "Derived", 5: "Placeholder" };
  var MIN_SCALE = 0.35, MAX_SCALE = 160;

  var st = {
    summary: null,
    programId: "",
    cells: null,
    view: null,
    cols: 1,
    selected: -1,
    filter: "all",
    matches: [],
    matchAt: -1,
    pendingFn: -1,
    lensToken: 0,
    drawQueued: false
  };

  function $(id) { return document.getElementById(id); }
  function fmt(n) { return n == null ? "–" : Number(n).toLocaleString(); }
  function hex(n) { return "0x" + Number(n).toString(16).padStart(8, "0"); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      return r.json().then(function (body) {
        if (!body || body.ok === false) throw new Error((body && body.error) || ("HTTP " + r.status));
        return body;
      });
    });
  }

  // ------------------------------------------------------------------ hash route
  function readHash() {
    var h = location.hash, q = h.indexOf("?");
    if (h.indexOf("#cockpit") !== 0 || q < 0) return {};
    var p = new URLSearchParams(h.slice(q + 1)), fn = Number(p.get("fn"));
    return { program: p.get("program") || "", fn: p.has("fn") && Number.isInteger(fn) && fn >= 0 ? fn : -1 };
  }
  function writeHash() {
    var p = new URLSearchParams();
    if (st.programId) p.set("program", st.programId);
    if (st.programId && st.selected >= 0) p.set("fn", String(st.selected));
    var s = p.toString(), h = s ? "#cockpit?" + s : "#cockpit";
    if (location.hash !== h) history.replaceState(history.state, "", location.pathname + location.search + h);
  }

  // ------------------------------------------------------------------ summary
  function setConn(text, cls) {
    var el = $("ck-conn");
    el.textContent = text;
    el.className = "ck-conn" + (cls ? " " + cls : "");
  }

  function renderSummary() {
    var s = st.summary, t = s.totals || {};
    var rows = [
      ["Builds", t.binaries], ["Functions", t.functions], ["Shared identities", t.logical],
      ["Bound", t.bound], ["Identities with recovered C", t.recovered_logical],
      ["Named", t.named_above_placeholder]
    ];
    $("ck-totals").innerHTML = rows.map(function (r) {
      return "<div><dt>" + esc(r[0]) + "</dt><dd>" + fmt(r[1]) + "</dd></div>";
    }).join("");
    var list = $("ck-program-list");
    list.innerHTML = (s.programs || []).map(function (p) {
      var fns = 0, bound = 0, rc = 0;
      p.builds.forEach(function (b) { fns += b.functions || 0; bound += b.bound || 0; rc += b.real_c || 0; });
      var pb = fns ? (100 * bound / fns) : 0, pr = fns ? (100 * rc / fns) : 0;
      return '<li role="option" tabindex="-1" data-id="' + esc(p.id) + '" aria-selected="' + (p.id === st.programId) + '">' +
        "<b>" + esc(p.label) + "</b><small>" + p.builds.length + " build" + (p.builds.length === 1 ? "" : "s") +
        " · " + fmt(p.n) + " functions in " + esc(p.ref) + "</small>" +
        '<span class="ck-bar" title="' + pb.toFixed(1) + '% bound, ' + pr.toFixed(2) + '% recovered C">' +
        '<i style="width:' + pb + '%;background:#4a78bb"></i><i style="width:' + pr + '%;background:#7fd6a4"></i></span></li>';
    }).join("") || '<li class="ck-muted">No programs in this corpus.</li>';
  }

  function loadSummary() {
    if (!st.summary) showEmpty("Reading the corpus… the first read of a large corpus can take a minute.");
    return getJSON(API + "/summary").then(function (s) {
      st.summary = s;
      renderActivity(s.activity || [], true);
      var loc = readHash(), ids = (s.programs || []).map(function (p) { return p.id; });
      if (!st.programId) {
        st.programId = ids.indexOf(loc.program) >= 0 ? loc.program : (ids[0] || "");
        st.pendingFn = ids.indexOf(loc.program) >= 0 ? loc.fn : -1;
      }
      renderSummary();
      if (st.programId) loadCells(st.programId);
    }).catch(function (e) {
      setConn("Corpus unavailable: " + e.message, "offline");
      showEmpty("The cockpit could not read the corpus database. " + e.message);
    });
  }

  // ------------------------------------------------------------------ cells
  function showEmpty(text) {
    var el = $("ck-empty");
    el.hidden = !text;
    el.textContent = text || "";
  }

  function loadCells(id) {
    st.cells = null;
    st.selected = -1;
    showEmpty("Loading the map…");
    queueDraw();
    getJSON(API + "/program/" + encodeURIComponent(id) + "/cells").then(function (c) {
      if (id !== st.programId) return;
      var n = c.n, state = new Uint8Array(n), tier = new Uint8Array(n), nb = new Uint16Array(n);
      for (var i = 0; i < n; i++) {
        state[i] = c.state.charCodeAt(i) - 48;
        tier[i] = c.tier.charCodeAt(i) - 48;
        nb[i] = c.nb[i] || 0;
      }
      st.cells = { n: n, ref: c.ref, addr: c.addr, size: c.size, state: state, tier: tier, nb: nb, names: c.names || {} };
      showEmpty(n ? "" : "This program has no functions yet.");
      fit();
      if (st.pendingFn >= 0 && st.pendingFn < n) select(st.pendingFn, true);
      st.pendingFn = -1;
      writeHash();
    }).catch(function (e) {
      if (id === st.programId) showEmpty("Could not load this program's map: " + e.message);
    });
  }

  function applyCellChanges(msg) {
    var c = st.cells;
    if (!c || msg.program_id !== st.programId) return;
    (msg.changes || []).forEach(function (ch) {
      var i = ch[0];
      if (i >= 0 && i < c.n) { c.state[i] = ch[1]; c.nb[i] = ch[2]; c.tier[i] = ch[3]; }
    });
    queueDraw();
  }

  function named(i) { var t = st.cells.tier[i]; return t >= 1 && t <= 3; }
  function passes(i) {
    var f = st.filter;
    if (f === "all") return true;
    if (f === "named") return named(i);
    return st.cells.state[i] === Number(f);
  }

  // ------------------------------------------------------------------ view + draw
  var canvas = $("ck-canvas"), ctx = canvas.getContext("2d");

  function size() {
    var r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    var w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    return { w: r.width, h: r.height, dpr: dpr };
  }
  function clampScale(s) { return Math.max(MIN_SCALE, Math.min(MAX_SCALE, isFinite(s) && s > 0 ? s : 1)); }

  function fit() {
    var c = st.cells, d = size();
    if (!c || !c.n) { st.view = null; queueDraw(); return; }
    st.cols = Math.max(1, Math.min(c.n, Math.ceil(Math.sqrt(c.n * d.w / Math.max(1, d.h)))));
    var rows = Math.ceil(c.n / st.cols), pad = 8;
    var scale = clampScale(Math.min((d.w - pad * 2) / st.cols, (d.h - pad * 2) / rows));
    st.view = { scale: scale, ox: (d.w - st.cols * scale) / 2, oy: (d.h - rows * scale) / 2 };
    queueDraw();
  }

  function zoomAt(factor, sx, sy) {
    var v = st.view;
    if (!v) return;
    var scale = clampScale(v.scale * factor), k = scale / v.scale;
    st.view = { scale: scale, ox: sx - (sx - v.ox) * k, oy: sy - (sy - v.oy) * k };
    queueDraw();
  }

  function centerOn(i) {
    var d = size(), v = st.view, scale = clampScale(Math.max(v.scale, 14));
    st.view = { scale: scale, ox: d.w / 2 - (i % st.cols + 0.5) * scale, oy: d.h / 2 - (Math.floor(i / st.cols) + 0.5) * scale };
  }

  function queueDraw() {
    if (st.drawQueued) return;
    st.drawQueued = true;
    requestAnimationFrame(draw);
  }

  function draw() {
    st.drawQueued = false;
    var d = size();
    ctx.setTransform(d.dpr, 0, 0, d.dpr, 0, 0);
    ctx.clearRect(0, 0, d.w, d.h);
    var c = st.cells, v = st.view;
    if (!c || !v) return;
    var s = v.scale, gap = s >= 6 ? 1 : s >= 3.5 ? 0.5 : 0, box = Math.max(0.5, s - gap);
    var rows = Math.ceil(c.n / st.cols);
    var r0 = Math.max(0, Math.floor(-v.oy / s)), r1 = Math.min(rows - 1, Math.ceil((d.h - v.oy) / s));
    var c0 = Math.max(0, Math.floor(-v.ox / s)), c1 = Math.min(st.cols - 1, Math.ceil((d.w - v.ox) / s));
    for (var r = r0; r <= r1; r++) {
      for (var col = c0; col <= c1; col++) {
        var i = r * st.cols + col;
        if (i >= c.n) break;
        ctx.fillStyle = passes(i) ? COLORS[c.state[i]][named(i) ? 1 : 0] : DIM;
        ctx.fillRect(v.ox + col * s, v.oy + r * s, box, box);
      }
    }
    if (st.selected >= 0) {
      var sx = v.ox + (st.selected % st.cols) * s, sy = v.oy + Math.floor(st.selected / st.cols) * s;
      ctx.strokeStyle = SEL;
      ctx.lineWidth = 2;
      ctx.strokeRect(sx - 2, sy - 2, box + 4, box + 4);
    }
    if (s >= 40) {
      ctx.fillStyle = "#0f1115";
      ctx.font = "10px sans-serif";
      for (r = r0; r <= r1; r++) {
        for (col = c0; col <= c1; col++) {
          i = r * st.cols + col;
          if (i >= c.n) break;
          var nm = c.names[i];
          if (nm) ctx.fillText(nm.slice(0, Math.floor(box / 6)), v.ox + col * s + 3, v.oy + r * s + 13, box - 6);
        }
      }
    }
  }

  function hit(sx, sy) {
    var c = st.cells, v = st.view;
    if (!c || !v) return -1;
    var col = Math.floor((sx - v.ox) / v.scale), row = Math.floor((sy - v.oy) / v.scale);
    if (col < 0 || col >= st.cols || row < 0) return -1;
    var i = row * st.cols + col;
    return i < c.n ? i : -1;
  }

  // ------------------------------------------------------------------ selection + lens
  function select(i, recenter) {
    if (!st.cells || i < 0 || i >= st.cells.n) return;
    st.selected = i;
    if (recenter) centerOn(i);
    queueDraw();
    writeHash();
    loadLens(i);
  }

  function lensRow(inst) {
    var href = "/dashboard/function/" + encodeURIComponent(inst.slug) + "/" + encodeURIComponent(hex(inst.addr));
    return "<tr><td>" + esc(inst.slug) + '<br><small class="ck-muted">' + esc(inst.platform || "") + "</small></td>" +
      '<td><a class="addr" href="' + href + '">' + hex(inst.addr) + "</a></td>" +
      "<td>" + esc(inst.method || "") + (inst.confidence != null ? "<br><small>" + Number(inst.confidence).toFixed(2) + "</small>" : "") + "</td></tr>";
  }

  function neighbours(title, list) {
    if (!list || !list.length) return "";
    return "<h3>" + esc(title) + " (" + list.length + ")</h3><ul>" + list.map(function (n) {
      return '<li><button type="button" data-index="' + Number(n.index) + '">' + esc(n.name || hex(n.addr)) + "</button></li>";
    }).join("") + "</ul>";
  }

  function loadLens(i) {
    var token = ++st.lensToken, c = st.cells, el = $("ck-lens");
    var stateText = ["Unbound in this build", "Bound to a shared identity", "C with a byte-exact receipt (this build or a sibling)"][c.state[i]];
    el.innerHTML = '<p class="ck-name">' + esc(c.names[i] || hex(c.addr[i])) + "</p>" +
      '<span class="ck-chip">' + esc(stateText) + '</span><span class="ck-chip">' + esc(TIERS[c.tier[i]] || "") + "</span>" +
      '<p class="ck-muted">Loading…</p>';
    getJSON(API + "/function?program_id=" + encodeURIComponent(st.programId) + "&index=" + i).then(function (f) {
      if (token !== st.lensToken) return;
      var rec = (f.recovered || []).map(function (r) {
        return "<tr><td>" + esc(r.binary_slug) + '</td><td class="addr">' + hex(r.addr) + "</td><td>" +
          (r.real_c ? "C" : "assembly floor") + "</td></tr>";
      }).join("");
      el.innerHTML = '<p class="ck-name">' + esc(f.name || hex(c.addr[i])) + "</p>" +
        '<span class="ck-chip">' + esc(stateText) + '</span><span class="ck-chip">' + esc(f.tier_name || TIERS[f.tier] || "") + "</span>" +
        (f.logical_id ? '<span class="ck-chip">identity ' + Number(f.logical_id) + "</span>" : "") +
        (f.signature ? '<p class="addr">' + esc(f.signature) + "</p>" : "") +
        (f.source_file ? '<p class="ck-muted">' + esc(f.source_file) + "</p>" : "") +
        "<h3>Found in " + (f.instances || []).length + " build" + ((f.instances || []).length === 1 ? "" : "s") + "</h3>" +
        "<table><tbody>" + (f.instances || []).map(lensRow).join("") + "</tbody></table>" +
        ((f.absent || []).length ? "<h3>Not found in</h3><p>" + f.absent.map(esc).join(", ") + "</p>" : "") +
        (rec ? "<h3>Recovered source</h3><table><tbody>" + rec + "</tbody></table>" : "") +
        neighbours("Called by", f.callers) + neighbours("Calls", f.callees);
    }).catch(function (e) {
      if (token === st.lensToken) el.innerHTML = '<p class="ck-muted">Could not load this function: ' + esc(e.message) + "</p>";
    });
  }

  // ------------------------------------------------------------------ activity
  function renderActivity(events, replace) {
    var ol = $("ck-activity");
    var html = events.map(function (e) {
      var ts = typeof e.ts === "number" ? new Date(e.ts * (e.ts < 1e12 ? 1000 : 1)) : new Date(e.ts);
      var time = isNaN(ts) ? "" : ts.toLocaleTimeString();
      var status = String(e.status || "");
      return "<li><time>" + esc(time) + '</time><span class="lane">' + esc(e.lane) + "</span><span>" + esc(e.label) +
        '</span><span class="st-' + esc(status) + '">' + esc(status) + "</span></li>";
    }).join("");
    if (replace) ol.innerHTML = html || '<li class="ck-muted">No recorded work yet.</li>';
    else {
      ol.insertAdjacentHTML("afterbegin", html);
      while (ol.children.length > 100) ol.removeChild(ol.lastChild);
    }
  }

  // ------------------------------------------------------------------ live stream
  function connect() {
    if (!window.EventSource) { setConn("Live updates unavailable in this browser", "offline"); return; }
    var es = new EventSource(API + "/stream");
    es.addEventListener("hello", function () { setConn("Live", "live"); });
    es.addEventListener("summary", function (m) {
      try { var s = JSON.parse(m.data); s.activity = st.summary ? st.summary.activity : []; st.summary = s; renderSummary(); } catch (e) { /* keep last */ }
    });
    es.addEventListener("cells", function (m) { try { applyCellChanges(JSON.parse(m.data)); } catch (e) { /* ignore */ } });
    es.addEventListener("activity", function (m) { try { renderActivity([JSON.parse(m.data)], false); } catch (e) { /* ignore */ } });
    es.onerror = function () { setConn("Reconnecting…", "offline"); };
  }

  // ------------------------------------------------------------------ input
  var drag = null;
  canvas.addEventListener("pointerdown", function (e) {
    canvas.setPointerCapture(e.pointerId);
    drag = { x: e.offsetX, y: e.offsetY, moved: false };
  });
  canvas.addEventListener("pointermove", function (e) {
    if (!drag || !st.view) return;
    var dx = e.offsetX - drag.x, dy = e.offsetY - drag.y;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    drag.moved = true;
    st.view.ox += dx; st.view.oy += dy;
    drag.x = e.offsetX; drag.y = e.offsetY;
    queueDraw();
  });
  canvas.addEventListener("pointerup", function (e) {
    if (drag && !drag.moved) { var i = hit(e.offsetX, e.offsetY); if (i >= 0) select(i, false); }
    drag = null;
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    zoomAt(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY);
  }, { passive: false });
  canvas.addEventListener("keydown", function (e) {
    var c = st.cells;
    if (!c || !c.n) return;
    var i = st.selected < 0 ? 0 : st.selected, d = size(), next = i;
    switch (e.key) {
      case "ArrowLeft": next = i - 1; break;
      case "ArrowRight": next = i + 1; break;
      case "ArrowUp": next = i - st.cols; break;
      case "ArrowDown": next = i + st.cols; break;
      case "PageUp": next = i - st.cols * 10; break;
      case "PageDown": next = i + st.cols * 10; break;
      case "Home": next = 0; break;
      case "End": next = c.n - 1; break;
      case "+": case "=": zoomAt(1.4, d.w / 2, d.h / 2); e.preventDefault(); return;
      case "-": zoomAt(1 / 1.4, d.w / 2, d.h / 2); e.preventDefault(); return;
      case "Enter": {
        var a = $("ck-lens").querySelector("a.addr");
        if (a) location.href = a.href;
        return;
      }
      default: return;
    }
    e.preventDefault();
    select(Math.max(0, Math.min(c.n - 1, next)), false);
    var v = st.view, x = v.ox + (st.selected % st.cols) * v.scale, y = v.oy + Math.floor(st.selected / st.cols) * v.scale;
    if (x < 0 || y < 0 || x + v.scale > d.w || y + v.scale > d.h) { centerOn(st.selected); queueDraw(); }
  });

  $("ck-program-list").addEventListener("click", function (e) {
    var li = e.target.closest("li[data-id]");
    if (!li || li.dataset.id === st.programId) return;
    st.programId = li.dataset.id;
    renderSummary();
    loadCells(st.programId);
  });
  $("ck-program-list").addEventListener("keydown", function (e) {
    var items = Array.prototype.slice.call(this.querySelectorAll("li[data-id]"));
    var at = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var n = items[Math.max(0, Math.min(items.length - 1, at + (e.key === "ArrowDown" ? 1 : -1)))];
      if (n) n.focus();
    } else if ((e.key === "Enter" || e.key === " ") && at >= 0) {
      e.preventDefault();
      items[at].click();
    }
  });
  $("ck-program-list").addEventListener("focusin", function () {
    var cur = this.querySelector('li[aria-selected="true"]');
    this.querySelectorAll("li[data-id]").forEach(function (li) { li.tabIndex = li === cur ? 0 : -1; });
  });
  $("ck-lens").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-index]");
    if (b) select(Number(b.dataset.index), true);
  });
  $("ck-filter").addEventListener("change", function () { st.filter = this.value; queueDraw(); });
  $("ck-fit").addEventListener("click", fit);
  $("ck-q").addEventListener("input", function () { st.matches = []; st.matchAt = -1; });
  $("ck-search").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = $("ck-q").value.trim().toLowerCase(), c = st.cells;
    if (!q || !c) return;
    if (!st.matches.length) {
      st.matches = Object.keys(c.names).filter(function (k) { return c.names[k].toLowerCase().indexOf(q) >= 0; })
        .map(Number).sort(function (a, b) { return a - b; });
      st.matchAt = -1;
    }
    if (!st.matches.length) { $("ck-q").setCustomValidity("No named function matches"); $("ck-q").reportValidity(); $("ck-q").setCustomValidity(""); return; }
    st.matchAt = (st.matchAt + 1) % st.matches.length;
    select(st.matches[st.matchAt], true);
  });
  window.addEventListener("resize", function () { if (st.cells) fit(); });
  window.addEventListener("hashchange", function () {
    var loc = readHash();
    if (loc.program && loc.program !== st.programId) { st.programId = loc.program; st.pendingFn = loc.fn; renderSummary(); loadCells(loc.program); }
    else if (loc.fn >= 0 && loc.fn !== st.selected) select(loc.fn, true);
  });

  document.title = "AgentDecompile · Cockpit";
  loadSummary();
  connect();
})();
