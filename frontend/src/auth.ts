import { Amplify } from "aws-amplify";
import { fetchAuthSession } from "aws-amplify/auth";
import type { AppConfig } from "./config";

/** Amplify is used only as the Cognito login library (D-009), not for hosting or backend. */
export function configureAuth(config: AppConfig): void {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.userPoolId,
        userPoolClientId: config.userPoolClientId,
        loginWith: { email: true },
      },
    },
  });
}

/** Returns a valid access token, refreshing it if needed. The API Gateway JWT authorizer checks it. */
export async function getAccessToken(): Promise<string> {
  const { tokens } = await fetchAuthSession();
  const token = tokens?.accessToken?.toString();
  if (!token) throw new Error("Not signed in");
  return token;
}
