"""Novofon Data API JSON-RPC client. Docs: novofon-contract.md — read-only get.*."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.novofon import contract, parser
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NovofonPrincipal:
    """Who the access token acts as. user_id is sent only for an agent."""

    kind: str
    summary: str
    app_id: int | None = None
    name: str | None = None
    user_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "app_id": self.app_id,
            "name": self.name,
            "user_id": self.user_id,
        }


class NovofonClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
        page_limit: int | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig()
        self.retry = retry or RetryPolicy()
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self._page_limit_override = page_limit
        auth = connection.auth_settings or {}
        self._token = (auth.get(contract.AUTH_ACCESS_TOKEN) or "").strip() or None
        user_id = auth.get(contract.AUTH_USER_ID)
        self._configured_user_id: int | None = None
        if user_id is not None and str(user_id).strip() != "":
            try:
                self._configured_user_id = int(user_id)
            except (TypeError, ValueError) as exc:
                raise ProviderAuthError(
                    f"Novofon auth_settings.user_id must be a number, got {user_id!r}"
                ) from exc
        self._principal: NovofonPrincipal | None = None
        self._scope_user_id: int | None = None

    def limit_for(self, method: str) -> int:
        if self._page_limit_override is not None:
            return min(self._page_limit_override, contract.MAX_LIMIT)
        if method == contract.METHOD_VIRTUAL_NUMBERS:
            return contract.PURCHASED_PAGE_LIMIT
        return contract.FREE_PAGE_LIMIT

    async def call(self, method: str, params: dict[str, Any] | None = None) -> RawHttpResult:
        envelope = {
            "jsonrpc": contract.JSONRPC_VERSION,
            "id": str(uuid.uuid4()),
            "method": method,
            "params": {k: v for k, v in (params or {}).items() if v is not None},
        }
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await client.post(
                    self.base_url,
                    json=envelope,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                )

        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label=f"Novofon {method}",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        try:
            body_json: Any | None = response.json()
        except ValueError:
            body_json = None
        return RawHttpResult(
            status_code=response.status_code,
            body_text=response.text,
            body_json=body_json,
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )

    def require_access_token(self) -> str:
        if not self._token:
            raise ProviderAuthError(
                "Novofon access_token is required (API key from the Novofon personal account)"
            )
        return self._token

    def adopt_principal(self, principal: NovofonPrincipal) -> None:
        self._principal = principal
        self._scope_user_id = principal.user_id

    async def _rpc(
        self,
        method: str,
        extra: dict[str, Any] | None = None,
        *,
        scope_user: bool = False,
    ) -> RawHttpResult:
        token = self.require_access_token()
        params: dict[str, Any] = {contract.AUTH_ACCESS_TOKEN: token}
        if scope_user and self._scope_user_id is not None:
            params[contract.AUTH_USER_ID] = self._scope_user_id
        if extra:
            params.update(extra)
        retried = False
        while True:
            raw = await self.call(method, params)
            wait = parser.limit_retry_wait(raw)
            if wait is not None and not retried:
                retried = True
                logger.warning("Novofon %s minute limit; sleeping %.0fs", method, wait)
                await asyncio.sleep(wait)
                continue
            return raw

    async def resolve_principal(self) -> NovofonPrincipal:
        """Classify the token before any number read. Does not mutate auth_settings."""
        if self._principal is not None:
            return self._principal
        self.require_access_token()
        users_raw = await self._rpc(
            contract.METHOD_CUSTOMER_USERS,
            {"offset": 0, "limit": 1},
        )
        users_result, users_miss = parser.audience_or_result(users_raw)
        agent = False
        users_total: int | None = None
        if users_result is not None:
            agent, users_total = parser.customer_users_are_agent(users_result)
        if agent:
            principal = await self._resolve_agent()
        else:
            principal = await self._resolve_client(
                users_miss=users_miss,
                users_total=users_total,
            )
        self.adopt_principal(principal)
        return principal

    async def _resolve_client(
        self,
        *,
        users_miss: str | None,
        users_total: int | None,
    ) -> NovofonPrincipal:
        account_raw = await self._rpc(contract.METHOD_ACCOUNT)
        account_result, account_miss = parser.audience_or_result(account_raw)
        if account_result is not None:
            account = parser.parse_account(account_result)
            if account is None:
                raise ProviderError(
                    "Novofon get.account не вернул app_id",
                    code="NOVOFON_PRINCIPAL_UNKNOWN",
                )
            name = account["name"] or "без названия"
            summary = f"Клиент «{name}» app_id={account['app_id']}"
            if users_total == 0:
                summary += ", get.customer_users вернул 0"
            if self._configured_user_id is not None:
                summary += f", сохранённый user_id={self._configured_user_id} не отправлен"
            return NovofonPrincipal(
                kind="client",
                summary=summary,
                app_id=account["app_id"],
                name=account["name"],
                user_id=None,
            )
        if users_miss and account_miss:
            raise ProviderError(
                "Novofon: не удалось определить клиента или агента "
                f"(get.customer_users={users_miss}, get.account={account_miss})",
                code="NOVOFON_PRINCIPAL_UNKNOWN",
            )
        if users_total == 0 and account_miss:
            raise ProviderError(
                "Ключ агента Novofon: get.customer_users вернул 0 пользователей",
                code="NOVOFON_AGENT_USER_REQUIRED",
            )
        raise ProviderError(
            "Novofon: не удалось определить клиента или агента "
            f"(get.customer_users={users_miss or 'empty'}, get.account={account_miss})",
            code="NOVOFON_PRINCIPAL_UNKNOWN",
        )

    async def _resolve_agent(self) -> NovofonPrincipal:
        if self._configured_user_id is None:
            preview_raw = await self._rpc(
                contract.METHOD_CUSTOMER_USERS,
                {"offset": 0, "limit": contract.USER_PREVIEW_LIMIT},
            )
            preview, _miss = parser.audience_or_result(preview_raw)
            if preview is None:
                raise ProviderError(
                    "Novofon get.customer_users недоступен при перечислении пользователей",
                    code="NOVOFON_AGENT_USER_REQUIRED",
                )
            users, total = parser.parse_customer_users(preview)
            shown = "; ".join(
                f"id={row['id']} name={row['name']} login={row['login']} "
                f"customer_id={row['customer_id']}"
                for row in users
            ) or "пусто"
            total_shown = total if total is not None else len(users)
            raise ProviderError(
                "Ключ агента Novofon: укажите user_id пользователя клиента "
                f"из get.customer_users. Всего {total_shown}. Первые: {shown}",
                code="NOVOFON_AGENT_USER_REQUIRED",
                details={"total_items": total, "users": users},
            )
        filtered = await self._rpc(
            contract.METHOD_CUSTOMER_USERS,
            {
                "offset": 0,
                "limit": 1,
                "filter": {
                    "field": "id",
                    "operator": "=",
                    "value": self._configured_user_id,
                },
            },
        )
        found, _miss = parser.audience_or_result(filtered)
        if found is None:
            raise ProviderError(
                "Novofon get.customer_users недоступен при проверке user_id",
                code="NOVOFON_AGENT_USER_REQUIRED",
            )
        users, _total = parser.parse_customer_users(found)
        match = next((row for row in users if row["id"] == self._configured_user_id), None)
        if match is None:
            raise ProviderError(
                f"Ключ агента Novofon: user_id={self._configured_user_id} "
                "нет в get.customer_users",
                code="NOVOFON_AGENT_USER_REQUIRED",
            )
        name = match["name"] or match["login"] or str(match["id"])
        return NovofonPrincipal(
            kind="agent",
            summary=f"Агент, user_id={match['id']} ({name})",
            user_id=match["id"],
            name=name,
        )

    def _category_filter(
        self, *, category: str | None, category_is_null: bool
    ) -> dict[str, Any] | None:
        if category_is_null:
            return {"field": "category", "operator": "=", "value": None}
        if category is not None:
            return {"field": "category", "operator": "=", "value": category}
        return None

    async def get_page(
        self,
        method: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        category: str | None = None,
        category_is_null: bool = False,
    ) -> RawHttpResult:
        extra: dict[str, Any] = {
            "offset": offset,
            "limit": limit if limit is not None else self.limit_for(method),
        }
        filt = self._category_filter(category=category, category_is_null=category_is_null)
        if filt is not None:
            extra["filter"] = filt
        return await self._rpc(method, extra, scope_user=True)

    async def _walk(
        self,
        method: str,
        *,
        category: str | None = None,
        category_is_null: bool = False,
        on_progress: Any | None = None,
        label: str = "",
        reject_over_window: bool = False,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        from app.providers.progress_emit import emit_progress

        limit = self.limit_for(method)
        window = contract.MAX_OFFSET + limit
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        total: int | None = None
        page_limits: dict[str, Any] | None = None
        stopped_at_max_offset = False
        stop_reason = "unknown"
        prefix = f"Novofon: {method}{label}"
        await emit_progress(on_progress, prefix)
        while True:
            if offset > contract.MAX_OFFSET:
                stopped_at_max_offset = True
                stop_reason = "max_offset"
                break
            raw = await self.get_page(
                method,
                offset=offset,
                limit=limit,
                category=category,
                category_is_null=category_is_null,
            )
            envelopes.append(raw)
            page_items, page_total = parser.parse_list_page(raw)
            if page_limits is None:
                body = raw.body_json
                result = body.get("result") if isinstance(body, dict) else None
                if isinstance(result, dict):
                    page_limits = parser.result_limits(result)
            if total is None and page_total is not None:
                total = page_total
            if reject_over_window and total is not None and total > window:
                raise ProviderError(
                    f"Novofon {method}{label} slice exceeds offset window: "
                    f"total_items={total} window={window}",
                    code="NOVOFON_PAGINATION_TRUNCATED",
                    details={
                        "method": method,
                        "category": category,
                        "category_is_null": category_is_null,
                        "total_items": total,
                        "window": window,
                    },
                )
            items.extend(page_items)
            await emit_progress(on_progress, f"{prefix} offset={offset}", len(items), total)
            if not page_items:
                stop_reason = "empty_page"
                break
            offset += len(page_items)
            if total is not None and offset >= total:
                stop_reason = "reached_total"
                break
            if len(page_items) < limit and (total is None or offset >= total):
                stop_reason = "short_page"
                break
            if offset > contract.MAX_OFFSET:
                stopped_at_max_offset = True
                stop_reason = "max_offset"
                break

        integrity: dict[str, Any] = {
            "method": method,
            "category": category,
            "category_is_null": category_is_null,
            "fetched": len(items),
            "total_items": total,
            "stop_reason": stop_reason,
            "stopped_at_max_offset": stopped_at_max_offset,
            "total_items_mismatch": bool(
                total is not None and len(items) < total and not stopped_at_max_offset
            ),
            "limits": page_limits or {},
        }
        if total is not None and len(items) < total and (
            stopped_at_max_offset or reject_over_window
        ):
            raise ProviderError(
                f"Novofon {method}{label} truncated: fetched {len(items)} of {total}",
                code="NOVOFON_PAGINATION_TRUNCATED",
                details=integrity,
            )
        if total is not None and len(items) < total:
            logger.warning(
                "Novofon %s%s incomplete: fetched %s of %s (stop_reason=%s); persisting fetched",
                method,
                label,
                len(items),
                total,
                stop_reason,
            )
        return items, envelopes, integrity

    async def iter_all(
        self,
        method: str,
        *,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        """Full read. Partition by category when total_items exceeds one offset window."""
        limit = self.limit_for(method)
        window = contract.MAX_OFFSET + limit
        probe = await self.get_page(method, offset=0, limit=limit)
        _probe_items, probe_total = parser.parse_list_page(probe)
        if probe_total is not None and probe_total > window:
            return await self._iter_by_category(
                method,
                expected_total=probe_total,
                on_progress=on_progress,
            )
        return await self._walk(method, on_progress=on_progress)

    async def _iter_by_category(
        self,
        method: str,
        *,
        expected_total: int,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        categories = (
            contract.FREE_CATEGORIES
            if method == contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS
            else contract.PURCHASED_CATEGORIES
        )
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        slices: list[dict[str, Any]] = []
        for category in (*categories, None):
            label = " category=null" if category is None else f" category={category}"
            part, envs, integrity = await self._walk(
                method,
                category=category,
                category_is_null=category is None,
                on_progress=on_progress,
                label=label,
                reject_over_window=True,
            )
            items.extend(part)
            envelopes.extend(envs)
            slices.append(integrity)
        if len(items) != expected_total:
            raise ProviderError(
                f"Novofon {method} category merge fetched {len(items)} "
                f"of total_items={expected_total}",
                code="NOVOFON_PAGINATION_TRUNCATED",
                details={
                    "method": method,
                    "fetched": len(items),
                    "total_items": expected_total,
                    "slices": slices,
                },
            )
        return (
            items,
            envelopes,
            {
                "method": method,
                "fetched": len(items),
                "total_items": expected_total,
                "stop_reason": "category_partition",
                "stopped_at_max_offset": False,
                "total_items_mismatch": False,
                "partitioned": True,
                "slices": slices,
            },
        )
