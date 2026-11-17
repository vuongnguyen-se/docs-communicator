import { MockApi } from "./mock";
import type { ApiClient } from "./types";

/**
 * Local-first: the real HTTP client (Cognito + API Gateway) is added in Phase 2.
 * Until then the app always uses the mock, which is also what `npm run dev` shows.
 */
export function createApi(): ApiClient {
  return new MockApi();
}

export * from "./types";
