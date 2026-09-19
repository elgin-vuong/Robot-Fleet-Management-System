from backend.app.observability.logging import configure_logging

configure_logging()

from backend.app.observability.tracing import configure_tracing

configure_tracing(service_name="robot-fleet-simulator")

import logging
import random
import time

from backend.simulator.fleet import Fleet

TICK_SECONDS = 1.0
TICK_JITTER = 0.2

logger = logging.getLogger("backend.simulator")


def main():
    fleet = Fleet(5)
    logger.info("simulator.started", extra={"robot_count": len(fleet.robots)})

    # Kick things off with every robot moving instead of sitting idle.
    for robot_id in fleet.robots:
        fleet.send_command(robot_id, "START")

    try:
        while True:
            fleet.update_all()
            logger.debug("simulator.tick", extra={"robots": fleet.get_all_robots()})

            time.sleep(TICK_SECONDS + random.uniform(-TICK_JITTER, TICK_JITTER))
    except KeyboardInterrupt:
        logger.info("simulator.stopped")


if __name__ == "__main__":
    main()
