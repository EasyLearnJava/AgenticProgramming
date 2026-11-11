"""Small HTTP adapters for Tavily Search and Nebius Chat Completions."""

import hashlib
import json
import time
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .models import NEWS_DAYS, Source, one_line, public_url

TAVILY_SEARCH = "https://api.tavily.com/search"
NEBIUS_CHAT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class ProviderError(RuntimeError):
    """A user-facing provider error with no secrets or upstream response body."""

    def __init__(self, message: str, *, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


def _request(client: httpx.Client, service: str, url: str, key: str, payload: dict) -> dict:
    # A read timeout or 429/5xx gets one retry. Bad credentials and requests fail fast.
    if not key:
        raise ProviderError(f"{service} API key is missing. See Documentation.", permanent=True)
    error = f"{service} could not be reached. Check your connection and retry."
    for attempt in range(2):
        try:
            response = client.post(url, json=payload, headers={"Authorization": f"Bearer {key}"})
        except (httpx.TimeoutException, httpx.NetworkError):
            pass
        else:
            if response.is_success:
                try:
                    result = response.json()
                    if isinstance(result, dict):
                        return result
                except ValueError:
                    pass
                error = f"{service} returned unreadable data."
            elif response.status_code in {401, 403}:
                raise ProviderError(f"{service} refused access. Check your key and account access.",
                                    permanent=True)
            elif response.status_code in {408, 429} or response.status_code >= 500:
                error = f"{service} is unavailable or rate limited (HTTP {response.status_code})."
            else:
                hint = "Check NEBIUS_MODEL and provider balance." if service == "Nebius" else "Check your Tavily plan and credits."
                raise ProviderError(f"{service} rejected the request (HTTP {response.status_code}). {hint}",
                                    permanent=True)
        if attempt == 0:
            time.sleep(0.7)
    raise ProviderError(error)


def _date(value: object) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            try:
                return parsedate_to_datetime(value).date()
            except (TypeError, ValueError, OverflowError):
                return None
    return None


class Tavily:
    def __init__(self, key: str, client: httpx.Client):
        self.key = key
        self.client = client

    def search(self, query: str, field: str, as_of: date, *, domain: str = "") -> list[Source]:
        payload = {
            "query": query[:380],
            "search_depth": "basic",
            "max_results": 4,
            "include_answer": False,
            "include_raw_content": False,
        }
        if domain:
            payload["include_domains"] = [domain]
        if field == "news":
            payload.update(
                topic="news",
                start_date=(as_of - timedelta(days=NEWS_DAYS)).isoformat(),
                end_date=(as_of + timedelta(days=1)).isoformat(),
                include_published_date=True,
                filter_by_published_date=True,
            )
        result = _request(self.client, "Tavily", TAVILY_SEARCH, self.key, payload)
        rows = result.get("results")
        if not isinstance(rows, list):
            raise ProviderError("Tavily returned an unexpected search response.")
        sources = {}
        for row in rows[:4]:
            if not isinstance(row, dict):
                continue
            url = public_url(row["url"]) if isinstance(row.get("url"), str) else ""
            excerpt = row.get("content")
            if not url or not isinstance(excerpt, str) or not excerpt.strip():
                continue
            # A follow-up can return a new excerpt from the same page. Preserve both quotes.
            excerpt = one_line(excerpt)[:1800]
            source_id = hashlib.sha256(f"{field}:{url}:{excerpt}".encode()).hexdigest()[:12]
            title = row.get("title")
            sources[source_id] = Source(
                id=source_id, url=url,
                title=one_line(title)[:160] if isinstance(title, str) and title.strip() else url,
                excerpt=excerpt, field=field, retrieved=as_of,
                published=_date(row.get("published_date")),
            )
        return list(sources.values())


class Nebius:
    def __init__(self, settings: Settings, client: httpx.Client):
        self.key = settings.nebius_key
        self.model = settings.model
        self.client = client

    def generate(self, instructions: str, inputs: dict, schema: type[ResponseModel]) -> ResponseModel:
        # Local validation stays in charge even if JSON mode returns valid JSON with the wrong shape.
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({
                "inputs": inputs,
                "required_output_schema": schema.model_json_schema(),
            }, ensure_ascii=False)},
        ]
        for attempt in range(2):
            result = _request(self.client, "Nebius", NEBIUS_CHAT, self.key, {
                "model": self.model, "messages": messages,
                "response_format": {"type": "json_object"},
                "max_tokens": 4000,
            })
            try:
                content = result["choices"][0]["message"]["content"]
                return schema.model_validate_json(content)
            except (KeyError, IndexError, TypeError, ValidationError):
                if attempt == 0:
                    messages.append({"role": "user", "content":
                                     "The previous response did not match the schema. Return a JSON object only."})
        raise ProviderError("Nebius did not return usable structured data. Try again or check the model.")
