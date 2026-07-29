export interface AuthToken {
  token: string;
  tokenType: "Bearer";
  expiresAt: string;
}

export interface AuthTokenProvider {
  getToken(): Promise<AuthToken>;
}
