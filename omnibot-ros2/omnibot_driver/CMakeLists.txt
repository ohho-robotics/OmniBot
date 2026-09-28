cmake_minimum_required(VERSION 3.14)
project(omnibot_driver)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)

# The C++ controller target is not built. Serial I/O is Python (pyserial).
# Do not FetchContent a C++ serial library at configure time.

# Include directories
include_directories(include)

# Create library
# add_library(${PROJECT_NAME}
#   src/mecanum_controller.cpp
# )

# ament_target_dependencies(${PROJECT_NAME}
#   rclcpp
#   geometry_msgs
#   nav_msgs
#   tf2_ros
#   tf2_geometry_msgs
# )

# target_link_libraries(${PROJECT_NAME} ${SERIAL_LIB})

# Install library
# install(TARGETS
#   ${PROJECT_NAME}
#   ARCHIVE DESTINATION lib
#   LIBRARY DESTINATION lib
#   RUNTIME DESTINATION bin
# )

# Install Python scripts
install(PROGRAMS
  scripts/mecanum_controller_node.py
  scripts/serial_bridge_node.py
  scripts/yahboom_controller_node.py
  scripts/yahboom_test_node.py
  DESTINATION lib/${PROJECT_NAME}
)

# Install launch files
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}
)

# Install config files
install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}
)

# Install headers
install(DIRECTORY include/
  DESTINATION include
)

# Install package.xml
install(FILES package.xml
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_yahboom_protocol
    test/test_yahboom_protocol.py
    TIMEOUT 120
    APPEND_ENV PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/..
  )
endif()

ament_package()