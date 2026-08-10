import time

from backend.simulator.fleet import Fleet


fleet = Fleet(5)

fleet.send_command("R001", "START")

while True:
    for robot in fleet.robots.values():
        robot.update()

    for robot in fleet.get_all_robots():
        print(robot)

    print("----------------")

    time.sleep(1)
