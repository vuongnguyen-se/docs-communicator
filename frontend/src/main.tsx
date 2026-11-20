import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { configureAuth } from "./auth";
import { loadConfig } from "./config";

const root = createRoot(document.getElementById("root")!);

loadConfig()
  .then((config) => {
    if (config.mode === "http") configureAuth(config);
    root.render(
      <StrictMode>
        <App config={config} />
      </StrictMode>,
    );
  })
  .catch((err: unknown) => {
    console.error(err);
    root.render(
      <main className="signin">
        <div className="signin__panel">
          <h1 className="signin__title">Clouddocs</h1>
          <p className="alert" role="alert">
            The app could not start: its configuration is missing or invalid.
          </p>
        </div>
      </main>,
    );
  });
