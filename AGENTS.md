## Cursor Cloud specific instructions

This repository is a meta-workspace (ROS 2 robot, AI engines, Android, Unity Quest). On a headless Linux VM without a robot, GPU, Unity, or the Android SDK, develop the pure-Python cores below. Standard install and test commands are in each package README (`mecanum-kinematics/README.md`, `omnibot-ai-engines/learning_engine/README.md`, `omnibot-ai-engines/agent_engine/ARCHITECTURE.md`, `yahboom-python-driver/README.md`, `ros2-bev-stitcher/README.md`).

- Use the repo-local virtualenv at `.venv` (`source .venv/bin/activate`). It is not committed. Editable installs: `mecanum-kinematics`, `omnibot-ai-engines/learning_engine`, `omnibot-ai-engines/agent_engine`, `yahboom-python-driver`. Dev extras in that env: `pytest`, `numpy`, `pyserial`, `pyyaml`.
- Tests that pass with only that env:
  - `pytest mecanum-kinematics/tests`
  - `pytest yahboom-python-driver/tests`
  - `pytest ros2-bev-stitcher/tests` (the test file puts the package on `sys.path`; numpy is enough)
  - `python3 -m unittest discover -s omnibot-ai-engines/learning_engine/tests -t omnibot-ai-engines`
  - `python3 -m unittest discover -s omnibot-ai-engines/agent_engine/tests -t omnibot-ai-engines`
  - `PYTHONPATH=omnibot-ai-engines pytest omnibot-ai-engines/data_engine/tests` (the synchronizer test is numpy-only; do not `pip install -e` `data_engine`, its `setup.py` pulls torch)
- The root README's `cpu` bash block is what CI runs (`python3 scripts/check_readme_commands.py --section cpu`). `ruff.toml` checks syntax and undefined names (`ruff check .`).
- `pytest omnibot-ros2/omnibot_arm/test` imports `arm_math.py` and does not import `rclpy`. `omnibot_hybrid` and `omnibot_driver` tests still import ROS message packages and run under `colcon test` in the Jazzy CI job, not in this venv.
- Colcon packages are symlinked from `src/`. Build with the README `ros` block on Ubuntu 24.04 + ROS 2 Jazzy. Compose file: `omnibot-digital-twin/docker/docker-compose.yml`. There is no `.devcontainer`.
- `omnibot-android` needs the Android SDK and JDK 17 (`./gradlew`). `omnibot-vr` is a Unity project (`ProjectSettings/ProjectVersion.txt`). `vla_engine`, `lerobot_engine`, and `rl_engine` need GPU stacks (torch / Isaac) and are not installed.
