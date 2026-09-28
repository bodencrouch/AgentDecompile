import type {Data} from '../contracts';

export type CoverageRow = {
  key: string;
  build: string;
  inLibrary: boolean;
  members: Data[];
  coverage: string;
  addresses: string;
  methods: string;
};

const belongs=(binary:Data,member:Data)=>binary.slug===member.slug||Boolean(binary.aliasSlugs?.includes(member.slug));
const confidence=(member:Data)=>member.confidence===null||member.confidence===undefined||member.confidence===''?'confidence not recorded':`confidence ${member.confidence}`;

export function coverageText(count:number):string {
  return count===0?'No member returned':count===1?'1 member returned':`${count} members returned`;
}

/**
 * One row per build for the selected logical identity, built only from the
 * logical detail members and the binary library the workstation already reads.
 * It reports what was returned. It does not infer a locator status.
 */
export function coverageRows(members:Data[],binaries:Data[]):CoverageRow[] {
  const describe=(key:string,build:string,inLibrary:boolean,rows:Data[]):CoverageRow=>({
    key,build,inLibrary,members:rows,coverage:coverageText(rows.length),
    addresses:rows.map(row=>String(row.addr||'No address')).join(', '),
    methods:rows.map(row=>`${row.method||'Method not recorded'} · ${confidence(row)}`).join('; '),
  });
  const rows=binaries.map((binary,index)=>describe(`binary:${binary.slug||binary.sha256||index}`,String(binary.name||binary.label||binary.slug||binary.sha256||'Unnamed build'),true,members.filter(member=>belongs(binary,member))));
  const outside=[...new Set(members.filter(member=>!binaries.some(binary=>belongs(binary,member))).map(member=>String(member.slug||'')))];
  for(const slug of outside)rows.push(describe(`member:${slug}`,slug||'Build not recorded',false,members.filter(member=>String(member.slug||'')===slug)));
  return rows;
}

export function CoverageMatrix({members,binaries}:{members:Data[];binaries:Data[]}) {
  const rows=coverageRows(members,binaries);
  const covered=rows.filter(row=>row.members.length>0).length;
  return <section aria-label="Coverage by build"><h3>Coverage by build</h3>
    <p>{covered} of {rows.length} builds return a member for this identity.</p>
    <p className="muted">Locator status is not shown. The server does not send a per-build status for this identity yet.</p>
    {rows.length?<table className="ws-table"><thead><tr><th>Build</th><th>Members</th><th>Addresses</th><th>Method and confidence</th></tr></thead><tbody>{rows.map(row=><tr key={row.key}>
      <td><strong>{row.build}</strong>{!row.inLibrary&&<small>Not in the binary library</small>}</td>
      <td>{row.coverage}</td>
      <td>{row.addresses?<code>{row.addresses}</code>:'None'}</td>
      <td>{row.methods||'None'}</td>
    </tr>)}</tbody></table>:<p>No builds to compare.</p>}
  </section>;
}
