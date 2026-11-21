# Phase 3: Frontend, stop calling `/complete`

## Context

`frontend/src/api/http.ts` `uploadDocument` does three things in order: it requests the upload form, POSTs to S3, then calls `POST /documents/{id}/complete`. Polling (`components/status.ts` `isUnresolved`) already covers `PENDING_UPLOAD`, `UPLOADED` and `INDEXING`.

## Requirements

- `uploadDocument` returns after a successful S3 POST, with the document in `PENDING_UPLOAD`. The list's backoff polling then shows the progress from the worker.
- The `PENDING_UPLOAD` label changes from "Uploading…" to "Checking file…", because by then the upload has finished.
- `MockApi` mirrors this: it moves the document forward on later list calls.
- If the owner keeps `/complete` (see the plan's decisions), the endpoint stays in the API but the UI no longer calls it.

## Files

Edit:
- `frontend/src/api/http.ts`, `frontend/src/api/http.test.ts`,
- `frontend/src/api/mock.ts`, `frontend/src/api/mock.test.ts`,
- `frontend/src/components/status.ts`.

## Steps

1. Remove the `/complete` call. Update the test to expect exactly 2 calls (upload-url, then S3).
2. Update the mock and the label.
3. Run `npm test`, `npm run lint` and `npm run build`.

## Validation

Frontend checks pass locally and in CI. In mock mode, the document goes from "Checking file…" to "Ready".

## Risk / rollback

If the worker path fails in production, documents stay in `PENDING_UPLOAD` until it is fixed. That is visible, not silent: the DLQ alarm fires. Rollback: restore the `/complete` call, a 1-line revert.
