import { useCallback, useMemo, useState } from "react";
import { createApi, type DocumentInfo } from "./api";
import { Chat } from "./components/Chat";
import { DocumentList } from "./components/DocumentList";

export function App() {
  const api = useMemo(() => createApi(), []);
  // Login stub: real Cognito sign-in is wired in Phase 2.
  const [signedIn, setSignedIn] = useState(false);
  const [ready, setReady] = useState(false);
  const onDocs = useCallback((docs: DocumentInfo[]) => setReady(docs.some((d) => d.status === "READY")), []);

  if (!signedIn) {
    return (
      <main>
        <h1>CloudDocs AI</h1>
        <p>Sign in to upload PDFs and ask questions about them.</p>
        <p>
          <em>Local mock mode: no real authentication or AWS connection yet.</em>
        </p>
        <button onClick={() => setSignedIn(true)}>Sign in (mock)</button>
      </main>
    );
  }

  return (
    <main>
      <header>
        <h1>CloudDocs AI</h1>
        <button onClick={() => setSignedIn(false)}>Sign out</button>
      </header>
      <DocumentList api={api} onChange={onDocs} />
      <Chat api={api} hasReadyDocuments={ready} />
    </main>
  );
}
