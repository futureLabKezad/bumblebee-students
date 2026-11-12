/*
 * Visualization marker for camera alignment
 * Copyright (C) 2018 Copter Express Technologies
 *
 * Ported to ROS 2 (Jazzy)
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <visualization_msgs/msg/marker.hpp>
#include <visualization_msgs/msg/marker_array.hpp>

using visualization_msgs::msg::Marker;
using visualization_msgs::msg::MarkerArray;

class CameraMarkers : public rclcpp::Node
{
public:
    CameraMarkers() : Node("camera_markers")
    {
        markers_scale_ = declare_parameter("scale", 1.0);

        // Latched publisher (transient_local = QoS equivalent of latch=true)
        markers_pub_ = create_publisher<MarkerArray>(
            "camera_markers", rclcpp::QoS(1).transient_local());

        // One-shot subscription: get camera frame_id from first CameraInfo message
        camera_info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
            "camera_info", rclcpp::SensorDataQoS(),
            [this](const sensor_msgs::msg::CameraInfo::SharedPtr msg) {
                camera_frame_ = msg->header.frame_id;
                markers_pub_->publish(createMarkers());
                camera_info_sub_.reset();  // unsubscribe after first message
                RCLCPP_INFO(get_logger(), "Camera markers initialized (frame: %s)",
                            camera_frame_.c_str());
            });
    }

private:
    double markers_scale_;
    std::string camera_frame_;
    rclcpp::Publisher<MarkerArray>::SharedPtr markers_pub_;
    rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr camera_info_sub_;

    MarkerArray createMarkers()
    {
        MarkerArray markers;

        Marker lens;
        lens.header.frame_id = camera_frame_;
        lens.ns = "camera_markers";
        lens.id = 0;
        lens.action = Marker::ADD;
        lens.type = Marker::CYLINDER;
        lens.frame_locked = true;
        lens.scale.x = 0.013 * markers_scale_;
        lens.scale.y = 0.013 * markers_scale_;
        lens.scale.z = 0.015 * markers_scale_;
        lens.color.r = 0.3f;
        lens.color.g = 0.3f;
        lens.color.b = 0.3f;
        lens.color.a = 0.9f;
        lens.pose.position.z = 0.0075 * markers_scale_;
        lens.pose.orientation.w = 1;

        Marker board;
        board.header.frame_id = camera_frame_;
        board.ns = "camera_markers";
        board.id = 1;
        board.action = Marker::ADD;
        board.type = Marker::CUBE;
        board.frame_locked = true;
        board.scale.x = 0.024 * markers_scale_;
        board.scale.y = 0.024 * markers_scale_;
        board.scale.z = 0.001 * markers_scale_;
        board.color.r = 0.0f;
        board.color.g = 0.8f;
        board.color.b = 0.0f;
        board.color.a = 0.9f;
        board.pose.orientation.w = 1;

        Marker wire;
        wire.header.frame_id = camera_frame_;
        wire.ns = "camera_markers";
        wire.id = 2;
        wire.action = Marker::ADD;
        wire.type = Marker::CUBE;
        wire.frame_locked = true;
        wire.scale.x = 0.014 * markers_scale_;
        wire.scale.y = 0.04 * markers_scale_;
        wire.scale.z = 0.001 * markers_scale_;
        wire.color.r = 0.9f;
        wire.color.g = 0.9f;
        wire.color.b = 1.0f;
        wire.color.a = 0.8f;
        wire.pose.position.x = 0;
        wire.pose.position.y = (0.01 + 0.02) * markers_scale_;
        wire.pose.position.z = 0.002 * markers_scale_;
        wire.pose.orientation.w = 1;

        markers.markers.push_back(lens);
        markers.markers.push_back(board);
        markers.markers.push_back(wire);

        return markers;
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<CameraMarkers>());
    rclcpp::shutdown();
    return 0;
}
