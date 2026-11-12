/*
 * VPE publisher node
 * Copyright (C) 2018 Copter Express Technologies
 *
 * Ported to ROS 2 (Jazzy): ros:: → rclcpp::, tf1 → tf2
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <string>
#include <rclcpp/rclcpp.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/static_transform_broadcaster.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2/LinearMath/Transform.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/utils.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <std_srvs/srv/trigger.hpp>

using geometry_msgs::msg::PoseStamped;
using geometry_msgs::msg::PoseWithCovarianceStamped;
using geometry_msgs::msg::TransformStamped;

// ──────────────────────────────────────────────────────────────────────────────
// Helpers replacing tf1 convenience functions
// ──────────────────────────────────────────────────────────────────────────────

/// Build tf2::Transform from geometry_msgs::msg::Pose
static tf2::Transform poseToTF(const geometry_msgs::msg::Pose& p)
{
    tf2::Transform t;
    t.setOrigin({p.position.x, p.position.y, p.position.z});
    tf2::Quaternion q;
    tf2::fromMsg(p.orientation, q);
    t.setRotation(q);
    return t;
}

/// Build tf2::Transform from geometry_msgs::msg::Transform
static tf2::Transform transformToTF(const geometry_msgs::msg::Transform& t)
{
    tf2::Transform result;
    tf2::fromMsg(t, result);
    return result;
}

/// Set geometry_msgs::msg::Quaternion to yaw-only (zero roll/pitch)
static void keepYaw(geometry_msgs::msg::Quaternion& q_msg)
{
    double yaw = tf2::getYaw(q_msg);
    tf2::Quaternion q;
    q.setRPY(0, 0, yaw);
    q_msg = tf2::toMsg(q);
}

// ──────────────────────────────────────────────────────────────────────────────

class VpePublisher : public rclcpp::Node
{
public:
    VpePublisher()
        : Node("vpe_publisher"),
          tf_buffer_(get_clock()),
          tf_listener_(tf_buffer_),
          static_br_(this),
          reset_flag_(true)
    {
        frame_id_        = declare_parameter("frame_id", std::string(""));
        offset_frame_id_ = declare_parameter("offset_frame_id", std::string(""));
        offset_timeout_s_ = declare_parameter("offset_timeout", 3.0);

        // Read mavros parameters (checked at startup only)
        local_frame_id_  = declare_parameter("local_frame_id", std::string("map"));
        child_frame_id_  = declare_parameter("child_frame_id", std::string("base_link"));

        if (!frame_id_.empty()) {
            RCLCPP_INFO(get_logger(), "using data from TF");
        } else {
            RCLCPP_INFO(get_logger(), "using data topic");
        }

        vpe_pub_ = create_publisher<PoseStamped>("vpe", 1);

        pose_sub_ = create_subscription<PoseStamped>(
            "pose", 1,
            [this](const PoseStamped::SharedPtr msg) { callback(msg); });

        pose_cov_sub_ = create_subscription<PoseWithCovarianceStamped>(
            "pose_cov", 1,
            [this](const PoseWithCovarianceStamped::SharedPtr msg) { callback(msg); });

        reset_serv_ = create_service<std_srvs::srv::Trigger>(
            "reset",
            [this](const std_srvs::srv::Trigger::Request::SharedPtr,
                   std_srvs::srv::Trigger::Response::SharedPtr res) {
                reset_flag_ = true;
                res->success = true;
            });

        bool force_init = declare_parameter("force_init", false);
        if (force_init || declare_parameter("publish_zero", false)) {
            double timeout  = declare_parameter("force_init_timeout", 5.0);
            double duration = declare_parameter("force_init_duration", 5.0);
            force_init_timeout_  = std::chrono::duration<double>(timeout);
            force_init_duration_ = std::chrono::duration<double>(duration);

            local_pos_sub_ = create_subscription<PoseStamped>(
                "mavros/local_position/pose", 1,
                [this](const PoseStamped::SharedPtr msg) {
                    local_pose_ = *msg;
                });

            zero_timer_ = create_wall_timer(
                std::chrono::milliseconds(100),
                [this]() { publishZero(); });
        }

        RCLCPP_INFO(get_logger(), "ready");
    }

private:
    tf2_ros::Buffer tf_buffer_;
    tf2_ros::TransformListener tf_listener_;
    tf2_ros::StaticTransformBroadcaster static_br_;

    std::string frame_id_, offset_frame_id_, local_frame_id_, child_frame_id_;
    double offset_timeout_s_;
    bool reset_flag_;

    PoseStamped vpe_, pose_, local_pose_;
    rclcpp::Time got_local_pos_{0, 0, RCL_ROS_TIME};
    TransformStamped offset_;

    std::chrono::duration<double> force_init_timeout_{5.0};
    std::chrono::duration<double> force_init_duration_{5.0};

    rclcpp::Publisher<PoseStamped>::SharedPtr vpe_pub_;
    rclcpp::Subscription<PoseStamped>::SharedPtr pose_sub_, local_pos_sub_;
    rclcpp::Subscription<PoseWithCovarianceStamped>::SharedPtr pose_cov_sub_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr reset_serv_;
    rclcpp::TimerBase::SharedPtr zero_timer_;

    static bool stampIsZero(const builtin_interfaces::msg::Time& t)
    {
        return t.sec == 0 && t.nanosec == 0;
    }

    static geometry_msgs::msg::Pose getPose(const PoseStamped::SharedPtr& p)
    {
        return p->pose;
    }

    static geometry_msgs::msg::Pose getPose(const PoseWithCovarianceStamped::SharedPtr& p)
    {
        return p->pose.pose;
    }

    template <typename T>
    void callback(const T& msg)
    {
        try {
            if (!frame_id_.empty()) {
                // Get VPE transform from TF
                rclcpp::Time stamp(msg->header.stamp, RCL_ROS_TIME);
                auto transform = tf_buffer_.lookupTransform(
                    frame_id_, child_frame_id_, stamp,
                    tf2::durationFromSec(0.02));
                vpe_.pose.position.x   = transform.transform.translation.x;
                vpe_.pose.position.y   = transform.transform.translation.y;
                vpe_.pose.position.z   = transform.transform.translation.z;
                vpe_.pose.orientation  = transform.transform.rotation;
            } else {
                vpe_.pose = getPose(msg);
            }

            // Offset handling
            if (!offset_frame_id_.empty()) {
                rclcpp::Time msg_stamp(msg->header.stamp, RCL_ROS_TIME);
                bool vpe_stale = stampIsZero(vpe_.header.stamp) ||
                    (msg_stamp - rclcpp::Time(vpe_.header.stamp, RCL_ROS_TIME)).seconds()
                    > offset_timeout_s_;

                if (reset_flag_ || vpe_stale) {
                    if (!frame_id_.empty()) {
                        // Calculate offset from TF
                        rclcpp::Time stamp(msg->header.stamp, RCL_ROS_TIME);
                        offset_ = tf_buffer_.lookupTransform(
                            local_frame_id_, frame_id_, stamp,
                            tf2::durationFromSec(0.02));
                        offset_.child_frame_id = offset_frame_id_;
                    } else {
                        // Calculate transform between vpe frame pose and local frame pose
                        rclcpp::Time stamp(msg->header.stamp, RCL_ROS_TIME);
                        auto local_pose = tf_buffer_.lookupTransform(
                            local_frame_id_, child_frame_id_, stamp,
                            tf2::durationFromSec(0.02));
                        keepYaw(local_pose.transform.rotation);

                        tf2::Transform vpeTransform = poseToTF(vpe_.pose);
                        tf2::Transform poseTransform = transformToTF(local_pose.transform);
                        tf2::Transform offset_tf = vpeTransform.inverseTimes(poseTransform);

                        offset_.transform    = tf2::toMsg(offset_tf);
                        offset_.header.frame_id = local_frame_id_;
                        offset_.header.stamp    = msg->header.stamp;
                        offset_.child_frame_id  = offset_frame_id_;
                    }

                    static_br_.sendTransform(offset_);
                    reset_flag_ = false;
                    RCLCPP_INFO(get_logger(), "offset reset");
                }

                // Apply the offset
                tf2::doTransform(vpe_, vpe_, offset_);
            }

            vpe_.header.frame_id = local_frame_id_;
            vpe_.header.stamp    = msg->header.stamp;
            vpe_pub_->publish(vpe_);

        } catch (const tf2::TransformException& e) {
            RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "%s", e.what());
        }
    }

    void publishZero()
    {
        rclcpp::Time now = get_clock()->now();

        // Don't publish if we have fresh VPE data
        if (!stampIsZero(vpe_.header.stamp)) {
            rclcpp::Time vpe_t(vpe_.header.stamp, RCL_ROS_TIME);
            if ((now - vpe_t).seconds() < force_init_timeout_.count()) return;
        }

        // Track when we first got local position
        if (!stampIsZero(local_pose_.header.stamp)) {
            rclcpp::Time local_t(local_pose_.header.stamp, RCL_ROS_TIME);
            if ((now - local_t).seconds() < force_init_timeout_.count()) {
                // Have local position
                if (got_local_pos_.seconds() == 0.0) {
                    RCLCPP_INFO(get_logger(), "got local position");
                    got_local_pos_ = now;
                }
                if ((now - got_local_pos_).seconds() > force_init_duration_.count()) return;
            } else {
                got_local_pos_ = rclcpp::Time(0, 0, RCL_ROS_TIME);
            }
        } else {
            got_local_pos_ = rclcpp::Time(0, 0, RCL_ROS_TIME);
        }

        RCLCPP_INFO_THROTTLE(get_logger(), *get_clock(), 10000, "publish zero");
        PoseStamped zero;
        zero.header.frame_id = local_frame_id_;
        zero.header.stamp    = static_cast<builtin_interfaces::msg::Time>(now);
        zero.pose.orientation.w = 1;
        vpe_pub_->publish(zero);
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<VpePublisher>());
    rclcpp::shutdown();
    return 0;
}
