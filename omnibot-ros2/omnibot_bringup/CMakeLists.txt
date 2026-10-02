cmake_minimum_required(VERSION 3.8)
project(omnibot_bringup)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()

  # Headless Gazebo launch test. The sim-smoke CI job exports
  # OMNIBOT_SIM_SMOKE=1 before configure. The default colcon test job
  # does not, so it does not start Gazebo.
  if("$ENV{OMNIBOT_SIM_SMOKE}" STREQUAL "1")
    find_package(launch_testing_ament_cmake REQUIRED)
    add_launch_test(
      test/test_sim_launch.py
      TIMEOUT 240
    )
  endif()
endif()

# Install launch files (including master/ subfolder)
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}
)

# Install config files
install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}
)

# Install world files
install(DIRECTORY
  worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
