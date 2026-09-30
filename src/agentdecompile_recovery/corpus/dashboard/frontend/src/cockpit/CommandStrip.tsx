// The one command that feeds the cockpit: point it at any folder of binaries.
import { useState } from 'react';

export const CLI_BASE = 'uvx --from git+https://github.com/bolabaden/agentdecompile agentdecompile-cli';
export const CLI_ARG = '<path>';
export const CLI_COMMAND = `${CLI_BASE} ${CLI_ARG}`;

export function CommandStrip() {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    };
    if (navigator.clipboard?.writeText) void navigator.clipboard.writeText(CLI_COMMAND).then(done).catch(() => fallbackCopy() && done());
    else if (fallbackCopy()) done();
  };
  return (
    <div className="cp-cli" data-tip="One command: recognise, group and recover everything under <path>">
      <code className="cp-mono">
        <span className="cp-cli-prompt" aria-hidden="true">$</span> {CLI_BASE} <span className="cp-cli-arg">{CLI_ARG}</span>
      </code>
      <button type="button" className="cp-iconbtn" onClick={copy} aria-label="Copy command" data-tip={copied ? 'Copied' : 'Copy command'}>
        {copied ? (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="1" fill="none" stroke="currentColor" strokeWidth="1.3" /><path d="M8 3.5V1.5H1.5V8h2" fill="none" stroke="currentColor" strokeWidth="1.3" /></svg>
        )}
      </button>
      <span className="cp-sr" aria-live="polite">{copied ? 'Copied' : ''}</span>
    </div>
  );
}

function fallbackCopy(): boolean {
  const ta = document.createElement('textarea');
  ta.value = CLI_COMMAND;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}
