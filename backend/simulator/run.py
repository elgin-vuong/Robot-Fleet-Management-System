import random
import time

from backend.simulator.fleet import Fleet

TICK_SECONDS = 1.0
TICK_JITTER = 0.2


def main():
    fleet = Fleet(5)

    # Kick things off with a bit of variety instead of every robot sitting idle.
    fleet.send_command("R001", "START")
    fleet.send_command("R002", "START")
    fleet.send_command("R003", "CHARGE")

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
