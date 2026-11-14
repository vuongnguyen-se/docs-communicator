import { useState } from "react";
import { ApiError, type ApiClient, type ChatAnswer } from "../api";
import { validateQuestion } from "../api/validation";

interface Props {
  api: ApiClient;
  hasReadyDocuments: boolean;
}

export function Chat({ api, hasReadyDocuments }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ChatAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const problem = validateQuestion(question);
    if (problem) return setError(problem);
    setLoading(true);
    try {
      setResult(await api.ask(question));
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="chat-h">
      <h2 id="chat-h">Ask your documents</h2>
      {!hasReadyDocuments && <p>Upload a PDF and wait until it is READY to ask questions.</p>}
      <form onSubmit={(e) => void submit(e)}>
        <textarea
          aria-label="Question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          maxLength={2000}
        />
        <button type="submit" disabled={loading || !hasReadyDocuments}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div>
          <h3>Answer</h3>
          <p>{result.answer}</p>
          {result.citations.length > 0 ? (
            <>
              <h3>Sources</h3>
              <ul>
                {result.citations.map((c, i) => (
                  <li key={`${c.documentId}-${i}`}>
                    <strong>{c.documentName}</strong>
                    <blockquote>{c.excerpt}</blockquote>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p>
              <em>No sources found for this answer.</em>
            </p>
          )}
          <small>Request ID: {result.requestId}</small>
        </div>
      )}
    </section>
  );
}
