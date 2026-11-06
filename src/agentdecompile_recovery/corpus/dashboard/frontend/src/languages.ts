export type SourceLanguage =
  | 'c'
  | 'cxx'
  | 'rust'
  | 'go'
  | 'csharp'
  | 'java'
  | 'gas'
  | 'masm'
  | 'asm'
  | 'text'
  | 'unknown';

export type LanguageSpec = {
  id: SourceLanguage;
  displayName: string;
  fileExtensions: readonly string[];
  monacoId: string | null;
  defaultExportExtension: string;
};

const REGISTRY = {} as Record<SourceLanguage, LanguageSpec>;
const SUFFIX_INDEX: Record<string, SourceLanguage> = {};
const ALIAS: Record<string, SourceLanguage> = {};

function register(spec: LanguageSpec): LanguageSpec {
  REGISTRY[spec.id] = spec;
  for (const ext of spec.fileExtensions) {
    SUFFIX_INDEX[ext.toLowerCase()] = spec.id;
  }
  for (const alias of [spec.id, ...spec.fileExtensions]) {
    ALIAS[alias.toLowerCase()] = spec.id;
  }
  return spec;
}

export const C = register({
  id: 'c',
  displayName: 'C',
  fileExtensions: ['.c', '.h'],
  monacoId: 'c',
  defaultExportExtension: '.c',
});

export const CXX = register({
  id: 'cxx',
  displayName: 'C++',
  fileExtensions: ['.cpp', '.cxx', '.cc', '.hpp', '.hh', '.hxx'],
  monacoId: 'cpp',
  defaultExportExtension: '.cpp',
});

export const RUST = register({
  id: 'rust',
  displayName: 'Rust',
  fileExtensions: ['.rs'],
  monacoId: 'rust',
  defaultExportExtension: '.rs',
});

export const GO = register({
  id: 'go',
  displayName: 'Go',
  fileExtensions: ['.go'],
  monacoId: 'go',
  defaultExportExtension: '.go',
});

export const CSHARP = register({
  id: 'csharp',
  displayName: 'C#',
  fileExtensions: ['.cs'],
  monacoId: 'csharp',
  defaultExportExtension: '.cs',
});

export const JAVA = register({
  id: 'java',
  displayName: 'Java',
  fileExtensions: ['.java'],
  monacoId: 'java',
  defaultExportExtension: '.java',
});

export const GAS = register({
  id: 'gas',
  displayName: 'GNU assembly',
  fileExtensions: ['.s'],
  monacoId: 'agentdecompile-asm',
  defaultExportExtension: '.s',
});

export const MASM = register({
  id: 'masm',
  displayName: 'MASM assembly',
  fileExtensions: ['.asm'],
  monacoId: 'agentdecompile-asm',
  defaultExportExtension: '.asm',
});

export const ASM = register({
  id: 'asm',
  displayName: 'Assembly',
  fileExtensions: [],
  monacoId: 'agentdecompile-asm',
  defaultExportExtension: '.asm',
});

export const TEXT = register({
  id: 'text',
  displayName: 'Plain text',
  fileExtensions: ['.txt'],
  monacoId: 'plaintext',
  defaultExportExtension: '.txt',
});

export const UNKNOWN = register({
  id: 'unknown',
  displayName: 'Unknown',
  fileExtensions: [],
  monacoId: 'plaintext',
  defaultExportExtension: '.txt',
});

for (const [alias, target] of Object.entries({
  'c++': 'cxx',
  cpp: 'cxx',
  cxx: 'cxx',
  'c#': 'csharp',
  cs: 'csharp',
  csharp: 'csharp',
  rs: 'rust',
  rust: 'rust',
  go: 'go',
  java: 'java',
  masm: 'masm',
  gas: 'gas',
  asm: 'asm',
  assembly: 'asm',
  text: 'text',
} satisfies Record<string, SourceLanguage>)) {
  ALIAS[alias] = target;
}

export function defaultSourceLanguage(): SourceLanguage {
  return 'cxx';
}

export function languageSpec(language: SourceLanguage): LanguageSpec {
  return REGISTRY[language] ?? REGISTRY.unknown;
}

export function parseSourceLanguage(
  value: unknown,
  options?: { default?: SourceLanguage },
): SourceLanguage {
  const text = String(value ?? '').trim().toLowerCase();
  if (!text) {
    return options?.default ?? defaultSourceLanguage();
  }
  if (text in ALIAS) {
    return ALIAS[text];
  }
  if (text in REGISTRY) {
    return text as SourceLanguage;
  }
  return options?.default ?? 'unknown';
}

export function languageFromPath(
  path: string,
  options?: { default?: SourceLanguage },
): SourceLanguage {
  const match = /\.[^./\\]+$/.exec(path);
  const suffix = match ? match[0].toLowerCase() : '';
  if (suffix && suffix in SUFFIX_INDEX) {
    return SUFFIX_INDEX[suffix];
  }
  return options?.default ?? 'unknown';
}

export function sourceWitnessLabel(record: {
  sourceLanguage?: unknown;
  source_language?: unknown;
}): string {
  const explicit = parseSourceLanguage(
    record.sourceLanguage ?? record.source_language,
    { default: undefined },
  );
  if (explicit !== 'unknown') {
    return `${languageSpec(explicit).displayName} witness`;
  }
  return 'Source witness';
}
