import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import Any
import httpx

from src.core.config import Settings, get_settings
from src.core.exceptions import InvalidParamsError, NotFoundError
from src.core.logging import current_millis, log_context
from src.integrations.overseas_adapter import adapt_device_detail

logger = logging.getLogger(__name__)

# 蓝牙名称格式：AA 开头，共 10 个大写字母/数字（例如 AA250862SE）
_BLUETOOTH_NAME_RE = re.compile(r"^AA[A-Z0-9]{8}$", re.IGNORECASE)
_AdaptedData = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any | None = None
    error: Exception | None = None


def is_bluetooth_name(term: str) -> bool:
    """判断是否为蓝牙名称（AA 开头）"""
    return term.upper().startswith("AA")


def validate_bluetooth_name(name: str) -> str:
    """
    校验蓝牙名称格式并返回大写形式。
    蓝牙名称必须是完整的 10 位字母数字（AA + 8位），不支持模糊查询。
    如不合法，抛出 InvalidParamsError 提示用户传入完整蓝牙名称。
    """
    upper = name.strip().upper()
    if not _BLUETOOTH_NAME_RE.match(upper):
        raise InvalidParamsError(
            f"Bluetooth name '{name}' is invalid. "
            "Please provide a complete Bluetooth name (e.g. AA250862SE). "
            "Fuzzy search by Bluetooth name is not supported."
        )
    return upper


class OverseasCGMClient:
    """
    海外 CGM 设备数据客户端。
    通过登录获取 access_token，然后调用 deviceDetail 接口获取设备详情。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Token 缓存
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        # 设备数据缓存 (SN -> adapted data tuple)
        self._cache: dict[str, _CacheEntry] = {}
        # deviceName 查询结果缓存 (deviceName -> adapted data tuple list)
        self._name_cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        self._inflight_lock = asyncio.Lock()
        # HTTP client for connection reuse
        self._http_client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            async with self._client_lock:
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient(
                        timeout=self.settings.overseas_api_request_timeout_seconds
                    )
        return self._http_client

    async def close(self) -> None:
        async with self._client_lock:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None

    # ── Public API ───────────────────────────────────────────────

    async def get_device(self, serial_no: str) -> dict[str, Any] | list[dict[str, Any]]:
        """
        获取设备基础信息（已适配为规则引擎所需格式）。

        - 传入 SN（非 AA 开头）：返回单个 dict。
        - 传入蓝牙名称（AA 开头）：校验格式后查询，返回 list[dict]（可能对应多台设备）。
        """
        term = serial_no.strip().upper()
        if is_bluetooth_name(term):
            validated = validate_bluetooth_name(term)
            res_list = await self._get_adapted_data_by_device_name(validated)
            return [res[0] for res in res_list]
        res = await self._get_adapted_data(term)
        return res[0]

    async def get_glucose_series(self, serial_no: str) -> dict[str, Any]:
        """获取血糖序列数据（已适配为规则引擎所需格式）"""
        res = await self._get_adapted_data(serial_no)
        return res[1]

    async def get_latest_alarm(self, serial_no: str) -> dict[str, Any]:
        """获取最新告警数据（已适配为规则引擎所需格式）"""
        res = await self._get_adapted_data(serial_no)
        return res[2]

    async def search_devices(self, keyword: str) -> list[dict[str, Any]]:
        """
        按关键词搜索设备。
        - 蓝牙名称（AA 开头）：校验格式后查询，返回可能多台设备。
        - SN：精确查询，返回单台设备。
        """
        term = keyword.strip().upper()
        if not term:
            return []
        try:
            result = await self.get_device(term)
            # get_device 对蓝牙名称返回 list，对 SN 返回 dict
            if isinstance(result, list):
                return result
            return [result]
        except (InvalidParamsError, NotFoundError, Exception) as exc:
            logger.error(
                "Overseas device search failed",
                extra=log_context(
                    "overseas.device_search_failed",
                    serial_no=term,
                    error_type=type(exc).__name__,
                ),
            )
            return []

    async def search_device_terms(self, terms: list[str]) -> list[dict[str, Any]]:
        """
        批量搜索设备，支持 SN 和蓝牙名称混合传入。
        蓝牙名称必须完整（不支持模糊查询），一个蓝牙名称可能对应多台设备。
        结果按 SN 去重。
        """
        unique_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in terms:
            t = term.strip().upper()
            if not t or t in seen_terms:
                continue
            seen_terms.add(t)
            unique_terms.append(t)

        sem = asyncio.Semaphore(self._search_concurrency())

        async def sem_get_device(t: str):
            async with sem:
                return await self.get_device(t)

        tasks = [sem_get_device(t) for t in unique_terms]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[dict[str, Any]] = []
        seen_sns: set[str] = set()
        for term, res in zip(unique_terms, raw_results):
            if isinstance(res, Exception):
                logger.error(
                    "Overseas device term search failed",
                    extra=log_context(
                        "overseas.device_term_failed",
                        term=term,
                        error_type=type(res).__name__,
                        error=str(res),
                    ),
                )
            else:
                # get_device 对蓝牙名称返回 list，对 SN 返回 dict
                devices = res if isinstance(res, list) else [res]
                for device in devices:
                    sn = device.get("sn", "").upper()
                    if sn and sn not in seen_sns:
                        seen_sns.add(sn)
                        results.append(device)
        return results

    async def batch_get_devices(self, serial_nos: list[str]) -> list[dict[str, Any]]:
        """
        批量获取设备信息，支持 SN 和蓝牙名称混合传入。
        蓝牙名称必须完整（不支持模糊查询），一个蓝牙名称可能对应多台设备。
        结果按 SN 去重。
        """
        sem = asyncio.Semaphore(self._search_concurrency())

        async def sem_get_device(sn: str):
            async with sem:
                return await self.get_device(sn)

        tasks = [sem_get_device(sn) for sn in serial_nos]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[dict[str, Any]] = []
        seen_sns: set[str] = set()
        for sn, res in zip(serial_nos, raw_results):
            if isinstance(res, Exception):
                logger.error(
                    "Overseas batch device fetch failed",
                    extra=log_context(
                        "overseas.batch_device_failed",
                        serial_no=sn,
                        error_type=type(res).__name__,
                        error=str(res),
                    ),
                )
            else:
                # get_device 对蓝牙名称返回 list，对 SN 返回 dict
                devices = res if isinstance(res, list) else [res]
                for device in devices:
                    device_sn = device.get("sn", "").upper()
                    if device_sn and device_sn not in seen_sns:
                        seen_sns.add(device_sn)
                        results.append(device)
        return results

    # ── Internal: Adapted Data Layer ─────────────────────────────

    async def _get_adapted_data(self, serial_no: str) -> _AdaptedData:
        sn_key = serial_no.strip().upper()
        cached = await self._get_cached(self._cache, sn_key)
        if cached is not None:
            logger.info(
                "Overseas adapted device cache hit",
                extra=log_context("overseas.cache_hit", serial_no=sn_key),
            )
            return cached

        async def load() -> _AdaptedData:
            cached_inner = await self._get_cached(self._cache, sn_key)
            if cached_inner is not None:
                return cached_inner
            adapted = await self._load_adapted_data_uncached(sn_key)
            await self._store_cache_value(self._cache, sn_key, adapted)
            return adapted

        logger.info(
            "Overseas adapted device cache miss",
            extra=log_context("overseas.cache_miss", serial_no=sn_key),
        )
        try:
            return await self._run_once(f"device:{sn_key}", load)
        except NotFoundError as exc:
            await self._store_cache_error(self._cache, sn_key, exc)
            raise

    async def _get_adapted_data_by_device_name(
        self, device_name: str
    ) -> list[_AdaptedData]:
        """
        按蓝牙名称（deviceName）查询设备，返回匹配的所有设备的适配数据列表。
        每个元素与 _get_adapted_data 返回格式相同：(device, glucose_series, alarm)。
        结果按 SN 缓存到 self._cache。
        """
        cached = await self._get_cached(self._name_cache, device_name)
        if cached is not None:
            logger.info(
                "Overseas deviceName cache hit",
                extra=log_context(
                    "overseas.device_name_cache_hit", device_name=device_name
                ),
            )
            return cached

        async def load() -> list[_AdaptedData]:
            cached_inner = await self._get_cached(self._name_cache, device_name)
            if cached_inner is not None:
                return cached_inner
            adapted = await self._load_adapted_data_by_device_name_uncached(device_name)
            await self._store_cache_value(self._name_cache, device_name, adapted)
            return adapted

        logger.info(
            "Overseas device detail by device name started",
            extra=log_context(
                "overseas.device_detail_by_name_started", device_name=device_name
            ),
        )
        try:
            return await self._run_once(f"device_name:{device_name}", load)
        except NotFoundError as exc:
            await self._store_cache_error(self._name_cache, device_name, exc)
            raise

    def clear_cache(self, serial_no: str | None = None) -> None:
        """清除缓存。传入 SN 清除单条，否则清除全部"""
        if serial_no:
            key = serial_no.strip().upper()
            self._cache.pop(key, None)
            self._name_cache.pop(key, None)
        else:
            self._cache.clear()
            self._name_cache.clear()

    def _search_concurrency(self) -> int:
        return max(1, int(self.settings.overseas_api_search_concurrency))

    def _success_ttl(self) -> float:
        return max(0.0, float(self.settings.overseas_api_cache_ttl_seconds))

    def _negative_ttl(self) -> float:
        return max(0.0, float(self.settings.overseas_api_negative_cache_ttl_seconds))

    async def _get_cached(self, cache: dict[str, _CacheEntry], key: str) -> Any | None:
        async with self._cache_lock:
            entry = cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                cache.pop(key, None)
                return None
            if entry.error is not None:
                raise entry.error
            return entry.value

    async def _store_cache_value(
        self, cache: dict[str, _CacheEntry], key: str, value: Any
    ) -> None:
        ttl = self._success_ttl()
        if ttl <= 0:
            return
        async with self._cache_lock:
            cache[key] = _CacheEntry(expires_at=time.monotonic() + ttl, value=value)

    async def _store_cache_error(
        self, cache: dict[str, _CacheEntry], key: str, error: Exception
    ) -> None:
        ttl = self._negative_ttl()
        if ttl <= 0:
            return
        async with self._cache_lock:
            cache[key] = _CacheEntry(expires_at=time.monotonic() + ttl, error=error)

    async def _run_once(self, key: str, factory) -> Any:
        async with self._inflight_lock:
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(factory())
                self._inflight[key] = task
                owner = True
            else:
                owner = False
        try:
            return await task
        finally:
            if owner:
                async with self._inflight_lock:
                    if self._inflight.get(key) is task:
                        self._inflight.pop(key, None)

    async def _load_adapted_data_uncached(self, sn_key: str) -> _AdaptedData:
        try:
            raw_detail = await self._fetch_device_detail(sn_key)
            return adapt_device_detail(raw_detail, sn_key, self.settings)
        except Exception as exc:
            # Fallback to MockCGMClient
            logger.warning(
                "Fetch device detail from overseas API failed, trying fallback to MockCGMClient",
                extra=log_context(
                    "overseas.fallback_to_mock", serial_no=sn_key, error=str(exc)
                ),
            )
            try:
                from datetime import datetime
                from src.integrations.mock_cgm import MockCGMClient

                mock_client = MockCGMClient()

                device = await mock_client.get_device(sn_key)
                glucose = await mock_client.get_glucose_series(sn_key)
                alarm = await mock_client.get_latest_alarm(sn_key)

                # Format timestamps to string to keep it consistent with adapt_device_detail
                adapted_glucose = {
                    "points": [
                        {
                            "glucose": p["glucose"],
                            "timestamp": p["timestamp"].isoformat()
                            if isinstance(p["timestamp"], datetime)
                            else str(p["timestamp"]),
                            "alarm_status": p["alarm_status"],
                            "effective": p.get("effective", True),
                        }
                        for p in glucose.get("points", [])
                    ],
                    "timezone": glucose.get("timezone", "UTC"),
                }

                adapted_alarm = {
                    "latest_alarm_status": alarm["latest_alarm_status"],
                    "abnormal_duration_minutes": alarm["abnormal_duration_minutes"],
                    "latest_sensor_alert": alarm["abnormal_started_at"].isoformat()
                    if isinstance(alarm["abnormal_started_at"], datetime)
                    else str(alarm["abnormal_started_at"]),
                }

                return (device, adapted_glucose, adapted_alarm)
            except Exception as mock_exc:
                logger.error(
                    "Mock fallback failed as well",
                    extra=log_context(
                        "overseas.mock_fallback_failed",
                        serial_no=sn_key,
                        error=str(mock_exc),
                    ),
                )
                raise exc

    async def _load_adapted_data_by_device_name_uncached(
        self, device_name: str
    ) -> list[_AdaptedData]:
        try:
            raw_list = await self._fetch_device_detail_by_name(device_name)
        except Exception as exc:
            # Fallback: 用 Mock 按 deviceName 匹配
            logger.warning(
                "Fetch device detail by deviceName failed, trying fallback to MockCGMClient",
                extra=log_context(
                    "overseas.fallback_to_mock_by_name",
                    device_name=device_name,
                    error=str(exc),
                ),
            )
            try:
                from src.integrations.mock_cgm import MockCGMClient

                mock_client = MockCGMClient()
                return await mock_client.get_devices_by_name(device_name)
            except Exception as mock_exc:
                logger.error(
                    "Mock fallback by deviceName failed as well",
                    extra=log_context(
                        "overseas.mock_fallback_by_name_failed",
                        device_name=device_name,
                        error=str(mock_exc),
                    ),
                )
                raise exc

        results: list[_AdaptedData] = []
        for raw_detail in raw_list:
            # 海外 API 的 deviceDetail 接口（无论 sn 还是 deviceName 查询）响应体里
            # 都没有 serialNo/sn 字段。deviceName（蓝牙名称）本身就是设备标识，
            # 与硬件 SN 平级，用户可直接用它发起检测。
            sn = (raw_detail.get("deviceName") or device_name).strip().upper()
            if not sn:
                logger.error(
                    "Device detail by name returned entry with no usable deviceName, skipping",
                    extra=log_context(
                        "overseas.device_name_no_id", device_name=device_name
                    ),
                )
                continue

            cached = await self._get_cached(self._cache, sn)
            if cached is not None:
                results.append(cached)
                continue

            adapted = adapt_device_detail(raw_detail, sn, self.settings)
            await self._store_cache_value(self._cache, sn, adapted)
            results.append(adapted)

        if not results:
            raise NotFoundError(f"Device '{device_name}' not found")
        return results

    async def _clear_token(self) -> None:
        async with self._token_lock:
            self._token = None
            self._token_expires_at = 0.0

    # ── Internal: Login & Token ──────────────────────────────────

    async def _ensure_token(self) -> str:
        """确保有有效的 access_token，过期则重新登录"""
        async with self._token_lock:
            # Token 还有效（预留 60 秒缓冲）
            if self._token and time.time() < (self._token_expires_at - 60):
                return self._token

            started = time.perf_counter()
            logger.info(
                "Overseas login started",
                extra=log_context(
                    "overseas.login_started",
                    endpoint_configured=bool(self.settings.overseas_api_login_url),
                    username_configured=bool(self.settings.overseas_api_username),
                ),
            )
            login_url = self.settings.overseas_api_login_url
            payload = {
                "username": self.settings.overseas_api_username,
                "password": self.settings.overseas_api_password,
            }

            http_client = await self._get_http_client()
            resp = await http_client.post(login_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 200 or not data.get("data"):
                raise RuntimeError(
                    f"Overseas login failed: {data.get('msg', 'Unknown error')}"
                )

            token_data = data["data"]
            self._token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 1209600)  # 默认 14 天
            self._token_expires_at = time.time() + float(expires_in)
            logger.info(
                "Overseas login completed",
                extra=log_context(
                    "overseas.login_completed",
                    duration_ms=current_millis(started),
                    expires_in_seconds=expires_in,
                ),
            )
            return self._token

    # ── Internal: Device Detail Fetch ────────────────────────────

    async def _fetch_device_detail(self, serial_no: str) -> dict[str, Any]:
        """
        调用 deviceDetail 接口，以 SN 查询设备详情原始数据（单条）。
        认证方式: Authorization 请求头直接传入 access_token
        """
        base_url = self.settings.overseas_api_base_url
        detail_path = self.settings.overseas_api_device_detail_path
        url = f"{base_url}{detail_path}"
        params = {"sn": serial_no}
        started = time.perf_counter()

        logger.info(
            "Overseas device detail request started",
            extra=log_context(
                "overseas.device_detail_started",
                serial_no=serial_no,
                path=detail_path,
            ),
        )

        http_client = await self._get_http_client()
        try:
            detail_data, status_code = await self._request_device_detail_with_retry(
                http_client=http_client,
                url=url,
                params=params,
                query_key=serial_no,
            )
            logger.info(
                "Overseas device detail request completed",
                extra=log_context(
                    "overseas.device_detail_completed",
                    duration_ms=current_millis(started),
                    serial_no=serial_no,
                    status_code=status_code,
                ),
            )
            if not isinstance(detail_data, list):
                raise NotFoundError(
                    f"Device {serial_no} not found (unexpected data type: {type(detail_data).__name__})"
                )
            if not detail_data:
                raise NotFoundError(
                    f"Device {serial_no} not found (empty list returned)"
                )
            return detail_data[0]
        except NotFoundError:
            raise
        except Exception as exc:
            logger.exception(
                "Overseas device detail request failed",
                extra=log_context(
                    "overseas.device_detail_failed",
                    serial_no=serial_no,
                    error_type=type(exc).__name__,
                ),
            )
            raise

    async def _fetch_device_detail_by_name(
        self, device_name: str
    ) -> list[dict[str, Any]]:
        """
        调用 deviceDetail 接口，以蓝牙名称（deviceName）查询设备详情，返回列表。
        一个蓝牙名称可能对应多台设备。
        """
        base_url = self.settings.overseas_api_base_url
        detail_path = self.settings.overseas_api_device_detail_path
        url = f"{base_url}{detail_path}"
        params = {"deviceName": device_name}
        started = time.perf_counter()

        logger.info(
            "Overseas device detail by name request started",
            extra=log_context(
                "overseas.device_detail_by_name_started",
                device_name=device_name,
                path=detail_path,
            ),
        )

        http_client = await self._get_http_client()
        try:
            detail_data, status_code = await self._request_device_detail_with_retry(
                http_client=http_client,
                url=url,
                params=params,
                query_key=device_name,
            )
            logger.info(
                "Overseas device detail by name request completed",
                extra=log_context(
                    "overseas.device_detail_by_name_completed",
                    duration_ms=current_millis(started),
                    device_name=device_name,
                    status_code=status_code,
                    result_count=len(detail_data)
                    if isinstance(detail_data, list)
                    else 1,
                ),
            )
            # 接口可能返回单个 dict 或 list of dict
            if isinstance(detail_data, list):
                return detail_data
            return [detail_data]
        except NotFoundError:
            raise
        except Exception as exc:
            logger.exception(
                "Overseas device detail by name request failed",
                extra=log_context(
                    "overseas.device_detail_by_name_failed",
                    device_name=device_name,
                    error_type=type(exc).__name__,
                ),
            )
            raise

    async def _request_device_detail_with_retry(
        self,
        *,
        http_client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
        query_key: str,
    ) -> tuple[dict[str, Any] | list[dict[str, Any]], int]:
        """发送设备详情请求，含 token 失效自动刷新重试逻辑。
        data 字段允许为 dict（SN 查询）或 list（蓝牙名称查询）。
        """
        for attempt in range(2):
            resp, token_used = await self._send_device_detail_request(
                http_client=http_client, url=url, params=params
            )
            if self._is_token_expired_response(resp):
                logger.warning(
                    "Overseas token expired during device detail request",
                    extra=log_context(
                        "overseas.token_expired",
                        query_key=query_key,
                        attempt=attempt + 1,
                        status_code=resp.status_code,
                    ),
                )
                if attempt == 1:
                    resp.raise_for_status()
                    result = resp.json()
                    msg = result.get("msg", "Token expired")
                    raise RuntimeError(
                        f"Device '{query_key}' query failed after token refresh: {msg}"
                    )
                async with self._token_lock:
                    if self._token == token_used:
                        self._token = None
                        self._token_expires_at = 0.0
                continue
            resp.raise_for_status()
            result = resp.json()
            code = result.get("code")
            if code != 200:
                msg = result.get("msg", "Unknown error")
                raise NotFoundError(f"Device '{query_key}' query failed: {msg}")

            detail_data = result.get("data")
            if not detail_data:
                raise NotFoundError(f"Device '{query_key}' not found (empty data)")
            if not isinstance(detail_data, list):
                raise NotFoundError(
                    f"Device '{query_key}' not found (unexpected data type)"
                )
            return detail_data, resp.status_code
        raise RuntimeError(f"Device '{query_key}' query failed after token refresh.")

    async def _send_device_detail_request(
        self,
        *,
        http_client: httpx.AsyncClient,
        url: str,
        params: dict[str, str],
    ) -> tuple[httpx.Response, str]:
        token = await self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await http_client.get(url, params=params, headers=headers)
        return resp, token

    @staticmethod
    def _is_token_expired_response(resp: httpx.Response) -> bool:
        if resp.status_code == 401:
            return True
        try:
            payload = resp.json()
        except ValueError:
            return False
        return payload.get("code") == 401
