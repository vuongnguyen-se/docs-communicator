import type { DocumentStatus } from "../api";

/** Status polling: start quick, then back off so a slow index doesn't hammer the API. */
export const POLL_START_MS = 2000;
export const POLL_MAX_MS = 10000;

export function nextPollDelay(currentMs: number): number {
  return Math.min(POLL_MAX_MS, Math.round(currentMs * 1.5));
}

/** Statuses that will still change on their own, so the list keeps polling. */
export function isUnresolved(status: DocumentStatus): boolean {
  return status === "PENDING_UPLOAD" || status === "UPLOADED" || status === "INDEXING" || status === "DELETING";
}

const LABELS: Record<DocumentStatus, string> = {
  PENDING_UPLOAD: "Uploading…",
  UPLOADED: "Uploaded",
  INDEXING: "Indexing…",
  READY: "Ready",
  FAILED: "Failed",
  DELETING: "Deleting…",
};

export function statusLabel(status: DocumentStatus): string {
  return LABELS[status];
}
