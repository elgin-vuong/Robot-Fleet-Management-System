import random
import time

from backend.simulator.fleet import Fleet

TICK_SECONDS = 1.0
TICK_JITTER = 0.2


def main():
    fleet = Fleet(5)

    # Kick things off with every robot moving instead of sitting idle.
    for robot_id in fleet.robots:
        fleet.send_command(robot_id, "START")

    try:
        while True:
            fleet.update_all()

            for robot in fleet.get_all_robots():
                print(robot)

            print("----------------")

            time.sleep(TICK_SECONDS + random.uniform(-TICK_JITTER, TICK_JITTER))
    except KeyboardInterrupt:
        print("Simulator stopped.")


if __name__ == "__main__":
    main()
