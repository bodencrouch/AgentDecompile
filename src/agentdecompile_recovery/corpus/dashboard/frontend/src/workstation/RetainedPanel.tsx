import {cloneElement,useRef,type ReactElement} from 'react';
/** Keep drafts/attempts alive without feeding hidden tools new selection or refresh props. */
export function RetainedPanel({active,children}:{active:boolean;children:ReactElement<{active?:boolean}>}) {
  const retained=useRef<ReactElement<{active?:boolean}>|null>(null);
  if(active)retained.current=children;
  return <div className="ws-retained-panel" hidden={!active} inert={!active}>{retained.current&&cloneElement(retained.current,{active})}</div>;
}
