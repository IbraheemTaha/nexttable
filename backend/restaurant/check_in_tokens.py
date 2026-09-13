import base64
import hashlib
import hmac

from django.conf import settings
from django.utils import timezone


TOKEN_CONTEXT = 'nexttable.check-in-token.v1'
TOKEN_LENGTH = 32


def get_current_check_in_token(for_date=None):
    """Return the deterministic check-in token for a restaurant day."""
    restaurant_day = for_date or timezone.localdate()
    return _token_for_date(restaurant_day)


def is_valid_check_in_token(token, for_date=None):
    """Return True when token matches the current restaurant-day token."""
    if not isinstance(token, str) or not token.strip():
        return False

    expected_token = get_current_check_in_token(for_date=for_date)
    return hmac.compare_digest(token.strip(), expected_token)


def _token_for_date(restaurant_day):
    message = f'{TOKEN_CONTEXT}:{restaurant_day.isoformat()}'.encode()
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        message,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')[:TOKEN_LENGTH]
