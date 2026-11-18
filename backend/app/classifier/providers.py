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
import threading
import time
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
              "timeout": settings.ai_timeout_seconds, "max_retries": 0,
              "max_tokens": settings.ai_max_output_tokens}  # enough room so answers are not cut off
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


# ------------------------------------------------------------------ quota breaker

# provider -> monotonic time until which it is skipped. In memory: shared by all threads of THIS worker
# process (a restarted worker tries the provider again, which is harmless: one call finds out).
_cooldown_until: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def start_quota_cooldown(provider: str) -> None:
    """The provider said its DAILY quota is used up: skip it for ai_quota_cooldown_seconds."""
    with _cooldown_lock:
        _cooldown_until[provider] = time.monotonic() + settings.ai_quota_cooldown_seconds
    log.warning("ai.quota_cooldown_started", provider=provider, seconds=settings.ai_quota_cooldown_seconds)


def quota_cooldown_left(provider: str) -> float:
    """Seconds this provider is still skipped (0 = available)."""
    with _cooldown_lock:
        return max(0.0, _cooldown_until.get(provider, 0.0) - time.monotonic())


def reset_quota_cooldowns() -> None:
    """For tests."""
    with _cooldown_lock:
        _cooldown_until.clear()


# Daily-quota wording: Gemini "...PerDay..." / "per day"; Groq "tokens per day (TPD)" / "requests per day (RPD)".
DAILY_QUOTA_RE = re.compile(r"per ?day|\b(rpd|tpd)\b", re.IGNORECASE)


# ------------------------------------------------------------------ error classification

@dataclass
class AIErrorInfo:
    code: str                  # AI_TIMEOUT | AI_RATE_LIMITED | AI_QUOTA_EXHAUSTED | AI_INVALID_OUTPUT | AI_AUTH
                               # | AI_ERROR
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

    names = [type(e).__name__.lower() for e in _error_chain(exc)]
    if any("timeout" in n for n in names) or isinstance(exc, TimeoutError):
        return AIErrorInfo("AI_TIMEOUT", True, None, detail)
    if any("lengthfinishreason" in n for n in names):
        # The answer was cut off by the output-token limit: incomplete output, worth another try.
        return AIErrorInfo("AI_INVALID_OUTPUT", True, None, detail)
    if status == 429 or "resource_exhausted" in text or "rate limit" in text:
        if DAILY_QUOTA_RE.search(text):
            # Out of quota for the DAY: retrying in a few seconds cannot help -> cool down, next provider.
            return AIErrorInfo("AI_QUOTA_EXHAUSTED", False, None, detail + " daily quota")
        return AIErrorInfo("AI_RATE_LIMITED", True, _retry_after(exc), detail)  # per-minute: back off, retry
    if status in (401, 403) or (status == 400 and ("api key" in text or "api_key" in text)):
        return AIErrorInfo("AI_AUTH", False, None, detail)  # bad key: retrying cannot help
    if status is not None and status >= 500:
        return AIErrorInfo("AI_ERROR", True, None, detail)  # provider overloaded / down: may recover
    return AIErrorInfo("AI_ERROR", False, None, detail)     # e.g. 404 unknown model: go to next provider
