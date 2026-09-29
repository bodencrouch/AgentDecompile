# What MSVC actually did: optimization and code-generation transformations for decompilation and byte matching

Date: 2026-09-29. Status: research reference (text only; nothing here was compiled,
linked or run). It covers Microsoft Visual C++ (`cl.exe` and `link.exe`) on x86
and x64. It is organised around **observable transformations**, meaning what a
reader of a shipped PE image can see, so it can drive a "what the compiler
actually did" view.

For each transformation the entries give:

- **Cause**: the flags or toolchain versions that produce it.
- **Looks like**: an illustrative C fragment and the x86 (or x64) it becomes.
  Snippets are hand-written illustrations of the documented pattern. They are
  not captured compiler output, and exact registers and offsets vary.
- **Ghidra misrenders**: how a decompiler such as Ghidra typically shows it.
- **Matching practice**: how matching-decomp projects recognise it and write
  source that reproduces it.
- **Evidence**: what in a binary proves it or suggests it.

Anything not taken from a cited source is marked **(inference)**. Example
symbols are generic: `FUN_0041c880`, `ResourceRef::Resolve` and builds
`build-a` … `build-d`.

---

## 0. What this repository already records

These are the existing project notes that this research extends. All are text
references and none were re-verified here.

- **Global preconditions come before per-function idiom search.**
  [docs/plans/2026-07-31-001-ideal-reconstruction-loop.md](../plans/2026-07-31-001-ideal-reconstruction-loop.md) §2
  lists what must all be right at once for one objdiff match: compiler identity
  (for its 2003-era target it names the "MSVC 6.0 / 7.0 / 7.1 era"),
  optimization flags ("`/O2 /Ob1 /GF /Gy /GR /EHsc` and friends"), struct
  layouts, calling conventions and name mangling, inlining decisions, and
  source-level idiom. It concludes that items 1–4 are global and that the
  per-function loop "is attacking the wrong layer" while they are unsettled.
  The same document (§ on the msvc-wine backend) records that a modern
  `cl.exe` 19.51 compiles and produces valid objects, but "will not reproduce
  the original instruction selection, register allocation, or inlining
  decisions". Byte parity "needs the *era-correct* compiler".
- **METHODOLOGY.md** says compiler identity, optimization, ABI, calling
  conventions and layouts "affect thousands of functions", while expression
  shape, temporaries, inlining and control flow are per-function. It also says
  mismatch routing uses instruction-level objdiff evidence, with classes that
  feed permuter, shape search, boundary repair, prototype repair and
  compiler-profile correction.
- **STRATEGY.md** (Corpus recovery pipeline; Whole-image byte identity) says
  that recovery units, compilation units and comparison units are distinct.
  Fragments "may be assembled into translation units or LTCG groups; compare
  the final emitted region when an intermediate object is insufficient".
  Toolchain records include "compiler/linker hashes, headers/libraries,
  language, macros, packing, floating-point mode, grouping and scoped
  overrides". It says to "probe legacy toolchain support instead of copying
  modern switches". It also makes per-function objdiff-0 and a whole-image
  byte-identical relink **separate claims**. The linker owns section order,
  padding, the import table and relocations, and link maps must show that
  replacements "reach the checked image despite elimination, folding or
  preserved fallback code".
- **[docs/plans/2026-09-09-0334-feat-evidence-fusion-matcher-plan.md](../plans/2026-09-09-0334-feat-evidence-fusion-matcher-plan.md)**
  says that "Inlining, cloning, and ICF already break forced 1↔1 assumptions"
  in cross-build identity.
- **[docs/plans/2026-09-22-recovery-contracts-and-validation-plan.md](../plans/2026-09-22-recovery-contracts-and-validation-plan.md)**
  (§ reccmp) adopts reccmp as a companion to objdiff "for supported legacy MSVC
  C++ targets", with stack, vtable, global-data and symbol-location
  diagnostics. It requires reports bound to the exact binary, PDB and source.
- **[docs/solutions/architecture-patterns/decomp-matching-toolchain.md](../solutions/architecture-patterns/decomp-matching-toolchain.md)**
  records objdiff as the byte-match success criterion, m2c for switch-heavy
  assembly and decomp-permuter for near misses (via `run-decomp-match`).
- **docs/CRITICAL_PATH.md** says PE/MSVC verification needs `--vc-root` and a
  Wine prefix, and that names and types stay advisory until objdiff reports
  `differences==0`.

---

## 1. Flag bundles at a glance

| Flag | Expands to / effect | Source |
|---|---|---|
| `/Od` | No optimization. Implies `/Ob0`. Debug default. | [/Ob](https://learn.microsoft.com/en-us/cpp/build/reference/ob-inline-function-expansion) |
| `/O1` | `/Og /Os /Oy /Ob2 /GF /Gy` | [/O1,/O2](https://learn.microsoft.com/en-us/cpp/build/reference/o1-o2-minimize-size-maximize-speed) |
| `/O2` | `/Og /Oi /Ot /Oy /Ob2 /GF /Gy`. Release default. | same |
| `/Ox` | `/Og /Oi /Ot /Oy /Ob2`, without `/GF /Gy` | [/Ox](https://learn.microsoft.com/en-us/cpp/build/reference/ox-full-optimization) |
| `/Os` / `/Ot` | Favor size / favor speed within `/Og` | [/Os,/Ot](https://learn.microsoft.com/en-us/cpp/build/reference/os-ot-favor-small-code-favor-fast-code) |
| `/Oy` | x86 frame-pointer omission. `/O1` and `/O2` imply it on x86. | [/Oy](https://learn.microsoft.com/en-us/cpp/build/reference/oy-frame-pointer-omission) |
| `/Ob0/1/2/3` | Inlining off / only marked `inline` / any / more aggressive (VS2019+) | [/Ob](https://learn.microsoft.com/en-us/cpp/build/reference/ob-inline-function-expansion) |
| `/Oi` | Intrinsic forms of `memcpy`, `strlen`, and so on | [/Oi](https://learn.microsoft.com/en-us/cpp/build/reference/oi-generate-intrinsic-functions), [#pragma intrinsic](https://learn.microsoft.com/en-us/cpp/preprocessor/intrinsic) |
| `/GL` + `/LTCG` | Whole-program code generation at link time | [/GL](https://learn.microsoft.com/en-us/cpp/build/reference/gl-whole-program-optimization), [/LTCG](https://learn.microsoft.com/en-us/cpp/build/reference/ltcg-link-time-code-generation) |
| `/Gy` | Every function becomes its own COMDAT | [/Gy](https://learn.microsoft.com/en-us/cpp/build/reference/gy-enable-function-level-linking) |
| `/OPT:REF,ICF` | Drop unreferenced COMDATs; fold identical ones. On by default unless `/DEBUG`. | [/OPT](https://learn.microsoft.com/en-us/cpp/build/reference/opt-optimizations) |
| `/GF` | Pool identical string literals into read-only data | [/GF](https://learn.microsoft.com/en-us/cpp/build/reference/gf-eliminate-duplicate-strings) |
| `/GS` | Stack security cookie. On by default in current toolsets. | [/GS](https://learn.microsoft.com/en-us/cpp/build/reference/gs-buffer-security-check) |
| `/EHsc`, `/EHa`, legacy `/GX` | C++ exception model | [/EH](https://learn.microsoft.com/en-us/cpp/build/reference/eh-exception-handling-model) |
| `/RTC1` (`/RTCsu`), `/RTCc`; legacy `/GZ` | Debug runtime checks | [/RTC](https://learn.microsoft.com/en-us/cpp/build/reference/rtc-run-time-error-checks) |
| `/INCREMENTAL` | Jump thunks and padding. Implied by `/DEBUG`. | [/INCREMENTAL](https://learn.microsoft.com/en-us/cpp/build/reference/incremental-link-incrementally) |
| `/hotpatch` + `/FUNCTIONPADMIN` | 2-byte first instruction plus pre-function pad | [/hotpatch](https://learn.microsoft.com/en-us/cpp/build/reference/hotpatch-create-hotpatchable-image), [/FUNCTIONPADMIN](https://learn.microsoft.com/en-us/cpp/build/reference/functionpadmin-create-hotpatchable-image) |
| `/Gd /Gr /Gz /Gv` | Default convention: cdecl / fastcall / stdcall / vectorcall | [conventions](https://learn.microsoft.com/en-us/cpp/cpp/argument-passing-and-naming-conventions) |
| `/Zp[n]`, `#pragma pack` | Struct member alignment | [/Zp](https://learn.microsoft.com/en-us/cpp/build/reference/zp-struct-member-alignment) |
| `/GR` | Emit RTTI | [/GR](https://learn.microsoft.com/en-us/cpp/build/reference/gr-enable-run-time-type-information) |
| `/Gs[n]` | Stack-probe threshold (`__chkstk`) | [/Gs](https://learn.microsoft.com/en-us/cpp/build/reference/gs-control-stack-checking-calls) |
| `/Gw` | Global data in COMDATs (so it can be removed or folded) | [/Gw](https://learn.microsoft.com/en-us/cpp/build/reference/gw-optimize-global-data) |

Legacy bundles differ. For VC6-era compilers, `/O2` is commonly remembered as
`/Og /Oi /Ot /Oy /Ob1 /Gs /Gf /Gy` **(inference; from VC6-era documentation,
not re-verified)**. The key difference is **`/Ob1`**: only functions marked
`inline` or defined in-class were inlined. That is consistent with the
`/O2 /Ob1 …` recipe this repo already records (§0).

The decomp.me MSVC flag picker exposes exactly the axes that matter for the
legacy compilers it hosts:

- optimization level: `/Od /O1 /O2 /Os /Ot /Og /Ox`
- CPU target: `/GB /G3–/G6`
- `/fp:*`
- CRT: `/ML /MT /MD` and their debug forms
- inlining: `/Ob0–2`
- alignment: `/Zp1–16`
- default convention: `/Gd /Gr /Gz`
- checkboxes: `/TP`, `/GR`, `/GX`, `/Gs`, `/GS-`, `/GZ`

Source: `COMMON_MSVC_FLAGS` in
[decomp.me backend flags.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py).

---

## 2. Transformations: optimization level and frame shape

### T1. `/Od` versus `/O1`, `/O2`, `/Ox`, `/Os`, `/Ot`

**Cause.**

- `/Od` is the debug default: no register allocation across statements, no
  inlining (`/Ob0`), and an EBP frame.
- `/O2` is the release default. `/O1` favors size. `/Ox` is `/O2` without
  `/GF /Gy`.
- All are documented at
  [/O1,/O2](https://learn.microsoft.com/en-us/cpp/build/reference/o1-o2-minimize-size-maximize-speed)
  and [/Ox](https://learn.microsoft.com/en-us/cpp/build/reference/ox-full-optimization).

**Looks like.**

```c
int SumArray(const int *values, int count) {
    int total = 0;
    for (int i = 0; i < count; i++) total += values[i];
    return total;
}
```

```asm
; /Od: every variable lives in memory; the loop test sits at the bottom behind a jmp
push ebp
mov  ebp, esp
sub  esp, 8
mov  dword ptr [ebp-4], 0        ; total
mov  dword ptr [ebp-8], 0        ; i
jmp  short check
next: mov eax, [ebp-8]
      add eax, 1
      mov [ebp-8], eax
check: mov ecx, [ebp-8]
      cmp ecx, [ebp+0Ch]
      jge short done
      mov edx, [ebp+8]
      mov eax, [ebp-4]
      add eax, [edx+ecx*4]
      mov [ebp-4], eax
      jmp short next
done: mov eax, [ebp-4]
      mov esp, ebp
      pop ebp
      ret
```

```asm
; /O2: no frame, strength-reduced pointer, count-down loop
mov  ecx, [esp+8]      ; count
xor  eax, eax
test ecx, ecx
jle  short done
mov  edx, [esp+4]      ; values
top: add eax, [edx]
     add edx, 4
     dec ecx
     jnz short top
done: ret
```

`/O1` (`/Os`) prefers shorter encodings:

- `push`/`pop` pairs in place of `mov`
- `lea` chains
- `xor r,r`
- the shared `_EH_prolog` helper for C++ EH frames

That last point is described in
[OpenRCE Part I](https://www.openrce.org/articles/full_view/21). The rest of
this list is **(inference)**.

**Ghidra misrenders.**

- At `/Od` Ghidra's output is close to source, but it gives stack names
  (`local_8`, `local_c`) and the loop often comes out as `while` or `for` with
  the increment in an odd place.
- At `/O2` the induction variable disappears into a pointer walk:
  `do { total += *p; p++; count--; } while (count != 0);`.
  The original index form is not visible.

**Matching practice.**

- The optimization level is a global parameter; it is decomp.me's first flag
  group. Get it right before editing any function.
- At `/O2`, write the **natural source** (the indexed `for`), not Ghidra's
  pointer form. The compiler strength-reduces it back. Writing the pointer
  form often changes register choice.
- Mixed levels inside one image are common (for example `#pragma optimize("", off)`
  or per-file settings). Use
  [#pragma optimize](https://learn.microsoft.com/en-us/cpp/preprocessor/optimize)
  to reproduce a single function.

**Evidence.**

| Level | What to look for |
|---|---|
| `/Od` | every local round-trips through `[ebp-x]`; `jmp` to a bottom-of-loop test; no callee-saved register use in leaf functions; often `/RTC` fills (T11) |
| `/O2` vs `/O1` | whether small functions are inlined and whether loops are aligned or padded (inference) |

### T2. `/Oy` frame-pointer omission (EBP versus ESP frames, FPO data)

**Cause.**

- `/Oy` is implied by `/O1` and `/O2` on x86
  ([/Oy](https://learn.microsoft.com/en-us/cpp/build/reference/oy-frame-pointer-omission)).
  It is x86 only.
- On x64 there is normally no frame pointer. Unwinding uses `.pdata`/`.xdata`
  ([x64 prolog/epilog](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog)).
  A frame register is established only for `alloca` and similar dynamic
  frames.
- Functions with SEH or C++ EH, or with `alloca`, keep EBP even under `/Oy`
  **(inference, consistent with the EH frame layouts in OpenRCE Part I)**.

**Looks like.**

```asm
; EBP frame (/Oy-): arguments at fixed [ebp+8], [ebp+0Ch]
push ebp
mov  ebp, esp
mov  eax, [ebp+8]

; FPO (/Oy): arguments addressed from ESP; offsets shift after every push
push esi
mov  esi, [esp+8]          ; first argument (was [esp+4] before the push)
push edi
mov  edi, [esp+10h]        ; second argument
; EBP may now be used as an ordinary register
```

**Ghidra misrenders.**

- Ghidra tracks ESP deltas. When a callee's stack purge is unknown (an
  unresolved `__stdcall` import, or an indirect call), the depth analysis
  fails. The output then shows `in_stack_0000000c`, "Stack depth mismatch"
  warnings, or the wrong parameter count.
- When EBP is used as a general register, Ghidra shows `unaff_EBP`.

**Matching practice.** This is a global flag: `/Oy` versus `/Oy-`. A mismatch
shows up in the first byte of almost every function.

**Evidence.**

- Most non-EH functions start without `push ebp; mov ebp, esp`.
- EBP is written as data.
- For x86 PDB/DBG images, the presence of FPO records
  ([FPO_DATA](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-fpo_data)).

### T3. Inlining: `/Ob0`–`/Ob3` and `__forceinline`

**Cause.**

- `/Ob1` expands only functions marked `inline`, `__inline` or
  `__forceinline`, or member functions defined in the class body.
- `/Ob2` (the `/O1` and `/O2` default) lets the compiler inline anything not
  marked `noinline`. `/Ob3` is VS2019+.
- `__forceinline` is still only a strong hint
  ([/Ob](https://learn.microsoft.com/en-us/cpp/build/reference/ob-inline-function-expansion),
  [inline functions](https://learn.microsoft.com/en-us/cpp/cpp/inline-functions-cpp)).
- Cross-TU inlining requires LTCG (T5).

**Looks like.**

```cpp
class ResourceRef {
    void *m_cached; int m_id;
public:
    void *Resolve() { return m_cached ? m_cached : Load(m_id); }  // in-class, inline under /Ob1
    static void *Load(int id);
};
void *UseTwice(ResourceRef *r) { r->Resolve(); return r->Resolve(); }
```

```asm
; No call to Resolve: its body appears twice in the caller
mov  eax, [esi]            ; m_cached
test eax, eax
jnz  short have1
push dword ptr [esi+4]     ; m_id
call ?Load@ResourceRef@@SAPAXH@Z
add  esp, 4
have1:
mov  eax, [esi]
test eax, eax
jnz  short have2
...
```

**Ghidra misrenders.**

- The inlined body is flattened into the caller. The same `m_cached`/`m_id`
  test appears several times with no name.
- Field offsets may be typed differently in each copy.
- A standalone copy of `Resolve` (the COMDAT kept when the address is taken or
  some call site was not inlined) shows as a separate `FUN_…` with no link to
  the inlined sites.

**Matching practice.**

- Under `/Ob1`, *where the function is defined* (in-class, or `inline` in a
  header) decides whether it inlines. That is a source-structure decision, not
  a flag tweak.
- Projects keep small accessors in headers and test the inline versus
  out-of-line placement of each helper.
- Useful hints include `__forceinline`, `__declspec(noinline)` and
  `#pragma auto_inline(off)`
  ([/Ob](https://learn.microsoft.com/en-us/cpp/build/reference/ob-inline-function-expansion)).
- The project's evidence-fusion plan already treats inline occurrences as
  non-1:1 identity (§0).

**Evidence.**

- The same short instruction sequence with the same field offsets appears
  across many callers.
- An out-of-line COMDAT twin exists.
- Newer PDBs carry inline-site symbol records that name the inlinee
  **(inference about which toolset versions emit them)**.

### T4. `/Oi` intrinsics (`memcpy`, `strlen`, `memset` expanded inline; `rep movs`)

**Cause.**

- `/Oi` is included in `/O2` and `/Ox`, not in `/O1`.
- `#pragma intrinsic(...)` or `#pragma function(...)` switches it per function
  ([/Oi](https://learn.microsoft.com/en-us/cpp/build/reference/oi-generate-intrinsic-functions),
  [#pragma intrinsic](https://learn.microsoft.com/en-us/cpp/preprocessor/intrinsic)).

**Looks like.**

```c
struct Header { int words[16]; };
void CopyHeader(struct Header *d, const struct Header *s) { memcpy(d, s, sizeof *d); }
size_t NameLen(const char *s) { return strlen(s); }
```

```asm
; memcpy of a constant 64 bytes
mov  ecx, 10h
mov  esi, [esp+8+..]
mov  edi, [esp+4+..]
rep movsd

; strlen, the classic legacy-x86 idiom
mov  edi, [esp+4]
or   ecx, 0FFFFFFFFh
xor  eax, eax
repne scasb
not  ecx
dec  ecx                ; ecx = length
```

**Ghidra misrenders.**

- `rep movsd` becomes `for (i = 0x10; i != 0; i--) { *dst = *src; src++; dst++; }`.
- `repne scasb` becomes a do/while that decrements `0xffffffff` and ends in
  `~uVar1 - 1`. That is hard to recognise as `strlen`.
- Variable-length forms produce a `movsd` loop followed by a `movsb` tail.
- **(inference)**: this is Ghidra's generic string-instruction p-code
  modelling.

**Matching practice.**

- Write the library call in the source, not the loop. The byte pattern is
  reproduced by `/Oi` plus the matching CRT headers.
- If a function has the call rather than the inline form, the TU was built
  without `/Oi`, or with `#pragma function`.

**Evidence.**

- `or ecx,-1 / repne scasb / not ecx` for strlen.
- `rep movsd` followed by `and ecx,3 / rep movsb` for variable-length copies.
- `rep stosd` with `eax` zeroed for memset.
- No import or call of `memcpy` or `strlen` from those sites.

### T5. `/GL` + `/LTCG`: whole-program optimization

**Cause.** When `/LTCG` links modules compiled with `/Og`, `/O1`, `/O2` or
`/Ox`, Microsoft lists these optimizations
([/LTCG](https://learn.microsoft.com/en-us/cpp/build/reference/ltcg-link-time-code-generation)):

- cross-module inlining
- interprocedural register allocation (64-bit only)
- **custom calling convention (x86 only)**
- small TLS displacement
- stack double alignment
- improved memory disambiguation

The same page says:

> "If the compiler can identify all of the call sites of a function, the
> compiler ignores explicit calling-convention modifiers, and tries to optimize
> the function's calling convention: pass parameters in registers; reorder
> parameters for alignment; remove unused parameters."

It does not do this for functions called through pointers or from outside the
`/GL` set.

**Looks like.**

```c
static int Clamp(int lo, int value, int hi, int unused) { ... }   /* only called directly */
```

```asm
; Without LTCG: cdecl, four stack pushes, caller cleans up with add esp, 10h
; With LTCG (x86), illustrative:
mov  eax, esi            ; value passed in EAX
mov  edx, 64h            ; hi in EDX; 'lo' constant-propagated; 'unused' removed
call FUN_0041c880        ; no add esp afterwards
```

**Ghidra misrenders.**

- Parameters show as `in_EAX`, `unaff_ESI` and `in_EDX`, and the prototype is
  "unknown calling convention".
- Callers appear to pass fewer arguments than the declared type.
- A function called with ECX from unrelated classes looks like `__thiscall`
  when it is not.
- Ghidra only models a fixed set of named conventions. Custom per-function
  register storage has to be set by hand (see the discussion in
  [Ghidra #4537](https://github.com/NationalSecurityAgency/ghidra/issues/4537)
  and [#4575](https://github.com/NationalSecurityAgency/ghidra/issues/4575)).

**Matching practice.**

- Per-TU object comparison cannot match LTCG output. The `.obj` holds
  intermediate code, not machine code, and the final bytes depend on every
  other `/GL` module in the link.
- STRATEGY.md already requires comparing "the final emitted region" for "LTCG
  groups" (§0).
- For source, keep the **original** prototype, including the dead argument.
  The linker removes it. Removing it by hand yields different inlining
  decisions **(inference)**.

**Evidence.**

- Rich header entries whose tool type is `LTC`/`LT+` (LTCG C/C++ objects)
  rather than plain `C`/`C++`, per the richprint
  [comp_id.txt](https://github.com/dishather/richprint/blob/master/comp_id.txt)
  legend.
- Many non-exported functions take register arguments outside ECX/EDX.
- Stack-cleanup behaviour is inconsistent between conventions.
- Inlining across what PDB module boundaries say are different TUs.

---

## 3. Transformations: linker folding, pooling, layout

### T6. `/Gy` + `/OPT:REF` and `/OPT:ICF`: one address, many symbols

**Cause.**

- `/Gy` makes each function a COMDAT. Inline functions and in-class members
  always are.
- `/OPT:REF` removes unreferenced COMDATs.
- `/OPT:ICF[=n]` folds identical COMDATs. Both are default at the command line
  unless `/DEBUG` is given, where the default is `NOREF,NOICF`.
- ICF "can cause the same address to be assigned to different functions or
  read-only data members"
  ([/OPT](https://learn.microsoft.com/en-us/cpp/build/reference/opt-optimizations)).
- Raymond Chen explains the naming and the debugger symptoms
  ([why "ICF"](https://devblogs.microsoft.com/oldnewthing/20161024-00/?p=94575),
  [debugging folded functions](https://devblogs.microsoft.com/oldnewthing/20160815-00/?p=94085)).

**Looks like.**

```cpp
int Circle::GetRadius() const { return m_radius; }   // m_radius at +8
int Channel::GetId() const    { return m_id; }       // m_id at +8
```

```asm
; one body at 0x0041c880 serves both (and any other "return field +8")
mov eax, [ecx+8]
ret
; vftable of Circle, slot 3   -> 0x0041c880
; vftable of Channel, slot 5  -> 0x0041c880
```

**Ghidra misrenders.**

- The function gets one name (the first symbol or the RTTI-derived guess).
- Cross-references come from unrelated classes, and the `this` type is
  whichever class was applied first.
- Automated class recovery can wrongly merge the classes or assign the method
  to a parent.

**Matching practice.**

- The reccmp toolchain uses a `FOLDED` annotation so that several source
  functions can claim one original address:
  `// FUNCTION: <MODULE> 0x4513d0 FOLDED`
  ([reccmp annotations](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md)).
- Each folded source function must compile on its own to the same bytes.
- The **absence** of unreferenced functions (dead code) is evidence of
  `/OPT:REF`.
- Without `/Gy`, the whole `.text` contribution of an object is kept together
  in source order. That makes TU boundaries and link order recoverable from
  function adjacency **(inference)**.

**Evidence.**

- Several vftable slots, in classes with no inheritance relation, point to one
  address.
- Very short bodies (`xor eax,eax; ret`, `mov eax,[ecx+N]; ret`, `ret 4`) are
  reached from dozens of unrelated places.
- A PDB lists several public symbols at the same RVA.

### T7. `/GF` string pooling

**Cause.**

- `/GF` places one copy of each identical literal in read-only memory.
- It is included in `/O1` and `/O2` but not in `/Ox`
  ([/GF](https://learn.microsoft.com/en-us/cpp/build/reference/gf-eliminate-duplicate-strings)).
- Pooled literals are COMDATs named `??_C@_0…` **(inference from the MSVC
  decorated-name scheme)**.

**Looks like.**

```c
Log("missing resource");          /* TU 1 */
Log("missing resource");          /* TU 2 */
```

```asm
push offset ??_C@_0BB@KHLMDPCN@missing?5resource?$AA@   ; the same VA from both TUs
call _Log
```

**Ghidra misrenders.** The data view itself is fine. Cross-references merge
across TUs, so a "strings used by this module" view over-attributes. Without
`/GF`, duplicate writable copies land in `.data` and look like separate
globals **(inference)**.

**Matching practice.** This is a global flag. It matters for **data** layout
and whole-image identity more than for function bytes. Relocations make the
function bytes compare equal either way under relocation-aware objdiff.

**Evidence.**

- Every literal text appears exactly once.
- Literals live in `.rdata`.
- In debug data, `??_C@` symbols.

### T8. `/GS` security cookies

**Cause.**

- `/GS` is on by default in current toolsets
  ([/GS](https://learn.microsoft.com/en-us/cpp/build/reference/gs-buffer-security-check)).
  It was introduced in the 7.0 toolset **(inference)**.
- A function gets a cookie only if it has a "GS buffer": an array larger than
  4 bytes with more than two non-pointer elements, a pointer-free struct
  larger than 8 bytes, or an `_alloca` buffer.
- With optimization on, *vulnerable parameters* (pointers and references) are
  copied below the buffers in the prologue.
- The CRT entry point initialises the cookie through `__security_init_cookie`.

**Looks like.**

```c
void FormatName(const char *src) { char buf[64]; strcpy(buf, src); Emit(buf); }
```

```asm
push ebp
mov  ebp, esp
sub  esp, 44h
mov  eax, ___security_cookie
xor  eax, ebp                   ; frame-XORed cookie (2005-era and later x86)
mov  [ebp-4], eax
...
mov  ecx, [ebp-4]
xor  ecx, ebp
call @__security_check_cookie@4 ; __fastcall, cookie in ECX
mov  esp, ebp
pop  ebp
ret
```

**Ghidra misrenders.**

- The prologue shows as `local_8 = DAT_0045a010 ^ (uint)&stack0xfffffffc;`.
- The epilogue shows as `FUN_00412345(local_8 ^ (uint)&stack0xfffffffc);`.
- Until the helper is identified, this reads as meaningful logic.
- Buffers are laid out above other locals, so Ghidra's `local_NN` order does
  not follow declaration order.

**Matching practice.**

- The `/GS` versus `/GS-` flag is global (decomp.me offers `/GS-` as a
  checkbox, §1).
- Buffer placement is the compiler's choice. Source declaration order still
  affects the non-buffer locals.
- `__declspec(safebuffers)` removes the cookie from one function.

**Evidence.**

- A global cookie initialised to the well-known default constant before CRT
  randomisation. For x86 that is `0xBB40E64E` **(inference; widely documented
  constant, not re-sourced here)**.
- `__security_check_cookie` called just before `ret`.
- `__report_gsfailure` present.
- Load-config `SecurityCookie` field set.

### T9. C++ exceptions: `/EH`, FH3 versus FH4, state writes, unwind funclets

**Cause.**

- `/EHsc` (current) or `/GX` (legacy) turns on C++ EH
  ([/EH](https://learn.microsoft.com/en-us/cpp/build/reference/eh-exception-handling-model)).
- Any function with a local object that has a destructor, or with a
  `try`/`catch`, gets an EH frame.
- On x86 this is a `fs:[0]` registration record plus a *state* variable.
- On x64 the metadata is table-driven, with no runtime registration
  ([x64 exception handling](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64)).
- FH4 (`__CxxFrameHandler4`) arrived in VS2019 and is the x64 default from
  16.3.
  - It uses variable-length encoding that shrinks most metadata fields from
    4 bytes to 1.
  - It needs `vcruntime140_1.dll`.
  - `/d2FH4-` reverts to FH3.
  - Source: the MSVC team's
    [FH4 post](https://devblogs.microsoft.com/cppblog/making-cpp-exception-handling-smaller-x64/).

**Looks like (x86).**

```cpp
void Loader::Load() { Buffer tmp; Parse(tmp); }   // Buffer has a destructor
```

```asm
push ebp
mov  ebp, esp
push 0FFFFFFFFh                                   ; initial state -1
push offset __ehhandler$?Load@Loader@@QAEXXZ
mov  eax, large fs:0
push eax
mov  large fs:0, esp                              ; register EH record
...
lea  ecx, [ebp-14h]
call ??0Buffer@@QAE@XZ
mov  dword ptr [ebp-4], 0                         ; state 0: tmp is live
...
mov  dword ptr [ebp-4], 0FFFFFFFFh                ; state -1 before the destructor
lea  ecx, [ebp-14h]
call ??1Buffer@@QAE@XZ
mov  ecx, [ebp-0Ch]
mov  large fs:0, ecx                              ; unregister

__unwindfunclet$?Load@Loader@@QAEXXZ$0:           ; placed after the function body
lea  ecx, [ebp-14h]
jmp  ??1Buffer@@QAE@XZ
__ehhandler$?Load@Loader@@QAEXXZ:
mov  eax, offset __ehfuncinfo$?Load@Loader@@QAEXXZ
jmp  ___CxxFrameHandler3                          ; ___CxxFrameHandler in older CRTs
```

The FuncInfo magic word distinguishes the metadata revision: `0x19930520`,
`0x19930521` or `0x19930522`. Structures and layout are covered in
[OpenRCE Part I](https://www.openrce.org/articles/full_view/21). The mapping of
revisions to toolset versions is **(inference)**. Newer x86 toolsets also put a
cookie check into the `__ehhandler` stub **(inference)**.

**Ghidra misrenders.**

- State writes appear as bare `local_8 = 0; … local_8 = 0xffffffff;`.
- Registration appears as `*in_FS_OFFSET = &local_10;`.
- Catch-block bodies can be missing from the output entirely
  ([Ghidra #5845](https://github.com/NationalSecurityAgency/ghidra/issues/5845)).
- Unwind funclets and catch funclets become orphan `FUN_…` functions that jump
  into destructors.

**Matching practice.**

- The state numbering is a direct trace of **object lifetimes in source
  order**.
- Every constructed object with a destructor, including temporaries and
  partially constructed members in constructors, bumps the state.
- To match, declare the same objects in the same scopes and order, and use the
  same temporaries (for example, whether a value is bound to a named local or
  passed as a temporary).
- The EH model flag (`/GX` versus `/EHsc` versus none) is global.
- reccmp calls out "exception-sensitive" candidates as a class; see this repo's
  recovery-contracts plan (§0).

**Evidence.**

- `__ehhandler$`/`__ehfuncinfo$` pairs.
- FuncInfo records with the magic word above, plus unwind-map and try-map
  counts that give the number of states and try blocks.
- The imported handler name: `__CxxFrameHandler`, `__CxxFrameHandler3` or
  `__CxxFrameHandler4`.
- On x64: `UNW_FLAG_EHANDLER` unwind info pointing at the handler.

### T10. SEH: `__try`/`__except`, `_except_handler3`/`_except_handler4`, scope tables

**Cause.** The `__try`/`__except`/`__finally` extensions
([try-except](https://learn.microsoft.com/en-us/cpp/cpp/try-except-statement)).

On x86 the frame is a registration record with a **scope table** and a
try-level variable:

| Handler | Era | Scope table | Try level at rest |
|---|---|---|---|
| `_except_handler3` | legacy CRTs | entries `{previousTryLevel, filter, handler}` | `-1` |
| `_except_handler4` | 2005-era and later, set up through `__SEH_prolog4` | pointer XORed with the security cookie; four-dword header `GSCookieOffset, GSCookieXOROffset, EHCookieOffset, EHCookieXOROffset` (`-2` meaning "no GS cookie") | `-2` |

Sources:

- The EH3 layout is from [OpenRCE Part I](https://www.openrce.org/articles/full_view/21).
- The EH4 header is from the LLVM review that implemented it
  ([D21231](https://reviews.llvm.org/D21231)).
- The mapping of the EH3→EH4 switch to a toolset version is **(inference)**.

**Looks like.**

```c
int SafeRead(int *p) { int v = 0; __try { v = *p; } __except (EXCEPTION_EXECUTE_HANDLER) { v = -1; } return v; }
```

```asm
push 10h
push offset stru_4521A0          ; scope table (encoded at run time)
call __SEH_prolog4
and  dword ptr [ebp-4], 0        ; try level 0: enter __try
mov  eax, [ebp+8]
mov  eax, [eax]
mov  [ebp-1Ch], eax
mov  dword ptr [ebp-4], 0FFFFFFFEh   ; leave __try (-2)
...
; filter: mov eax, 1 / ret
; handler: mov esp, [ebp-18h]   ; restore ESP, then v = -1
```

**Ghidra misrenders.**

- There is no `__try` structure in the output.
- The filter and handler blocks are either unreachable (and dropped) or
  separate functions.
- The try level shows as `local_8 = 0; local_8 = 0xfffffffe;`.
- Tracked as [Ghidra #2477](https://github.com/NationalSecurityAgency/ghidra/issues/2477).

**Matching practice.**

- Filter and handler expressions compile into small separate code blocks.
  Their order and the nesting of `__try` blocks decide scope-table indices.
- `__finally` blocks are emitted as local unwind functions.

**Evidence.**

- A `_except_handler3` or `_except_handler4` reference.
- `__SEH_prolog4`/`__SEH_epilog4` calls.
- Scope tables in `.rdata`.
- The try-level idle value: `-1` for EH3, `-2` for EH4.

### T11. `/RTC` run-time checks (debug builds)

**Cause.**

- `/RTC1` (`= /RTCsu`) and `/RTCc`, used only with `/Od`
  ([/RTC](https://learn.microsoft.com/en-us/cpp/build/reference/rtc-run-time-error-checks)).
- Legacy toolsets use `/GZ`.

**Looks like.**

```asm
push ebp
mov  ebp, esp
sub  esp, 0CCh
push ebx
push esi
push edi
lea  edi, [ebp-0CCh]
mov  ecx, 33h
mov  eax, 0CCCCCCCCh
rep stosd                        ; fill the frame with 0xCC
...
mov  esi, esp
call dword ptr [__imp__GetTickCount@0]
cmp  esi, esp
call __RTC_CheckEsp              ; after every indirect or stdcall call
...
push edx                         ; frame descriptor
lea  ecx, [ebp-..]
call @_RTC_CheckStackVars@8      ; checks guard bytes around arrays
```

**Ghidra misrenders.**

- The `0xCCCCCCCC` fill becomes a loop at the top of every function.
- `__RTC_CheckEsp` calls clutter every call site.
- `_RTC_CheckStackVars` shows up with a pointer to a descriptor table.

**Matching practice.** The target is a debug build. Pin `/Od /RTC1` (and
usually `/ZI`, which brings T12). Source idioms matter less and **flags and
declaration order** matter more, because every local has a fixed slot.

**Evidence.**

- The `rep stosd` 0xCC fill.
- The `__RTC_*`/`_RTC_*` imports or static CRT pieces.
- `RTC_framedesc` data.
- ILT thunks (T12).

### T12. Incremental-link thunks (ILT `jmp` stubs)

**Cause.**

- `/INCREMENTAL`, which `/DEBUG` implies.
- It is disabled by `/OPT:REF`, `/OPT:ICF`, `/OPT:LBR` or `/ORDER`.
- It adds code and data padding and "jump thunks to handle relocation of
  functions to new addresses"
  ([/INCREMENTAL](https://learn.microsoft.com/en-us/cpp/build/reference/incremental-link-incrementally)).

**Looks like.**

```asm
; the start of .text: a dense table of 5-byte jmps
@ILT+0(_main):             jmp _main
@ILT+5(?Resolve@ResourceRef@@QAEPAXXZ): jmp ?Resolve@ResourceRef@@QAEPAXXZ
...
call @ILT+5(...)           ; every direct call goes through the table
```

**Ghidra misrenders.** Every stub becomes a `thunk_FUN_…`. Call graphs show
thunks rather than callees until thunk resolution runs. Function counts double.

**Matching practice.** Reproducing the ILT order needs the same object and
edit history, which is effectively not reproducible **(inference)**. Match
functions through the thunks, and treat whole-image identity for such builds
as a special case.

**Evidence.**

- A run of `E9 xx xx xx xx` at the start of `.text`.
- `0xCC` padding between functions.
- A debug directory pointing at a PDB built with `/ZI` **(inference)**.

### T13. `/hotpatch` (`mov edi, edi`) and function padding (`int3`/`0xCC`)

**Cause.**

- `/hotpatch` (x86 only) guarantees the first instruction is at least 2 bytes
  and that nothing jumps to it.
- `/FUNCTIONPADMIN` inserts padding before each function.
- x64 and ARM64 are "always treated as hotpatchable"
  ([/hotpatch](https://learn.microsoft.com/en-us/cpp/build/reference/hotpatch-create-hotpatchable-image)).
- `mov edi, edi` is the 2-byte NOP chosen so it can be replaced with
  `jmp $-5` into the 5-byte pad
  ([Old New Thing](https://devblogs.microsoft.com/oldnewthing/20110921-00/?p=9583)).

**Looks like.**

```asm
CC CC CC CC CC           ; padding (hot-patch space)
8B FF                    ; mov edi, edi
55                       ; push ebp
8B EC                    ; mov ebp, esp
```

Separately, MSVC aligns function starts, usually to 16 bytes, with `int3`
(`0xCC`) fill between functions. Older toolsets sometimes used `0x90` fill
**(inference)**.

**Ghidra misrenders.** Rarely a problem. Padding can occasionally be taken as
part of the previous function when that function ends in a non-returning call.

**Matching practice.** Padding bytes belong to **placement**. This is exactly
the exact-placement gap STRATEGY.md tracks (§0). The alignment value and fill
byte are part of the whole-image recipe.

**Evidence.**

- `8B FF 55 8B EC` prologues.
- Five `CC` or `90` bytes before each function.
- `CC` runs between functions.

---

## 4. Calling conventions and ABI

| Convention | Arguments | Cleanup | Return | C decoration | Source |
|---|---|---|---|---|---|
| `__cdecl` | stack, right-to-left | caller (`add esp, n`) | EAX (EDX:EAX 64-bit) | `_Func` | [conventions](https://learn.microsoft.com/en-us/cpp/cpp/argument-passing-and-naming-conventions) |
| `__stdcall` | stack, right-to-left | callee (`ret n`) | EAX | `_Func@8` | same |
| `__fastcall` | ECX, EDX, then stack | callee | EAX | `@Func@8` | same |
| `__thiscall` | `this` in ECX, rest on stack | callee (vararg members use cdecl with `this` on the stack) | EAX | C++ only | [thiscall](https://learn.microsoft.com/en-us/cpp/cpp/thiscall) |
| `__vectorcall` | fastcall GPRs plus XMM0–5 (x86); x64 as below plus HVA | callee (x86) | EAX/XMM0 | `Func@@8` | [vectorcall](https://learn.microsoft.com/en-us/cpp/cpp/vectorcall) |
| x64 | RCX, RDX, R8, R9 / XMM0–3 by position; 32-byte caller-reserved home (shadow) space; RSP 16-aligned at call | caller | RAX/XMM0 | undecorated | [x64 convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention), [stack usage](https://learn.microsoft.com/en-us/cpp/build/stack-usage) |

Agner Fog's [calling conventions manual](https://www.agner.org/optimize/calling_conventions.pdf)
compares these across compilers, including struct returns and register
preservation.

**Looks like: call sites.**

```asm
; cdecl
push 2
push 1
call _Add
add  esp, 8

; stdcall
push 2
push 1
call _AddStd@8          ; callee does ret 8

; fastcall
mov  edx, 2
mov  ecx, 1
call @AddFast@8

; thiscall
mov  ecx, esi
call ?Resolve@ResourceRef@@QAEPAXXZ

; x64
sub  rsp, 28h           ; 32-byte home area + 8 alignment
mov  edx, 2
mov  ecx, 1
call Add

; x64 /Od callee: spills its register args into the caller's home space
mov  [rsp+10h], edx
mov  [rsp+8], ecx
```

**Ghidra misrenders.**

- A missed `__thiscall` gives `in_ECX` and a lost `this`. A missed stdcall
  purge corrupts caller stack depth (T2).
- Unused `EDX` in fastcall is dropped from the prototype.
- Hidden struct-return pointers show as an extra first parameter, or as
  `__return_storage_ptr__`.
- x64 home-space spills at `/Od` appear as `param_1` writes to the caller
  frame.

**Matching practice.**

- The default convention is a global flag (`/Gd`, `/Gr`, `/Gz`).
- Explicit keywords on prototypes must match. Mangled names encode them
  (`QAE` = public `__thiscall` member, `YA` = `__cdecl` free function, `YG` =
  `__stdcall`, `YI` = `__fastcall`), so they are recoverable from
  symbol-bearing builds
  ([decorated names](https://learn.microsoft.com/en-us/cpp/build/reference/decorated-names)).

**How LTCG changes this.** See T5. For x86 functions whose call sites are all
visible, declared conventions are ignored:

- arguments move into registers;
- arguments are reordered;
- dead arguments are removed.

So a function can be declared `__stdcall` in source and show a custom register
convention in the binary.

**Evidence.**

- `ret n` versus `ret` per function.
- ECX read before being written.
- `add esp, n` after calls.
- Stable x64 frame shapes via `.pdata`.

---

## 5. Codegen idioms

### I1. Switch lowering: jump tables, byte index tables, binary search

**Cause.** Dense case ranges become an indirect jump through a table. Very
sparse cases become compare trees (binary search) or compare chains. Mixed
cases become a **byte index table** that maps values to a small set of targets.
Thresholds are compiler-internal **(inference)**.

**Looks like.**

```c
switch (kind) { case 0: ...; case 1: ...; case 2: ...; case 5: ...; default: ...; }
```

```asm
mov  eax, [esp+4]
cmp  eax, 5
ja   short def                       ; unsigned range check
movzx eax, byte ptr [eax+idx_tbl]    ; byte index table (case 3,4 -> default slot)
jmp  dword ptr [eax*4+jmp_tbl]
; on x86, MSVC emits jmp_tbl and idx_tbl in .text right after the function
; x64: lea rdx,[__ImageBase]; mov ecx,[rdx+rax*4+RVA_tbl]; add rcx,rdx; jmp rcx
```

**Ghidra misrenders.**

- Tables in `.text` can be disassembled as bogus instructions.
- If the byte index table is not followed, Ghidra reports that it "could not
  recover jumptable" and shows `(*(code *)…)()`.
- Compare trees come out as nested `if`/`else` that hides the `switch`.

**Matching practice.**

- The *set* of case values and the `default` decide the lowering. Reproduce
  the exact cases, including empty ones that fall into shared bodies.
- Case **order in source** affects block layout.
- The project's toolchain note already points to m2c as preferred for
  switches (§0).

**Evidence.**

- `cmp/ja` then `jmp [reg*4+table]`.
- Tables adjacent to the function.
- `movzx … byte ptr [reg+tbl]` before the jump.

### I2. Division by constants via magic multiply

**Cause.** Any optimized build. The method is Granlund and Montgomery,
[Division by Invariant Integers using Multiplication](https://gmplib.org/~tege/divcnst-pldi94.pdf).

**Looks like.**

```c
int   SDiv10(int x)          { return x / 10; }
unsigned UDiv10(unsigned x)  { return x / 10; }
int   SDiv4(int x)           { return x / 4; }
```

```asm
; signed /10
mov  eax, 66666667h
imul dword ptr [esp+4]
sar  edx, 2
mov  eax, edx
shr  eax, 1Fh           ; +1 when negative (round toward zero)
add  eax, edx

; unsigned /10
mov  eax, 0CCCCCCCDh
mul  dword ptr [esp+4]
shr  edx, 3
mov  eax, edx

; signed /4
mov  eax, [esp+4]
cdq
and  edx, 3
add  eax, edx
sar  eax, 2
```

`x % 10` becomes `x - q*10`, computed with `lea` or `imul`.

**Ghidra misrenders.** Ghidra folds many forms back to `/`. Some variants
stay as `(int)((ulonglong)x * 0x66666667 >> 0x20) >> 2` or similar:
[Ghidra #668](https://github.com/NationalSecurityAgency/ghidra/issues/668),
[#1718](https://github.com/NationalSecurityAgency/ghidra/issues/1718).

**Matching practice.** Signedness decides the sequence. A `cdq`/`shr 1Fh`
correction means the operand was **signed**. The reccmp recommendations note
that changing `undefined4` to `int` fixing a match "is a strong indicator that
the original variable was signed"
([reccmp recommendations](https://github.com/isledecomp/reccmp/blob/master/docs/recommendations.md)).

**Evidence.**

- Magic constants such as `0x66666667`, `0xCCCCCCCD`, `0x55555556` and
  `0x92492493`, followed by `sar`/`shr edx`.
- A sign-fix tail.

### I3. Booleans, `setcc`, `sbb` masks, `cmov`

**Looks like.**

```c
int IsSet(int x)                 { return x != 0; }
int Pick(int c)                  { return c ? 7 : 3; }
```

```asm
; legacy branchless != 0
mov  eax, [esp+4]
neg  eax
sbb  eax, eax
neg  eax

; later toolsets
xor  eax, eax
cmp  [esp+4], eax
setne al

; branchless select via a mask
cmp  dword ptr [esp+4], 0
sbb  eax, eax           ; 0 or -1 (sense depends on cmp)
and  eax, -4
add  eax, 7             ; 7 or 3
```

`cmov` appears on x64. On x86 it appears only when the target CPU level
permits, which in practice means newer toolsets **(inference)**.

**Ghidra misrenders.** `-(uint)(x != 0)`-style expressions, and
`(-(uint)(c == 0) & 0xfffffffc) + 7` for the select.

**Matching practice.** Try `?:` versus `if/else` versus `!!x`. The source form
and the value range (bool versus int) switch between these sequences. This is
a classic permuter-style search axis.

**Evidence.** `neg/sbb/neg` and `sbb/and/add` sequences; `setcc` followed by
`movzx`.

### I4. Tail calls (`jmp` to callee)

**Looks like.**

```c
void Release(Obj *o) { Cleanup(o); free(o); }
```

```asm
push esi
mov  esi, [esp+8]
push esi
call _Cleanup
add  esp, 4
mov  [esp+8], esi       ; reuse the incoming argument slot
pop  esi
jmp  _free              ; tail call
```

**Ghidra misrenders.**

- When the callee is not yet a known function, the `jmp` can merge the callee
  body into the caller.
- Otherwise Ghidra shows `free(o); return;`, which is correct but hides the
  reuse of the caller's argument slot.
- Very short functions that only `jmp` are classed as thunks.

**Matching practice.** Tail calls happen when the call is the last action and
the argument layout is compatible. Adding a return value, or changing the
argument count, suppresses them **(inference)**.

**Evidence.** A function ending in `jmp` to another function's entry after the
epilogue.

### I5. Loop rotation, unrolling, strength reduction

**Looks like.** See T1: the `for` loop is rotated to a bottom test, and the
counter is turned into a pointer and a count-down. Multiplications by small
constants become `lea eax,[eax+eax*4]` (×5) or `shl`. Newer toolsets unroll
and auto-vectorize at `/O2` (the VS2012 auto-vectorizer) **(inference about
the exact version)**.

**Ghidra misrenders.** `do/while` with a guard `if`, where source had `for`.
Pointer arithmetic replaces indices.

**Matching practice.** Write the natural loop first. If the loop is a
count-down in the binary, try `while (n--)` versus `for (i=0;i<n;i++)`. Each
form produces a different prologue.

**Evidence.** A pre-loop guard `test/jle` followed by a bottom-tested body;
`lea` multiply idioms.

### I6. Register allocation order, stack slot reuse, local ordering

**Observed behaviour.**

- MSVC x86 saves callee-saved registers in a fixed push order and prefers
  ESI/EDI (then EBX) for long-lived values.
- The **choice of which variable gets ESI versus EDI** depends on the order
  variables are introduced and used.
- Locals whose lifetimes do not overlap share stack slots.
- Frame order is not declaration order.
- All of the above is **(inference from general matching experience)**.

**Ghidra misrenders.** Merged slots appear as one `local_14` used for two
unrelated values, often with a union-like type conflict. Split live ranges of
one variable appear as two variables.

**Matching practice.**

- Near-miss diffs that are "the same code but ESI and EDI swapped" are the
  most common MSVC residue.
- reccmp explicitly tolerates some of these as an **effective match**: it
  detects register swaps, swapped `cmp` operands with compatible jumps, and
  commutative `fld`/`fmul` reorderings (`reccmp/compare/asm/fixes.py`).
  It ranks "100% match … over effective match"
  ([reccmp](https://github.com/isledecomp/reccmp)).
- reccmp's `stackcmp` compares the stack layout of an almost-matching function.
- Levers: declaration order, introducing or removing a temporary, splitting an
  expression, and reusing a variable.

**Evidence.** The push order in the prologue; the frame size; the offsets of
arrays relative to scalars.

### I7. Struct copy idioms

**Looks like.**

```c
struct Pose { float m[12]; };
void Set(struct Pose *d, const struct Pose *s) { *d = *s; }
```

```asm
mov  ecx, 0Ch
mov  esi, [esp+8+8]
mov  edi, [esp+4+8]
rep movsd              ; larger structs
; small structs (<= ~16 bytes) become paired mov eax,[src]/mov [dst],eax sequences
```

Returned structs of 8 bytes or less come back in EDX:EAX on x86. Larger ones
use a hidden pointer. Details are in
[Agner Fog](https://www.agner.org/optimize/calling_conventions.pdf).

**Ghidra misrenders.** Field-by-field copies or a `rep movs` loop instead of
`*d = *s`.

**Matching practice.** Assign the whole struct. Copying member by member
produces a different sequence.

**Evidence.** `rep movsd` with a constant count; runs of paired
`mov eax,[esi+N] / mov [edi+N],eax`.

### I8. `alloca` and `_chkstk` probes

**Cause.**

- Frames larger than one page, or larger than the `/Gs` threshold, call the
  stack probe
  ([/Gs](https://learn.microsoft.com/en-us/cpp/build/reference/gs-control-stack-checking-calls)).
- `_alloca` uses the same probe (`_alloca_probe`).
- On x64 the probe returns and the caller does `sub rsp, rax`.

**Looks like.**

```asm
push ebp
mov  ebp, esp
mov  eax, 2010h
call __chkstk           ; instead of sub esp, 2010h
```

**Ghidra misrenders.** The function's frame size is hidden inside the probe
call. Locals may be shown relative to a wrong stack depth until `__chkstk` is
known to adjust ESP by EAX.

**Matching practice.** A large local buffer, or a `/Gs` setting. Frame size
must match exactly.

**Evidence.** `mov eax, N; call __chkstk` in prologues.

---

## 6. C++ object model (MSVC ABI)

The primary reverse-engineering references are
[OpenRCE Part II: classes, methods and RTTI](https://www.openrce.org/articles/full_view/23)
and [OpenRCE Part I: exception handling](https://www.openrce.org/articles/full_view/21).

| Artifact | Mangled prefix | Shape |
|---|---|---|
| vftable | `??_7Class@@6B@` | array of function pointers; entry `[-1]` points to the RTTI Complete Object Locator |
| vbtable | `??_8Class@@7B@` | offsets from the vbptr to virtual bases |
| Complete Object Locator | `??_R4Class@@6B@` | `{signature, offset, cdOffset, pTypeDescriptor, pClassHierarchyDescriptor}` (x64 adds image-relative `pSelf`, signature 1) |
| TypeDescriptor | `??_R0?AVClass@@@8` | `{pVFTable(type_info), spare, name ".?AVClass@@"}` |
| Class Hierarchy / Base Class Descriptors | `??_R3`, `??_R2`, `??_R1` | base list with `mdisp`/`pdisp`/`vdisp` offsets |
| scalar deleting destructor | `??_G` | `~Class(); if (flags & 1) operator delete(this);` |
| vector deleting destructor | `??_E` | the above, plus an array path when `flags & 2`, using a count stored before the array |
| constructor / destructor | `??0` / `??1` | |
| this-adjustor thunk | `[thunk]:…`adjustor{N}'` | `sub ecx, N; jmp Target` |

The x64 `pSelf`/signature detail comes from general ABI knowledge
**(inference)**.

**Looks like.**

```cpp
struct ResourceRef : Base, IObserver { virtual ~ResourceRef(); virtual void *Resolve(); int m_id; };
ResourceRef::ResourceRef() : Base() { m_id = 0; }
```

```asm
; constructor
push esi
mov  esi, ecx
call ??0Base@@QAE@XZ                   ; base constructors first
mov  dword ptr [esi], offset ??_7ResourceRef@@6BBase@@@    ; then install own vftables
mov  dword ptr [esi+4], offset ??_7ResourceRef@@6BIObserver@@@
mov  dword ptr [esi+8], 0              ; m_id
mov  eax, esi
pop  esi
ret

; virtual call: vftable slot 1 at +4
mov  eax, [ecx]
call dword ptr [eax+4]

; scalar deleting destructor ??_G
push esi
mov  esi, ecx
call ??1ResourceRef@@UAE@XZ
test byte ptr [esp+8], 1
jz   short skip
push esi
call ??3@YAXPAX@Z                      ; operator delete
add  esp, 4
skip: mov eax, esi
pop  esi
ret  4

; this-adjustor thunk for the IObserver sub-object
sub  ecx, 4
jmp  ?Notify@ResourceRef@@UAEXXZ
```

**Name mangling.** For example `?Resolve@ResourceRef@@QAEPAXXZ` is
`public: void * __thiscall ResourceRef::Resolve(void)`: `Q` public, `A` no cv,
`E` `__thiscall`, `PAX` `void*`, `XZ` no arguments
([decorated names](https://learn.microsoft.com/en-us/cpp/build/reference/decorated-names)).
Templates encode their arguments (`?$vector@H…`) and are COMDATs, so every TU
that instantiates them emits a copy. The linker keeps one (and ICF may fold
unrelated instantiations with equal bodies, as in T6).

**Ghidra misrenders.**

- Virtual calls show as `(**(code **)(*param_1 + 4))(param_1)` until a class
  structure with a vftable type is applied.
- `??_G` shows as `FUN_x(void *this, byte flags)`, with `flags & 1` logic that
  looks like user code.
- Adjustor thunks show as tiny `FUN_` functions.
- Ghidra's RTTI analyzer labels vftables and COLs. Its
  `RecoverClassesFromRTTIScript` builds class structures (script name from
  Ghidra's bundled scripts; **path not re-verified**).
- Class recovery can still mis-assign ICF-folded methods (T6).

**Matching practice.**

- **vftable slot order equals declaration order** of virtual functions in the
  class. reccmp has a `VTABLE` annotation and a `vtable` tool that compares
  recompiled vtables with the original.
- Synthetic functions (`??_G`, default destructors, assignment operators) are
  annotated `SYNTHETIC`, and templates `TEMPLATE`.
- Projects add `// SIZE 0x1c` plus a `DECOMP_SIZE_ASSERT(Class, 0x1c)`
  compile-time check and per-member offset comments.
- Sources:
  [reccmp annotations](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md),
  [reccmp recommendations](https://github.com/isledecomp/reccmp/blob/master/docs/recommendations.md).
- Destructor presence and ordering drive both `??_G` generation and EH states
  (T9).

**Evidence.**

- The `.?AV`/`.?AU` strings: RTTI is present, so `/GR` was used.
- COL signature 0 (x86) versus 1 (x64).
- Vftables in `.rdata` preceded by a COL pointer.
- `test byte ptr [esp+8],1` deleting-destructor shapes.
- `sub ecx,N; jmp` thunks.

---

## 7. Compiler and version identification

### 7.1 Rich header

**What it is.**

- An undocumented, XOR-masked block between the DOS stub and `PE\0\0`.
- It starts `DanS` (masked) and ends with `Rich` plus the 32-bit key.
- Each entry is `(compId, count)`, where `compId = (productId << 16) | buildNumber`.
- There is one entry per tool, object kind and build that contributed objects:
  C, C++, ASM, LNK, IMP, EXP, RES, and the LTCG kinds LTC/LT+.
- References: [bytepointer write-up](https://bytepointer.com/articles/the_microsoft_rich_header.htm),
  [richprint](https://github.com/dishather/richprint).

The known compIds below come from richprint's
[comp_id.txt](https://github.com/dishather/richprint/blob/master/comp_id.txt):

| Toolset | C compId | C++ compId | Linker compId | Build |
|---|---|---|---|---|
| VS98 (6.0) RTM | `000a1fe8` | `000b1fe8` | (`00041fe8` imp/exp) | 8168 |
| VS6 SP3 | `000a20ff` | `000b20ff` | — | 8447 |
| VS98 (6.0) SP5/SP6 | `000a2636` / `00152306` | `000b2636` / `00162306` | — | 8804 |
| VS2002 (7.0) | `001c24fa` | `001d24fa` | `003d24fa` | 9466 |
| VS2003 (7.1) | `005f0c05` | `00600c05` | `005a0c05` | 3077 |
| VS2005 (8.0) | `006dc627` | `006ec627` | `0078c627` | 50727 |
| VS2008 (9.0) RTM / SP1 | `0083521e` / `00837809` | `0084521e` / `00847809` | `0091521e` / `00917809` | 21022 / 30729 |
| VS2010 (10.0) RTM / SP1 | `00aa766f` / `00aa9d1b` | `00ab766f` / `00ab9d1b` | `009d766f` / `009d9d1b` | 30319 / 40219 |
| VS2012 (11.0) | `00cec627` | `00cfc627` | `00ccc627` | 50727 |

For VS2015 and later (14.x), product ids start at `0x0100` and up. Example:
VS2022 17.8 build 33128 has C `01048168`, C++ `01058168`, LNK `01028168` and
LTC `01088168`.

**Using it.**

- The **counts** show how many objects came from each compiler. That separates
  your code from statically linked CRT objects and from assembler objects.
- Several compiler builds in one image mean mixed toolchains, for example a
  static library built with an older compiler.
- LTC/LT+ entries prove `/GL`.
- The header is absent from images built by non-Microsoft linkers.
- Build tools that zero the header exist, so its absence is not proof
  **(inference)**.

### 7.2 Other identifying evidence

- **PE optional header `MajorLinkerVersion.MinorLinkerVersion`.** Values such
  as 6.0, 7.10, 8.0, 9.0, 10.0 and 14.xx line up with the toolsets above.
  `_MSC_VER` values for each version are listed at
  [compiler versions](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions).
- **Debug directory CodeView record.**
  - `NB10` means PDB 2.0 (the VC6 era).
  - `RSDS` (GUID, age, path) means PDB 7.0 (VS2002 and later).
  - The path often reveals the project layout.
  - Source: [debuginfo.com: matching debug information](https://www.debuginfo.com/articles/debuginfomatch.html).
- **PDB contents, when available.** These are the best flag evidence:
  - Module list: one module per object, which is the TU list in link order.
  - Section contributions: which bytes came from which object.
  - `S_COMPILE2`/`S_COMPILE3`: compiler version, language, some flags.
  - `S_ENVBLOCK`: the compiler command line (`cmd`). The LLVM patch
    [D137723](https://reviews.llvm.org/D137723) aligned LLVM's output to what
    MSVC emits.
- **CRT startup shape and imports.**
  - The CRT DLL name identifies the version: `MSVCRT.dll` (VC6-era system CRT),
    `MSVCR71.dll`, `MSVCR80.dll` (with SxS manifest), `MSVCR90.dll`,
    `MSVCR100.dll`, or `VCRUNTIME140.dll` plus `api-ms-win-crt-*` (2015+).
    `VCRUNTIME140_1.dll` means FH4 on x64 (T9).
  - Entry stubs differ: legacy `WinMainCRTStartup` sets up an SEH frame inline
    and calls `GetVersion`. 2005-era entries do `call __security_init_cookie;
    jmp __tmainCRTStartup`. 2015+ entries go to `__scrt_common_main_seh`.
    **(inference: recalled shapes, not re-sourced)**.
  - Static CRT functions can be identified by signature. Ghidra ships Function
    ID databases for several Visual Studio versions **(inference about exact
    coverage)**.
- **Codegen tells** (each **(inference)** unless tied to a section above):

  | Toolset | Tells |
  |---|---|
  | VC6 (12.00) | `_except_handler3`; FuncInfo `0x19930520`; x87-only FP; `/Ob1` defaults under `/O2`; no `/GS`; `NB10` PDB; `__chkesp` under `/GZ` |
  | 7.0 / 7.1 (13.00 / 13.10) | `/GS` available (cookie without EBP XOR); `RSDS` PDB; `__SEH_prolog` helper with handler3; SSE options arrive |
  | 8.0 (14.00, 2005) | `/GS` on by default with EBP-XORed cookie; `_except_handler4` with `__SEH_prolog4`; `__CxxFrameHandler3`; secure CRT; `/fp:` model; first-class x64 |
  | 9.0 / 10.0 | Like 8.0; SP-level build numbers distinguish them (7.1) |
  | 11.0 (2012) | x86 default `/arch:SSE2`, so scalar SSE float code replaces x87; auto-vectorizer |
  | 14.x (2015+) | UCRT/vcruntime split; `/guard:cf` checks ([/guard](https://learn.microsoft.com/en-us/cpp/build/reference/guard-enable-control-flow-guard)); `/Gw`; thread-safe statics (`_Init_thread_header`); FH4 on x64 (2019); `/Ob3` (2019) |

### 7.3 How matching projects pin the toolchain

- **decomp.me** pins compiler binaries by id. For the `win32` platform it
  hosts `msvc4.0`, `4.1`, `4.2`, `6.0`, `6.3`, `6.4`, `6.5`, `6.5pp`, `6.6`,
  `7.0`, `7.1`, `8.0` and `8.0p`.
  - Each is run through the `wibo` Win32 loader as
    `CL.EXE /c /nologo /I… ${COMPILER_FLAGS} /Fd… /Bk… /Fo…`.
  - Output is compared with `i686-w64-mingw32-objdump`.
  - Source: [decomp.me compilers.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/compilers.py)
    and `platforms.py`.
  - Named presets pair a compiler id with a flag string. The live preset list
    was **not** enumerated for this note.
- **reccmp-style projects** pin one compiler version, build the whole program,
  and compare the recompiled image against the original using the rebuilt PDB
  ([reccmp README](https://github.com/isledecomp/reccmp)). This moves
  per-function matching to **link-output** comparison, which also covers ICF,
  COMDAT selection and LTCG.
- **This repo's position** (§0): a modern 19.51 compiler is fine for
  compile-checking but cannot establish byte parity against an older target.
  Record the exact compiler and linker hashes, headers and libraries, and probe
  legacy toolchain support rather than copying modern switches.

---

## 8. Matching-decomp practice for MSVC

### 8.1 Tools

- **objdiff**
  ([repo](https://github.com/encounter/objdiff)).
  - Diffs object files, functions and data.
  - Supports x86 and x86_64 and demangles MSVC names.
  - Highlights registers and values, and produces progress reports.
  - Needs a *target object* per unit. For a PE image that means first
    splitting the original into per-TU objects, which is easy for
    `/Gy`-less adjacency but hard after ICF and LTCG **(inference)**.
- **decomp-permuter**
  ([repo](https://github.com/simonlindholm/decomp-permuter)).
  - Its README says it supports MIPS, PowerPC and ARM32 assembly. It does not
    list x86.
  - For MSVC x86, "permuting" is done by project-specific scripts or by hand
    **(inference)**.
  - This repo already routes near misses to a permuter lane (§0). For x86
    targets that lane needs an MSVC-aware scorer.
- **reccmp.**
  - Source annotations: `FUNCTION`, `STUB`, `TEMPLATE`, `SYNTHETIC`,
    `LIBRARY`, `VTABLE`, `FOLDED`.
  - Whole-image comparison with PDB, a `stackcmp` tool, a `vtable` tool and a
    Ghidra import.
  - Its "effective match" category covers register swaps, `cmp`/jump operand
    swaps and commutative x87 reorderings
    ([reccmp](https://github.com/isledecomp/reccmp),
    [annotations](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md)).
- **decomp.me.** A scratch-based online editor with the MSVC compilers in §7.3
  and the flag groups in §1.

### 8.2 Known tricks: source levers that change MSVC output

1. **Declaration order and scope** of locals. This changes register choice
   (I6), stack slots, EH state numbering (T9) and GS layout (T8).
2. **Temporaries.** Introducing or removing a named temporary, splitting or
   joining an expression, or `a = b = c` chains. Each changes register
   pressure and ordering.
3. **Signedness and width.** For example `int` versus `unsigned` versus
   `undefined4`, and `char` versus `unsigned char` loads (`movsx` versus
   `movzx`). This changes I2 sequences and comparisons (`jl` versus `jb`).
4. **`volatile`.** Forces memory round trips. Used sparingly to reproduce `/Od`
   islands or odd reloads **(inference)**.
5. **Inline placement.** In-class definition, `inline`, `__forceinline` or
   `__declspec(noinline)` (T3). Under `/Ob1` this is decisive.
6. **`#pragma optimize("", off/on)`, `#pragma function`/`intrinsic`,
   `#pragma auto_inline`.** Reproduce per-function flag islands
   ([optimize](https://learn.microsoft.com/en-us/cpp/preprocessor/optimize),
   [intrinsic](https://learn.microsoft.com/en-us/cpp/preprocessor/intrinsic)).
7. **Splitting translation units.**
   - Static functions and file-scope data are ordered by definition within a
     TU.
   - Without `/Gy`, a TU's functions are contiguous in the image.
   - Wrong TU boundaries change both placement and what can be inlined.
8. **Link order.** Object order on the linker command line (or `/ORDER`)
   determines `.text` and `.data` placement. This is required for whole-image
   identity.
9. **Packing.** `/Zp`, `#pragma pack` and explicit padding members. Layout
   errors poison every function that touches the struct
   ([/Zp](https://learn.microsoft.com/en-us/cpp/build/reference/zp-struct-member-alignment)).
   reccmp projects assert sizes (§6).
10. **Case order and case sets** in `switch` (I1). **Loop form** (`for`,
    `while`, `do`) (I5). **Ternary versus `if`** (I3).
11. **Virtual declaration order** decides vftable slots. **Destructor
    virtuality** decides `??_G`/`??_E` and the vftable shape (§6).

### 8.3 Why "matching" is not the same as "functionally equivalent"

A functionally equivalent rewrite can differ in:

- register choice;
- block order;
- instruction selection (`neg/sbb` versus `setne`);
- stack layout;
- EH state numbering;
- whether a helper is inlined or folded;
- data placement.

None of these change behaviour, and every one breaks byte identity. Matching
therefore constrains *source shape*, *toolchain* and *link recipe*. Semantics
alone is not enough.

In the other direction, a byte match proves only that this source and this
recipe produce these bytes. It does not prove the source is the original: ICF
can make two different sources equal, and several source forms can compile
identically.

reccmp distinguishes "100%" from "effective match". This repo already keeps
per-function objdiff-0, whole-image identity, and C+assembly-floor versus max-C
as separately reported claims (STRATEGY.md, §0). The UI should keep those
distinctions visible.

---

## 9. UI implications

Each view below names the transformation(s) it shows and the data needed. "PDB"
means optional. Every view must degrade to heuristics labelled **inferred**
when authoritative data is missing.

1. **Pointer and field-access walk (base + offset chains).**
   - *Shows:* `this` (ECX, or RCX on x64) → `[ecx+N]` fields; vftable slot
     dereference `[[ecx]+4*k]` resolved to a slot index and target; this-adjust
     `sub ecx,N` thunks; vbtable indirections; ICF targets shared between
     classes (T6, §6, I7).
   - *Data:* per-instruction operand decomposition (base register, index,
     scale, displacement); register-origin dataflow back to the parameter or
     `this`; class layouts and vftables from RTTI (COL→TypeDescriptor→CHD);
     struct size and offset table with provenance; folded-target set.
2. **"Compiler did this" annotation layer over the listing.** Ranges and badges
   drawn on disassembly and decompiler output:
   - inlined-callee ranges (T3), with the out-of-line twin linked;
   - folded COMDAT markers, listing all symbols and vftable slots at the
     address (T6);
   - GS cookie prologue and epilogue (T8);
   - EH registration and each **state write**, labelled with the object whose
     lifetime it tracks (T9);
   - SEH try-level writes and filter/handler blocks (T10);
   - `/RTC` fills and checks (T11);
   - ILT thunks (T12);
   - hotpatch prologue and padding (T13);
   - magic-divide sequences rewritten as `x / 10` (I2);
   - `rep movs`/`repne scasb` intrinsic expansions labelled
     `memcpy`/`strlen` (T4);
   - `neg/sbb` bool idioms (I3);
   - tail-call `jmp` (I4);
   - `__chkstk` frames (I8);
   - jump and index tables (I1).

   *Data:* pattern detector output per address range, with detector id and
   confidence; FuncInfo, UnwindMap, TryMap and scope-table parses; the
   ICF alias map; inline-site records (PDB) or clone-similarity hits; switch
   table extents.
3. **Flags and toolchain evidence panel (per image and per build a–d).**
   - Rich header entries decoded to tool, build and count (LTC/LT+ flagged).
   - Linker version, CodeView `NB10`/`RSDS` plus the PDB path.
   - CRT DLL imports and entry-stub shape.
   - Handler flavours: `_except_handler3`/`4`, `__CxxFrameHandler`/`3`/`4`.
   - GS cookie default constant, `/guard:cf` load-config.
   - Inferred flags, each with its evidence: `/Oy` share of functions without
     an EBP frame, `/Oi` idioms, `/GF` single-copy literals, `/Gy` and
     `/OPT:REF` (no dead code), ICF alias count, `/RTC`, `/INCREMENTAL`,
     `/hotpatch`.
   - The pinned compiler and linker (hash, version banner) actually used for
     candidates, with a mismatch warning when the pinned toolset differs from
     the Rich-header-implied one.

   *Data:* PE parser output (headers, Rich, debug directory, imports,
   load-config); detector aggregates; toolchain registry records (STRATEGY's
   toolchain identity).
4. **Per-function matching-diff explanation.**
   - An objdiff-style instruction diff, with each residual difference
     classified: register swap (I6), stack-slot or frame-size difference (I6,
     I8), instruction-selection idiom (I3, I2), block order or loop form (I5),
     switch lowering (I1), EH state numbering (T9), GS presence (T8), inlining
     difference (T3), relocation-only difference, or placement-only difference
     (T13).
   - Each class links to the source levers in §8.2 and states whether it is a
     reccmp-style "effective match" or a true mismatch.
   - Both claims shown separately: per-function objdiff result and whole-image
     status.

   *Data:* original and candidate objects or regions; relocation-aware diff
   JSON (for example objdiff `diff_kind`); classifier output; candidate
   compile recipe (flags, TU, pragma overrides); stack-layout comparison
   (`stackcmp`-like).
5. **Frame and stack layout view.**
   - EBP or ESP frame, callee-saved push order, locals by offset.
   - GS buffer and cookie placement.
   - EH registration record, state slot and SEH scope-table offsets.
   - x64 home space and `.pdata` unwind codes.
   - Slot-reuse overlaps drawn as lifetime bars.

   *Data:* prologue parse, stack-reference analysis with live ranges, EH and
   SEH metadata, unwind info.
6. **Calling-convention and signature audit.**
   - Per function: declared or inferred convention, `ret n` purge, register
     parameters actually read before being written (flagging LTCG custom
     conventions, T5), hidden struct-return pointer, and caller-side argument
     count disagreements.

   *Data:* per-function register liveness at entry; call-site argument setup
   and stack cleanup; demangled prototypes when symbols exist.
7. **C++ class and vtable browser.**
   - RTTI hierarchy (COL, CHD, BCD), vftables with slot → target (showing folds
     and adjustor thunks), ctor/dtor, `??_G`/`??_E` pairs, and vbtables.
   - Class size assertions and member offsets with evidence source.

   *Data:* RTTI parse, vftable extents, ICF alias map, demangler, layout store.
8. **Translation-unit and placement map.**
   - `.text`/`.data` laid out by address, grouped into inferred TUs (from PDB
     section contributions, or from adjacency when `/Gy` is absent), with
     link order, alignment and padding bytes, ILT region, folded or removed
     COMDATs, and LTCG groups.
   - Supports STRATEGY's exact-placement track.

   *Data:* section contributions or map file, function extents, padding
   classification, Rich counts per tool, LTCG evidence.
9. **Cross-build (build-a … build-d) transformation comparison.**
   - For one logical function, which transformations differ across builds.
     Examples: inlined in build-b but not build-c; folded in build-d; GS
     present only after a toolchain change.
   - Explains why a verified source for one build does not transfer.

   *Data:* logical identity links, per-build detector annotations, per-build
   toolchain evidence (view 3).

---

## Sources

Microsoft Learn (MSVC reference):

- [/O1 /O2](https://learn.microsoft.com/en-us/cpp/build/reference/o1-o2-minimize-size-maximize-speed)
- [/Ox](https://learn.microsoft.com/en-us/cpp/build/reference/ox-full-optimization)
- [/Os /Ot](https://learn.microsoft.com/en-us/cpp/build/reference/os-ot-favor-small-code-favor-fast-code)
- [/Oy](https://learn.microsoft.com/en-us/cpp/build/reference/oy-frame-pointer-omission)
- [/Ob](https://learn.microsoft.com/en-us/cpp/build/reference/ob-inline-function-expansion)
- [/Oi](https://learn.microsoft.com/en-us/cpp/build/reference/oi-generate-intrinsic-functions)
- [/GL](https://learn.microsoft.com/en-us/cpp/build/reference/gl-whole-program-optimization)
- [/LTCG](https://learn.microsoft.com/en-us/cpp/build/reference/ltcg-link-time-code-generation)
- [/Gy](https://learn.microsoft.com/en-us/cpp/build/reference/gy-enable-function-level-linking)
- [/OPT](https://learn.microsoft.com/en-us/cpp/build/reference/opt-optimizations)
- [/GF](https://learn.microsoft.com/en-us/cpp/build/reference/gf-eliminate-duplicate-strings)
- [/GS](https://learn.microsoft.com/en-us/cpp/build/reference/gs-buffer-security-check)
- [/EH](https://learn.microsoft.com/en-us/cpp/build/reference/eh-exception-handling-model)
- [/RTC](https://learn.microsoft.com/en-us/cpp/build/reference/rtc-run-time-error-checks)
- [/INCREMENTAL](https://learn.microsoft.com/en-us/cpp/build/reference/incremental-link-incrementally)
- [/hotpatch](https://learn.microsoft.com/en-us/cpp/build/reference/hotpatch-create-hotpatchable-image)
- [/FUNCTIONPADMIN](https://learn.microsoft.com/en-us/cpp/build/reference/functionpadmin-create-hotpatchable-image)
- [/Gs](https://learn.microsoft.com/en-us/cpp/build/reference/gs-control-stack-checking-calls)
- [/Gw](https://learn.microsoft.com/en-us/cpp/build/reference/gw-optimize-global-data)
- [/GR](https://learn.microsoft.com/en-us/cpp/build/reference/gr-enable-run-time-type-information)
- [/Zp](https://learn.microsoft.com/en-us/cpp/build/reference/zp-struct-member-alignment)
- [/guard](https://learn.microsoft.com/en-us/cpp/build/reference/guard-enable-control-flow-guard)
- [#pragma optimize](https://learn.microsoft.com/en-us/cpp/preprocessor/optimize)
- [#pragma intrinsic](https://learn.microsoft.com/en-us/cpp/preprocessor/intrinsic)
- [inline functions](https://learn.microsoft.com/en-us/cpp/cpp/inline-functions-cpp)
- [argument passing and naming conventions](https://learn.microsoft.com/en-us/cpp/cpp/argument-passing-and-naming-conventions)
- [__thiscall](https://learn.microsoft.com/en-us/cpp/cpp/thiscall)
- [__vectorcall](https://learn.microsoft.com/en-us/cpp/cpp/vectorcall)
- [x64 calling convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention)
- [x64 stack usage](https://learn.microsoft.com/en-us/cpp/build/stack-usage)
- [x64 prolog and epilog](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog)
- [x64 exception handling](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64)
- [try-except](https://learn.microsoft.com/en-us/cpp/cpp/try-except-statement)
- [decorated names](https://learn.microsoft.com/en-us/cpp/build/reference/decorated-names)
- [compiler versions](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions)
- [FPO_DATA](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-fpo_data)

Microsoft blogs:

- [FH4: making C++ exception handling smaller on x64](https://devblogs.microsoft.com/cppblog/making-cpp-exception-handling-smaller-x64/)
- Raymond Chen:
  [MOV EDI, EDI](https://devblogs.microsoft.com/oldnewthing/20110921-00/?p=9583),
  [why "ICF"](https://devblogs.microsoft.com/oldnewthing/20161024-00/?p=94575),
  [debugging COMDAT-folded functions](https://devblogs.microsoft.com/oldnewthing/20160815-00/?p=94085)

Reverse-engineering references:

- OpenRCE:
  [Reversing MSVC Part I: exception handling](https://www.openrce.org/articles/full_view/21),
  [Part II: classes, methods and RTTI](https://www.openrce.org/articles/full_view/23)
- [Agner Fog, calling conventions](https://www.agner.org/optimize/calling_conventions.pdf)
- [Granlund & Montgomery, division by invariant integers](https://gmplib.org/~tege/divcnst-pldi94.pdf)
- Rich header:
  [bytepointer Rich header](https://bytepointer.com/articles/the_microsoft_rich_header.htm),
  [richprint and comp_id.txt](https://github.com/dishather/richprint)
- [debuginfo.com, matching debug information](https://www.debuginfo.com/articles/debuginfomatch.html)
- LLVM reviews:
  [D21231 (SEH4 cookie offsets)](https://reviews.llvm.org/D21231),
  [D137723 (S_ENVBLOCK cmd)](https://reviews.llvm.org/D137723)

Ghidra issues:

- [#5845 (catch blocks)](https://github.com/NationalSecurityAgency/ghidra/issues/5845)
- [#2477 (SEH)](https://github.com/NationalSecurityAgency/ghidra/issues/2477)
- [#668](https://github.com/NationalSecurityAgency/ghidra/issues/668) and
  [#1718 (magic division)](https://github.com/NationalSecurityAgency/ghidra/issues/1718)
- [#4537](https://github.com/NationalSecurityAgency/ghidra/issues/4537) and
  [#4575 (calling conventions)](https://github.com/NationalSecurityAgency/ghidra/issues/4575)

Decomp tooling:

- decomp.me:
  [compilers.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/compilers.py),
  [flags.py](https://github.com/decompme/decomp.me/blob/main/backend/coreapp/flags.py)
- [objdiff](https://github.com/encounter/objdiff)
- [decomp-permuter](https://github.com/simonlindholm/decomp-permuter)
- reccmp:
  [repo](https://github.com/isledecomp/reccmp),
  [annotations](https://github.com/isledecomp/reccmp/blob/master/docs/annotations.md),
  [recommendations](https://github.com/isledecomp/reccmp/blob/master/docs/recommendations.md)
