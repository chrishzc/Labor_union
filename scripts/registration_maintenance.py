"""Internal-only registration maintenance. No external provider sends or legacy data migration."""
from __future__ import annotations

import argparse
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--initialize-new-instance", action="store_true",
                        help="Only for a verified brand-new empty dedicated Redis; never for an incomplete restore.")
    args = parser.parse_args()
    from api.dependencies.line_identity import get_line_identity_application
    from infrastructure.redis.registration_connection import registration_redis_client
    from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository
    from infrastructure.redis.registration_maintenance import RegistrationAofMaintenance
    from subsystems.case_import.registration_staging import RegistrationReviewApplication
    from subsystems.case_import.registration_maintenance import RegistrationMaintenanceRunner
    formal = get_line_identity_application()
    staging = RedisRegistrationStagingRepository(registration_redis_client(role="admin"))
    staging.initialize(formal.registration_id_high_water(), new_empty_instance=args.initialize_new_instance)
    review = RegistrationReviewApplication(staging, formal)
    maintenance = RegistrationAofMaintenance(staging)
    runner = RegistrationMaintenanceRunner(staging, review, maintenance)
    while True:
        if not runner.tick():
            print("registration_maintenance_incomplete", file=sys.stderr)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
