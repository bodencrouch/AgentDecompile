/* Selection-bound Ghidra tools. Catalog metadata owns fields and read permission. */
(function () {
  "use strict";
  const html=htm.bind(React.createElement);
  const {useState,useEffect,useMemo,useRef,useId}=React;
  const CATEGORIES=[
    {id:"references",label:"References",matches:/reference|xref/},
    {id:"types",label:"Types / ABI",matches:/data-types|structures|enums|vtable|(?:get|manage)-function/},
    {id:"memory",label:"Memory",matches:/memory|read-bytes|(?:get|list|manage)-data\b/},
    {id:"flow",label:"Data flow",matches:/data-flow|pcode|dissect/},
    {id:"notes",label:"Notes",matches:/comments|bookmarks/},
    {id:"other",label:"Other Ghidra tools",matches:/.*/}
  ];
  const title=value=>String(value).replace(/([a-z])([A-Z])/g,"$1 $2").replace(/[_-]/g," ").replace(/^./,letter=>letter.toUpperCase());
  const scalar=value=>value===null?"Not recorded":typeof value==="object"?JSON.stringify(value):String(value);
  const safeRead=action=>Boolean(action&&action.danger===false&&action.mutating===false&&action.long_running===false);
  function unpack(value) {
    for(let depth=0;depth<4;depth++) {
      if(!value||typeof value!=="object")break;
      if(value.parsed&&typeof value.parsed==="object"){value=value.parsed;continue;}
      if(value.structuredContent){value=value.structuredContent;continue;}
      if(Array.isArray(value.content)) {
        const texts=value.content.filter(item=>item.type==="text"&&typeof item.text==="string");
        if(texts.length===1){try{value=JSON.parse(texts[0].text);continue;}catch(_){return {observation:texts[0].text};}}
      }
      break;
    }
    return value;
  }
  function Observation({data}) {
    const [limit,setLimit]=useState(100);
    useEffect(function(){setLimit(100);},[data]);
    if(!data||typeof data!=="object")return html`<pre>${scalar(data)}</pre>`;
    const items=Object.entries(data),scalars=items.filter(([,value])=>value===null||typeof value!=="object"),groups=items.filter(([,value])=>value&&typeof value==="object");
    const fields=Array.isArray(data.fields)?data.fields:null;
    return html`<div className="wb-gi-observation">
      ${scalars.length?html`<dl>${scalars.map(([key,value])=>html`<div key=${key}><dt>${title(key)}</dt><dd>${scalar(value)}</dd></div>`)}</dl>`:null}
      ${fields&&fields.length?html`<section className="wb-gi-layout" aria-label="Recorded structure layout"><h4>Recorded field layout</h4>${fields.slice(0,limit).map((field,index)=>html`<div key=${index}><code>+${field.offset==null?"?":Number(field.offset).toString(16)}</code><span><strong>${field.name||"Unnamed field"}</strong><code>${field.type||"Type not recorded"}</code></span><small>${field.length==null?"Size unknown":field.length+" bytes"}</small></div>`)}</section>`:null}
      ${groups.map(function([key,value]) {
        if(key==="fields"&&fields&&fields.length)return null;
        if(!Array.isArray(value))return html`<section key=${key}><h4>${title(key)}</h4><dl>${Object.entries(value).map(([name,item])=>html`<div key=${name}><dt>${title(name)}</dt><dd>${scalar(item)}</dd></div>`)}</dl></section>`;
        const rows=value.slice(0,limit),objects=rows.filter(row=>row&&typeof row==="object"&&!Array.isArray(row));
        const columns=Array.from(new Set(objects.flatMap(row=>Object.keys(row))));
        return html`<section key=${key}><h4>${title(key)} <small>${rows.length} of ${value.length} returned</small></h4>${!rows.length?html`<p>No ${title(key).toLowerCase()} returned by this read.</p>`:objects.length===rows.length?html`<div className="wb-gi-table-scroll"><table><thead><tr>${columns.map(column=>html`<th key=${column}>${title(column)}</th>`)}</tr></thead><tbody>${rows.map((row,index)=>html`<tr key=${index}>${columns.map(column=>html`<td key=${column}>${Object.prototype.hasOwnProperty.call(row,column)?scalar(row[column]):"—"}</td>`)}</tr>`)}</tbody></table></div>`:html`<ul>${rows.map((row,index)=>html`<li key=${index}>${scalar(row)}</li>`)}</ul>`}${value.length>limit?html`<button type="button" onClick=${()=>setLimit(n=>n+100)}>Show more returned rows</button>`:null}</section>`;
      })}
    </div>`;
  }
  function GhidraInspector({program,addr,selectionKey,actions,runReadAction,onOpenAction}) {
    const prefix="gi-"+useId().replace(/:/g,"");
    const scope=JSON.stringify([selectionKey,program,addr]);
    const [tool,setTool]=useState(""),[toolFilter,setToolFilter]=useState(""),[customFields,setCustomFields]=useState([]),[values,setValues]=useState({}),[packet,setPacket]=useState(null),[pending,setPending]=useState(null),[error,setError]=useState("");
    const cache=useRef(new Map()),request=useRef(null),sequence=useRef(0),current=useRef(scope);
    current.current=scope;
    const available=useMemo(()=>(actions||[]).filter(action=>String(action.id||"").startsWith("mcp.")),[actions]);
    const tools=available.filter(action=>[action.title,action.command,action.id].join(" ").toLowerCase().includes(toolFilter.trim().toLowerCase()));
    const selected=available.find(action=>action.id===tool)||available.find(action=>CATEGORIES[0].matches.test(action.id))||available[0]||null;
    const grouped=CATEGORIES.map(category=>({category,tools:tools.filter(action=>CATEGORIES.find(item=>item.matches.test(action.id))===category)})).filter(group=>group.tools.length);
    const fields=selected&&selected.fields||[];
    const editable=fields.filter(field=>!field.from_context||!["addr","program","repo","slug","db","work_dir","kb"].includes(field.from_context));
    const activeFields=editable.filter(field=>field.required&&field.default==null||customFields.includes(field.name));
    const optionalFields=editable.filter(field=>!activeFields.includes(field));
    const bound=Boolean(program&&addr!=null&&String(addr)!=="");
    const busy=pending&&pending.scope===scope;
    useEffect(function(){sequence.current++;if(request.current)request.current.abort();setPending(null);setPacket(null);setError("");setValues({});},[scope]);
    useEffect(function(){return function(){sequence.current++;if(request.current)request.current.abort();};},[]);
    useEffect(function(){setValues({});setCustomFields([]);setPacket(null);setError("");},[selected&&selected.id]);
    useEffect(function(){setPacket(null);setError("");},[values]);
    function parameters() {
      const result={};
      fields.forEach(function(field) {
        let value=values[field.name];
        if(value!==undefined&&value!=="") {
          if(field.kind==="bool")value=value==="true";
          else if(field.kind==="int"||field.kind==="float") {value=Number(value);if(!Number.isFinite(value)||field.kind==="int"&&!Number.isInteger(value))throw new Error(title(field.name)+" must be a valid "+field.kind+".");}
          else if(field.kind==="json"||field.schema&&["object","array"].includes(field.schema.type))value=JSON.parse(value);
          result[field.name]=value;
        }else if(field.from_context==="addr")result[field.name]=String(addr);
        else if(field.from_context==="program")result[field.name]=program;
        else if(field.required&&!field.from_context&&field.default==null)throw new Error(title(field.name)+" is required.");
      });
      return result;
    }
    async function acquire(refresh) {
      if(!selected||!safeRead(selected)||!bound||busy)return;
      let params;try{params=parameters();}catch(reason){setError(String(reason.message||reason));return;}
      const key=JSON.stringify([scope,selected.id,params]),cached=cache.current.get(key);
      if(!refresh&&cached){setPacket(cached);setError("");return;}
      const serial=++sequence.current,controller=new AbortController();if(request.current)request.current.abort();request.current=controller;
      const actionId=selected.id,captured=scope;
      setPending({scope:captured,actionId});setError("");setPacket(null);
      try {
        const result=await runReadAction(actionId,params,{signal:controller.signal,timeoutMs:30000});
        if(controller.signal.aborted||serial!==sequence.current||captured!==current.current)return;
        if(!result||!result.ok)throw new Error(result&&result.error||"This Ghidra read did not return an observation.");
        const data=unpack(result.data);
        if(data&&typeof data==="object"&&(data.success===false||data.ok===false||data.error))throw new Error(data.error||"The provider reported an incomplete observation.");
        const item={scope:captured,key,actionId,data,elapsedMs:result.elapsedMs,readAt:Date.now()};
        cache.current.set(key,item);if(cache.current.size>24)cache.current.delete(cache.current.keys().next().value);setPacket(item);
      }catch(reason){if(!controller.signal.aborted&&serial===sequence.current&&captured===current.current)setError(String(reason.message||reason));}
      finally{if(serial===sequence.current&&captured===current.current)setPending(null);}
    }
    function configure() {
      if(!selected||!bound||!onOpenAction)return;
      try{onOpenAction(selected.id,parameters());}catch(reason){setError(String(reason.message||reason));}
    }
    const displayed=packet&&packet.scope===scope&&selected&&packet.actionId===selected.id?packet:null;
    return html`<section className="wb-ghidra-inspector" aria-label="Ghidra selection inspector">
      <header><h3>Inspect selection</h3><code>${program||"No program selected"}${addr!=null?" · "+addr:""}</code></header>
      <div className="wb-gi-body">
        ${!bound?html`<p>Select a function or address in an open program. Reads and edits remain bound to that selection.</p>`:null}
        ${available.length&&selected?html`<form onSubmit=${event=>{event.preventDefault();safeRead(selected)?acquire(false):configure();}}>
          <div className="wb-gi-tool-picker"><label htmlFor=${prefix+"-search"}>Find a tool<input id=${prefix+"-search"} type="search" disabled=${busy} value=${toolFilter} onInput=${event=>setToolFilter(event.target.value)} placeholder="References, types, memory…"/></label><label htmlFor=${prefix+"-tool"}>Tool<select id=${prefix+"-tool"} value=${selected.id} disabled=${busy} onChange=${event=>setTool(event.target.value)}>
            ${!tools.includes(selected)?html`<optgroup label="Current tool"><option value=${selected.id}>${title(selected.title||selected.command||selected.id)}</option></optgroup>`:null}
            ${grouped.map(group=>html`<optgroup key=${group.category.id} label=${group.category.label}>${group.tools.map(action=>html`<option key=${action.id} value=${action.id}>${title(action.title||action.command||action.id)}${safeRead(action)?"":" · configure"}</option>`)}</optgroup>`)}
          </select></label></div>
          ${!tools.length?html`<p className="wb-gi-empty" role="status">No tools match this search; the current tool is unchanged.</p>`:null}
          <div className="wb-gi-fields">${activeFields.map(function(field) {
            const id=prefix+"-"+field.name,choices=field.choices||[],value=values[field.name]===undefined?"":values[field.name],help=field.help||"";
            return html`<label key=${field.name} htmlFor=${id} title=${help}>${title(field.name)}${field.required&&!field.from_context&&field.default==null?" *":""}${field.kind==="bool"?html`<select id=${id} value=${value} disabled=${busy} onChange=${event=>setValues(old=>Object.assign({},old,{[field.name]:event.target.value}))}><option value="">Default${field.default!=null?" · "+field.default:""}</option><option value="true">Yes</option><option value="false">No</option></select>`:choices.length?html`<select id=${id} value=${value} disabled=${busy} onChange=${event=>setValues(old=>Object.assign({},old,{[field.name]:event.target.value}))}><option value="">${field.default!=null?"Default · "+field.default:"Choose…"}</option>${choices.map(choice=>html`<option key=${choice} value=${choice}>${title(choice)}</option>`)}</select>`:html`<input id=${id} type=${["int","float"].includes(field.kind)?"number":"text"} step=${field.kind==="float"?"any":undefined} value=${value} disabled=${busy} placeholder=${field.default==null?field.from_context?"Current selection":field.schema&&["object","array"].includes(field.schema.type)?"JSON":"Optional":String(field.default)} onInput=${event=>setValues(old=>Object.assign({},old,{[field.name]:event.target.value}))}/>`}</label>`;
          })}${optionalFields.length?html`<label htmlFor=${prefix+"-parameter"}>Customize a parameter<select id=${prefix+"-parameter"} value="" disabled=${busy} onChange=${event=>{if(event.target.value)setCustomFields(old=>old.concat(event.target.value));}}><option value="">Use defaults</option>${optionalFields.map(field=>html`<option key=${field.name} value=${field.name}>${title(field.name)}${field.default!=null?" · default "+field.default:""}</option>`)}</select></label>`:null}</div>
          <div className="wb-gi-actions"><button type="submit" disabled=${!bound||busy||safeRead(selected)&&!runReadAction||!safeRead(selected)&&!onOpenAction}>${busy?"Reading…":safeRead(selected)?"Read selection":"Configure action…"}</button>${safeRead(selected)&&displayed?html`<button type="button" disabled=${!bound||busy} onClick=${()=>acquire(true)}>Refresh this read</button>`:null}${busy?html`<button type="button" onClick=${()=>{sequence.current++;if(request.current)request.current.abort();setPending(null);setError("Stopped waiting. An admitted server operation may still finish; no new read was started.");}}>Stop waiting</button>`:null}</div>
          ${!safeRead(selected)?html`<p className="wb-gi-policy">This tool is catalogued as state-changing or long-running. Configure it in the existing approval controls; this inspector does not execute it directly.</p>`:null}
        </form>`:html`<p>No Ghidra tools are advertised by the current action catalog.</p>`}
        ${error?html`<p role="alert">${error}</p>`:null}
        ${displayed?html`<div className="wb-gi-result"><p className="wb-gi-receipt">Recorded read · ${new Date(displayed.readAt).toLocaleTimeString()}${Number.isFinite(displayed.elapsedMs)?" · "+Math.round(displayed.elapsedMs)+" ms":""} · this exact selection only</p><${Observation} data=${displayed.data}/></div>`:!busy&&bound&&available.length?html`<p className="wb-gi-empty">Choose a tool, then read. Tool selection alone starts no work.</p>`:null}
      </div>
    </section>`;
  }
  window.AgentDecompileGhidraInspector=GhidraInspector;
})();
