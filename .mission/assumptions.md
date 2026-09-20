## A1 Byte-window search is a last-resort identity signal
Source: inferred | Confidence: high | Impact if wrong: we under-document a method the user still uses by hand | Verification: matcher code + STRATEGY | Status: unverified

## A2 One signature family can cover most registered builds
Source: stated (prefer) | Confidence: med | Impact if wrong: we ship per-build families with a coverage report | Verification: C1/C4 | Status: unverified

## A3 Phasor can resolve hooks from portable signatures + logical_id
Source: inferred | Confidence: med | Impact if wrong: export is docs-only until resolver exists | Verification: C2 | Status: unverified

## A4 Do not commit
Source: default / standing user rule | Confidence: high | Impact if wrong: none | Verification: no git commit this mission | Status: confirmed
## V1 Applicable plans mean currently relevant Vite/workbench plans with
unimplemented requirements
Source: inferred from user directive | Confidence: high | Impact if wrong:
scope misses a current plan or implements a superseded one | Verification:
layered coordinator maps each plan requirement to source or a recorded
supersession | Status: unverified

## V2 Existing uncommitted frontend changes are in-flight mission evidence
Source: repository state | Confidence: high | Impact if wrong: overwriting
someone else's work | Verification: diff review and exclusive writer scopes |
Status: unverified

## V3 The supplied ecosystem survey is architectural evidence, not a license
to copy third-party source or add its engines
Source: user-supplied research and repo scope | Confidence: high | Impact if
wrong: a Vite change introduces unsupported dependencies, licensing risk, or
unbounded scope | Verification: integration reviews use only local plan
requirements and existing project contracts | Status: confirmed
