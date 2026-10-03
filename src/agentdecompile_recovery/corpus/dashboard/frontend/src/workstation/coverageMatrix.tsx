import type {Data} from '../contracts';

export type CoverageRow={key:string;build:string;inLibrary:boolean;members:Data[];coverage:string;addresses:string;methods:string;binary?:Data};
export type TierState={status:'available'|'unavailable';reason:string;functions?:number;bytes?:number|null};
export type MatrixTierCell={status:'available'|'unavailable';reason:string;verified:TierState;advisory:TierState;unclassified:TierState;basis?:string};
const unavailable=(reason:string):TierState=>({status:'unavailable',reason});
const validCount=(value:unknown)=>Number.isSafeInteger(value)&&Number(value)>=0;
const unique=(values:unknown):values is string[]=>Array.isArray(values)&&values.every(value=>typeof value==='string'&&value.length>0)&&new Set(values).size===values.length;
const validHash=(value:unknown)=>typeof value==='string'&&value.length===64&&/^[0-9a-f]{64}$/.test(value);

export function matrixTierCell(response:Data|undefined,expected:{logicalId:string;corpusIdentity:string;slug:string;contentSha256:string;expectedVersion:string}):MatrixTierCell {
  const fail=(reason:string):MatrixTierCell=>({status:'unavailable',reason,verified:unavailable(reason),advisory:unavailable(reason),unclassified:unavailable(reason)});
  if(!/^[1-9][0-9]*$/.test(expected.logicalId)||!Number.isSafeInteger(Number(expected.logicalId))||String(Number(expected.logicalId))!==expected.logicalId||!expected.corpusIdentity||!expected.slug||!validHash(expected.contentSha256)||expected.expectedVersion!==expected.contentSha256)return fail('Exact selection and content-hash version are required.');
  const projection=response?.matrix_projection,binary=projection?.binary;
  if(!projection)return fail(response?.error||'Per-entity tier report unavailable.');
  if(response?.ok!==true||response?.status!=='available')return fail(response?.error||'Per-entity tier report failed.');
  const scopeMatches=(scope:Data|undefined)=>scope?.kind==='logical_function'&&Number.isSafeInteger(scope.logical_id)&&scope.logical_id===Number(expected.logicalId)&&Object.keys(scope).length===2;
  if(!scopeMatches(projection.selection_scope)||!scopeMatches(response?.report?.selection_scope))return fail('Report scope does not match the selected logical entity.');
  if(projection.unbound!==null||projection.unbound_status!=='not_requested')return fail('Scoped report supplied global unbound counts.');
  if(projection.corpus_identity!==expected.corpusIdentity)return fail('Report belongs to another corpus selection.');
  if(projection.freshness?.status!=='current')return fail(projection.freshness?.reason||'Report is stale or failed.');
  if(binary?.slug!==expected.slug||binary?.content_sha256!==expected.contentSha256||binary?.version!==expected.expectedVersion)return fail('Report basis does not match this exact build and requested version.');
  const reportBinary=response?.report?.binary;
  if(reportBinary?.slug!==binary.slug||reportBinary?.content_sha256!==binary.content_sha256||reportBinary?.version!==binary.version)return fail('Report and projection build bases differ.');
  if(!validHash(binary?.report_sha256))return fail('Report digest is missing or malformed.');
  if(response?.report?.report_sha256!==binary.report_sha256)return fail('Report and projection digests differ.');
  if(!Array.isArray(projection.rows)||projection.rows.length!==1)return fail('Scoped report must contain exactly one logical tier row.');
  const row=projection.rows[0];
  if(!Number.isSafeInteger(row?.logical_id)||row.logical_id!==Number(expected.logicalId))return fail('No authoritative tier row was returned for this logical entity.');
  if(!unique(row.member_keys)||!validCount(row.physical_members)||row.member_keys.length!==row.physical_members)return fail('Physical member count does not equal its member set.');
  const tierKeys:string[]=[];
  for(const name of ['verified','advisory','unclassified']){
    const tier=row[name];
    if(!unique(tier?.member_keys))return fail(`${name} member set is malformed.`);
    if(name==='verified'&&tier.status==='unavailable'){
      if(tier.functions!==null||tier.bytes!==null)return fail('Unavailable verified tier supplied numeric progress.');
    }else if(!validCount(tier?.functions)||tier.member_keys.length!==tier.functions)return fail(`${name} count does not equal its member set.`);
    tierKeys.push(...tier.member_keys);
  }
  if(new Set(tierKeys).size!==tierKeys.length||tierKeys.length!==row.member_keys.length||tierKeys.some(key=>!row.member_keys.includes(key)))return fail('Tier member sets overlap or do not reconcile to physical members.');
  const provider=projection.provider||{};
  if(row.verified.status==='available'&&provider.status!=='connected')return fail('Verified tier conflicts with disconnected acceptance provider.');
  const verified:TierState=row.verified.status==='available'?{status:'available',reason:'',functions:row.verified.functions,bytes:row.verified.bytes}:unavailable(provider.reason||'Verified acceptance provider unavailable.');
  return {status:'available',reason:'',verified,advisory:{status:'available',reason:'',functions:row.advisory.functions,bytes:row.advisory.bytes},unclassified:{status:'available',reason:'',functions:row.unclassified.functions,bytes:row.unclassified.bytes},basis:`${binary.slug} · ${binary.version} · ${binary.report_sha256}`};
}

const belongs=(binary:Data,member:Data)=>binary.slug===member.slug||Boolean(binary.aliasSlugs?.includes(member.slug));
const confidence=(member:Data)=>member.confidence===null||member.confidence===undefined||member.confidence===''?'confidence not recorded':`confidence ${member.confidence}`;
export function coverageText(count:number){return count===0?'No member returned':count===1?'1 member returned':`${count} members returned`;}
export function coverageRows(members:Data[],binaries:Data[]):CoverageRow[]{
  const describe=(key:string,build:string,inLibrary:boolean,rows:Data[],binary?:Data):CoverageRow=>({key,build,inLibrary,members:rows,binary,coverage:coverageText(rows.length),addresses:rows.map(row=>String(row.addr||'No address')).join(', '),methods:rows.map(row=>`${row.method||'Method not recorded'} · ${confidence(row)}`).join('; ')});
  const rows=binaries.map((binary,index)=>describe(`binary:${binary.slug||binary.sha256||index}`,String(binary.name||binary.label||binary.slug||binary.sha256||'Unnamed build'),true,members.filter(member=>belongs(binary,member)),binary));
  const outside=[...new Set(members.filter(member=>!binaries.some(binary=>belongs(binary,member))).map(member=>String(member.slug||'')))];
  for(const slug of outside)rows.push(describe(`member:${slug}`,slug||'Build not recorded',false,members.filter(member=>String(member.slug||'')===slug)));
  return rows;
}

export function CoverageMatrix({members,binaries,logicalId='',corpusIdentity='',tierReportsBySlug={},loading=false}:{members:Data[];binaries:Data[];logicalId?:string;corpusIdentity?:string;tierReportsBySlug?:Record<string,Data>;loading?:boolean}){
  const rows=coverageRows(members,binaries),covered=rows.filter(row=>row.members.length>0).length;
  return <section aria-label="Coverage by build"><h3>Coverage by build</h3><p>{covered} of {rows.length} builds return a member for this identity.</p>{loading&&<p role="status">Reading exact tier reports…</p>}
    {rows.length?<table className="ws-table"><thead><tr><th>Build</th><th>Corpus matches</th><th>Verified</th><th>Advisory</th><th>Unclassified</th><th>Addresses</th><th>Method and confidence</th></tr></thead><tbody>{rows.map(row=>{
      const binary=row.binary,slug=String(binary?.slug||row.members[0]?.slug||''),hash=String(binary?.content_sha256||binary?.contentSha256||binary?.sha256||'');
      const tier=matrixTierCell(tierReportsBySlug[slug],{logicalId,corpusIdentity,slug,contentSha256:hash,expectedVersion:hash});
      const show=(value:TierState)=>value.status==='available'?String(value.functions):`Unavailable · ${value.reason}`;
      return <tr key={row.key}><td><strong>{row.build}</strong>{!row.inLibrary&&<small>Not in the binary library</small>}</td><td>{row.coverage}</td><td>{show(tier.verified)}</td><td>{show(tier.advisory)}</td><td>{show(tier.unclassified)}</td><td>{row.addresses?<code>{row.addresses}</code>:'None'}</td><td>{row.methods||'None'}{tier.basis&&<small>{tier.basis}</small>}</td></tr>;
    })}</tbody></table>:<p>No builds to compare.</p>}
  </section>;
}
