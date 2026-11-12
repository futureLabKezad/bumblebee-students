cmake_minimum_required(VERSION 3.8)
project(bumblebee)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -std=c++17)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(rclpy REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(image_geometry REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc calib3d)
find_package(led_msgs QUIET)
find_package(rcl_interfaces REQUIRED)

# GeographicLib
set(CMAKE_MODULE_PATH "${CMAKE_MODULE_PATH};/usr/share/cmake/geographiclib")
find_package(GeographicLib REQUIRED)

###############################
## Generate messages/services ##
###############################
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/State.msg"
  "srv/GetTelemetry.srv"
  "srv/Navigate.srv"
  "srv/NavigateGlobal.srv"
  "srv/SetAltitude.srv"
  "srv/SetYaw.srv"
  "srv/SetYawRate.srv"
  "srv/SetPosition.srv"
  "srv/SetVelocity.srv"
  "srv/SetAttitude.srv"
  "srv/SetRates.srv"
  "srv/SetLEDEffect.srv"
  "srv/Execute.srv"
  "srv/SetParam.srv"
  DEPENDENCIES std_msgs geometry_msgs sensor_msgs
)

###########
## Build ##
###########

# optical_flow — composable node (бывший nodelet)
add_library(optical_flow SHARED src/cpp/optical_flow.cpp)
ament_target_dependencies(optical_flow
  rclcpp rclcpp_components sensor_msgs geometry_msgs
  tf2 tf2_ros tf2_geometry_msgs
  cv_bridge image_transport mavros_msgs)
target_include_directories(optical_flow PUBLIC ${OpenCV_INCLUDE_DIRS})
target_link_libraries(optical_flow ${OpenCV_LIBRARIES})
rclcpp_components_register_node(optical_flow
  PLUGIN "bumblebee::OpticalFlow"
  EXECUTABLE optical_flow_node)

# simple_offboard
add_executable(simple_offboard src/cpp/simple_offboard.cpp)
ament_target_dependencies(simple_offboard
  rclcpp tf2 tf2_ros tf2_geometry_msgs
  std_srvs std_msgs geometry_msgs sensor_msgs mavros_msgs)
target_link_libraries(simple_offboard ${GeographicLib_LIBRARIES})
rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} "rosidl_typesupport_cpp")
target_link_libraries(simple_offboard ${cpp_typesupport_target})

# camera_markers
add_executable(camera_markers src/cpp/camera_markers.cpp)
ament_target_dependencies(camera_markers rclcpp sensor_msgs visualization_msgs)

# vpe_publisher
add_executable(vpe_publisher src/cpp/vpe_publisher.cpp)
ament_target_dependencies(vpe_publisher
  rclcpp tf2 tf2_ros tf2_geometry_msgs
  geometry_msgs std_srvs)

# rc
add_executable(rc src/cpp/rc.cpp)
ament_target_dependencies(rc rclcpp mavros_msgs)
target_link_libraries(rc ${cpp_typesupport_target})

# led (опционально — требует led_msgs)
if(led_msgs_FOUND)
  add_executable(led src/cpp/led.cpp)
  ament_target_dependencies(led
    rclcpp mavros_msgs sensor_msgs led_msgs rcl_interfaces)
  target_link_libraries(led ${cpp_typesupport_target})
  list(APPEND OPTIONAL_TARGETS led)
  message(STATUS "led_msgs found — building led node")
else()
  message(WARNING "led_msgs not found — skipping led node (install led_msgs to enable)")
endif()

# shell
add_executable(shell src/cpp/shell.cpp)
ament_target_dependencies(shell rclcpp)
target_link_libraries(shell ${cpp_typesupport_target})

#############
## Install ##
#############

install(TARGETS
  optical_flow
  optical_flow_node
  simple_offboard
  camera_markers
  vpe_publisher
  rc
  shell
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

if(led_msgs_FOUND)
  install(TARGETS led
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION lib/${PROJECT_NAME}
  )
endif()

# Python scripts (rosidl уже создаёт Python-пакет bumblebee для msgs/srvs)
# The src/python/ copies are byte-identical to what runs in install/ on the
# V1.0.0-beta image (030726).
install(PROGRAMS
  src/python/selfcheck.py
  src/python/vpe_fix.py
  src/python/set_params.py
  src/python/camera_fix.py
  src/python/aruco_detect.py
  src/python/qos_relay.py
  src/python/setpoint_freshness.py
  src/ros_mjpeg_server.py
  scripts/servo_rc.py
  scripts/wheel_rc.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
install(DIRECTORY camera_info DESTINATION share/${PROJECT_NAME})
install(DIRECTORY www DESTINATION share/${PROJECT_NAME})

#############
## Testing ##
#############

# colcon build --packages-select bumblebee && colcon test --packages-select bumblebee
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  find_package(ament_cmake_ros REQUIRED)
  find_package(launch_testing_ament_cmake REQUIRED)

  ament_add_pytest_test(test_test_safety test/test_test_safety.py TIMEOUT 30)
  ament_add_pytest_test(test_setpoint_freshness_unit test/test_setpoint_freshness_unit.py TIMEOUT 30)
  ament_add_pytest_test(test_mavros_scoped_config test/test_mavros_scoped_config.py TIMEOUT 30)
  ament_add_pytest_test(test_setpoint_freshness_ros test/test_setpoint_freshness_ros.py TIMEOUT 150)

  ament_add_pytest_test(test_auto_arm_interrupt test/test_auto_arm_interrupt.py TIMEOUT 30)
  # P2: a Ctrl+C seen before navigate(auto_arm) returns is always a cancel
  ament_add_pytest_test(test_auto_arm_late_cancel test/test_auto_arm_late_cancel.py TIMEOUT 30)
  ament_add_pytest_test(test_rpc_latency test/test_rpc_latency.py TIMEOUT 120)
  ament_add_pytest_test(test_fake_px4_model test/test_fake_px4_model.py TIMEOUT 30)
  ament_add_pytest_test(test_drone_py_cancel_launch test/test_drone_py_cancel_launch.py TIMEOUT 150)

  # drone.py flight guards (D1-D3); ROS is faked, no rclpy needed
  ament_add_pytest_test(test_drone_flight_guards test/test_drone_flight_guards.py TIMEOUT 120)

  # Navigate segment math (S1): compiles simple_offboard.cpp itself without main()
  ament_add_gtest(test_simple_offboard test/test_simple_offboard.cpp)
  target_include_directories(test_simple_offboard PRIVATE src/cpp)
  ament_target_dependencies(test_simple_offboard
    rclcpp tf2 tf2_ros tf2_geometry_msgs
    std_srvs geometry_msgs sensor_msgs mavros_msgs)
  target_link_libraries(test_simple_offboard ${GeographicLib_LIBRARIES} ${cpp_typesupport_target})

  # The real simple_offboard binary against a fake MAVROS (S1-S5). Runs in its
  # own ROS_DOMAIN_ID so parallel test runs on one machine cannot cross-talk.
  add_launch_test(test/test_land_pilot_launch.py TARGET test_land_pilot_launch TIMEOUT 120)
  add_launch_test(test/test_simple_offboard_px4model_launch.py
    TARGET test_simple_offboard_px4model_launch
    TIMEOUT 300
    RUNNER "${ament_cmake_ros_DIR}/run_test_isolated.py")
  add_launch_test(test/test_simple_offboard_launch.py
    TARGET test_simple_offboard_launch
    TIMEOUT 240
    RUNNER "${ament_cmake_ros_DIR}/run_test_isolated.py")
  # The same binary under use_sim_time with a fake /clock at 25% real time (the
  # Gazebo sim); its own ROS_DOMAIN_ID keeps that /clock away from other tests
  add_launch_test(test/test_simple_offboard_simtime_launch.py
    TARGET test_simple_offboard_simtime_launch
    TIMEOUT 180
    RUNNER "${ament_cmake_ros_DIR}/run_test_isolated.py")

  # vpe_fix H2 round 2 (port-rc3): code pins, unknown write outcome, no extra in-air write. Offline (ROS stubbed, no
  # DDS); byte copies of the round-2 hand-over, see test/vpe_fix_h2_r2/README.md
  set(_H2R2 ${CMAKE_CURRENT_SOURCE_DIR}/test/vpe_fix_h2_r2)
  set(_VPE ${CMAKE_CURRENT_SOURCE_DIR}/src/python/vpe_fix.py)
  # r2h (T44): code pins round 3. The round-2 pins pin r2g's vpe_fix (byte copy ref/vpe_fix_r2g_3b8a93d4.py), so
  # the chain c33 -> P1 -> H2 -> r2g stays pinned; test_pins_r3 pins src/python/vpe_fix.py (r2h) against that
  # copy: only the declared B1/B2 parts differ.
  ament_add_pytest_test(test_vpe_fix_h2_r2_pins test/vpe_fix_h2_r2/tests_r2/test_pins_r2.py TIMEOUT 60
    ENV PIN_TARGET=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py PIN_C33=${_H2R2}/ref/vpe_fix_c33_product.py
        PIN_P1=${_H2R2}/ref/vpe_fix_7f107882.py PIN_HARNESS=${_H2R2}/tests_existing/harness)
  # r2i (T46): round 3 pins the r2h copy (ref/vpe_fix_r2h_66d806ba.py) against the r2g copy; round 4 pins
  # src/python/vpe_fix.py (r2i: vision in AUTO.LAND) against the r2h copy.
  ament_add_pytest_test(test_vpe_fix_pins_r3 test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py TIMEOUT 60
    ENV PIN_TARGET=${_H2R2}/ref/vpe_fix_r2h_66d806ba.py PIN_R2G=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py
        PIN_HARNESS=${_H2R2}/tests_existing/harness)
  ament_add_pytest_test(test_vpe_fix_pins_r4 test/vpe_fix_h2_r2/tests_r4/test_pins_r4.py TIMEOUT 60
    ENV PIN_TARGET=${_VPE} PIN_R2H=${_H2R2}/ref/vpe_fix_r2h_66d806ba.py PIN_HARNESS=${_H2R2}/tests_existing/harness)
  ament_add_pytest_test(test_vpe_fix_h2_r2 test/vpe_fix_h2_r2/tests_r2/test_h2_r2.py TIMEOUT 120
    ENV H2_TARGET=${_VPE} H2_CONTROL=${_H2R2}/ref/vpe_fix_7f107882.py H2_EVAL=${_H2R2}/eval
        H2_OUT=${CMAKE_CURRENT_BINARY_DIR}/vpe_fix_h2_r2_out/h2 H2_REAL_S1=${_H2R2}/real_s1)
  ament_add_pytest_test(test_vpe_fix_h2_r2_in_air test/vpe_fix_h2_r2/tests_r2/test_in_air_writes.py TIMEOUT 120
    ENV H2_TARGET=${_VPE} H2_CONTROL=${_H2R2}/ref/vpe_fix_7f107882.py H2_OUT=${CMAKE_CURRENT_BINARY_DIR}/vpe_fix_h2_r2_out/air)
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_package()
