"""
File: historical_baseline_owner_vector.py
Description: 以明確 owner read port 組合歷史訂單 11 步根事實並回傳可修復投影。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_CATALOG_VERSION,
    HISTORICAL_BASELINE_CATALOG_VERSION_V2,
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRepairReferralV2,
    HistoricalBaselineOwnerRootCollection,
    HistoricalBaselineOwnerRoot,
    HistoricalBaselineOwnerRootContract,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOperationalBaselineError,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    build_historical_baseline_owner_root_vector_v2,
    historical_baseline_owner_binding_fingerprint_v2,
    historical_baseline_owner_repair_referrals_v2,
    project_earliest_invalidated_root_v2,
    historical_baseline_owner_binding_fingerprint,
    project_earliest_invalidated_root,
    validate_historical_baseline_owner_catalog,
    validate_historical_baseline_owner_catalog_v2,
)
from shared_kernel.fingerprints import PreviewFingerprint


_EXPECTED_OWNER_DOMAINS = frozenset(
    {"orders", "matching", "line", "contract_signing", "client_finance", "scheduling"}
)
_EXPECTED_OWNER_DOMAINS_V2 = frozenset(
    descriptor.owner_domain for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
)


def _materialize_port_items(
    ports: Mapping[str, object] | Iterable[tuple[str, object]],
    *,
    invalid_message: str,
) -> tuple[tuple[str, object], ...]:
    """Normalize mappings and pair iterables without weakening pair shape."""

    if isinstance(ports, Mapping):
        return tuple(ports.items())
    try:
        raw_items = tuple(ports)
    except TypeError as error:
        raise TypeError(invalid_message) from error
    items: list[tuple[str, object]] = []
    for raw_item in raw_items:
        try:
            pair = tuple(raw_item)
        except TypeError as error:
            raise TypeError(invalid_message) from error
        if len(pair) != 2:
            raise TypeError(invalid_message)
        items.append((pair[0], pair[1]))  # type: ignore[arg-type]
    try:
        set(item[0] for item in items)
    except TypeError as error:
        raise TypeError(invalid_message) from error
    return tuple(items)


class HistoricalBaselineOwnerVectorError(ValueError):
    """Typed fail-closed error for the cross-owner read composition."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRootReadback:
    """Fresh root value paired with the complete order identity it read."""

    identity: HistoricalOrderIdentity
    root: HistoricalBaselineOwnerRoot | None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline owner root readback identity is invalid")


class HistoricalBaselineOwnerReadPort(Protocol):
    """One owner-domain read port; implementations must perform a fresh read only."""

    owner_domain: str

    def read_owner_root(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootContract,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerRootReadback: ...


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerObservationReadback:
    """Fresh order identity paired with one descriptor's typed observations."""

    identity: HistoricalOrderIdentity
    observations: tuple[HistoricalBaselineOwnerObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline v2 observation readback identity is invalid")
        if not isinstance(self.observations, tuple):
            raise TypeError("historical baseline v2 observation readback is invalid")


class HistoricalBaselineOwnerObservationReadPort(Protocol):
    """One owner port for a descriptor-scoped, fresh observation collection."""

    owner_domain: str

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback: ...


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerVectorQueryRequest:
    """Exact case/provenance identity used for one read-only vector query."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline owner vector identity is invalid")
        if not isinstance(
            self.historical_provenance, HistoricalOrderProvenanceIdentity
        ):
            raise TypeError("historical baseline owner vector provenance is invalid")
        if isinstance(self.catalog_version, bool) or not isinstance(
            self.catalog_version, int
        ):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_catalog_version_invalid"
            )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineRepairReferral:
    """Server-owned repair destination for one catalog descriptor."""

    step: int
    owner_domain: str
    root_identity_path: str
    repair_target: str
    repair_capability: str


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerVectorProjection:
    """Complete immutable projection returned by the read-only composition."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    catalog_version: int
    owner_root_vector: tuple[HistoricalBaselineOwnerRoot, ...]
    owner_binding_fingerprint: PreviewFingerprint
    current_step: int
    earliest_unavailable_step: int | None
    repair_referrals: tuple[HistoricalBaselineRepairReferral, ...]

    @property
    def fingerprint(self) -> PreviewFingerprint:
        """Compatibility name used by projections that call this the vector digest."""

        return self.owner_binding_fingerprint


class HistoricalBaselineOwnerVectorQuery:
    """Read each catalog descriptor exactly once through its owning port."""

    def __init__(
        self,
        *,
        orders: HistoricalBaselineOwnerReadPort,
        matching: HistoricalBaselineOwnerReadPort,
        contract_signing: HistoricalBaselineOwnerReadPort,
        client_finance: HistoricalBaselineOwnerReadPort,
        scheduling: HistoricalBaselineOwnerReadPort,
        staff_payables: HistoricalBaselineOwnerReadPort | None = None,
        line: HistoricalBaselineOwnerReadPort | None = None,
        catalog: tuple[HistoricalBaselineOwnerRootContract, ...]
        | list[HistoricalBaselineOwnerRootContract]
        | tuple[HistoricalBaselineOwnerRootDescriptor, ...]
        | list[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
        catalog_version: int | None = None,
    ) -> None:
        catalog_entries = tuple(catalog)
        catalog_is_v2 = bool(catalog_entries) and isinstance(
            catalog_entries[0], HistoricalBaselineOwnerRootDescriptor
        )
        effective_catalog_version = (
            HISTORICAL_BASELINE_CATALOG_VERSION_V2
            if catalog_is_v2 and catalog_version is None
            else HISTORICAL_BASELINE_CATALOG_VERSION
            if catalog_version is None
            else catalog_version
        )
        if effective_catalog_version == HISTORICAL_BASELINE_CATALOG_VERSION_V2 or catalog_is_v2:
            if staff_payables is None:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_port_missing"
                )
            self._v2_delegate = HistoricalBaselineOwnerVectorV2Query(
                orders=orders,
                matching=matching,
                contract_signing=contract_signing,
                client_finance=client_finance,
                scheduling=scheduling,
                staff_payables=staff_payables,
                line=line,
                catalog=catalog_entries,  # type: ignore[arg-type]
                catalog_version=effective_catalog_version,
            )
            return
        try:
            validated_catalog = validate_historical_baseline_owner_catalog(
                catalog_entries, catalog_version=effective_catalog_version
            )
        except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_catalog_invalid"
            ) from error
        if tuple(entry.canonical_tuple for entry in validated_catalog) != tuple(
            entry.canonical_tuple for entry in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG
        ):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_catalog_invalid"
            )
        self._catalog_version = effective_catalog_version
        self._catalog = validated_catalog
        if {entry.owner_domain for entry in self._catalog} != _EXPECTED_OWNER_DOMAINS:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_owner_catalog_invalid"
            )
        supplied = {
            "orders": orders,
            "matching": matching,
            "line": line,
            "contract_signing": contract_signing,
            "client_finance": client_finance,
            "scheduling": scheduling,
        }
        self._ports = self._validate_ports(supplied)

    @classmethod
    def from_ports(
        cls,
        ports: Mapping[str, HistoricalBaselineOwnerReadPort]
        | Iterable[tuple[str, HistoricalBaselineOwnerReadPort]],
        **kwargs: object,
    ) -> "HistoricalBaselineOwnerVectorQuery":
        """Construct from an explicit owner-keyed set, rejecting missing/extra keys."""

        items = _materialize_port_items(
            ports,
            invalid_message="historical baseline owner ports are invalid",
        )
        keys = tuple(key for key, _port in items)
        try:
            duplicate_keys = len(keys) != len(set(keys))
        except TypeError as error:
            raise TypeError("historical baseline owner ports are invalid") from error
        if duplicate_keys:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_duplicate"
            )
        requested_catalog = kwargs.get("catalog")
        requested_version = kwargs.get("catalog_version", HISTORICAL_BASELINE_CATALOG_VERSION)
        is_v2 = requested_version == HISTORICAL_BASELINE_CATALOG_VERSION_V2 or (
            isinstance(requested_catalog, (tuple, list))
            and bool(requested_catalog)
            and isinstance(requested_catalog[0], HistoricalBaselineOwnerRootDescriptor)
        ) or set(keys) == _EXPECTED_OWNER_DOMAINS_V2
        if is_v2:
            return HistoricalBaselineOwnerVectorV2Query.from_ports(  # type: ignore[return-value]
                items, **kwargs
            )

        expected = _EXPECTED_OWNER_DOMAINS
        supplied = set(keys)
        if supplied - expected:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_extra"
            )
        if expected - supplied:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_missing"
            )
        return cls(**dict(items), **kwargs)  # type: ignore[arg-type]

    from_bindings = from_ports

    @staticmethod
    def _validate_ports(
        ports: Mapping[str, object],
    ) -> dict[str, HistoricalBaselineOwnerReadPort]:
        if set(ports) != _EXPECTED_OWNER_DOMAINS:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_set_invalid"
            )
        result: dict[str, HistoricalBaselineOwnerReadPort] = {}
        for owner_domain, port in ports.items():
            reader = getattr(port, "read_owner_root", None)
            if not callable(reader):
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_{owner_domain}_port_invalid"
                )
            if getattr(port, "owner_domain", None) != owner_domain:
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_{owner_domain}_port_owner_invalid"
                )
            result[owner_domain] = port  # type: ignore[assignment]
        return result

    def query(
        self, request: HistoricalBaselineOwnerVectorQueryRequest
    ) -> HistoricalBaselineOwnerVectorProjection:
        """Perform no writes and bind all fresh reads to the exact request identity."""

        if hasattr(self, "_v2_delegate"):
            return self._v2_delegate.query(request)  # type: ignore[return-value]

        if not isinstance(request, HistoricalBaselineOwnerVectorQueryRequest):
            raise TypeError("historical baseline owner vector request is invalid")
        if request.catalog_version != self._catalog_version:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_catalog_version_mismatch"
            )
        roots: list[HistoricalBaselineOwnerRoot] = []
        seen_roots: set[tuple[str, int]] = set()
        for descriptor in self._catalog:
            port = self._ports.get(descriptor.owner_domain)
            if port is None:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_port_missing"
                )
            reader = getattr(port, "read_owner_root")
            try:
                root = reader(request.identity, descriptor, for_update=False)
            except Exception as error:
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_{descriptor.owner_domain}_read_failed"
                ) from error
            root_value = self._validate_root(root, request.identity, descriptor)
            root_key = (root_value.contract_id, root_value.contract_version)
            if root_key in seen_roots:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_root_duplicate"
                )
            seen_roots.add(root_key)
            roots.append(root_value)

        vector = tuple(roots)
        try:
            owner_binding_fingerprint = historical_baseline_owner_binding_fingerprint(
                request.identity,
                request.historical_provenance,
                vector,
                catalog=self._catalog,
                catalog_version=self._catalog_version,
            )
            earliest_issue = project_earliest_invalidated_root(
                vector, identity=request.identity
            )
        except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_projection_invalid"
            ) from error
        earliest_unavailable = next(
            (root.step for root in vector if not root.available), None
        )
        current_step = earliest_issue or self._catalog[-1].step
        referrals = tuple(
            HistoricalBaselineRepairReferral(
                step=descriptor.step,
                owner_domain=descriptor.owner_domain,
                root_identity_path=descriptor.root_identity_path,
                repair_target=descriptor.repair_target,
                repair_capability=descriptor.repair_capability,
            )
            for descriptor in self._catalog
        )
        return HistoricalBaselineOwnerVectorProjection(
            identity=request.identity,
            historical_provenance=request.historical_provenance,
            catalog_version=self._catalog_version,
            owner_root_vector=vector,
            owner_binding_fingerprint=owner_binding_fingerprint,
            current_step=current_step,
            earliest_unavailable_step=earliest_unavailable,
            repair_referrals=referrals,
        )

    execute = query

    @staticmethod
    def _validate_root(
        readback: object,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootContract,
    ) -> HistoricalBaselineOwnerRoot:
        if not isinstance(readback, HistoricalBaselineOwnerRootReadback):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_result_malformed"
            )
        if readback.identity.case_no != identity.case_no:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_cross_case"
            )
        if readback.identity != identity:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_identity_mismatch"
            )
        root = readback.root
        if root is None:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_result_unavailable"
            )
        if not isinstance(root, HistoricalBaselineOwnerRoot):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_port_result_malformed"
            )
        if root.case_no != identity.case_no:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_cross_case"
            )
        if root.contract.canonical_tuple != descriptor.canonical_tuple:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_unsupported_descriptor"
            )
        # A typed unavailable root is valid evidence of an unavailable owner and
        # is projected as such; it must still be the domain's complete typed value.
        if root.unavailable_reason is None and (
            root.root_identity is None
            or root.source_event_identity is None
            or root.source_version is None
            or root.terminal_result is None
        ):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_root_incomplete"
            )
        return root


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerVectorV2Projection:
    """Complete immutable v2 projection for the 21-descriptor catalog."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    catalog_version: int
    owner_observations: tuple[HistoricalBaselineOwnerObservation, ...]
    owner_collections: tuple[HistoricalBaselineOwnerRootCollection, ...]
    owner_binding_fingerprint: PreviewFingerprint
    current_step: int
    earliest_unavailable_step: int | None
    repair_referrals: tuple[HistoricalBaselineOwnerRepairReferralV2, ...]

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return self.owner_binding_fingerprint

    @property
    def observations(self) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        """Short alias for typed clients that call the vector observations."""

        return self.owner_observations

    @property
    def owner_root_vector(self) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        """Compatibility vocabulary for consumers migrating from v1."""

        return self.owner_observations

    @property
    def collections(self) -> tuple[HistoricalBaselineOwnerRootCollection, ...]:
        return self.owner_collections


class HistoricalBaselineOwnerVectorV2Query:
    """Compose every canonical v2 descriptor through its owning typed port."""

    def __init__(
        self,
        *,
        orders: HistoricalBaselineOwnerObservationReadPort,
        matching: HistoricalBaselineOwnerObservationReadPort,
        contract_signing: HistoricalBaselineOwnerObservationReadPort,
        client_finance: HistoricalBaselineOwnerObservationReadPort,
        scheduling: HistoricalBaselineOwnerObservationReadPort,
        staff_payables: HistoricalBaselineOwnerObservationReadPort,
        line: HistoricalBaselineOwnerObservationReadPort | None = None,
        catalog: tuple[HistoricalBaselineOwnerRootDescriptor, ...]
        | list[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
        catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2,
    ) -> None:
        # ``line`` remains an explicit v1 port in the public constructor.  The
        # adopted v2 source map has no LINE-owned root; accepting a supplied
        # line port would conceal ownership drift, so reject it at the seam.
        if line is not None:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_line_owner_unsupported"
            )
        try:
            validated = validate_historical_baseline_owner_catalog_v2(
                catalog, catalog_version=catalog_version
            )
        except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_catalog_invalid"
            ) from error
        self._catalog_version = catalog_version
        self._catalog = validated
        self._ports = self._validate_ports(
            {
                "orders": orders,
                "matching": matching,
                "contract_signing": contract_signing,
                "client_finance": client_finance,
                "scheduling": scheduling,
                "staff_payables": staff_payables,
            }
        )

    @classmethod
    def from_ports(
        cls,
        ports: Mapping[str, HistoricalBaselineOwnerObservationReadPort]
        | Iterable[tuple[str, HistoricalBaselineOwnerObservationReadPort]],
        **kwargs: object,
    ) -> "HistoricalBaselineOwnerVectorV2Query":
        """Construct from an exact owner-keyed set, rejecting missing/extra ports."""

        items = _materialize_port_items(
            ports,
            invalid_message="historical baseline v2 owner ports are invalid",
        )
        keys = tuple(key for key, _port in items)
        try:
            duplicate_keys = len(keys) != len(set(keys))
        except TypeError as error:
            raise TypeError("historical baseline v2 owner ports are invalid") from error
        if duplicate_keys:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_port_duplicate"
            )
        supplied = set(keys)
        if supplied - _EXPECTED_OWNER_DOMAINS_V2:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_port_extra"
            )
        if _EXPECTED_OWNER_DOMAINS_V2 - supplied:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_port_missing"
            )
        return cls(**dict(items), **kwargs)  # type: ignore[arg-type]

    from_bindings = from_ports

    @staticmethod
    def _validate_ports(
        ports: Mapping[str, object],
    ) -> dict[str, HistoricalBaselineOwnerObservationReadPort]:
        if set(ports) != _EXPECTED_OWNER_DOMAINS_V2:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_port_set_invalid"
            )
        result: dict[str, HistoricalBaselineOwnerObservationReadPort] = {}
        for owner_domain, port in ports.items():
            reader = getattr(port, "read_owner_observations", None)
            if not callable(reader):
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_v2_{owner_domain}_port_invalid"
                )
            if getattr(port, "owner_domain", None) != owner_domain:
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_v2_{owner_domain}_port_owner_invalid"
                )
            result[owner_domain] = port  # type: ignore[assignment]
        return result

    def query(
        self,
        request: HistoricalBaselineOwnerVectorV2QueryRequest,
    ) -> HistoricalBaselineOwnerVectorV2Projection:
        if not isinstance(request, HistoricalBaselineOwnerVectorV2QueryRequest):
            raise TypeError("historical baseline v2 owner vector request is invalid")
        if request.catalog_version != self._catalog_version:
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_catalog_version_mismatch"
            )
        observations: list[HistoricalBaselineOwnerObservation] = []
        collections: list[HistoricalBaselineOwnerRootCollection] = []
        for descriptor in self._catalog:
            port = self._ports.get(descriptor.owner_domain)
            if port is None:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_port_missing"
                )
            try:
                readback = port.read_owner_observations(
                    request.identity, descriptor, for_update=request.for_update
                )
            except Exception as error:
                raise HistoricalBaselineOwnerVectorError(
                    f"historical_baseline_owner_vector_v2_{descriptor.owner_domain}_read_failed"
                ) from error
            if not isinstance(readback, HistoricalBaselineOwnerObservationReadback):
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_result_malformed"
                )
            if readback.identity.case_no != request.identity.case_no:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_cross_case"
                )
            if readback.identity != request.identity:
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_identity_mismatch"
                )
            if any(
                not isinstance(item, HistoricalBaselineOwnerObservation)
                for item in readback.observations
            ):
                raise HistoricalBaselineOwnerVectorError(
                    "historical_baseline_owner_vector_v2_observation_malformed"
                )
            try:
                ordered_observations = tuple(
                    sorted(
                        readback.observations,
                        key=lambda item: item.canonical_order_key,
                    )
                )
                collection = HistoricalBaselineOwnerRootCollection(
                    descriptor, ordered_observations
                )
                collections.append(collection)
                observations.extend(collection.observations)
            except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
                raise self._translate_domain_error(error) from error

        try:
            vector = build_historical_baseline_owner_root_vector_v2(
                observations,
                identity=request.identity,
                catalog=self._catalog,
                catalog_version=self._catalog_version,
            )
            fingerprint = historical_baseline_owner_binding_fingerprint_v2(
                request.identity,
                request.historical_provenance,
                vector,
                catalog=self._catalog,
                catalog_version=self._catalog_version,
            )
            earliest_issue = project_earliest_invalidated_root_v2(
                vector,
                identity=request.identity,
                catalog=self._catalog,
                catalog_version=self._catalog_version,
            )
            referrals = historical_baseline_owner_repair_referrals_v2(self._catalog)
        except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
            raise self._translate_domain_error(error) from error
        earliest_unavailable = next(
            (
                observation.descriptor.step
                for observation in vector
                if not observation.available
            ),
            None,
        )
        return HistoricalBaselineOwnerVectorV2Projection(
            identity=request.identity,
            historical_provenance=request.historical_provenance,
            catalog_version=self._catalog_version,
            owner_observations=vector,
            owner_collections=tuple(collections),
            owner_binding_fingerprint=fingerprint,
            current_step=earliest_issue or max(
                descriptor.step for descriptor in self._catalog
            ),
            earliest_unavailable_step=earliest_unavailable,
            repair_referrals=referrals,
        )

    execute = query

    @staticmethod
    def _translate_domain_error(error: Exception) -> HistoricalBaselineOwnerVectorError:
        code = getattr(error, "code", None)
        if isinstance(code, str):
            return HistoricalBaselineOwnerVectorError(
                f"historical_baseline_owner_vector_v2_{code}"
            )
        return HistoricalBaselineOwnerVectorError(
            "historical_baseline_owner_vector_v2_projection_invalid"
        )


# Naming variants keep the v2 boundary discoverable without changing v1
# persisted-history classes or their constructor contracts.
HistoricalBaselineOwnerVectorQueryV2 = HistoricalBaselineOwnerVectorV2Query


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerVectorV2QueryRequest:
    """Exact identity and server-selected lock mode used for one v2 read."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2
    for_update: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline v2 owner vector identity is invalid")
        if not isinstance(
            self.historical_provenance, HistoricalOrderProvenanceIdentity
        ):
            raise TypeError("historical baseline v2 owner vector provenance is invalid")
        if isinstance(self.catalog_version, bool) or not isinstance(
            self.catalog_version, int
        ):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_catalog_version_invalid"
            )
        if not isinstance(self.for_update, bool):
            raise HistoricalBaselineOwnerVectorError(
                "historical_baseline_owner_vector_v2_read_mode_invalid"
            )


HistoricalBaselineOwnerVectorQueryRequestV2 = HistoricalBaselineOwnerVectorV2QueryRequest
HistoricalBaselineOwnerObservationReadbackV2 = HistoricalBaselineOwnerObservationReadback


__all__ = [
    "HistoricalBaselineOwnerReadPort",
    "HistoricalBaselineOwnerRootReadback",
    "HistoricalBaselineOwnerObservationReadPort",
    "HistoricalBaselineOwnerObservationReadback",
    "HistoricalBaselineOwnerObservationReadbackV2",
    "HistoricalBaselineOwnerVectorError",
    "HistoricalBaselineOwnerVectorProjection",
    "HistoricalBaselineOwnerVectorQuery",
    "HistoricalBaselineOwnerVectorQueryRequest",
    "HistoricalBaselineOwnerVectorV2Projection",
    "HistoricalBaselineOwnerVectorV2Query",
    "HistoricalBaselineOwnerVectorQueryV2",
    "HistoricalBaselineOwnerVectorV2QueryRequest",
    "HistoricalBaselineOwnerVectorQueryRequestV2",
    "HistoricalBaselineRepairReferral",
]
