# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Isaac bringup stub.

Prints "not built" and exits 2. There is no USD scene, PhysX config, or GPU
requirement in this file.
"""

import sys


def main() -> int:
    print("not built")
    return 2


if __name__ == "__main__":
    sys.exit(main())
