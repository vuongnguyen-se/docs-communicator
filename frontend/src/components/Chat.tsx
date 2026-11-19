import { useState } from "react";
import { ApiError, type ApiClient, type ChatAnswer } from "../api";
import { validateQuestion } from "../api/validation";

interface Props {
  api: ApiClient;
  hasReadyDocuments: boolean;
}

interface Turn {
  id: number;
  question: string;
  result: ChatAnswer;
}

/** Grounded Q&A: each answer lists only sources the backend verified as the user's own documents. */
export function Chat({ api, hasReadyDocuments }: Props) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const problem = validateQuestion(question);
    if (problem) return setError(problem);
    const asked = question.trim();
    setLoading(true);
    try {
      const result = await api.ask(asked);
      setTurns((prev) => [...prev, { id: prev.length + 1, question: asked, result }]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="chat-h">
      <h2 id="chat-h">Ask your documents</h2>
      {!hasReadyDocuments && <p>Upload a PDF and wait until it is Ready to ask questions.</p>}

      {turns.length > 0 && (
        <ol aria-label="Conversation">
          {turns.map((t) => (
            <li key={t.id}>
              <p>
                <strong>You:</strong> {t.question}
              </p>
              <p>
                <strong>CloudDocs AI:</strong> {t.result.answer}
              </p>
              {t.result.citations.length > 0 ? (
                <details>
                  <summary>
                    {t.result.citations.length} source{t.result.citations.length > 1 ? "s" : ""}:{" "}
                    {[...new Set(t.result.citations.map((c) => c.documentName))].join(", ")}
                  </summary>
                  <ul>
                    {t.result.citations.map((c, i) => (
                      <li key={`${c.documentId}-${i}`}>
                        <strong>{c.documentName}</strong>
                        <blockquote>{c.excerpt}</blockquote>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : (
                <p>
                  <em>No source in your documents supports an answer to this question.</em>
                </p>
              )}
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={(e) => void submit(e)}>
        <textarea
          aria-label="Question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Ask a question about your documents (English or Vietnamese)"
        />
        <button type="submit" disabled={loading || !hasReadyDocuments}>
          {loading ? "Searching your documents…" : "Ask"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
