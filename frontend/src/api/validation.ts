import { MAX_FILE_BYTES, MAX_QUESTION_CHARS } from "./types";

/** Client-side pre-checks for UX only; the backend remains the authority. */
export function validateFile(file: { name: string; size: number; type: string }): string | null {
  if (file.type !== "application/pdf" || !file.name.toLowerCase().endsWith(".pdf")) {
    return "Only PDF files are supported.";
  }
  if (file.size <= 0) return "The file is empty.";
  if (file.size > MAX_FILE_BYTES) return "The file is larger than 10 MB.";
  return null;
}

export function validateQuestion(q: string): string | null {
  const t = q.trim();
  if (!t) return "Please enter a question.";
  if (t.length > MAX_QUESTION_CHARS) return `Questions are limited to ${MAX_QUESTION_CHARS} characters.`;
  return null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
