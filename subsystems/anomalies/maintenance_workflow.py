"""Bounded maintenance orchestration for canonical anomaly projection."""

from domains.anomalies.maintenance import ScanAnomalyDefinitionResult, RetryAnomalyProjectorResult


class AnomalyMaintenanceError(Exception):
    pass


class AnomalyMaintenanceApplication:
    def __init__(self, registry, scan_port, retry_port, projector, unit_of_work_factory):
        self._registry = registry
        self._scan_port = scan_port
        self._retry_port = retry_port
        self._projector = projector
        self._unit_of_work_factory = unit_of_work_factory

    def scan_definition(self, request, correlation_id):
        try:
            self._registry.require(request.definition_code)
            page = self._scan_port.scan_definition(request)
            receipts = tuple(self._projector.project(item, correlation_id) for item in page.root_facts)
            return ScanAnomalyDefinitionResult(request.definition_code, len(receipts), sum(item.predicate_active for item in receipts), sum(not item.predicate_active for item in receipts), page.next_after_source_id)
        except Exception as error:
            if error.__class__.__name__.endswith("Error"):
                raise
            raise AnomalyMaintenanceError(str(error)) from error

    def retry_projector(self, request, correlation_id):
        del correlation_id
        try:
            with self._unit_of_work_factory() as unit_of_work:
                event_ids = tuple(self._retry_port.requeue_failed_projector_events(request.maximum_events))
                unit_of_work.commit()
            return RetryAnomalyProjectorResult("anomaly-root-fact-projector-v1", event_ids)
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error
