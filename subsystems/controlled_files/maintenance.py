"""The declared management consumer of governed staging cleanup and observations."""
from dataclasses import asdict
from datetime import timedelta
import hashlib

from shared_kernel.identities import IdempotencyKey
from subsystems.controlled_files.cleanup import ControlledFileCleanupWorkflow
from subsystems.controlled_files.gc import ControlledFileStagingGarbageCollector, GarbageCollectControlledFileStaging
from subsystems.controlled_files.reconciliation import ControlledFileReconciler


class ControlledFileMaintenanceApplication:
    def __init__(self, repository, storage, unit_of_work_factory, clock):
        self.repository, self.storage, self.clock = repository, storage, clock
        self.cleanup_workflow = ControlledFileCleanupWorkflow(repository, storage, unit_of_work_factory, clock)
        self.reconciler = ControlledFileReconciler(repository, storage, unit_of_work_factory, clock)
        self.collector = ControlledFileStagingGarbageCollector(repository, self.cleanup_workflow, clock)

    def preview_cleanup(self, *, actor, correlation_id, limit=100):
        # The optional Preview is read-only. Apply independently locks current facts.
        result = self.collector.run(GarbageCollectControlledFileStaging(
            IdempotencyKey("controlled-file.preview:" + hashlib.sha256(correlation_id.value.encode()).hexdigest()), actor, correlation_id,
            limit=limit, grace_period=timedelta(0), dry_run=True,
        ))
        return asdict(result)

    def cleanup(self, command):
        receipt = self.cleanup_workflow.cleanup(command)
        return {"receipt": asdict(receipt), "deleted_set": [receipt.staging_id], "skipped_set": [],
                "readiness": asdict(self.storage.readiness())}

    def list_reconciliation(self, *, limit=100):
        return [{"file_id": row.file_id, "owner": row.owner.value, "purpose": row.purpose.value,
                 "version": row.version, "sha256_digest": row.sha256_digest}
                for row in self.repository.list_readbacks(limit=limit)]

    def reconcile(self, file_id, *, actor, correlation_id, apply=False):
        operation = self.reconciler.reconcile_registered if apply else self.reconciler.preview_registered
        event = operation(file_id, actor=actor, correlation_id=correlation_id)
        references = self.repository.reconciliation_reference_status(file_id)
        # A storage observation is never promoted to a four-world success when
        # an owning business/frozen outbound reference cannot be read.
        complete = event.outcome.value == "exact" and all(value in {"matched", "not_applicable"} for value in references.values())
        return {"event_id": event.event_id, "file_id": event.file_id, "staging_id": event.staging_id,
                "storage_outcome": event.outcome.value, "observed_sha256": event.observed_sha256,
                "observed_size_bytes": event.observed_size_bytes, "references": references,
                "complete": complete, "status": "exact" if complete else "review_required"}
