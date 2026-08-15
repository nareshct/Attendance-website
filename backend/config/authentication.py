from rest_framework.authentication import TokenAuthentication

from .models import AuthToken


class AuthTokenAuthentication(TokenAuthentication):
    """Same 'Authorization: Token <key>' scheme as DRF's built-in
    TokenAuthentication, just pointed at AuthToken (see its docstring)
    instead of the one-token-per-user rest_framework.authtoken.Token.
    """

    model = AuthToken
