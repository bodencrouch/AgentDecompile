/* Persistent, local-only workstation layout. Moving a panel never moves data
   or restarts its React subtree. Coordinates are bounded to the workspace. */
(function () {
  "use strict";
  const html = htm.bind(React.createElement);
  const { useState, useRef, useEffect, useLayoutEffect } = React;
  const ZONES = ["left", "center", "right", "bottom", "floating"];
  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const finite = (n, fallback) => Number.isFinite(Number(n)) ? Number(n) : fallback;
  const membersOf = (layout, panels, zone) => panels.filter(p => layout.panels[p.id] && !layout.panels[p.id].hidden && layout.panels[p.id].zone === zone)
    .sort((a,b) => layout.panels[a.id].order-layout.panels[b.id].order);
  function solveRectangles(layout, panels, size) {
    const members=zone=>membersOf(layout,panels,zone),small=size.width<760,available=size.width;
    const hasLeft=members("left").length>0,hasRight=members("right").length>0,hasCenter=members("center").length>0;
    const sideBudget=Math.max(0,available-(hasCenter?Math.min(360,available*.45):0));
    let left=hasLeft?Math.min(layout.widths.left,sideBudget):0,right=hasRight?Math.min(layout.widths.right,sideBudget-left):0;
    if(hasRight&&right<Math.min(180,sideBudget/2)){right=Math.min(180,sideBudget/2);left=Math.min(left,sideBudget-right);}
    const bottom=members("bottom").length?Math.min(layout.bottom,size.height*.45):0,rectangles={};
    if(small){let y=0;for(const zone of ["center","right","left","bottom"])for(const p of members(zone)){const height=Math.max(220,300*layout.panels[p.id].weight);rectangles[p.id]={x:0,y,width:available,height};y+=height+5;}}
    else for(const zone of ["left","center","right","bottom"]){
      const list=members(zone),total=list.reduce((sum,p)=>sum+layout.panels[p.id].weight,0);
      const area=zone==="bottom"?{x:0,y:size.height-bottom,width:available,height:bottom}:zone==="left"?{x:0,y:0,width:left,height:size.height-bottom}:zone==="right"?{x:available-right,y:0,width:right,height:size.height-bottom}:{x:left,y:0,width:available-left-right,height:size.height-bottom};
      if(zone!=="bottom"&&layout.heights[zone])area.height=Math.min(area.height,layout.heights[zone]);
      if(zone==="center"&&layout.centerWidth)area.width=Math.min(area.width,layout.centerWidth);
      let y=area.y;for(const p of list){const height=area.height*layout.panels[p.id].weight/total;rectangles[p.id]={x:area.x,y,width:area.width,height};y+=height;}
    }
    for(const p of members("floating")){const s=layout.panels[p.id],width=Math.min(s.width,available),height=Math.min(s.height,size.height);rectangles[p.id]={x:clamp(s.x,0,available-width),y:clamp(s.y,0,size.height-height),width,height};}
    return {rectangles,small,left,right,bottom,hasRight};
  }
  function placePanel(layout,panels,panelId,zone,before) {
    const next={...layout,panels:{...layout.panels}},list=membersOf(layout,panels,zone).filter(p=>p.id!==panelId);
    const at=before?list.findIndex(p=>p.id===before):-1;list.splice(at<0?list.length:at,0,panels.find(p=>p.id===panelId));
    list.forEach((p,index)=>{next.panels[p.id]={...layout.panels[p.id],zone,order:index,hidden:false};});
    return next;
  }
  function raiseFloating(layout,panels,panelId){
    const states=layout.panels,floating=panels.filter(p=>states[p.id].zone==="floating"&&!states[p.id].hidden),max=Math.max(15,...floating.map(p=>states[p.id].z||15));
    if((states[panelId].z||15)===max&&floating.filter(p=>(states[p.id].z||15)===max).length===1)return layout;
    const next={...layout,panels:{...states}};
    if(max<100000)next.panels[panelId]={...states[panelId],z:max+1};
    else{const ordered=floating.filter(p=>p.id!==panelId).sort((a,b)=>(states[a.id].z||15)-(states[b.id].z||15));ordered.push(panels.find(p=>p.id===panelId));ordered.forEach((p,index)=>{next.panels[p.id]={...states[p.id],z:Math.min(100000,15+index)};});}
    return next;
  }
  const controls=window.AgentDecompileDockControls instanceof Map?window.AgentDecompileDockControls:new Map();
  window.AgentDecompileDockControls=controls;
  function DockLayout({ id, title = id, panels, className = "", onContextMenu }) {
    const storageKey = "agentdecompile.docks.v1." + id;
    const host = useRef(null);
    const gesture = useRef(null);
    const [size, setSize] = useState({ width: 1000, height: 640 });
    const [target, setTarget] = useState(null);
    const [message, setMessage] = useState("");
    const defaults = () => ({ widths: { left: 260, right: 490 }, heights: {}, centerWidth: null, bottom: 190,
      panels: Object.fromEntries(panels.map((p, i) => [p.id, { zone: p.zone || "center", order: i, weight: p.weight || 1, x: 70, y: 60, width: 560, height: 400, hidden: p.hidden === true }])) });
    const [storedLayout, setLayout] = useState(() => {
      const initial = defaults();
      try {
        const saved = JSON.parse(localStorage.getItem(storageKey));
        if (!saved || typeof saved !== "object") return initial;
        for (const p of panels) {
          const s = saved.panels && saved.panels[p.id];
          if (!s || !ZONES.includes(s.zone)) continue;
          initial.panels[p.id] = { zone: s.zone, order: clamp(finite(s.order, 0), 0, 1000),
            weight: clamp(finite(s.weight, 1), .15, 10), x: finite(s.x, 70), y: finite(s.y, 60),
            width: clamp(finite(s.width, 560), 180, 4000), height: clamp(finite(s.height, 400), 120, 4000), hidden: s.hidden === true, z: clamp(finite(s.z, 15), 15, 100000) };
        }
        for (const z of ["left", "right"]) initial.widths[z] = clamp(finite(saved.widths && saved.widths[z], initial.widths[z]), 180, 1500);
        initial.bottom = clamp(finite(saved.bottom, 190), 100, 1000);
        initial.centerWidth = saved.centerWidth == null ? null : clamp(finite(saved.centerWidth, 560), 180, 4000);
        for (const z of ["left", "center", "right"]) if (saved.heights && Number.isFinite(saved.heights[z])) initial.heights[z] = clamp(saved.heights[z], 120, 4000);
      } catch (_) { /* A corrupt or unavailable local preference never blocks work. */ }
      return initial;
    });
    const layout = { ...storedLayout, panels: { ...defaults().panels, ...storedLayout.panels } };
    useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(layout)); } catch (_) {} }, [storedLayout, storageKey]);
    useLayoutEffect(() => {
      function fitWorkspace() {
        if (host.current) host.current.style.setProperty("--dock-available-height", Math.max(340, window.innerHeight - host.current.getBoundingClientRect().top - 28) + "px");
      }
      const observer = new ResizeObserver(entries => {
        const r = entries[0].contentRect;
        setSize({ width: Math.max(180, r.width), height: Math.max(120, r.height) });
      });
      if (host.current) observer.observe(host.current);
      const frame = requestAnimationFrame(fitWorkspace);
      window.addEventListener("resize", fitWorkspace);
      return () => { observer.disconnect(); cancelAnimationFrame(frame); window.removeEventListener("resize", fitWorkspace); };
    }, []);
    const members=zone=>membersOf(layout,panels,zone);
    const {rectangles,small,left,right,bottom,hasRight}=solveRectangles(layout,panels,size);
    const change = (panelId, values) => setLayout(old => ({ ...old, panels: { ...old.panels, [panelId]: { ...defaults().panels[panelId], ...old.panels[panelId], ...values } } }));
    function dock(panelId, zone, before) {
      if(!ZONES.includes(zone)||!panels.some(p=>p.id===panelId))return;
      setLayout(old=>{
        const base={...old,panels:{...defaults().panels,...old.panels}},next=placePanel(base,panels,panelId,zone,before);
        if(zone==="floating"){const rect=solveRectangles(base,panels,size).rectangles[panelId];if(rect)next.panels[panelId]={...next.panels[panelId],...rect};}
        return zone==="floating"?raiseFloating(next,panels,panelId):next;
      });
      setMessage(panels.find(p => p.id === panelId).title + " moved to " + zone + ".");
    }
    useEffect(()=>{
      const entry={id,title,panels:panels.map(p=>({id:p.id,title:p.title,zone:layout.panels[p.id].zone,hidden:layout.panels[p.id].hidden})),dock,
        hide:panelId=>{if(panels.some(p=>p.id===panelId))change(panelId,{hidden:true});},
        show:panelId=>{if(panels.some(p=>p.id===panelId))change(panelId,{hidden:false});},
        reset:()=>{setLayout(defaults());setMessage("Default layout restored.");}};
      controls.set(id,entry);
      window.dispatchEvent(new CustomEvent("agentdecompile:dock-controls",{detail:{id}}));
      return ()=>{if(controls.get(id)===entry){controls.delete(id);window.dispatchEvent(new CustomEvent("agentdecompile:dock-controls",{detail:{id}}));}};
    },[id,title,panels,storedLayout]);
    function panelMenu(event,p){
      if(!onContextMenu)return;event.preventDefault();if(event.stopPropagation)event.stopPropagation();
      const items=ZONES.map(zone=>({title:(zone==="floating"?"Float":"Dock "+zone)+" panel",run:()=>dock(p.id,zone)}));
      items.push({title:"Hide "+p.title,run:()=>change(p.id,{hidden:true})},{title:"Reset workspace layout",run:()=>{setLayout(defaults());setMessage("Default layout restored.");}});
      onContextMenu(event,items);
    }
    function contextKey(event,p){
      if(event.key!=="ContextMenu"&&!(event.key==="F10"&&event.shiftKey))return;
      const rect=event.currentTarget.getBoundingClientRect();
      panelMenu({clientX:rect.left+12,clientY:rect.bottom,preventDefault:()=>event.preventDefault(),stopPropagation:()=>event.stopPropagation()},p);
    }
    function begin(event, panelId, mode) {
      if (event.button !== 0 || event.target.closest("button, select, input, a")) return;
      event.preventDefault();
        const rect = rectangles[panelId];
      const snapshot = JSON.parse(JSON.stringify(layout));
      if(gesture.current)return;
      const g = { panelId, mode, startX: event.clientX, startY: event.clientY, rect, snapshot, moved: false, target: null, nextLayout:null, cancelled:false };
      gesture.current = g;
      const origin = host.current.getBoundingClientRect();
      function move(e) {
        const dx = e.clientX - g.startX, dy = e.clientY - g.startY;
        if (!g.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
        g.moved = true;
        if (mode === "move") {
          const x = e.clientX - origin.left, y = e.clientY - origin.top;
          let zone = null, before = null;
          if (!e.altKey && x >= 0 && x <= size.width && y >= 0 && y <= size.height) {
            for (const other of panels) {
              const r = rectangles[other.id];
              if (other.id !== panelId && r && layout.panels[other.id].zone !== "floating" && x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height) {
                zone = layout.panels[other.id].zone;
                const group=membersOf(snapshot,panels,zone).filter(p=>p.id!==panelId),index=group.findIndex(p=>p.id===other.id);
                before = y < r.y + r.height / 2 ? other.id : group[index+1]&&group[index+1].id; break;
              }
            }
            if(!zone){
              zone=y>size.height-48?"bottom":x<48?"left":x>size.width-48?"right":y<48?"center":null;
              if(zone&&y<48){const first=membersOf(snapshot,panels,zone).find(p=>p.id!==panelId);before=first&&first.id;}
            }
          }
          const ghost={x:clamp(rect.x+dx,0,Math.max(0,size.width-rect.width)),y:clamp(rect.y+dy,0,Math.max(0,size.height-rect.height)),width:rect.width,height:rect.height};
          if(!zone&&!e.shiftKey){
            const xs=[0,size.width],ys=[0,size.height];
            for(const other of panels){const r=rectangles[other.id];if(other.id===panelId||!r)continue;xs.push(r.x,r.x+r.width);ys.push(r.y,r.y+r.height);}
            function snap(position,length,edges,max){
              let answer=position,distance=9;
              for(const edge of edges)for(const candidate of [edge,edge-length]){const delta=Math.abs(candidate-position);if(candidate>=0&&candidate<=max&&delta<=8&&delta<distance){answer=candidate;distance=delta;}}
              return answer;
            }
            ghost.x=snap(ghost.x,ghost.width,xs,Math.max(0,size.width-ghost.width));
            ghost.y=snap(ghost.y,ghost.height,ys,Math.max(0,size.height-ghost.height));
          }
          g.target={zone:zone||"floating",before};
          g.nextLayout=zone?placePanel(snapshot,panels,panelId,zone,before):{...snapshot,panels:{...snapshot.panels,[panelId]:{...snapshot.panels[panelId],zone:"floating",hidden:false,...ghost}}};
          const landing=solveRectangles(g.nextLayout,panels,size).rectangles[panelId];
          setTarget({...g.target,rect:landing,ghost,title:panels.find(p=>p.id===panelId).title});
        } else if (snapshot.panels[panelId].zone === "floating") {
          change(panelId, { width:mode==="height"?rect.width:clamp(rect.width+dx,Math.min(180,size.width-rect.x),size.width-rect.x),height:mode==="width"?rect.height:clamp(rect.height+dy,Math.min(120,size.height-rect.y),size.height-rect.y) });
        } else {
          const zone = snapshot.panels[panelId].zone;
          setLayout(old => {
            const next = { ...old, widths: { ...old.widths }, heights: { ...old.heights }, panels: { ...old.panels } };
            if (mode !== "height" && !small) {
              if (zone === "left") next.widths.left = clamp(snapshot.widths.left + dx, 180, Math.max(180, size.width - 360 - right));
              if (zone === "right") next.widths.right = clamp(snapshot.widths.right - dx, 180, Math.max(180, size.width - 360 - left));
              if (zone === "center" && hasRight) next.widths.right = clamp(snapshot.widths.right - dx, 180, Math.max(180, size.width - 360 - left));
              if (zone === "center" && !hasRight) next.centerWidth = clamp(rect.width + dx, 180, size.width - left);
            }
            if (zone === "bottom" && !small) next.bottom = clamp(snapshot.bottom - dy, 100, size.height * .45);
            else if (mode !== "width") {
              const group = panels.filter(p => snapshot.panels[p.id].zone === zone && !snapshot.panels[p.id].hidden).sort((a, b) => snapshot.panels[a.id].order - snapshot.panels[b.id].order);
              const index = group.findIndex(p => p.id === panelId), neighbor = group[index + 1] || group[index - 1];
              const current = snapshot.panels[panelId], totalHeight = rect.height / current.weight;
              const delta = neighbor && index === group.length - 1 && !small ? -dy : dy;
              let weight = clamp(current.weight + delta / totalHeight, .2, 10);
              if (neighbor && !small) {
                const n = snapshot.panels[neighbor.id], sum = current.weight + n.weight;
                weight = clamp(weight, .2, sum - .2);
                next.panels[neighbor.id] = { ...n, weight: sum - weight };
              } else if (!small) next.heights[zone] = clamp(rect.height + dy, 120, size.height - bottom);
              next.panels[panelId] = { ...current, weight };
            }
            return next;
          });
        }
      }
      function end() {
        window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", cancel); window.removeEventListener("keydown", key);
        if (!g.cancelled&&g.moved&&mode==="move"&&g.nextLayout){setLayout(old=>{
          const next={...g.nextLayout,panels:Object.fromEntries(Object.entries(g.nextLayout.panels).map(([key,state])=>[key,{...state,z:old.panels[key]&&old.panels[key].z||state.z}]))};
          return g.target.zone==="floating"?raiseFloating(next,panels,panelId):next;
        });setMessage(panels.find(p=>p.id===panelId).title+" moved to "+g.target.zone+".");}
        gesture.current = null; setTarget(null);
      }
      function cancel() { g.cancelled=true;setLayout(snapshot);g.target=null;end(); }
      function key(e) { if (e.key === "Escape") {e.preventDefault();cancel();} }
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", end); window.addEventListener("pointercancel", cancel); window.addEventListener("keydown", key);
      g.cancel = cancel;
    }
    useEffect(() => () => { if (gesture.current) gesture.current.cancel(); }, []);
    function resizeKey(event, p) {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const s = layout.panels[p.id], step = event.shiftKey ? 50 : 10;
      if (s.zone === "floating") change(p.id, { width: clamp(s.width + (event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0), 180, size.width), height: clamp(s.height + (event.key === "ArrowDown" ? step : event.key === "ArrowUp" ? -step : 0), 120, size.height) });
      else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        const delta = event.key === "ArrowDown" ? step : -step;
        if (s.zone === "bottom" && !small) setLayout(old => ({ ...old, bottom: clamp(old.bottom - delta, 100, size.height * .45) }));
        else if (!small && members(s.zone).length === 1) setLayout(old => ({ ...old, heights: { ...old.heights, [s.zone]: clamp(rectangles[p.id].height + delta, 120, size.height - bottom) } }));
        else change(p.id, { weight: clamp(s.weight + (event.key === "ArrowDown" ? .1 : -.1), .2, 10) });
      }
      else {
        const delta = event.key === "ArrowRight" ? step : -step;
        if (s.zone === "center" && !hasRight) setLayout(old => ({ ...old, centerWidth: clamp(rectangles[p.id].width + delta, 180, size.width - left) }));
        else setLayout(old => ({ ...old, widths: { ...old.widths, [s.zone === "left" ? "left" : "right"]: clamp(old.widths[s.zone === "left" ? "left" : "right"] + (s.zone === "left" ? delta : -delta), 180, size.width * .65) } }));
      }
    }
    return html`<section className=${"wb-dock-workspace " + className} aria-label="Dockable workspace">
      <span className="wb-sr-only">Drag panel titles to dock. Hold Alt to float. Escape cancels. Panel layout commands are in View or the title context menu.</span>
      <div className=${"wb-dock-host" + (small ? " is-narrow" : "")} ref=${host} style=${small ? { height: Math.max(500, ...Object.values(rectangles).map(r => r.y + r.height)) + "px" } : undefined}>
        ${panels.map(p => {
          const s = layout.panels[p.id], r = rectangles[p.id] || { x: 0, y: 0, width: 180, height: 120 };
          const list = members(s.zone), tail = s.zone!=="floating"&&list.length>1&&list[list.length-1].id===p.id;
          function bringForward(){
            if(s.zone!=="floating")return;
            setLayout(old=>{
              const base={...old,panels:{...defaults().panels,...old.panels}},next=raiseFloating(base,panels,p.id);
              return next===base?old:next;
            });
          }
          return html`<section id=${p.id} key=${p.id} className=${"wb-dock-widget zone-" + s.zone + (tail ? " is-tail" : "") + (s.zone === "floating" ? " is-floating" : "") + (p.className ? " " + p.className : "")} aria-labelledby=${p.id + "-dock-title"} onPointerDownCapture=${bringForward} onFocusCapture=${bringForward} style=${{ display: s.hidden ? "none" : undefined, zIndex: s.zone === "floating" ? s.z || 15 : undefined, left: r.x + "px", top: r.y + "px", width: Math.max(0, r.width - 4) + "px", height: Math.max(0, r.height - 4) + "px" }}>
            <header className="wb-dock-widget-title" tabIndex="0" aria-label=${p.title+" panel. Right-click or Shift F10 for layout commands."} onContextMenu=${event=>panelMenu(event,p)} onKeyDown=${event=>contextKey(event,p)} onPointerDown=${event => begin(event, p.id, "move")} onDoubleClick=${event => { if (!event.target.closest("button, select")) dock(p.id, s.zone === "floating" ? p.zone || "center" : "floating"); }}>
              <strong id=${p.id + "-dock-title"}>${p.title}</strong>${p.actions || null}
            </header><div className="wb-dock-widget-body">${p.content}</div>
            <div className="wb-dock-edge is-width" onPointerDown=${event => begin(event, p.id, "width")} aria-hidden="true"></div>
            <div className="wb-dock-edge is-height" onPointerDown=${event => begin(event, p.id, "height")} aria-hidden="true"></div>
            <div className="wb-dock-resize" role="separator" tabIndex="0" aria-label=${"Resize " + p.title + "; arrow keys resize, Shift for larger steps"} onKeyDown=${event => resizeKey(event, p)} onPointerDown=${event => begin(event, p.id, "both")}></div>
          </section>`;
        })}
        ${target ? html`<div className="wb-dock-drag-ghost" aria-hidden="true" style=${{left:target.ghost.x+"px",top:target.ghost.y+"px",width:Math.max(0,target.ghost.width-4)+"px",height:Math.max(0,target.ghost.height-4)+"px"}}><strong>${target.title}</strong></div><div className=${"wb-dock-drop-preview is-"+target.zone} aria-hidden="true" style=${{left:target.rect.x+"px",top:target.rect.y+"px",width:Math.max(0,target.rect.width-4)+"px",height:Math.max(0,target.rect.height-4)+"px"}}>${target.zone==="floating"?"Float panel":"Dock "+target.zone}</div>` : null}
      </div><span className="wb-sr-only" role="status">${message}</span>
    </section>`;
  }
  window.AgentDecompileDockWorkspace = props => React.createElement(DockLayout, { ...props, key: props.id });
})();
