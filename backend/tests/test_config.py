"""Production refuses to start with a weak JWT secret."""
import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("secret", ["", "change-me", "too-short-secret"])
def test_production_refuses_weak_jwt_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret=secret)


def test_production_accepts_a_long_random_secret():
    s = Settings(_env_file=None, environment="production", jwt_secret="x" * 48)
    assert s.environment == "production"


def test_development_allows_the_default_secret():
    assert Settings(_env_file=None, environment="development").jwt_secret == "change-me"
