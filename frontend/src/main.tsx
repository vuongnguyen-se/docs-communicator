import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
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
      <main>
        <h1>CloudDocs AI</h1>
        <p role="alert">The app could not start: its configuration is missing or invalid.</p>
      </main>,
    );
  });
