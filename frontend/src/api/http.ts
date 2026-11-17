import {
  ApiError,
  type ApiClient,
  type ChatAnswer,
  type DocumentInfo,
} from "./types";
import { validateFile, validateQuestion } from "./validation";

export type TokenProvider = () => Promise<string>;
type FetchFn = typeof fetch;

interface UploadUrlResponse {
  document: DocumentInfo;
  upload: { url: string; fields: Record<string, string> };
  expiresInSeconds: number;
}

/** Real API client: API Gateway HTTP API with a Cognito JWT on every call. */
export class HttpApi implements ApiClient {
  private readonly baseUrl: string;

  constructor(
    baseUrl: string,
    private readonly getToken: TokenProvider,
    private readonly fetchFn: FetchFn = (...args) => fetch(...args),
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async whoAmI(): Promise<string> {
    return (await this.request<{ userId: string }>("GET", "/me")).userId;
  }

  async listDocuments(): Promise<DocumentInfo[]> {
    return (await this.request<{ documents: DocumentInfo[] }>("GET", "/documents")).documents;
  }

  async getDocument(id: string): Promise<DocumentInfo> {
    return (await this.request<{ document: DocumentInfo }>("GET", `/documents/${encodeURIComponent(id)}`))
      .document;
  }

  /** Presigned POST flow: ask for an upload form, send the file straight to S3, then confirm. */
  async uploadDocument(file: File): Promise<DocumentInfo> {
    const problem = validateFile(file);
    if (problem) throw new ApiError("VALIDATION_ERROR", problem, 400);

    const { document, upload } = await this.request<UploadUrlResponse>("POST", "/documents/upload-url", {
      filename: file.name,
      contentType: file.type,
      size: file.size,
    });

    const form = new FormData();
    for (const [k, v] of Object.entries(upload.fields)) form.append(k, v);
    form.append("file", file); // must be the last field for S3
    // No Authorization header: the signed form fields are the credential, and S3 is a different origin.
    const s3 = await this.fetchFn(upload.url, { method: "POST", body: form });
    if (!s3.ok) {
      throw new ApiError("UPLOAD_FAILED", "The file upload was rejected. Please try again.", s3.status);
    }

    return (
      await this.request<{ document: DocumentInfo }>(
        "POST",
        `/documents/${encodeURIComponent(document.documentId)}/complete`,
      )
    ).document;
  }

  async deleteDocument(id: string): Promise<void> {
    await this.request<unknown>("DELETE", `/documents/${encodeURIComponent(id)}`);
  }

  async ask(question: string): Promise<ChatAnswer> {
    const problem = validateQuestion(question);
    if (problem) throw new ApiError("VALIDATION_ERROR", problem, 400);
    return this.request<ChatAnswer>("POST", "/chat/query", { question: question.trim() });
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = await this.getToken();
    const headers: Record<string, string> = { authorization: `Bearer ${token}` };
    if (body !== undefined) headers["content-type"] = "application/json";

    let res: Response;
    try {
      res = await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("NETWORK_ERROR", "Cannot reach the server. Check your connection.", 0);
    }

    const text = await res.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!res.ok) throw toApiError(res.status, data);
    return data as T;
  }
}

export function toApiError(status: number, data: unknown): ApiError {
  const err = (data as { error?: { code?: unknown; message?: unknown } } | null)?.error;
  if (err && typeof err.code === "string" && typeof err.message === "string") {
    return new ApiError(err.code, err.message, status);
  }
  if (status === 401) return new ApiError("UNAUTHORIZED", "Your session has expired. Please sign in again.", status);
  if (status === 403) return new ApiError("FORBIDDEN", "You are not allowed to do that.", status);
  if (status === 404) return new ApiError("NOT_FOUND", "This feature is not available yet.", status);
  if (status === 429) return new ApiError("THROTTLED", "Too many requests. Please wait a moment.", status);
  return new ApiError("HTTP_ERROR", "Something went wrong. Please try again.", status);
}
