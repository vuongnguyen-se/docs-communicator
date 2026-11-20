/** Pure upload-queue rules (UI-03), kept out of the component so they are unit-tested. */

export const MAX_DOCUMENTS = 5;
export const MAX_PARALLEL = 2;

export interface QueueItem {
  id: number;
  name: string;
  progress: number; // 0..1
  state: "waiting" | "uploading" | "done" | "error";
  error?: string;
}

export interface Plan {
  accepted: File[];
  rejected: { file: File; reason: string }[];
}

/** Splits a dropped batch into files to upload and files to refuse, each with its own reason. */
export function planUploads(
  files: File[],
  existingCount: number,
  validate: (f: { name: string; size: number; type: string }) => string | null,
): Plan {
  const plan: Plan = { accepted: [], rejected: [] };
  let room = Math.max(0, MAX_DOCUMENTS - existingCount);
  for (const file of files) {
    const problem = validate(file);
    if (problem) plan.rejected.push({ file, reason: problem });
    else if (room === 0) plan.rejected.push({ file, reason: `The limit is ${MAX_DOCUMENTS} documents. Delete one to add another.` });
    else {
      plan.accepted.push(file);
      room--;
    }
  }
  return plan;
}

/** Plain-language reason for a FAILED document, from the backend's error code. */
export function failureReason(code: string | null): string {
  switch (code) {
    case "INVALID_FILE":
      return "Not a valid PDF, or larger than 10 MB";
    case "INDEXING_FAILED":
      return "No readable text found (a scanned PDF?)";
    case "INGEST_REQUEST_FAILED":
      return "Indexing couldn’t start. Upload it again";
    default:
      return "Something went wrong. Upload it again";
  }
}
