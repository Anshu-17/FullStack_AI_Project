"""AI providers: build a chat model per provider, decide the order to try them, classify their errors.

Primary: Gemini (Google). Fallback: Groq, through its OpenAI-compatible API
(so the standard OpenAI connector works with a different base_url).
Anthropic, xAI and OpenAI are wired too, for completeness.

Every client is created with temperature 0 (as repeatable as possible), our
timeout, and its OWN retries switched off - the pipeline does the retrying,
so every single call is visible in the ai_usage table.

API keys are only passed to the client; they are never logged or printed.
"""
import re
from dataclasses import dataclass

from app.classifier.schema import ClassificationOutput
from app.config import settings
from app.log_config import get_logger

log = get_logger("classifier.providers")

KNOWN_PROVIDERS = ("google", "groq", "anthropic", "xai", "openai", "fake")  # fake = TEST-ONLY
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def fake_allowed() -> bool:
    """The fake test provider can never be used in production."""
    return settings.environment != "production"


def provider_settings(provider: str) -> tuple[str, str]:
    """(api_key, model) for a provider, from settings. The fake provider needs no key (and is off in production)."""
    if provider == "fake":
        from app.classifier.fake_provider import MODEL_NAME
        return ("not-needed", MODEL_NAME) if fake_allowed() else ("", "")
    return getattr(settings, f"{provider}_api_key", ""), getattr(settings, f"{provider}_model", "")


def provider_order() -> list[str]:
    """AI_PROVIDER first, then AI_FALLBACK_PROVIDERS - skipping unknown or unconfigured ones."""
    wanted = [settings.ai_provider, *settings.ai_fallback_providers.split(",")]
    order: list[str] = []
    for name in (w.strip().lower() for w in wanted):
        if not name or name in order:
            continue
        if name not in KNOWN_PROVIDERS:
            log.warning("ai.provider_skipped", provider=name, reason="unknown provider")
            continue
        api_key, model = provider_settings(name)
        if not api_key or not model:
            missing = "api key" if not api_key else "model"
            log.warning("ai.provider_skipped", provider=name, reason=f"no {missing} configured")
            continue
        order.append(name)
    return order


def get_chat_model(provider: str):
    """A LangChain chat model for `provider` (temperature 0, our timeout, no built-in retries)."""
    api_key, model = provider_settings(provider)
    common = {"model": model, "api_key": api_key, "temperature": 0,
              "timeout": settings.ai_timeout_seconds, "max_retries": 0}
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(**common)
    if provider == "groq":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(base_url=GROQ_BASE_URL, **common)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**common)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(**common)
    if provider == "xai":
        from langchain_xai import ChatXAI
        return ChatXAI(**common)
    raise ValueError(f"unknown provider {provider}")


def build_structured_model(provider: str):
    """Chat model that must answer as ClassificationOutput.

    include_raw=True returns {"raw": message, "parsed": object-or-None, "parsing_error": ...}
    so we still get token usage, and can tell "bad output" apart from "call failed".
    """
    if provider == "fake":
        if not fake_allowed():
            raise ValueError("the fake AI provider is disabled in production")
        from app.classifier.fake_provider import FakeKeywordModel
        return FakeKeywordModel()
    kwargs = {"method": "json_schema"} if provider in ("google", "groq", "openai") else {}
    return get_chat_model(provider).with_structured_output(ClassificationOutput, include_raw=True, **kwargs)


# ------------------------------------------------------------------ error classification

@dataclass
class AIErrorInfo:
    code: str                  # AI_TIMEOUT | AI_RATE_LIMITED | AI_AUTH | AI_ERROR
    retryable: bool            # worth trying the SAME provider again?
    retry_after: float | None  # seconds the provider asked us to wait, if it said
    detail: str                # short, safe description (no keys)


def _error_chain(exc: BaseException):
    """The exception and the ones it wraps (LangChain often wraps the SDK's error)."""
    seen = 0
    while exc is not None and seen < 5:
        yield exc
        exc = exc.__cause__ or exc.__context__
        seen += 1


def _status_code(exc: BaseException) -> int | None:
    for e in _error_chain(exc):
        for attr in ("status_code", "code", "status"):
            value = getattr(e, attr, None)
            if isinstance(value, int) and 100 <= value < 600:
                return value
        response = getattr(e, "response", None)
        if isinstance(getattr(response, "status_code", None), int):
            return response.status_code
    return None


def _retry_after(exc: BaseException) -> float | None:
    """Retry-After header, or Gemini's 'Please retry in 12.3s' message."""
    for e in _error_chain(exc):
        response = getattr(e, "response", None)
        headers = getattr(response, "headers", None) or {}
        try:
            return float(headers.get("retry-after"))
        except (TypeError, ValueError):
            pass
        match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", str(e), re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def describe_error(exc: BaseException) -> AIErrorInfo:
    """Turn any provider exception into one of our error codes."""
    status = _status_code(exc)
    text = " ".join(str(e) for e in _error_chain(exc)).lower()
    detail = f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")

    if any("timeout" in type(e).__name__.lower() for e in _error_chain(exc)) or isinstance(exc, TimeoutError):
        return AIErrorInfo("AI_TIMEOUT", True, None, detail)
    if status == 429 or "resource_exhausted" in text or "rate limit" in text:
        return AIErrorInfo("AI_RATE_LIMITED", True, _retry_after(exc), detail)
    if status in (401, 403) or (status == 400 and ("api key" in text or "api_key" in text)):
        return AIErrorInfo("AI_AUTH", False, None, detail)  # bad key: retrying cannot help
    if status is not None and status >= 500:
        return AIErrorInfo("AI_ERROR", True, None, detail)  # provider overloaded / down: may recover
    return AIErrorInfo("AI_ERROR", False, None, detail)     # e.g. 404 unknown model: go to next provider
