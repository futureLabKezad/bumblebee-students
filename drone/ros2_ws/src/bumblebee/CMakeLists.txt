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
  std_srvs geometry_msgs sensor_msgs mavros_msgs)
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
  src/ros_mjpeg_server.py
  scripts/servo_rc.py
  scripts/wheel_rc.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
install(DIRECTORY camera_info DESTINATION share/${PROJECT_NAME})
install(DIRECTORY www DESTINATION share/${PROJECT_NAME})

ament_export_dependencies(rosidl_default_runtime)
ament_package()
