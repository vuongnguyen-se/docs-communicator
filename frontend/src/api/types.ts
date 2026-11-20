// Mirrors docs API contract (backend/src/clouddocs/models.py).

export type DocumentStatus =
  | "PENDING_UPLOAD"
  | "UPLOADED"
  | "INDEXING"
  | "READY"
  | "FAILED"
  | "DELETING";

export interface DocumentInfo {
  documentId: string;
  filename: string;
  fileSize: number;
  status: DocumentStatus;
  createdAt: string;
  updatedAt: string;
  errorCode: string | null;
}

export interface Citation {
  documentId: string;
  documentName: string;
  excerpt: string;
}

export interface ChatAnswer {
  answer: string;
  citations: Citation[];
  requestId: string;
}

export interface ApiClient {
  /** Caller's user id as seen by the backend (proves auth end to end). */
  whoAmI(): Promise<string>;
  listDocuments(): Promise<DocumentInfo[]>;
  getDocument(id: string): Promise<DocumentInfo>;
  /** Runs the full flow: presigned URL -> direct upload -> complete. `onProgress` gets 0..1 for the S3 upload. */
  uploadDocument(file: File, onProgress?: (fraction: number) => void): Promise<DocumentInfo>;
  /** False until the backend wires DELETE (P5-01): the UI hides the action instead of failing. */
  readonly canDelete: boolean;
  deleteDocument(id: string): Promise<void>;
  ask(question: string): Promise<ChatAnswer>;
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_QUESTION_CHARS = 2000;
