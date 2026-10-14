/* Paired call neighborhoods: solid arrows are calls, dotted links are recorded identities. */
(function () {
  "use strict";
  const html = htm.bind(React.createElement);
  const {useState, useEffect, useRef, useId} = React;
  const address = value => typeof value === "number" ? "0x" + value.toString(16) : String(value || "");
  const short = (value, limit) => String(value || "Unnamed function").length > limit ? String(value).slice(0, limit - 1) + "…" : String(value || "Unnamed function");

  function CallComparison({binaryIds, corpusIdentity, source, target, onInspect, claimState, claimDescription, onEvidenceSummary}) {
    const key = JSON.stringify([corpusIdentity, binaryIds, source.binaryId, source.addr, target.binaryId, target.addr]);
    const [packet, setPacket] = useState(null), [error, setError] = useState(""), [visible, setVisible] = useState(6);
    const [zoom, setZoom] = useState(1), [traced, setTraced] = useState(null);
    const canvas = useRef(null), center = useRef(0);
    const sequence = useRef(0), marker = "call-arrow-" + useId().replace(/:/g, "");
    const summaryListener = useRef(onEvidenceSummary);
    summaryListener.current = onEvidenceSummary;
    useEffect(function () {
      const current = ++sequence.current, controller = new AbortController();
      setError(""); setVisible(6); setTraced(null); setZoom(1);
      const q = new URLSearchParams({binary_ids:binaryIds.join(","),corpus_identity:corpusIdentity,
        source_binary_id:String(source.binaryId),source_addr:String(Number(source.addr)),
        target_binary_id:String(target.binaryId),target_addr:String(Number(target.addr))});
      fetch("/api/v1/projects/call-comparison?" + q, {cache:"no-store",signal:AbortSignal.any([controller.signal,AbortSignal.timeout(12000)])})
        .then(async response => {
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || "Recorded call neighborhood could not be read.");
          if (result.corpusIdentity !== corpusIdentity || JSON.stringify(result.binaryIds) !== JSON.stringify(binaryIds) || result.source.binaryId !== source.binaryId || result.target.binaryId !== target.binaryId || Number(result.source.addr) !== Number(source.addr) || Number(result.target.addr) !== Number(target.addr)) throw new Error("The returned call graph does not belong to this correspondence.");
          if (current === sequence.current) setPacket({key,data:result});
        }).catch(reason => {if (!controller.signal.aborted && current === sequence.current) setError(String(reason.message || reason));});
      return function () { controller.abort(); };
    }, [key]);
    const data = packet && packet.key === key ? packet.data : null;
    useEffect(function () {
      if (!summaryListener.current) return;
      if (!data) { summaryListener.current(null); return; }
      const links = data.alignments || [], sides = [data.source, data.target];
      summaryListener.current({ sourceBinary: source.binaryId, sourceAddr: Number(source.addr), targetBinary: target.binaryId, targetAddr: Number(target.addr),
        callers: links.filter(link => link.direction === "callers").length,
        callees: links.filter(link => link.direction === "callees").length,
        sourceCallers: (data.source.callers || []).length, sourceCallees: (data.source.callees || []).length,
        targetCallers: (data.target.callers || []).length, targetCallees: (data.target.callees || []).length,
        truncated: sides.some(side => Object.values(side.truncated || {}).some(Boolean)),
        ambiguousNeighborIdentities: Array.isArray(data.ambiguousLogicalIds) ? data.ambiguousLogicalIds.length : null });
    }, [data, key]);
    function recenter() {
      const viewport = canvas.current;
      if (!viewport) return;
      const svg = viewport.querySelector("svg");
      const ratio = svg ? svg.getBoundingClientRect().height / Number(svg.viewBox.baseVal.height || 1) : 1;
      viewport.scrollTop = Math.max(0, center.current * ratio - viewport.clientHeight / 2);
      viewport.scrollLeft = Math.max(0, (viewport.scrollWidth - viewport.clientWidth) / 2);
    }
    useEffect(function () {
      const frame = requestAnimationFrame(recenter);
      return function () { cancelAnimationFrame(frame); };
    }, [packet, visible, zoom]);
    function inspect(node, side) {
      if (onInspect) onInspect({binaryId:side.binaryId,addr:Number(node.addr),slug:side.slug,
        functions:{source:{name:node.name},destination:{name:node.name}},name:node.name});
    }
    if (!data) return html`<section className="wb-call-comparison" aria-label="Paired call neighborhoods"><h4>Call comparison</h4><p role=${error?"alert":"status"}>${error || "Reading recorded calls for this correspondence…"}</p></section>`;
    const sides = [data.source,data.target], xs = [250,750], nodes = [], lines = [];
    /* Equal-height rows encode recorded neighbor identity, never name/shape similarity.
       Unpaired neighbors remain separate; no inferred cross-build edges are added. */
    function pairedRows(direction) {
      const rows = [[],[]], used = [new Set(),new Set()];
      const lists = sides.map(side => side[direction] || []);
      (data.alignments || []).filter(link => link.direction === direction).forEach(function (link) {
        const a = lists[0].find(node => Number(node.addr) === Number(link.sourceAddr));
        const b = lists[1].find(node => Number(node.addr) === Number(link.targetAddr));
        if (!a || !b || used[0].has(Number(a.addr)) || used[1].has(Number(b.addr))) return;
        rows[0].push(a); rows[1].push(b);
        used[0].add(Number(a.addr)); used[1].add(Number(b.addr));
      });
      lists.forEach((list,index) => list.forEach(function (node) {
        if (!used[index].has(Number(node.addr))) rows[index].push(node);
      }));
      return rows.map(list => list.slice(0,visible));
    }
    const callers = pairedRows("callers"), callees = pairedRows("callees");
    const topRows = Math.max(callers[0].length,callers[1].length), centerY = 62 + topRows * 59;
    const height = centerY + 94 + Math.max(callees[0].length,callees[1].length) * 59;
    center.current = centerY;
    sides.forEach(function (side, index) {
      const x = xs[index];
      nodes.push({id:index+":center",x,y:centerY,node:side,side,center:true});
      callers[index].forEach(function (node,i) {
        const y=39+i*59;
        nodes.push({id:index+":caller:"+node.addr,x,y,node,side,direction:"callers"});
        lines.push({id:index+":incoming:"+node.addr,x,y,x2:x,y2:centerY-20+i*18/Math.max(1,callers[index].length-1),index,lane:i,count:callers[index].length,nodeId:index+":caller:"+node.addr});
      });
      callees[index].forEach(function (node,i) {
        const y=centerY+86+i*59;
        nodes.push({id:index+":callee:"+node.addr,x,y,node,side,direction:"callees"});
        lines.push({id:index+":outgoing:"+node.addr,x,y:centerY+2+i*18/Math.max(1,callees[index].length-1),x2:x,y2:y,index,lane:i,count:callees[index].length,nodeId:index+":callee:"+node.addr});
      });
    });
    const aligned = (data.alignments || []).map(function (link) {
      const a=nodes.find(n=>n.side===sides[0]&&n.direction===link.direction&&Number(n.node.addr)===Number(link.sourceAddr));
      const b=nodes.find(n=>n.side===sides[1]&&n.direction===link.direction&&Number(n.node.addr)===Number(link.targetAddr));
      return a && b ? {a,b,link} : null;
    }).filter(Boolean);
    const linkedNodes = new Set(aligned.flatMap(item => [item.a.id, item.b.id]));
    const centersLinked = data.centerRelation === "recorded-identity";
    if (centersLinked) { linkedNodes.add("0:center"); linkedNodes.add("1:center"); }
    const hasMore = sides.some(side=>(side.callers||[]).length>visible||(side.callees||[]).length>visible);
    const hasCalls = topRows || callees.some(list=>list.length);
    const traceNodes = new Set();
    if (traced) {
      traceNodes.add(traced);
      const selected = nodes.find(node => node.id === traced);
      if (selected) {
        traceNodes.add((selected.side === sides[0] ? "0" : "1") + ":center");
        if (selected.center) nodes.filter(node => node.side === selected.side).forEach(node => traceNodes.add(node.id));
        aligned.forEach(function (item) {
          if (traceNodes.has(item.a.id) || traceNodes.has(item.b.id)) { traceNodes.add(item.a.id); traceNodes.add(item.b.id); }
        });
        nodes.filter(node => traceNodes.has(node.id)).forEach(node => traceNodes.add((node.side === sides[0] ? "0" : "1") + ":center"));
        if (centersLinked && selected.center) { traceNodes.add("0:center"); traceNodes.add("1:center"); }
      }
    }
    return html`<section className="wb-call-comparison" aria-label="Paired call neighborhoods">
      <header><h4>Call graph</h4><div className="wb-call-key"><span title="Arrow follows a recorded caller-to-callee relationship"><i className="is-call"></i>Call</span><span title="Dashed connection means recorded logical identity, not identical bytes"><i className="is-identity"></i>Identity</span></div><div className="wb-call-tools" role="group" aria-label="Call graph viewport">
        <button type="button" disabled=${zoom<=.35} onClick=${()=>setZoom(n=>Math.max(.35,Math.round((n-.2)*10)/10))} aria-label="Zoom out call graph" title="Zoom out">−</button>
        <button type="button" onClick=${()=>setZoom(1)} title="Reset graph scale">${Math.round(zoom*100)}%</button>
        <button type="button" disabled=${zoom>=2} onClick=${()=>setZoom(n=>Math.min(2,Math.round((n+.2)*10)/10))} aria-label="Zoom in call graph" title="Zoom in">+</button>
        <button type="button" onClick=${()=>{if(canvas.current)setZoom(Math.max(.35,Math.min(2,(canvas.current.clientWidth-8)/1000)));}} title="Fit both builds in the graph viewport">Fit</button>
        <button type="button" onClick=${recenter} title="Center the selected function pair">Center</button>
      </div></header>
      <div className="wb-call-builds">${sides.map((side,index)=>html`<div key=${index}><strong>${index?"Counterpart":"Reference"}</strong><span title=${side.slug}>${side.slug || "Build"}</span><code>${address(side.addr)}</code></div>`)}</div>
      <div ref=${canvas} className="wb-call-canvas" tabIndex="0" role="region" aria-label="Call graph; callers above, callees below. Hover or focus a node to trace it; Enter opens the function.">
        <svg viewBox=${"0 0 1000 " + height} style=${{width:Math.round(1000*zoom)+"px",height:Math.round(height*zoom)+"px"}} role="group" aria-label="Directed callers, selected functions and callees">
          <defs><marker id=${marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>
          ${lines.map(function(line){const gutter=line.x-182-52*line.lane/Math.max(1,line.count-1),incident=traceNodes.has(line.nodeId);return html`<path key=${line.id} className=${"wb-call-link"+(traced?(incident?" is-traced":" is-untraced"):"")} d=${"M"+(line.x-160)+","+line.y+"C"+gutter+","+line.y+" "+gutter+","+line.y2+" "+(line.x-160)+","+line.y2} markerEnd=${"url(#"+marker+")"}/>`;})}
          ${aligned.map(item=>html`<g key=${item.link.direction+":"+item.link.sourceAddr+":"+item.link.targetAddr} className=${traced&&!traceNodes.has(item.a.id)&&!traceNodes.has(item.b.id)?"is-untraced":""}><path className="wb-call-alignment" d=${"M410,"+item.a.y+"C500,"+item.a.y+" 500,"+item.b.y+" 590,"+item.b.y}/><title>${"Recorded logical identity #"+item.link.logicalId+"; not byte equality"}</title></g>`)}
          ${centersLinked?html`<g><path className="wb-call-alignment is-center-identity" d=${"M410,"+centerY+"L590,"+centerY}/><title>Selected functions share a permitted recorded identity; not byte equality.</title></g>`:null}
          ${nodes.map(item=>html`<g key=${item.id} className=${"wb-call-node"+(item.center?" is-center":"")+(linkedNodes.has(item.id)?" is-corresponding":"")+(item.center&&!centersLinked?" is-provisional":"")+(traced&&!traceNodes.has(item.id)?" is-untraced":"")} transform=${"translate("+(item.x-160)+","+(item.y-24)+")"} role="button" tabIndex="0" aria-label=${(item.direction==="callers"?"Caller ":item.direction==="callees"?"Callee ":"Selected function ")+item.node.name+", "+address(item.node.addr)+" in "+item.side.slug} onMouseEnter=${()=>setTraced(item.id)} onMouseLeave=${()=>setTraced(null)} onFocus=${()=>setTraced(item.id)} onBlur=${()=>setTraced(null)} onClick=${()=>inspect(item.node,item.side)} onKeyDown=${event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();inspect(item.node,item.side);}}}>
            <title>${item.node.name+" · "+address(item.node.addr)+(item.node.logicalId==null?"":" · identity #"+item.node.logicalId)+(item.center&&!centersLinked?" · "+(claimDescription||"Provisional correspondence; identity not established"):"")}</title><rect width="320" height="48" rx="3"/><text x="12" y="20">${short(item.node.name,item.center&&!centersLinked?34:37)}</text>${item.center&&!centersLinked?html`<text className=${"wb-call-uncertainty is-"+(claimState||"provisional")} x="298" y="20" aria-label="Provisional correspondence">△</text>`:null}<text className="wb-call-address" x="12" y="37">${address(item.node.addr)}${item.node.logicalId==null?"":"  ◇ #"+item.node.logicalId}</text>
          </g>`)}
        </svg>
      </div>
      ${!hasCalls?html`<p>No calls are recorded in this snapshot. That does not establish that these functions make no calls.</p>`:null}
      ${!aligned.length&&hasCalls?html`<p className="wb-call-gap">No shared neighbor identities are recorded here. Similar shapes alone do not establish correspondence.</p>`:null}
      <footer><span title="Only recorded identity links are drawn; matching labels or similar call shapes do not create a connection.">${aligned.length} aligned neighbor ${aligned.length===1?"identity":"identities"} · callers ↑ / callees ↓</span>
        ${hasMore?html`<button type="button" onClick=${()=>setVisible(n=>Math.min(n+6,64))}>Show more calls</button>`:null}
        ${sides.some(side=>Object.values(side.truncated || {}).some(Boolean))?html`<span>Neighborhood snapshot is bounded; additional calls may exist.</span>`:null}
      </footer>
    </section>`;
  }
  window.AgentDecompileCallComparison = CallComparison;
})();
