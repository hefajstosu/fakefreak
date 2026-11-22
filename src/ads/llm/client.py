"""Provider-agnostic LLM client with disk cache and retries.

Usage:
    client = make_client()                       # reads config/llm.yaml and .env
    data = client.generate_json(system, parts)   # parts: [("text", "..."), ("image", "path.png")]

Providers: "gemini" (google-genai), "mock" (tests). Adding another provider means one
subclass of LLMClient with `_call`. Responses are cached on disk keyed by everything that
influences them, so reruns and demo runs cost nothing.
"""
import hashlib
import io
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..paths import CACHE, CONFIG, REPO

Part = Tuple[str, str]  # ("text", content), ("image", path) or ("audio", path)
AUDIO_MIME = {".mp3": "audio/mp3", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac"}


def load_env(path: Optional[str] = None) -> None:
    from dotenv import load_dotenv
    load_dotenv(path or os.path.join(REPO, ".env"))


def load_llm_config() -> Dict[str, Any]:
    """config/llm.yaml (models, fallback models, cache directory, variant settings)."""
    import yaml
    with open(os.path.join(CONFIG, "llm.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def image_bytes(path: str, max_side: int = 1600) -> Tuple[bytes, str]:
    """Load an image, shrink it (phone screenshots are huge) and return JPEG bytes."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if max(im.size) > max_side:
        scale = max_side / max(im.size)
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


class QuotaExhausted(RuntimeError):
    """Every model in the failover list is out of quota (or unavailable); retrying right away is pointless."""


def is_quota_error(e: Exception) -> bool:
    msg = str(e)
    return any(c in msg for c in ("429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "403", "PERMISSION_DENIED"))


def with_fallback(models: List[str], fn: Callable[[str], str]) -> str:
    """Call fn(model) for each model in order; move on when a model is out of quota or unavailable."""
    last: Optional[Exception] = None
    for m in models:
        try:
            return fn(m)
        except Exception as e:  # noqa: BLE001
            if not is_quota_error(e):
                raise
            last = e
    raise QuotaExhausted(f"all {len(models)} model(s) are out of free quota or unavailable ({', '.join(models)}). "
                         f"Last error: {str(last)[:160]}")


class LLMClient:
    def __init__(self, model: str, cache_dir: str, max_retries: int = 2, temperature: float = 0.0, json_mode: bool = True):
        self.model, self.max_retries, self.temperature, self.json_mode = model, max_retries, temperature, json_mode
        self.cache_dir = cache_dir if os.path.isabs(cache_dir) else os.path.join(REPO, cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

    # -- to implement per provider -------------------------------------------------
    def _call(self, system: str, parts: List[Part]) -> str:
        raise NotImplementedError

    # -- shared ----------------------------------------------------------------------
    def _key(self, system: str, parts: List[Part]) -> str:
        h = hashlib.sha256()
        h.update(f"{type(self).__name__}|{self.model}|{self.temperature}|{self.json_mode}|".encode())
        h.update(system.encode())
        for kind, val in parts:
            h.update(kind.encode())
            h.update(open(val, "rb").read() if kind in ("image", "audio") else val.encode())
        return h.hexdigest()

    def generate_text(self, system: str, parts: List[Part], use_cache: bool = True) -> str:
        key = self._key(system, parts)
        path = os.path.join(self.cache_dir, key + ".txt")
        if use_cache and os.path.exists(path):
            return open(path, encoding="utf-8").read()
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._call(system, parts)
                if use_cache:
                    open(path, "w", encoding="utf-8").write(text)
                return text
            except QuotaExhausted:  # every model is out of quota: fail fast, with a clear message
                raise
            except Exception as e:  # rate limit / transient server error -> back off and retry
                last = e
                msg = str(e)
                transient = any(c in msg for c in ("429", "500", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
                if not transient or attempt == self.max_retries:
                    break
                m = re.search(r"retry in ([\d.]+)s", msg, re.I)
                time.sleep(min(float(m.group(1)) + 1 if m else 5 * 2 ** attempt, 60))
        raise RuntimeError(f"LLM call failed after retries: {last}") from last

    def generate_json(self, system: str, parts: List[Part], use_cache: bool = True) -> Dict[str, Any]:
        text = self.generate_text(system, parts, use_cache)
        try:
            return parse_json(text)
        except ValueError:  # malformed output must not stay cached, or every rerun would fail the same way
            path = os.path.join(self.cache_dir, self._key(system, parts) + ".txt")
            if os.path.exists(path):
                os.remove(path)
            raise


def parse_json(text: str) -> Dict[str, Any]:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return json.loads(t[i:j + 1])
        raise


class GeminiClient(LLMClient):
    def __init__(self, *a, api_key_env: str = "GEMINI_API_KEY", fallback_models: Optional[List[str]] = None, **kw):
        super().__init__(*a, **kw)
        self.models = [self.model] + [m for m in (fallback_models or []) if m != self.model]
        from google import genai
        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"{api_key_env} is not set (put it in .env)")
        self._genai, self._client = genai, genai.Client(api_key=key)

    def _call(self, system: str, parts: List[Part]) -> str:
        return with_fallback(self.models, lambda m: self._call_model(m, system, parts))

    def _call_model(self, model: str, system: str, parts: List[Part]) -> str:
        from google.genai import types
        contents = []
        for kind, val in parts:
            if kind == "image":
                data, mime = image_bytes(val)
                contents.append(types.Part.from_bytes(data=data, mime_type=mime))
            elif kind == "audio":
                contents.append(types.Part.from_bytes(data=open(val, "rb").read(),
                                                      mime_type=AUDIO_MIME[os.path.splitext(val)[1].lower()]))
            else:
                contents.append(types.Part.from_text(text=val))
        r = self._client.models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=self.temperature,
                **({"response_mime_type": "application/json"} if self.json_mode else {})))
        return "".join(p.text for p in r.candidates[0].content.parts if getattr(p, "text", None))


class MockClient(LLMClient):
    """Returns canned JSON; used in tests so nothing hits the network."""
    def __init__(self, responses: List[str]):
        super().__init__("mock", os.path.join(CACHE, "mock"))
        self.responses, self.calls = list(responses), []

    def generate_text(self, system, parts, use_cache=True):
        self.calls.append((system, parts))
        return self.responses.pop(0)


def make_client(model_key: str = "extraction_model", json_mode: bool = True, **overrides) -> LLMClient:
    load_env()
    cfg = {**load_llm_config(), **overrides}
    provider = cfg.get("provider", "gemini")
    if provider == "gemini":
        explicit = bool(overrides.get(model_key))  # an explicitly chosen model is used as is, without failover
        return GeminiClient(cfg[model_key], cfg["cache_dir"], cfg.get("max_retries", 2), json_mode=json_mode,
                            api_key_env=cfg.get("api_key_env", "GEMINI_API_KEY"),
                            fallback_models=None if explicit else cfg.get("fallback_models"))
    raise ValueError(f"unknown provider: {provider}")
