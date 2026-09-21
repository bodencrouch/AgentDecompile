import {useRef,type ReactNode} from 'react';
/** Keep drafts/attempts alive without feeding hidden tools new selection or refresh props. */
export function RetainedPanel({active,children}:{active:boolean;children:ReactNode}) {
  const retained=useRef<ReactNode>(null);
  if(active)retained.current=children;
  return <div className="ws-retained-panel" hidden={!active} inert={!active}>{retained.current}</div>;
}
