# Task9.1 interrupted review findings — preserved controller receipt

2026-10-03 resume. Previous reviewer sent these confirmed Important findings before interruption; its final review was not written. These are retained reviewer observations, not fresh execution proof or a final verdict. Current source owner must check which corrections survived; a fresh independent source review follows coherent handoff.

- DA-S1 (reported confidence100): command-lock acquisition contention becomes authority refusal then execute poison/per-entry suspension, permanently invalidating healthy witness. Separate retryable no-effect control prerequisite; no mutation/dispatch without freshcontrol, acquisition permission and postwrite uncertainty still fault.
- DA-S2 (100): _read accepts raw []/null; queue ranking TypeError/inventory AttributeError escape and stop sharedworker. Validate row shape/ranking and isolate perentry, continue healthy laterrow, never secondcatch-path write.
- DA-S3 (100): early _check lostlease refuses without poisoning; execute initialguard beforetry; rootfinished cleanretirement keepshealthywitness and subsequentresume heals observedloss. Exactcurrent authority invalidation beforeescape, successor-safe physicallease/token/witness handling.
- DA-S4 (100): advisory extractor unconditionalfinally mutation replaces original persistence503 with authoritylost409. Skipcanonicalcleanup after invalidation, preserve originalcause/phase/status; healthycleanup guarded.
- DA-S5 (75, concreteinterleaving): issuerB passes prelockfaultcheck; A appendsvalidrecord thenfsyncfails/latches; B takes releasedlock andissues because latchnotrechecked. Recheck irreversiblefault/limit underactualacquiredlock before scan/append; healthyexistingrow operations independent.

No tests/DB/crash/process/route/fixture behavior was executed for these findings. Reviewerjudgment was source reasoning. Neither U9 nor packet9.1 is accepted. Source5ceefab6 checkpoint plus preserveddirtyfivefiles/newtest remains protected; controller alone Git.
