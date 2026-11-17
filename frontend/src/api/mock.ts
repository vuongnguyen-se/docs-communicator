import { ApiError, type ApiClient, type ChatAnswer, type DocumentInfo } from "./types";
import { validateFile, validateQuestion } from "./validation";

const MAX_DOCS = 5;

/** In-memory API used for local development and tests. Simulates indexing delay. */
export class MockApi implements ApiClient {
  private docs = new Map<string, DocumentInfo & { readyAt: number }>();
  private seq = 0;

  constructor(
    private readonly indexingMs = 3000,
    private readonly latencyMs = 150,
  ) {}

  private async delay(): Promise<void> {
    await new Promise((r) => setTimeout(r, this.latencyMs));
  }

  private view(d: DocumentInfo & { readyAt: number }): DocumentInfo {
    const status = d.status === "INDEXING" && Date.now() >= d.readyAt ? "READY" : d.status;
    const { readyAt: _readyAt, ...rest } = { ...d, status };
    void _readyAt;
    return rest;
  }

  async listDocuments(): Promise<DocumentInfo[]> {
    await this.delay();
    return [...this.docs.values()].map((d) => this.view(d));
  }

  async getDocument(id: string): Promise<DocumentInfo> {
    await this.delay();
    const d = this.docs.get(id);
    if (!d) throw new ApiError("NOT_FOUND", "Document not found", 404);
    return this.view(d);
  }

  async uploadDocument(file: File): Promise<DocumentInfo> {
    await this.delay();
    const problem = validateFile(file);
    if (problem) throw new ApiError("VALIDATION_ERROR", problem, 400);
    if (this.docs.size >= MAX_DOCS) {
      throw new ApiError("LIMIT_EXCEEDED", `Document limit reached (${MAX_DOCS})`, 409);
    }
    const now = new Date().toISOString();
    const id = `doc_${(++this.seq).toString(16).padStart(32, "0")}`;
    const doc = {
      documentId: id,
      filename: file.name,
      fileSize: file.size,
      status: "INDEXING" as const,
      createdAt: now,
      updatedAt: now,
      errorCode: null,
      readyAt: Date.now() + this.indexingMs,
    };
    this.docs.set(id, doc);
    return this.view(doc);
  }

  async deleteDocument(id: string): Promise<void> {
    await this.delay();
    if (!this.docs.delete(id)) throw new ApiError("NOT_FOUND", "Document not found", 404);
  }

  async ask(question: string): Promise<ChatAnswer> {
    await this.delay();
    const problem = validateQuestion(question);
    if (problem) throw new ApiError("VALIDATION_ERROR", problem, 400);
    const ready = [...this.docs.values()].map((d) => this.view(d)).filter((d) => d.status === "READY");
    const requestId = `mock-${Date.now()}`;
    if (ready.length === 0) {
      return {
        answer: "I could not find relevant information in your documents to answer this question.",
        citations: [],
        requestId,
      };
    }
    const first = ready[0]!;
    return {
      answer: `(mock answer) Based on "${first.filename}": this is a placeholder response to "${question.trim()}".`,
      citations: [
        { documentId: first.documentId, documentName: first.filename, excerpt: "Mock excerpt from the document." },
      ],
      requestId,
    };
  }
}
