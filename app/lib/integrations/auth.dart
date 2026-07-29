final class AuthToken {
  const AuthToken({
    required this.token,
    required this.tokenType,
    required this.expiresAt,
  });

  final String token;
  final String tokenType;
  final DateTime expiresAt;
}

abstract interface class AuthTokenProvider {
  Future<AuthToken> getToken();
}
