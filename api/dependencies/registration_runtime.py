"""Internal host lifecycle only. Public intake never imports the formal approval runtime."""
from contextlib import contextmanager
import logging
import os
from threading import Event, Thread


@contextmanager
def registration_maintenance_runtime():
    if not os.environ.get("REGISTRATION_REDIS_ADMIN_PASSWORD_FILE"):
        yield
        return
    from api.dependencies.registration_applications import get_registration_review_application, get_registration_staging_repository
    from api.dependencies.line_identity import get_line_identity_application
    from infrastructure.redis.registration_maintenance import RegistrationAofMaintenance
    from subsystems.case_import.registration_maintenance import RegistrationMaintenanceRunner
    from api.dependencies.line_runtime import publish_line_wakeup_best_effort
    # Startup is the only ASGI path that synchronizes SQL's issued high-water mark.
    # A missing/corrupt Redis counter never falls back to SQL-only reinitialization.
    stopped = Event()
    def maintain():
        runner = None
        while not stopped.is_set():
            try:
                if runner is None:
                    staging = get_registration_staging_repository()
                    staging.initialize(get_line_identity_application().registration_id_high_water())
                    runner = RegistrationMaintenanceRunner(staging, get_registration_review_application(), RegistrationAofMaintenance(staging),
                        after_recovery=publish_line_wakeup_best_effort)
                if not runner.tick():
                    logging.getLogger(__name__).error("registration_maintenance_incomplete")
            except Exception:
                # Registration fails closed while unrelated management functions stay available.
                logging.getLogger(__name__).error("registration_maintenance_incomplete")
            stopped.wait(60)
    thread = Thread(target=maintain, name="registration-maintenance", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=10)
