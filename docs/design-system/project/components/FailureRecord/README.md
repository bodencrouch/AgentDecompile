# FailureRecord

A failure drawn at its real unmet dependency: stable reason, scope, freshness, spend, recovery action, wake condition, and authority only when unavoidable.

**Consumer provides** those fields, the failure lifecycle position, the classification (mismatch, transient, resource, policy) and the independent work that continues.

- Header on `lane-fault-fill` names the reason in a stable phrase ("Provider paused for this input revision"). The lifecycle rail sits in the body: observed → classified → contained → recovery_pending → reconciling → eligible.
- Always show what continues. The affected branch stops visibly; every eligible sibling continues.
- An escalation adds the failed predicate, raw evidence references, attempted recoveries and the exact external change required. It is emitted on transitions, not polls. Dismissing is not resolution.
