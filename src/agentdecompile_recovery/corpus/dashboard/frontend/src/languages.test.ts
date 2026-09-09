import { describe, expect, it } from 'vitest';
import {
  defaultSourceLanguage,
  languageFromPath,
  languageSpec,
  parseSourceLanguage,
} from './languages';

describe('languages registry', () => {
  it('defaults to C++ when value is empty', () => {
    expect(defaultSourceLanguage()).toBe('cxx');
    expect(parseSourceLanguage('')).toBe('cxx');
    expect(parseSourceLanguage(null)).toBe('cxx');
  });

  it('parses aliases and enum ids', () => {
    expect(parseSourceLanguage('cpp')).toBe('cxx');
    expect(parseSourceLanguage('C#')).toBe('csharp');
    expect(parseSourceLanguage('rust')).toBe('rust');
    expect(parseSourceLanguage('not-a-language', { default: undefined })).toBe('unknown');
  });

  it('infers language from path suffixes', () => {
    expect(languageFromPath('/tmp/foo/bar.rs')).toBe('rust');
    expect(languageFromPath('module.go')).toBe('go');
    expect(languageSpec(languageFromPath('witness.cpp')).monacoId).toBe('cpp');
    expect(languageFromPath('readme.md', { default: 'text' })).toBe('text');
  });
});
