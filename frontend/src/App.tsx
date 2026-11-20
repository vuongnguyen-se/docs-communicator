import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, HttpApi, MockApi, type ApiClient, type DocumentInfo } from "./api";
import { getAccessToken } from "./auth";
import { Chat } from "./components/Chat";
import { DocumentList } from "./components/DocumentList";
import { DocIcon, MoonIcon, SignOutIcon, SunIcon } from "./components/icons";
import type { AppConfig } from "./config";
import { brandAssets, useTheme, type Theme } from "./theme";

export function App({ config }: { config: AppConfig }) {
  const [theme, toggleTheme] = useTheme();
  return config.mode === "http" ? (
    <CognitoShell config={config} theme={theme} toggleTheme={toggleTheme} />
  ) : (
    <MockShell theme={theme} toggleTheme={toggleTheme} />
  );
}

interface ThemeProps {
  theme: Theme;
  toggleTheme: () => void;
}

/** Deployed mode: Cognito login, no sign-up (accounts are created by the admin, D-004). */
function CognitoShell({ config, theme, toggleTheme }: ThemeProps & { config: AppConfig }) {
  const api = useMemo(() => new HttpApi(config.apiUrl, getAccessToken), [config.apiUrl]);
  const { logo } = brandAssets(theme);
  return (
    <Authenticator
      hideSignUp
      components={{
        Header: () => <SignInIntro logo={logo} />,
        Footer: () => <p className="signin__note" style={{ textAlign: "center", padding: "16px 0" }}>Accounts are created by your administrator. There is no public sign-up.</p>,
      }}
    >
      {({ signOut, user }) => (
        <Workspace
          api={api}
          userLabel={user?.signInDetails?.loginId ?? "Signed in"}
          onSignOut={() => signOut?.()}
          theme={theme}
          toggleTheme={toggleTheme}
        />
      )}
    </Authenticator>
  );
}

function SignInIntro({ logo }: { logo: string }) {
  return (
    <div className="signin__panel" style={{ margin: "48px auto 24px", padding: "0 24px" }}>
      <img className="signin__logo" src={logo} alt="Clouddocs" />
      <div>
        <h1 className="signin__title">Sign in to your documents</h1>
        <p className="signin__lede">Ask questions about your PDFs and get answers with their sources.</p>
      </div>
    </div>
  );
}

/** Local mode: in-memory API, no AWS. */
function MockShell({ theme, toggleTheme }: ThemeProps) {
  const api = useMemo(() => new MockApi(), []);
  const [signedIn, setSignedIn] = useState(false);
  const { logo } = brandAssets(theme);
  if (!signedIn) {
    return (
      <main className="signin">
        <div className="signin__panel">
          <img className="signin__logo" src={logo} alt="Clouddocs" />
          <div>
            <h1 className="signin__title">Sign in to your documents</h1>
            <p className="signin__lede">Local mock mode: no real account or AWS connection.</p>
          </div>
          <button type="button" className="btn" onClick={() => setSignedIn(true)}>
            Continue in mock mode
          </button>
          <p className="signin__note">Deployed sites use Cognito. Accounts are created by your administrator.</p>
        </div>
      </main>
    );
  }
  return <Workspace api={api} userLabel="mock user" onSignOut={() => setSignedIn(false)} theme={theme} toggleTheme={toggleTheme} />;
}

interface WorkspaceProps extends ThemeProps {
  api: ApiClient;
  userLabel: string;
  onSignOut: () => void;
}

function Workspace({ api, userLabel, onSignOut, theme, toggleTheme }: WorkspaceProps) {
  const [ready, setReady] = useState(false);
  const [docCount, setDocCount] = useState(0);
  const [docsOpen, setDocsOpen] = useState(false); // phones only: documents fold above the chat
  const onDocs = useCallback((docs: DocumentInfo[]) => {
    setReady(docs.some((d) => d.status === "READY"));
    setDocCount(docs.length);
  }, []);
  const { logo, mark } = brandAssets(theme);
  const next = theme === "dark" ? "light" : "dark";

  return (
    <div className="app">
      <a className="skip-link" href="#question">
        Skip to the question box
      </a>
      <header className="topbar">
        <img className="topbar__logo" src={logo} alt="Clouddocs" />
        <ConnectionStatus api={api} />
        <div className="topbar__spacer" />
        <button
          type="button"
          className="btn btn-ghost docs-toggle"
          aria-expanded={docsOpen}
          aria-controls="sidebar"
          aria-label={`${docsOpen ? "Hide" : "Show"} documents (${docCount})`}
          onClick={() => setDocsOpen((o) => !o)}
        >
          <DocIcon />
          <span className="btn__label">Documents</span> <span className="docs__count">{docCount}</span>
        </button>
        <span className="topbar__user" title={userLabel}>
          {userLabel}
        </span>
        <button type="button" className="btn btn-ghost icon-btn" aria-label={`Switch to ${next} mode`} onClick={toggleTheme}>
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        <button type="button" className="btn btn-ghost" aria-label="Sign out" onClick={onSignOut}>
          <span className="btn__icon-only">
            <SignOutIcon />
          </span>
          <span className="btn__label">Sign out</span>
        </button>
      </header>
      <div className="layout">
        <aside id="sidebar" className={`sidebar${docsOpen ? "" : " sidebar--collapsed"}`} aria-label="Documents">
          <DocumentList api={api} onChange={onDocs} />
        </aside>
        <Chat api={api} hasReadyDocuments={ready} mark={mark} />
      </div>
    </div>
  );
}

/** Calls GET /me: proves browser -> Cognito token -> API Gateway authorizer -> Lambda works. */
function ConnectionStatus({ api }: { api: ApiClient }) {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .whoAmI()
      .then(() => !cancelled && setState({ ok: true, text: "Connected" }))
      .catch((e: unknown) => !cancelled && setState({ ok: false, text: e instanceof ApiError ? e.message : "API not reachable" }));
    return () => {
      cancelled = true;
    };
  }, [api]);
  if (!state) return null;
  return (
    <span className={`connection${state.ok ? "" : " connection--down"}`} role={state.ok ? "status" : "alert"} title={state.text}>
      <span className="connection__dot" aria-hidden="true" />
      <span className="connection__text">{state.ok ? "Connected" : state.text}</span>
    </span>
  );
}
