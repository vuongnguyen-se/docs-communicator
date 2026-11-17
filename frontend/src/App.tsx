import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, HttpApi, MockApi, type ApiClient, type DocumentInfo } from "./api";
import { getAccessToken } from "./auth";
import { Chat } from "./components/Chat";
import { DocumentList } from "./components/DocumentList";
import type { AppConfig } from "./config";

export function App({ config }: { config: AppConfig }) {
  return config.mode === "http" ? <CognitoShell config={config} /> : <MockShell />;
}

/** Deployed mode: Cognito login (no sign-up: accounts are created by the admin, D-004). */
function CognitoShell({ config }: { config: AppConfig }) {
  const api = useMemo(() => new HttpApi(config.apiUrl, getAccessToken), [config.apiUrl]);
  return (
    <Authenticator hideSignUp>
      {({ signOut, user }) => (
        <Workspace
          api={api}
          userLabel={user?.signInDetails?.loginId ?? "Signed in"}
          onSignOut={() => signOut?.()}
        />
      )}
    </Authenticator>
  );
}

/** Local mode: in-memory API, no AWS. */
function MockShell() {
  const api = useMemo(() => new MockApi(), []);
  const [signedIn, setSignedIn] = useState(false);
  if (!signedIn) {
    return (
      <main>
        <h1>CloudDocs AI</h1>
        <p>Sign in to upload PDFs and ask questions about them.</p>
        <p>
          <em>Local mock mode: no real authentication or AWS connection.</em>
        </p>
        <button onClick={() => setSignedIn(true)}>Sign in (mock)</button>
      </main>
    );
  }
  return <Workspace api={api} userLabel="mock user" onSignOut={() => setSignedIn(false)} />;
}

function Workspace({ api, userLabel, onSignOut }: { api: ApiClient; userLabel: string; onSignOut: () => void }) {
  const [ready, setReady] = useState(false);
  const onDocs = useCallback((docs: DocumentInfo[]) => setReady(docs.some((d) => d.status === "READY")), []);
  return (
    <main>
      <header>
        <h1>CloudDocs AI</h1>
        <span>{userLabel}</span> <button onClick={onSignOut}>Sign out</button>
        <ConnectionStatus api={api} />
      </header>
      <DocumentList api={api} onChange={onDocs} />
      <Chat api={api} hasReadyDocuments={ready} />
    </main>
  );
}

/** Calls GET /me: proves browser -> Cognito token -> API Gateway authorizer -> Lambda works. */
function ConnectionStatus({ api }: { api: ApiClient }) {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .whoAmI()
      .then((id) => !cancelled && setState({ ok: true, text: `API connected (user id ${id})` }))
      .catch(
        (e: unknown) =>
          !cancelled && setState({ ok: false, text: e instanceof ApiError ? e.message : "API not reachable" }),
      );
    return () => {
      cancelled = true;
    };
  }, [api]);
  if (!state) return <p role="status">Checking API connection…</p>;
  return <p role={state.ok ? "status" : "alert"}>{state.text}</p>;
}
