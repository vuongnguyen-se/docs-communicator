import { ApiError, type ApiClient, type ChatAnswer, type DocumentInfo } from "./types";
import { stringsFor } from "../lang";
import { validateFile, validateQuestion } from "./validation";

const MAX_DOCS = 5;

/** In-memory API used for local development and tests. Simulates indexing delay. */
export class MockApi implements ApiClient {
  readonly canDelete = true;
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

  async whoAmI(): Promise<string> {
    await this.delay();
    return "mock-user";
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

  async uploadDocument(file: File, onProgress?: (fraction: number) => void): Promise<DocumentInfo> {
    // Simulated transfer so the per-file progress bar can be seen in mock mode.
    for (const f of [0.15, 0.4, 0.7, 1]) {
      await this.delay();
      onProgress?.(f);
    }
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
    // Mock rule: a document "answers" only if the question names a word from its file name
    // (e.g. "nimbus" for nimbus-handbook.pdf); anything else is declined, like an unrelated question.
    const words = question.toLowerCase();
    const match = ready.find((d) =>
      d.filename.toLowerCase().replace(/\.pdf$/, "").split(/[^a-z0-9à-ỹ]+/).some((w) => w.length >= 4 && words.includes(w)),
    );
    if (!match) {
      return { answer: stringsFor(question).noEvidenceAnswer, citations: [], requestId };
    }
    return {
      answer: `(mock answer) From "${match.filename}": a placeholder response to "${question.trim()}".`,
      citations: [
        { documentId: match.documentId, documentName: match.filename, excerpt: "Mock excerpt: the passage the answer came from appears here." },
      ],
      requestId,
    };
  }
}
