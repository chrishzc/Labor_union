"""Google Routes transport; no response content, addresses or credentials are logged."""
from __future__ import annotations

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from subsystems.scheduling.commute_query import RouteResult


class GoogleRoutesProvider:
    def __init__(self, api_key: str | None = None, opener=None):
        self._key = (os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY", "") if api_key is None else api_key).strip()
        self._open = opener or urlopen

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def compute(self, origin: str, destination: str) -> RouteResult:
        request = Request("https://routes.googleapis.com/directions/v2:computeRoutes",
            data=json.dumps({"origin": {"address": origin}, "destination": {"address": destination},
                "travelMode": "TWO_WHEELER", "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
                "computeAlternativeRoutes": False,
                "languageCode": "zh-TW", "regionCode": "TW"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": self._key,
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"}, method="POST")
        try:
            with self._open(request, timeout=15) as response:
                raw = response.read(65537)
        except HTTPError as error:
            # Some 4xx statuses can be billable. Do not treat all failures as free.
            billing = "not_billable" if error.code in (401, 403, 429) or error.code >= 500 else "unknown"
            error.close()
            return RouteResult("failed", billing, message="Google 路線查詢失敗，請確認 API 設定或稍後手動查詢。")
        except (URLError, OSError, TimeoutError, ValueError):
            return RouteResult("unknown", "unknown", message="連線失敗或逾時，是否計費待確認；系統不會自動重試。")
        try:
            if len(raw) > 65536:
                raise ValueError()
            payload = json.loads(raw)
            routes = payload.get("routes", [])
            if routes == []:
                return RouteResult("no_route", "billable", message="找不到可用的機車路線。")
            route = routes[0]
            # ProtoJSON omits default scalar values, including distanceMeters=0,
            # even when the field is explicitly requested in the field mask.
            distance = route.get("distanceMeters", 0)
            raw_duration = route["duration"]
            if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0 or not raw_duration.endswith("s"):
                raise ValueError()
            duration = float(raw_duration[:-1])
            if not math.isfinite(duration) or duration < 0:
                raise ValueError()
            message = "Google 返回零距離，請核對起訖地址是否完整，或是否定位到同一地點。" if distance == 0 else ""
            return RouteResult("ready", "billable", distance, duration, message)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return RouteResult("failed", "billable", message="Google 已回應，但路線資料無法辨識。")
