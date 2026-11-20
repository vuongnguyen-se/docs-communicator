import { useEffect, useRef, useState } from "react";
import { ApiError, type ApiClient, type ChatAnswer } from "../api";
import { MAX_QUESTION_CHARS } from "../api/types";
import { validateQuestion } from "../api/validation";
import { isVietnamese, stringsFor } from "../lang";
import { DocIcon } from "./icons";

interface Props {
  api: ApiClient;
  hasReadyDocuments: boolean;
  /** Names of the Ready documents, shown being "scanned" while a question is answered. */
  readyDocs: string[];
  /** The client's mark for the current theme (public/brand). */
  mark: string;
}

interface Turn {
  id: number;
  question: string;
  result: ChatAnswer;
}

/** Grounded Q&A: every source shown is one the backend verified as the user's own document. */
export function Chat({ api, hasReadyDocuments, readyDocs, mark }: Props) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const logEnd = useRef<HTMLLIElement>(null);

  useEffect(() => {
    logEnd.current?.scrollIntoView?.({ block: "end" });
  }, [turns, pending]);

  async function submit() {
    setError(null);
    const problem = validateQuestion(question);
    if (problem) return setError(problem);
    const asked = question.trim();
    setPending(asked);
    setQuestion("");
    try {
      const result = await api.ask(asked);
      setTurns((prev) => [...prev, { id: prev.length + 1, question: asked, result }]);
    } catch (err) {
      setQuestion(asked); // give the question back so it can be retried
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="main" aria-labelledby="chat-h">
      <div className="chat__head">
        <h1 id="chat-h" className="chat__title">
          Ask your documents
        </h1>
        <p className="chat__sub">
          {hasReadyDocuments
            ? "Answers come only from your Ready PDFs, in English or Vietnamese."
            : "Upload a PDF and wait until it is Ready to ask questions."}
        </p>
      </div>

      <ol className="chat__log" aria-label="Conversation" aria-live="polite">
        {turns.map((t) => (
          <TurnView key={t.id} turn={t} mark={mark} />
        ))}
        {pending && (
          <>
            <li className="turn-q">
              <p className="bubble" lang={isVietnamese(pending) ? "vi" : undefined}>
                {pending}
              </p>
            </li>
            <Searching mark={mark} docs={readyDocs} vi={isVietnamese(pending)} />
          </>
        )}
        <li ref={logEnd} aria-hidden="true" />
      </ol>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="composer__box">
          <label className="sr-only" htmlFor="question">
            Question
          </label>
          <textarea
            id="question"
            className="composer__input"
            rows={1}
            maxLength={MAX_QUESTION_CHARS}
            value={question}
            disabled={!hasReadyDocuments}
            placeholder="Ask about your documents"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (!pending && hasReadyDocuments) void submit();
              }
            }}
          />
          <button type="submit" className="btn" disabled={!!pending || !hasReadyDocuments || !question.trim()}>
            Ask
          </button>
        </div>
        <p className="composer__hint">
          Enter to send · Shift + Enter for a new line · {question.length} / {MAX_QUESTION_CHARS}
        </p>
        {error && (
          <p className="alert" role="alert" style={{ marginTop: 8 }}>
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

/**
 * The "searching" moment: the mark pulses, the user's Ready documents are swept by a scan
 * line and placeholder lines shimmer where the answer will appear. It only shows the documents
 * that can be searched; it never claims a step (reading, writing) the client cannot observe.
 * Under prefers-reduced-motion everything rests (styles.css) and the label stays.
 */
function Searching({ mark, docs, vi }: { mark: string; docs: string[]; vi: boolean }) {
  const shown = docs.slice(0, 3);
  return (
    <li className="turn-a searching">
      <img className="turn-a__avatar searching__mark" src={mark} alt="" />
      <div className="turn-a__body searching__body">
        <p className="searching__label" role="status">
          {vi ? "Đang tìm trong tài liệu của bạn…" : "Searching your documents…"}
        </p>
        {shown.length > 0 && (
          <div className="searching__docs" aria-hidden="true">
            {shown.map((name, i) => (
              <span key={name} className="searching__doc" style={{ ["--i" as string]: i }}>
                <DocIcon size={14} />
                <span className="searching__doc-name">{name}</span>
              </span>
            ))}
            {docs.length > shown.length && <span className="searching__more">+{docs.length - shown.length}</span>}
          </div>
        )}
        <div className="searching__lines" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>
    </li>
  );
}

function TurnView({ turn, mark }: { turn: Turn; mark: string }) {
  const [open, setOpen] = useState<number | null>(null);
  const { question, result } = turn;
  const vi = isVietnamese(question);
  const declined = result.citations.length === 0;
  const opened = open === null ? null : result.citations[open];

  return (
    <>
      <li className="turn-q">
        <p className="bubble" lang={vi ? "vi" : undefined}>
          {question}
        </p>
      </li>
      <li className="turn-a">
        <img className={`turn-a__avatar${declined ? " turn-a__avatar--muted" : ""}`} src={mark} alt="" />
        <div className="turn-a__body">
          <p lang={isVietnamese(result.answer) ? "vi" : undefined}>{result.answer}</p>
          {declined ? (
            <p className="turn-a__note">{stringsFor(question).noSourceNote}</p>
          ) : (
            <>
              <div className="chips" role="group" aria-label="Sources">
                {result.citations.map((c, i) => (
                  <button
                    key={`${c.documentId}-${i}`}
                    type="button"
                    className="chip"
                    aria-expanded={open === i}
                    onClick={() => setOpen(open === i ? null : i)}
                  >
                    <DocIcon size={14} />
                    {c.documentName}
                    {result.citations.length > 1 && <span className="sr-only">, passage {i + 1}</span>}
                  </button>
                ))}
              </div>
              {opened && (
                <blockquote className="excerpt" style={{ margin: 0 }}>
                  <p className="excerpt__doc">From {opened.documentName}</p>
                  <p>“{opened.excerpt}”</p>
                </blockquote>
              )}
            </>
          )}
        </div>
      </li>
    </>
  );
}
