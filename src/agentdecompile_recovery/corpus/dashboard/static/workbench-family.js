/* Recorded family relationships. Layout never supplies matching evidence. */
(function () {
  "use strict";
  const html = htm.bind(React.createElement);
  const { useMemo, useRef, useState } = React;
  const GRAPH_LIMIT = 48;
  const label = build => String(build.name || build.program || build.slug || build.id);
  const ids = row => (Array.isArray(row.binaryIds) && row.binaryIds.length ? row.binaryIds : [row.id]).map(String);
  const paths = row => (Array.isArray(row.sourcePaths) && row.sourcePaths.length ? row.sourcePaths : [row.repo]).filter(Boolean);
  const pairKey = (a, b) => JSON.stringify([a, b].sort());
  const number = value => Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : 0;

  const edgeLabel = edge => edge.kind === "recorded_identity" ? "at least " + edge.count + " sampled identity witnesses" : edge.count + " accepted matches";
  function familyModel(builds, binaries, relationships) {
    const nodes = builds.filter(build => build && build.id != null).map(build => ({
      id: String(build.id), build, name: label(build), peers: [], weight: 0,
    }));
    const members = new Map();
    nodes.forEach(node => (node.build.binaryIds || []).forEach(id => {
      const key = String(id);
      if (!members.has(key)) members.set(key, new Set());
      members.get(key).add(node);
    }));
    const byPath = new Map();
    binaries.forEach(binary => paths(binary).forEach(path => {
      if (!byPath.has(path)) byPath.set(path, new Set());
      ids(binary).forEach(id => (members.get(id) || []).forEach(node => byPath.get(path).add(node)));
    }));
    const receipts = new Map();
    binaries.forEach(binary => ((binary.variant_group || {}).evidence || []).forEach(receipt => {
      if (!receipt || !receipt.receipt || number(receipt.acceptedMatches) <= 0 || !receipt.source || !receipt.target || receipt.source === receipt.target) return;
      const key = pairKey(receipt.source, receipt.target);
      const previous = receipts.get(key);
      if (!previous || number(receipt.completedAt) > number(previous.completedAt)) receipts.set(key, receipt);
    }));
    let unresolved = 0;
    const pairs = new Map();
    receipts.forEach(receipt => {
      const source = Array.from(byPath.get(receipt.source) || []);
      const target = Array.from(byPath.get(receipt.target) || []);
      if (!source.length || !target.length) return; // Receipt lies outside open-project scope.
      let choices = source.flatMap(a => target.filter(b => a.id !== b.id).map(b => [a, b]));
      if (choices.length > 1) {
        // Repeated project memberships cannot be guessed from a display name.
        choices = choices.filter(([a, b]) => (a.build.projectIds || []).some(id => (b.build.projectIds || []).includes(id)));
      }
      if (choices.length !== 1) { unresolved += 1; return; }
      const [a, b] = choices[0];
      const key = pairKey(a.id, b.id);
      const previous = pairs.get(key);
      if (!previous || number(receipt.completedAt) > number(previous.receipt.completedAt)) {
        pairs.set(key, { key, a, b, count: number(receipt.acceptedMatches), receipt });
      }
    });
    ((relationships || {}).edges || []).forEach(relation => {
      if (!relation || relation.kind !== "recorded_identity" || number(relation.observedCorrespondences) < 1) return;
      const source = Array.from(members.get(String(relation.sourceBinaryId)) || []);
      const target = Array.from(members.get(String(relation.targetBinaryId)) || []);
      let choices = source.flatMap(a => target.filter(b => a.id !== b.id).map(b => [a, b]));
      if (choices.length > 1) choices = choices.filter(([a, b]) => (a.build.projectIds || []).some(id => (b.build.projectIds || []).includes(id)));
      if (choices.length !== 1) { if (choices.length) unresolved += 1; return; }
      const [a, b] = choices[0], key = pairKey(a.id, b.id);
      // External accepted-run receipts and sampled installed identities are
      // distinct evidence. Never add their counts or invent a receipt path.
      const previous = pairs.get(key);
      if (previous) {
        previous.identityWitnesses = (relation.witnesses || []).map(witness => ({ ...witness, sourceBinaryId: relation.sourceBinaryId, targetBinaryId: relation.targetBinaryId }));
        return;
      }
      pairs.set(key, { key, a, b, count: number(relation.observedCorrespondences), kind: "recorded_identity", relation });
    });
    const edges = Array.from(pairs.values());
    edges.forEach(edge => {
      edge.a.peers.push({ node: edge.b, edge });
      edge.b.peers.push({ node: edge.a, edge });
      edge.a.weight += edge.count;
      edge.b.weight += edge.count;
    });
    nodes.sort((a, b) => b.peers.length - a.peers.length || b.weight - a.weight || a.id.localeCompare(b.id));
    nodes.forEach(node => node.peers.sort((a, b) => b.edge.count - a.edge.count || a.node.id.localeCompare(b.node.id)));
    return { nodes, edges, connected: nodes.filter(node => node.peers.length), isolated: nodes.filter(node => !node.peers.length), unresolved };
  }

  function positions(nodes) {
    const result = new Map();
    if (!nodes.length) return result;
    result.set(nodes[0].id, { x: 600, y: 460 });
    let start = 1;
    // Stronger-connected peers appear nearer the anchor; no force layout drift.
    [[8, 220, 165], [16, 410, 300], [23, 510, 410]].forEach(([capacity, rx, ry]) => {
      const ring = nodes.slice(start, start + capacity);
      ring.forEach((node, i) => {
        const angle = -Math.PI / 2 + i * Math.PI * 2 / ring.length;
        result.set(node.id, { x: 600 + Math.cos(angle) * rx, y: 460 + Math.sin(angle) * ry });
      });
      start += capacity;
    });
    return result;
  }

  function FamilyMap({ builds = [], binaries = [], relationships, selectedIds = [], onSelection, onFocus }) {
    const model = useMemo(() => familyModel(builds, binaries, relationships), [builds, binaries, relationships]);
    const selected = new Set(Array.from(selectedIds || [], String));
    const [edgeKey, setEdgeKey] = useState("");
    const [relationNodeId, setRelationNodeId] = useState("");
    const lastRange = useRef(null);
    const componentId = React.useId().replace(/:/g, "");
    const visible = model.connected.slice(0, GRAPH_LIMIT);
    const placed = positions(visible);
    const edge = model.edges.find(item => item.key === edgeKey);
    const relationNode = model.nodes.find(node => node.id === relationNodeId);
    const anchor = model.connected[0];
    const emit = next => typeof onSelection === "function" && onSelection(Array.from(next));
    function toggle(node, event) {
      const next = new Set(selected);
      const checked = !next.has(node.id);
      const range = event && event.shiftKey && lastRange.current;
      const from = range ? model.nodes.findIndex(item => item.id === lastRange.current) : -1;
      const to = model.nodes.findIndex(item => item.id === node.id);
      (from >= 0 ? model.nodes.slice(Math.min(from, to), Math.max(from, to) + 1) : [node]).forEach(item => checked ? next.add(item.id) : next.delete(item.id));
      lastRange.current = node.id;
      emit(next);
    }
    function activate(node, event) {
      if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      toggle(node, event);
    }
    const card = node => html`<li key=${node.id} className=${"wb-family-member" + (selected.has(node.id) ? " is-selected" : "")}>
      <label className="wb-family-check" title=${node.name + " — " + (node.build.program || node.build.slug || "Program binding unavailable")}>
        <input type="checkbox" checked=${selected.has(node.id)} onClick=${event => toggle(node, event)} onChange=${() => {}} />
        <span><strong>${node.name}</strong></span>
      </label>
      ${onFocus ? html`<button type="button" className="wb-family-inspect" onClick=${() => onFocus(node.build)} aria-label=${"Inspect " + node.name}>Inspect</button>` : null}
      <div className="wb-family-peerline">${node.peers.length ? html`<button type="button" className="wb-family-connections" aria-expanded=${relationNodeId === node.id} aria-label=${"Inspect " + node.peers.length + " recorded connections for " + node.name} onClick=${() => { setRelationNodeId(relationNodeId === node.id ? "" : node.id); setEdgeKey(""); }}>${node.peers.length} recorded ${node.peers.length === 1 ? "connection" : "connections"}</button>` : html`<span>No connection observed</span>`}
        ${node === anchor ? html`<span className="wb-family-anchor-tag">Observed comparison anchor</span>` : null}</div>
    </li>`;
    return html`<section className="wb-family" aria-labelledby=${componentId + "-title"}>
      <header className="wb-family-heading"><div><h3 id=${componentId + "-title"}>Build relationships</h3><p>Choose builds to narrow the shared workspace. Inspect opens a build without changing that set.</p></div>
        <div className="wb-family-controls"><span role="status">${selected.size ? selected.size + " builds selected" : "No builds selected"}</span>
          <button type="button" onClick=${() => emit(new Set(model.nodes.map(node => node.id)))} disabled=${!model.nodes.length}>Select all</button>
          <button type="button" onClick=${() => emit(new Set())} disabled=${!selected.size}>Clear selection</button></div></header>
      ${!model.nodes.length ? html`<p className="wb-family-empty">Load project facts to show its builds and recorded relationships.</p>` : null}
      ${relationships && relationships.sampled ? html`<p className="wb-family-limit">Stored identity connections are a bounded sample, not total match counts.${relationships.partial ? " The read budget limited this snapshot; additional connections may exist." : " Additional connections may exist outside the sampled functions."} Refresh project facts to update this map.</p>` : null}
      ${relationships && relationships.available === false ? html`<p className="wb-family-limit">${relationships.reason || "Stored identity relationships could not be observed."}</p>` : null}
      ${anchor ? html`<div className="wb-family-topology" role="group" aria-label="Recorded build relationship map">
        <div className="wb-family-map-caption"><strong>${anchor.name}</strong> is the most connected build in this observed snapshot. Placement is navigation, not proof of equivalent code.</div>
        <div className="wb-family-canvas"><svg viewBox="0 0 1200 920" aria-label="Select builds in the relationship map; the full labelled build list follows">
          <circle className="wb-family-orbit" cx="600" cy="460" r="165" fill="none" />
          ${model.edges.filter(item => placed.has(item.a.id) && placed.has(item.b.id)).map(item => {
            const a = placed.get(item.a.id), b = placed.get(item.b.id);
            return html`<g key=${item.key}><line className=${"wb-family-edge" + (edgeKey === item.key ? " is-active" : "")} x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y} strokeDasharray=${item.kind === "recorded_identity" ? "6 4" : undefined} strokeWidth=${Math.min(5, 1 + Math.log10(1 + item.count))}><title>${item.a.name + " ↔ " + item.b.name + ": " + edgeLabel(item) + "; correspondence is not source parity"}</title></line></g>`;
          })}
          ${visible.map(node => {
            const p = placed.get(node.id), isAnchor = node === anchor;
            const shortName = node.name.length > 24 ? node.name.slice(0, 21) + "…" : node.name;
            return html`<g key=${node.id} className=${"wb-family-node" + (selected.has(node.id) ? " is-selected" : "") + (isAnchor ? " is-anchor" : "")} transform=${"translate(" + p.x + "," + p.y + ")"} role="button" tabIndex="0" aria-pressed=${selected.has(node.id)} aria-label=${node.name + ", " + node.peers.length + " recorded connections. Toggle build selection."} onClick=${event => activate(node, event)} onKeyDown=${event => activate(node, event)}>
              <title>${node.name + " — " + (node.build.program || "")}</title><circle r=${isAnchor ? 18 : 11} /><text y=${isAnchor ? 37 : 29} textAnchor="middle">${shortName}</text>
            </g>`;
          })}
        </svg></div>
        ${model.connected.length > GRAPH_LIMIT ? html`<p className="wb-family-limit">Map shows the ${GRAPH_LIMIT} most connected builds. All ${model.nodes.length} builds and their recorded peers remain in the list below.</p>` : null}
      </div>` : model.nodes.length ? html`<p className="wb-family-empty">No usable relationship was observed in the available snapshot. Builds remain separate; missing or unsampled evidence does not establish that they are unrelated.</p>` : null}
      ${relationNode ? html`<aside className="wb-family-relation" aria-label=${"Recorded connections for " + relationNode.name}><strong>${relationNode.name}: recorded connections</strong>
        <ul className="wb-family-peers">${relationNode.peers.map(peer => html`<li key=${peer.node.id}><button type="button" onClick=${() => setEdgeKey(peer.edge.key)} aria-pressed=${edgeKey === peer.edge.key}>${peer.node.name}<span>${edgeLabel(peer.edge)}</span></button></li>`)}</ul>
        <button type="button" onClick=${() => { setRelationNodeId(""); setEdgeKey(""); }}>Close connections</button></aside>` : null}
      ${edge ? html`<aside className="wb-family-relation" aria-label="Selected relationship evidence"><strong>${edge.a.name} ↔ ${edge.b.name}</strong>
        <span>${edgeLabel(edge)}${edge.receipt ? " · " + (edge.receipt.related ? "meets the recorded family display policy" : "below the recorded family display policy") : " · unique stored memberships with checked lineage"}</span>
        <span>Correspondence is not matching C, byte equality or ABI compatibility.</span>
        ${edge.receipt ? html`<code>${edge.receipt.receipt}</code>` : html`<ul>${(edge.relation.witnesses || []).map(witness => html`<li key=${witness.logicalId}>Identity ${witness.logicalId}: ${"0x" + witness.sourceAddr.toString(16)} ↔ ${"0x" + witness.targetAddr.toString(16)} · ${witness.sourceMethod || "method not recorded"} / ${witness.targetMethod || "method not recorded"}</li>`)}</ul>`}
        ${edge.receipt && edge.identityWitnesses && edge.identityWitnesses.length ? html`<div><span>Additional sampled stored identity witnesses; not added to the receipt's accepted-match count.</span><ul>${edge.identityWitnesses.map(witness => html`<li key=${witness.logicalId}>Identity ${witness.logicalId}: binary ${witness.sourceBinaryId} ${"0x" + witness.sourceAddr.toString(16)} ↔ binary ${witness.targetBinaryId} ${"0x" + witness.targetAddr.toString(16)} · ${witness.sourceMethod || "method not recorded"} / ${witness.targetMethod || "method not recorded"}</li>`)}</ul></div>` : null}
        <button type="button" onClick=${() => setEdgeKey("")}>Close relationship detail</button></aside>` : null}
      ${model.unresolved ? html`<p className="wb-family-limit">${model.unresolved} recorded ${model.unresolved === 1 ? "relation is" : "relations are"} not drawn because project membership is ambiguous. No connection was guessed.</p>` : null}
      <div className="wb-family-inventory" tabIndex="0" role="region" aria-label="Build selection; scroll to see every build">
        ${model.connected.length ? html`<ul className="wb-family-members" aria-label="Connected builds; Shift-click a checkbox to select a range">${model.connected.map(card)}</ul>` : null}
        ${model.isolated.length ? html`<div className="wb-family-outskirts"><h4>No connection observed</h4><p>These builds have no connecting lines in this snapshot. They are not proven unrelated; sampled evidence may omit existing connections.</p><ul className="wb-family-members" aria-label="Builds without an observed connection">${model.isolated.map(card)}</ul></div>` : null}
      </div>
    </section>`;
  }
  window.AgentDecompileFamilyMap = FamilyMap;
})();
