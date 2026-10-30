"""
File: accounting_pricing.py
Description: 組合單一帳務計價交易連線，並提供唯讀計價目錄之選用 Redis 與記憶體快取。
"""

from __future__ import annotations

import inspect
import logging
from threading import RLock

from fastapi import Request

from api.schemas.accounting_pricing import PricingCatalogView
from infrastructure.cache import default_redis_cache_backend
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.performance import CacheKeyParts, build_cache_key
from shared_kernel.ttl_cache import TtlProjectionCache
from subsystems.client_finance.pricing_configuration import PricingConfigurationApplication


LOGGER = logging.getLogger("labor_union.api.accounting_pricing")

_pricing_catalog_cache = TtlProjectionCache[PricingCatalogView](
    ttl_seconds=60,
    serialize=lambda view: view.model_dump_json(),
    deserialize=PricingCatalogView.model_validate_json,
    backend_provider=default_redis_cache_backend,
)
_catalog_key_lock = RLock()
_known_catalog_keys: set[str] = set()


def _current_catalog_cache_key() -> str:
    host = str(DB_CONFIG.get("host", "127.0.0.1") or "127.0.0.1")
    port = str(DB_CONFIG.get("port", 3306) or 3306)
    database = str(DB_CONFIG.get("database", "union_db") or "union_db")
    return build_cache_key(
        CacheKeyParts(
            namespace="client-finance.pricing-catalog",
            resource_identity=f"{host}:{port}/{database}:catalog",
            permission_scope=("system.administration",),
            facts_version=0,
            contract_version="v1",
            time_zone="Asia/Taipei",
        )
    )


def _load_catalog_view_from_mysql() -> PricingCatalogView:
    connection = get_connection()
    try:
        catalog = MySqlPricingConfigurationRepository(connection).catalog(lock=False)
        return PricingCatalogView.model_validate(catalog)
    finally:
        connection.close()


def query_cached_pricing_catalog_view(request: Request) -> PricingCatalogView:
    override = request.app.dependency_overrides.get(get_pricing_application)
    if override is not None:
        resolved = override()
        if inspect.isgenerator(resolved):
            try:
                application = next(resolved)
                return PricingCatalogView.model_validate(application.catalog())
            finally:
                resolved.close()
        return PricingCatalogView.model_validate(resolved.catalog())

    key = _current_catalog_cache_key()
    with _catalog_key_lock:
        _known_catalog_keys.add(key)
    return _pricing_catalog_cache.get_or_load(key, _load_catalog_view_from_mysql)


def invalidate_pricing_catalog_cache() -> None:
    current_key = _current_catalog_cache_key()
    with _catalog_key_lock:
        keys = tuple(_known_catalog_keys | {current_key})
        _known_catalog_keys.clear()
    _pricing_catalog_cache.invalidate_many(keys)


def pricing_catalog_cache_telemetry():
    return _pricing_catalog_cache.telemetry()


def get_pricing_application():
    connection = get_connection()
    try:
        yield PricingConfigurationApplication(
            MySqlPricingConfigurationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
    finally:
        connection.close()
