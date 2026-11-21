# Phase 4: Docs, live demo, teardown (💰🧹, ask first)

## Docs to update

- `ARCHITECTURE.md` §3 (upload flow) and §5 (future async architecture: now implemented).
- `API_SPECIFICATION.md`: `/complete` described as an optional "check now" call, or removed, per the owner's decision.
- `docs/HOW_IT_WORKS.md`: the upload sequence diagram and the state diagram (`PENDING_UPLOAD → UPLOADED` is triggered by the worker).
- `DECISIONS.md`: new D-019, event-driven ingestion (queue settings, error policy, `/complete` decision).
- `TASKS.md`: P6-01, and the session log.

## Live demo (after approval)

1. Deploy with `scripts\deploy.ps1 -AlarmEmail <owner email>` and confirm the subscription.
2. Upload a PDF in the UI. It reaches **Ready**. The Documents Lambda logs show no `/complete`, and the worker logs show the document processed.
3. Upload a text file renamed `.pdf`. It ends `FAILED` / `INVALID_FILE`, and the S3 object is gone.
4. Send one poison message to `IngestQueue` (valid JSON, but the worker raises on it). After 3 receives it is in `IngestDLQ`, `IngestDLQNotEmpty` fires, and the email arrives.
5. Run `eval/run_eval.py`. Expect 14/14 (isolation and grounding unchanged). The evaluation script itself must stop calling `/complete`, or keep calling it if the owner keeps the route.
6. Destroy, then the teardown check passes.

## Done when

All acceptance criteria in `plan.md` are verified, and the docs and `TASKS.md` are updated in one PR.
