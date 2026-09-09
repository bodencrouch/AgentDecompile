import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker';
import 'monaco-editor/esm/vs/editor/contrib/find/browser/findController.js';
import 'monaco-editor/esm/vs/editor/contrib/folding/browser/folding.js';
import 'monaco-editor/esm/vs/editor/contrib/bracketMatching/browser/bracketMatching.js';

const contributionByMonacoId: Record<string, () => Promise<unknown>> = {
  c: () => import('monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution.js'),
  cpp: () => import('monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution.js'),
  rust: () => import('monaco-editor/esm/vs/basic-languages/rust/rust.contribution.js'),
  go: () => import('monaco-editor/esm/vs/basic-languages/go/go.contribution.js'),
  csharp: () => import('monaco-editor/esm/vs/basic-languages/csharp/csharp.contribution.js'),
  java: () => import('monaco-editor/esm/vs/basic-languages/java/java.contribution.js'),
};

const loadedContributions = new Set<string>();

export async function ensureMonacoLanguage(monacoId: string): Promise<void> {
  const loader = contributionByMonacoId[monacoId];
  if (!loader || loadedContributions.has(monacoId)) {
    return;
  }
  await loader();
  loadedContributions.add(monacoId);
  if (monacoId === 'c' || monacoId === 'cpp') {
    loadedContributions.add('c');
    loadedContributions.add('cpp');
  }
}

(globalThis as typeof globalThis & {MonacoEnvironment: unknown}).MonacoEnvironment={getWorker:()=>new EditorWorker()};
export {monaco};
monaco.languages.register({id:'agentdecompile-asm'});
monaco.languages.setMonarchTokensProvider('agentdecompile-asm',{ignoreCase:true,tokenizer:{root:[[/[;#].*$/,'comment'],[/\b(?:0x[0-9a-f]+|[0-9a-f]+h|\d+)\b/,'number'],[/\b(?:r(?:[0-9]|1[0-5])|[wx]\d+|[re]?(?:ax|bx|cx|dx|sp|bp|si|di|ip)|[xyz]mm\d+|lr|pc|sp|fp)\b/,'variable'],[/\b(?:mov|lea|ldr|str|push|pop|call|ret|jmp|j[a-z]+|cmp|test|add|sub|mul|div|and|orr?|xor|not|nop|b|bl|bx|cbz|cbnz)\b/,'keyword'],[/[\[\](),:+*=-]/,'delimiter']]}});
