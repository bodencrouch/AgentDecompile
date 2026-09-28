import type { ArtifactFormat } from "../analysis/contracts";
import type { WorkerMessage, WorkerRequest } from "./protocol";

export type ArtifactNode = {id: string; name: string; kind: string; offset: number | null; size: number; children?: ArtifactNode[]};

export type ArtifactInspection = {
  format: ArtifactFormat;
  architecture: string;
  byteLength: number;
  strings: string[];
  structure: ArtifactNode[];
};

const architectureByElfMachine: Record<number, string> = {
  3: "x86",
  40: "arm",
  62: "x86_64",
  183: "aarch64",
};
const architectureByPeMachine: Record<number, string> = {
  0x14c: "x86",
  0x8664: "x86_64",
  0x1c0: "arm",
  0xaa64: "aarch64",
};

function asciiStrings(bytes: Uint8Array, maximum = 250): string[] {
  const results: string[] = [];
  let start = -1;
  for (let index = 0; index <= bytes.length; index += 1) {
    const printable = index < bytes.length && bytes[index] >= 0x20 && bytes[index] <= 0x7e;
    if (printable && start < 0) start = index;
    if ((!printable || index === bytes.length) && start >= 0) {
      if (index - start >= 4) results.push(new TextDecoder().decode(bytes.slice(start, index)));
      start = -1;
      if (results.length >= maximum) break;
    }
  }
  return results;
}

/** Bounded ELF/PE section metadata; no archive extraction or executable loading. */
export function artifactStructure(bytes: Uint8Array, format: "elf"|"pe"): ArtifactNode[] {
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const range=(offset:number,size:number)=>{
    if(!Number.isSafeInteger(offset)||!Number.isSafeInteger(size)||offset<0||size<0||offset>bytes.length||size>bytes.length-offset)throw new Error("Section range exceeds artifact bytes");
  };
  const name=(offset:number,length:number)=>{range(offset,length);const part=bytes.subarray(offset,offset+length);const nul=part.indexOf(0);return new TextDecoder().decode(nul<0?part:part.subarray(0,nul));};
  const rows:ArtifactNode[]=[];
  if(format==='pe') {
    range(0,64);const coff=view.getUint32(60,true);range(coff,24);
    if(view.getUint32(coff,true)!==0x00004550)throw new Error('Invalid PE signature');
    const count=view.getUint16(coff+6,true),start=coff+24+view.getUint16(coff+20,true);
    if(count>4096)throw new Error('PE section count exceeds parser limit');
    range(start,count*40);
    for(let i=0;i<count;i++) {const at=start+i*40;const size=view.getUint32(at+16,true),offset=view.getUint32(at+20,true);if(size)range(offset,size);
      rows.push({id:`section:${i}`,name:name(at,8)||`Section ${i}`,kind:'section',offset:size?offset:null,size});}
    return [{id:'pe',name:'PE image',kind:'image',offset:0,size:bytes.length,children:[{id:'headers',name:'Headers and section table',kind:'headers',offset:0,size:start+count*40},...rows]}];
  }
  range(0,16);const wide=bytes[4]===2,little=bytes[5]===1;
  if(![1,2].includes(bytes[4])||![1,2].includes(bytes[5]))throw new Error('Invalid ELF class or byte order');
  range(0,wide?64:52);
  const word=(at:number)=>{range(at,wide?8:4);const value=wide?Number(view.getBigUint64(at,little)):view.getUint32(at,little);if(!Number.isSafeInteger(value))throw new Error('ELF offset exceeds exact integer range');return value;};
  const start=word(wide?40:32),entry=view.getUint16(wide?58:46,little),count=view.getUint16(wide?60:48,little),names=view.getUint16(wide?62:50,little);
  if(!start&&count===0)return [{id:'elf',name:'ELF image (no section table)',kind:'image',offset:0,size:bytes.length}];
  if(count===0||names===0xffff)throw new Error('Extended ELF section numbering is not supported by this parser');
  if(count>4096||entry<(wide?64:40)||names>=count)throw new Error('Invalid or oversized ELF section table');
  range(start,count*entry);
  const nameHeader=start+names*entry,nameOffset=word(nameHeader+(wide?24:16)),nameSize=word(nameHeader+(wide?32:20));range(nameOffset,nameSize);
  for(let i=0;i<count;i++) {const at=start+i*entry,type=view.getUint32(at+4,little),size=word(at+(wide?32:20)),offset=word(at+(wide?24:16)),nameIndex=view.getUint32(at,little);
    if(type!==8&&size)range(offset,size);
    if(nameIndex>=nameSize&&nameIndex!==0)throw new Error('ELF section name exceeds string table');
    rows.push({id:`section:${i}`,name:nameIndex?name(nameOffset+nameIndex,nameSize-nameIndex):`Section ${i}`,kind:type===8?'zero-fill':'section',offset:type===8||!size?null:offset,size});}
  return [{id:'elf',name:'ELF image',kind:'image',offset:0,size:bytes.length,children:rows}];
}

function inspect(bytes: Uint8Array): ArtifactInspection {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length >= 20 && bytes[0] === 0x7f && bytes[1] === 0x45 && bytes[2] === 0x4c && bytes[3] === 0x46) {
    const littleEndian = bytes[5] !== 2;
    return {
      structure: artifactStructure(bytes, "elf"),
      format: "elf",
      architecture: architectureByElfMachine[view.getUint16(18, littleEndian)] ?? "unknown",
      byteLength: bytes.length,
      strings: asciiStrings(bytes),
    };
  }
  if (bytes.length >= 0x40 && bytes[0] === 0x4d && bytes[1] === 0x5a) {
    const offset = view.getUint32(0x3c, true);
    if (offset + 6 <= bytes.length && bytes[offset] === 0x50 && bytes[offset + 1] === 0x45) {
      return {
        structure: artifactStructure(bytes, "pe"),
        format: "pe",
        architecture: architectureByPeMachine[view.getUint16(offset + 4, true)] ?? "unknown",
        byteLength: bytes.length,
        strings: asciiStrings(bytes),
      };
    }
  }
  throw new Error("Unsupported or malformed artifact; expected ELF or PE");
}

self.onmessage = (event: MessageEvent<WorkerRequest<ArrayBuffer>>) => {
  const request = event.data;
  try {
    if (request.payload.byteLength > request.limits.maxArtifactBytes) {
      const error: WorkerMessage<ArtifactInspection> = {
        kind: "error",
        id: request.id,
        revisionId: request.revisionId,
        failure: {
          code: "artifact-too-large",
          message: "Artifact exceeds the worker memory limit",
          retryable: false,
        },
      };
      self.postMessage(error);
      return;
    }
    const value = inspect(new Uint8Array(request.payload));
    const result: WorkerMessage<ArtifactInspection> = {
      kind: "result",
      id: request.id,
      revisionId: request.revisionId,
      value,
      freshness: { state: "fresh", version: request.revisionId, indexedAt: new Date().toISOString() },
    };
    self.postMessage(result);
  } catch (error) {
    const failure: WorkerMessage<ArtifactInspection> = {
      kind: "error",
      id: request.id,
      revisionId: request.revisionId,
      failure: {
        code: "artifact-parse-failed",
        message: error instanceof Error ? error.message : "Artifact parsing failed",
        retryable: false,
      },
    };
    self.postMessage(failure);
  }
};
