# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Isaac bringup stub.

Prints "not built" and exits 2 from ``main`` and from
``generate_launch_description`` (what ``ros2 launch`` calls). There is no
USD scene, PhysX config, or GPU requirement in this file.
"""

import os
import sys


def generate_launch_description():
    print("not built", flush=True)
    # os._exit so a launch event loop cannot swallow SystemExit.
    os._exit(2)


def main() -> int:
    print("not built")
    return 2


if __name__ == "__main__":
    sys.exit(main())
