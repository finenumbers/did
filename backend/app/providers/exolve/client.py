"""Exolve Numbering API client — GetList + GetFree only (read-only)."""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.exolve import contract, parser
from app.providers.progress_emit import ProgressCb, emit_progress
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)

RandomMode = Literal["omit", "false", "true"]
SyncMode = Literal["type_region", "type_region_category"]

DOC_PROBE_NAMES = frozenset({"doc_moscow_def_regular", "doc_moscow_abc_regular"})
NO_CATEGORY_PROBE_NAMES = frozenset(
    {"moscow_def_random_false", "moscow_def_omit_random", "type_only_def"}
)


class ExolveClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
        page_limit: int | None = None,
        random_mode: RandomMode | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(read_timeout=90.0, total_timeout=120.0)
        self.retry = retry or RetryPolicy(retry_on_status=[429, 502, 503, 504])
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self.page_limit = int(page_limit or contract.DEFAULT_PAGE_LIMIT)
        # Default omit for inventory pagination (docs examples use random=true for demos).
        self.random_mode: RandomMode = random_mode or contract.DEFAULT_RANDOM_MODE  # type: ignore[assignment]
        auth = connection.auth_settings or {}
        self._api_key = (auth.get(contract.AUTH_API_KEY) or "").strip() or None
        if not self._api_key:
            raise ProviderAuthError(
                "Exolve API key missing (Settings → Exolve → API-ключ)",
                details={"code": "EXOLVE_API_KEY_MISSING"},
            )
        self._shared_http: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

    async def open(self) -> None:
        """Reuse one AsyncClient across fan-out slice calls."""
        if self._shared_http is None:
            self._shared_http = httpx.AsyncClient(timeout=self._http_timeout())

    async def aclose(self) -> None:
        if self._shared_http is not None:
            await self._shared_http.aclose()
            self._shared_http = None

    async def _post(self, path: str, body: dict[str, Any]) -> RawHttpResult:
        url = f"{self.base_url}{path}"
        timeout = self._http_timeout()
        t0 = time.perf_counter()

        async def _once() -> httpx.Response:
            if self._shared_http is not None:
                return await self._shared_http.post(
                    url, json=body, headers=self._headers()
                )
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.post(url, json=body, headers=self._headers())

        response = await request_with_retries(
            retry=self.retry, label=f"Exolve {path}", do_request=_once
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        text = response.text
        try:
            payload = response.json()
        except Exception:
            payload = None
        raw = RawHttpResult(
            status_code=response.status_code,
            body_text=text[:4000],
            body_json=payload,
            headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
            request_url=url,
        )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Exolve auth failed HTTP {response.status_code}",
                details={"status": response.status_code, "hint": "EXOLVE_AUTH_FAILED"},
            )
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"Exolve {path} HTTP {response.status_code}: {text[:300]}",
                code="EXOLVE_HTTP_ERROR",
                details={"status": response.status_code, "path": path},
            )
        return raw

    async def get_reference(self) -> tuple[dict[str, Any], RawHttpResult]:
        raw = await self._post(contract.PATH_REFERENCE, {})
        data = raw.body_json if isinstance(raw.body_json, dict) else {}
        return data, raw

    def _free_body(
        self,
        *,
        type_id: int,
        region_id: int | None,
        offset: int,
        limit: int,
        random_mode: RandomMode | None = None,
        category_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type_id": int(type_id),
            "limit": int(limit),
            "offset": int(offset),
        }
        if region_id is not None:
            body["region_id"] = int(region_id)
        if category_id is not None:
            body["category_id"] = int(category_id)
        mode = random_mode if random_mode is not None else self.random_mode
        if mode == "false":
            body["random"] = False
        elif mode == "true":
            body["random"] = True
        return body

    async def get_free_page(
        self,
        *,
        type_id: int,
        region_id: int | None,
        offset: int,
        limit: int | None = None,
        random_mode: RandomMode | None = None,
        category_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], RawHttpResult]:
        body = self._free_body(
            type_id=type_id,
            region_id=region_id,
            offset=offset,
            limit=int(limit if limit is not None else self.page_limit),
            random_mode=random_mode,
            category_id=category_id,
        )
        raw = await self._post(contract.PATH_GET_FREE, body)
        try:
            items = parser.extract_free_numbers(raw.body_json)
        except TypeError as exc:
            raise ProviderError(
                str(exc),
                code="EXOLVE_BAD_RESPONSE",
            ) from exc
        return items, raw

    async def probe_get_free(self) -> list[dict[str, Any]]:
        """Canary variants: docs examples (with category) + no-category baselines."""
        probes: list[tuple[str, dict[str, Any]]] = [
            (
                "doc_moscow_def_regular",
                {
                    "type_id": contract.DOC_EXAMPLE_MOSCOW_DEF["type_id"],
                    "region_id": contract.DOC_EXAMPLE_MOSCOW_DEF["region_id"],
                    "category_id": contract.DOC_EXAMPLE_MOSCOW_DEF["category_id"],
                    "random_mode": "true",
                },
            ),
            (
                "doc_moscow_abc_regular",
                {
                    "type_id": contract.DOC_EXAMPLE_MOSCOW_ABC["type_id"],
                    "region_id": contract.DOC_EXAMPLE_MOSCOW_ABC["region_id"],
                    "category_id": contract.DOC_EXAMPLE_MOSCOW_ABC["category_id"],
                    "random_mode": "true",
                },
            ),
            (
                "moscow_def_random_false",
                {
                    "type_id": contract.TYPE_DEF,
                    "region_id": 10230,
                    "category_id": None,
                    "random_mode": "false",
                },
            ),
            (
                "moscow_def_omit_random",
                {
                    "type_id": contract.TYPE_DEF,
                    "region_id": 10230,
                    "category_id": None,
                    "random_mode": "omit",
                },
            ),
            (
                "type_only_def",
                {
                    "type_id": contract.TYPE_DEF,
                    "region_id": None,
                    "category_id": None,
                    "random_mode": "omit",
                },
            ),
        ]
        out: list[dict[str, Any]] = []
        for name, kwargs in probes:
            items, raw = await self.get_free_page(
                type_id=int(kwargs["type_id"]),
                region_id=kwargs["region_id"],  # type: ignore[arg-type]
                offset=0,
                limit=1,
                random_mode=kwargs["random_mode"],  # type: ignore[arg-type]
                category_id=kwargs["category_id"],  # type: ignore[arg-type]
            )
            summary = parser.summarize_free_payload(
                raw.status_code, raw.body_json, raw.body_text or ""
            )
            summary["probe"] = name
            summary["request"] = {
                "type_id": kwargs["type_id"],
                "region_id": kwargs["region_id"],
                "category_id": kwargs["category_id"],
                "random_mode": kwargs["random_mode"],
                "limit": 1,
                "offset": 0,
            }
            summary["parsed_len"] = len(items)
            out.append(summary)
        return out

    @staticmethod
    def probe_number_totals(probes: list[dict[str, Any]]) -> dict[str, int]:
        doc_n = 0
        no_cat_n = 0
        for p in probes:
            n = int(p.get("numbers_len") or 0)
            name = str(p.get("probe") or "")
            if name in DOC_PROBE_NAMES:
                doc_n = max(doc_n, n)
            if name in NO_CATEGORY_PROBE_NAMES:
                no_cat_n = max(no_cat_n, n)
        best = max((int(p.get("numbers_len") or 0) for p in probes), default=0)
        return {
            "doc_example_numbers": doc_n,
            "no_category_numbers": no_cat_n,
            "best_numbers": best,
        }

    def choose_random_mode_from_probes(self, probes: list[dict[str, Any]]) -> RandomMode:
        """Prefer omit when random=false is empty but omit returns numbers."""
        by_name = {p.get("probe"): p for p in probes}
        false_p = by_name.get("moscow_def_random_false") or {}
        omit_p = by_name.get("moscow_def_omit_random") or {}
        false_n = int(false_p.get("numbers_len") or 0)
        omit_n = int(omit_p.get("numbers_len") or 0)
        if omit_n > 0 and false_n == 0:
            return "omit"
        if false_n > 0:
            return "false"
        return "omit"

    def choose_sync_mode_from_probes(self, probes: list[dict[str, Any]]) -> SyncMode:
        """
        If docs examples (with category_id) return numbers but no-category probes
        do not, sync must pass category_id (type×region×category).
        """
        totals = self.probe_number_totals(probes)
        if totals["doc_example_numbers"] > 0 and totals["no_category_numbers"] == 0:
            return contract.SYNC_MODE_TYPE_REGION_CATEGORY  # type: ignore[return-value]
        return contract.SYNC_MODE_TYPE_REGION  # type: ignore[return-value]

    async def iter_free_slice(
        self,
        *,
        type_id: int,
        region_id: int,
        category_id: int | None = None,
        on_progress: ProgressCb | None = None,
        type_label: str = "",
        on_first_raw: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate one (type_id, region_id[, category_id]) slice until short/empty page."""
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        page_limit = self.page_limit
        first_logged = False
        cat_part = f" category={category_id}" if category_id is not None else ""
        while offset <= contract.MAX_OFFSET:
            await emit_progress(
                on_progress,
                (
                    f"Exolve GetFree {type_label or type_id} "
                    f"region={region_id}{cat_part} offset={offset}"
                ),
                len(items),
                None,
            )
            page, raw = await self.get_free_page(
                type_id=type_id,
                region_id=region_id,
                category_id=category_id,
                offset=offset,
                limit=page_limit,
            )
            envelopes.append(raw)
            if not first_logged and on_first_raw is not None:
                first_logged = True
                on_first_raw(raw)
            if not page:
                break
            items.extend(page)
            if len(page) < page_limit:
                break
            offset += len(page)
            if offset > contract.MAX_OFFSET:
                raise ProviderError(
                    (
                        "Exolve GetFree pagination truncated "
                        f"type_id={type_id} region_id={region_id} "
                        f"category_id={category_id} offset={offset}"
                    ),
                    code="EXOLVE_PAGINATION_TRUNCATED",
                    details={
                        "type_id": type_id,
                        "region_id": region_id,
                        "category_id": category_id,
                        "offset": offset,
                        "max_offset": contract.MAX_OFFSET,
                    },
                )
        return items, envelopes
