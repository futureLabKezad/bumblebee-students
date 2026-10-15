/*
 * Simplified copter control in OFFBOARD mode
 * Copyright (C) 2019 Copter Express Technologies
 * Migrated to ROS 2 (Jazzy)
 *
 * Author: Oleg Kalachev <okalachev@gmail.com>
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <string>
#include <cmath>
#include <stdexcept>
#include <memory>
#include <map>
#include <mutex>
#include <optional>
#include <thread>

#include <GeographicLib/Geodesic.hpp>

#include <rclcpp/rclcpp.hpp>
#include <tf2/utils.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/transform_broadcaster.h>
#include <tf2_ros/static_transform_broadcaster.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <std_srvs/srv/trigger.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <geometry_msgs/msg/vector3_stamped.hpp>
#include <geometry_msgs/msg/quaternion_stamped.hpp>
#include <sensor_msgs/msg/nav_sat_fix.hpp>
#include <sensor_msgs/msg/battery_state.hpp>
#include <sensor_msgs/msg/range.hpp>
#include <mavros_msgs/srv/command_bool.hpp>
#include <mavros_msgs/srv/set_mode.hpp>
#include <mavros_msgs/msg/position_target.hpp>
#include <mavros_msgs/msg/attitude_target.hpp>
#include <mavros_msgs/msg/thrust.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <mavros_msgs/msg/status_text.hpp>
#include <mavros_msgs/msg/manual_control.hpp>
#include <mavros_msgs/msg/altitude.hpp>

#include <bumblebee/srv/get_telemetry.hpp>
#include <bumblebee/srv/navigate.hpp>
#include <bumblebee/srv/navigate_global.hpp>
#include <bumblebee/srv/set_altitude.hpp>
#include <bumblebee/srv/set_yaw.hpp>
#include <bumblebee/srv/set_yaw_rate.hpp>
#include <bumblebee/srv/set_position.hpp>
#include <bumblebee/srv/set_velocity.hpp>
#include <bumblebee/srv/set_attitude.hpp>
#include <bumblebee/srv/set_rates.hpp>
#include <bumblebee/msg/state.hpp>

using std::string;
using std::isnan;
using namespace geometry_msgs::msg;
using namespace sensor_msgs::msg;
using mavros_msgs::msg::PositionTarget;
using mavros_msgs::msg::AttitudeTarget;
using mavros_msgs::msg::Thrust;
using mavros_msgs::msg::Altitude;

// tf2 helpers replacing removed tf:: functions
inline Quaternion quatFromYaw(double yaw) {
    tf2::Quaternion q;
    q.setRPY(0, 0, yaw);
    return tf2::toMsg(q);
}

inline Quaternion quatFromRPY(double roll, double pitch, double yaw) {
    tf2::Quaternion q;
    q.setRPY(roll, pitch, yaw);
    return tf2::toMsg(q);
}

inline bool stampIsZero(const builtin_interfaces::msg::Time& stamp) {
    return stamp.sec == 0 && stamp.nanosec == 0;
}

// Monotonic time for navigate segment progress on the drone. The ROS clock follows
// the Pi's wall clock, which NTP steps by seconds (or by months on the first sync
// after boot); the steady clock never jumps. Under use_sim_time the node uses the
// simulation clock instead (SimpleOffboard::monotonicNs()).
// Only requests in a continuous flight-command run share a start time.
inline int64_t flightRunStart(int64_t previous_start, int64_t last_exit, int64_t now_ns) {
    return now_ns < last_exit || now_ns - last_exit > 500000000LL ? now_ns : previous_start;
}
inline bool queuedArmBlocked(int64_t now_ns, int64_t run_start, int64_t land_done) {
    return land_done != 0 && now_ns >= land_done && run_start < land_done + 500000000LL;
}

inline int64_t steadyNs() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

// The setpoint publisher is a wall timer: use steady time even under use_sim_time.
// Its first callback after SIGCONT can precede the queued /clock and FCU State
// callbacks. Publishing then could pull PX4 out of its OFFBOARD-loss landing.
// This 1 s bound matches the project's COM_OF_LOSS_T=1; it is independent of
// the 4.5 s State watchdog and therefore tolerates missing heartbeats while
// the publisher keeps ticking. The caller holds mutex_ for all timestamp access.
constexpr int64_t kSetpointResumeGapNs = 1000000000LL;
inline bool setpointResumeBlocked(bool active, bool armed_or_in_doubt,
                                  int64_t last_tick_ns, int64_t now_ns) {
    if (!active || !armed_or_in_doubt || last_tick_ns == 0) return false;
    return now_ns < last_tick_ns || now_ns - last_tick_ns > kSetpointResumeGapNs;
}
// After a stop, an old queued request must not use the pre-stall OFFBOARD
// snapshot. A newly received State plus the usual checkState/checkPilot is
// needed; a confirmed disarmed vehicle may begin a new explicit takeoff.
inline bool publisherResumeStateAllowed(bool connected, bool armed, bool offboard,
                                         int64_t state_receipt_ns, int64_t stopped_ns) {
    return stopped_ns == 0 || (state_receipt_ns > stopped_ns && connected && (!armed || offboard));
}

// Fraction of a navigate segment of `distance` m covered at `speed` m/s between
// start_ns and now_ns, clamped to [0, 1]: it never extrapolates past either end.
// A start in the future holds the start, a long wait stops at the target.
// A zero-length segment is complete; without a positive speed the start is held.
// Pure function, unit-tested in test/test_simple_offboard.cpp.
inline double navigateProgress(double distance, double speed, int64_t start_ns, int64_t now_ns) {
    if (!(distance > 0)) return 1.0;
    if (!(speed > 0) || !std::isfinite(speed)) return 0.0;
    // Subtract as integers first: epoch-sized nanosecond values lose precision
    // as doubles, their difference does not
    double elapsed = static_cast<double>(now_ns - start_ns) * 1e-9;
    double progress = elapsed * speed / distance;
    if (std::isnan(progress)) return 0.0;
    return std::clamp(progress, 0.0, 1.0);
}

// Navigate setpoint: the point on the segment start -> target at navigateProgress().
// It only clips onto the segment and always returns a point, so the setpoint
// stream never stops because of it.
inline Point navigateSetpoint(const Point& start, const Point& target, double speed,
                              int64_t start_ns, int64_t now_ns) {
    double dx = target.x - start.x, dy = target.y - start.y, dz = target.z - start.z;
    double progress = navigateProgress(std::sqrt(dx*dx + dy*dy + dz*dz), speed, start_ns, now_ns);
    if (progress >= 1.0) return target;
    Point p;
    p.x = start.x + dx * progress;
    p.y = start.y + dy * progress;
    p.z = start.z + dz * progress;
    return p;
}

enum setpoint_type_t {
    NONE,
    NAVIGATE,
    NAVIGATE_GLOBAL,
    POSITION,
    VELOCITY,
    ATTITUDE,
    RATES,
    _ALTITUDE,
    _YAW,
    _YAW_RATE,
};

enum yaw_type_t { YAW, YAW_RATE, TOWARDS };

enum class ArmReply { ACCEPTED, REJECTED, UNKNOWN };
inline ArmReply classifyArmReply(bool replied, bool success, uint8_t result) {
    if (!replied || (!success && result == 0)) return ArmReply::UNKNOWN;
    return success ? ArmReply::ACCEPTED : ArmReply::REJECTED;
}
inline bool armSendAllowed(const mavros_msgs::msg::State& state, int64_t rx_ns, int64_t now_ns,
                           ArmReply last_reply, int64_t last_send_ns, int64_t last_reply_ns) {
    return state.connected && !state.armed && state.mode == "OFFBOARD" && rx_ns > 0 &&
           now_ns >= rx_ns && now_ns - rx_ns <= 300000000LL && rx_ns > last_reply_ns &&
           now_ns >= last_send_ns && now_ns - last_send_ns >= 2000000000LL &&
           last_reply == ArmReply::REJECTED;
}
inline bool disarmAllowed(const mavros_msgs::msg::State& state) {
    return !(state.armed && state.mode != "OFFBOARD");
}

class SimpleOffboard : public rclcpp::Node
{
public:
    SimpleOffboard() : Node("simple_offboard"),
        tf_buffer_(get_clock()),
        tf_listener_(tf_buffer_)
    {
        // Parameters
        mavros_ = declare_parameter("mavros", string("mavros"));
        target_.child_frame_id = declare_parameter("target_frame", string("navigate_target"));
        setpoint_.child_frame_id = declare_parameter("setpoint", string("setpoint"));
        auto_release_ = declare_parameter("auto_release", true);
        land_only_in_offboard_ = declare_parameter("land_only_in_offboard", true);
        if (!land_only_in_offboard_) RCLCPP_WARN(get_logger(),
            "land_only_in_offboard=false allows AUTO.LAND outside OFFBOARD only while disarmed; pilot modes remain protected");
        nav_from_sp_ = declare_parameter("nav_from_sp", true);
        check_kill_switch_ = declare_parameter("check_kill_switch", true);
        default_speed_ = declare_parameter("default_speed", 0.5);
        body_.child_frame_id = declare_parameter("body_frame", string("body"));
        terrain_.child_frame_id = declare_parameter("terrain_frame", string("terrain"));
        terrain_frame_mode_ = declare_parameter("terrain_frame_mode", string("altitude"));

        state_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("state_timeout", 3.0));
        // Stream watchdog in publishSetpoint(): longer than state_timeout, MAVROS
        // reports State once per 1 Hz heartbeat and a false stop in the air is a failsafe
        state_watchdog_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("state_watchdog_timeout", 4.5));
        local_position_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("local_position_timeout", 2.0));
        velocity_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("velocity_timeout", 2.0));
        global_position_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("global_position_timeout", 10.0));
        battery_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("battery_timeout", 2.0));
        manual_control_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("manual_control_timeout", 0.0));
        transform_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("transform_timeout", 0.5));
        telemetry_transform_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("telemetry_transform_timeout", 0.5));
        offboard_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("offboard_timeout", 3.0));
        land_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("land_timeout", 3.0));
        arming_timeout_ = rclcpp::Duration::from_seconds(declare_parameter("arming_timeout", 4.0));
        arm_settle_time_ = rclcpp::Duration::from_seconds(declare_parameter("arm_settle_time", 1.5));
        // auto_arm stays refused this long after a /land (see checkArmCancel())
        arm_hold_after_land_ = rclcpp::Duration::from_seconds(declare_parameter("arm_hold_after_land", 3.0));
        setpoint_rate_ = declare_parameter("setpoint_rate", 30.0);
        setpoint_smooth_alpha_ = declare_parameter("setpoint_smooth_alpha", 0.3);

        // reference_frames param: passed as key:value pairs via yaml
        declare_parameter("reference_frames", std::vector<std::string>());

        // Read local_position tf frame_ids from mavros params (defaults)
        local_frame_ = declare_parameter("local_frame", string("map"));
        fcu_frame_ = declare_parameter("fcu_frame", string("base_link"));

        // Default reference frames
        reference_frames_[body_.child_frame_id] = local_frame_;
        reference_frames_[fcu_frame_] = local_frame_;
        if (!target_.child_frame_id.empty()) {
            reference_frames_[target_.child_frame_id] = local_frame_;
        }

        if (!body_.child_frame_id.empty() && !terrain_.child_frame_id.empty()) {
            terrain_.header.frame_id = local_frame_;
        }

        // tf broadcasters
        transform_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this);
        static_transform_broadcaster_ = std::make_shared<tf2_ros::StaticTransformBroadcaster>(this);

        // Callback groups: srvs may block; concurrent runs alongside them; land has
        // its own group so /land is answered (and can cancel auto_arm) while serve() blocks
        cb_grp_telemetry_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
        cb_grp_srvs_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
        cb_grp_land_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
        cb_grp_concurrent_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

        // Service clients (in cb_grp_concurrent_ so responses are processed while srvs block)
        auto qos = rclcpp::ServicesQoS();
        arming_ = create_client<mavros_msgs::srv::CommandBool>(mavros_ + "/cmd/arming", qos, cb_grp_concurrent_);
        set_mode_ = create_client<mavros_msgs::srv::SetMode>(mavros_ + "/set_mode", qos, cb_grp_concurrent_);

        // Subscribers (all in cb_grp_concurrent_ so they run while service callbacks block)
        auto sub_qos = rclcpp::SensorDataQoS();
        auto state_qos = rclcpp::QoS(1).reliable().transient_local();
        auto sub_opts = rclcpp::SubscriptionOptions();
        sub_opts.callback_group = cb_grp_concurrent_;
        state_sub_ = create_subscription<mavros_msgs::msg::State>(
            mavros_ + "/state", state_qos,
            [this](const mavros_msgs::msg::State::SharedPtr msg) { handleState(*msg); }, sub_opts);
        velocity_sub_ = create_subscription<TwistStamped>(
            mavros_ + "/local_position/velocity_body", sub_qos,
            [this](const TwistStamped::SharedPtr msg) { std::lock_guard<std::mutex> lock(telemetry_mutex_); velocity_ = *msg; }, sub_opts);
        global_pos_sub_ = create_subscription<NavSatFix>(
            mavros_ + "/global_position/global", 1,
            [this](const NavSatFix::SharedPtr msg) { std::lock_guard<std::mutex> lock(telemetry_mutex_); global_position_ = *msg; }, sub_opts);
        battery_sub_ = create_subscription<BatteryState>(
            mavros_ + "/battery", sub_qos,
            [this](const BatteryState::SharedPtr msg) {
                std::lock_guard<std::mutex> lock(telemetry_mutex_);
                battery_stamp_ = msg->header.stamp; battery_voltage_ = msg->voltage;
                battery_cell0_ = msg->cell_voltage.empty() ? NAN : msg->cell_voltage[0]; }, sub_opts);
        statustext_sub_ = create_subscription<mavros_msgs::msg::StatusText>(
            mavros_ + "/statustext/recv", sub_qos,
            [this](const mavros_msgs::msg::StatusText::SharedPtr msg) {
                std::lock_guard<std::mutex> lock(mutex_);
                statustext_ = *msg; }, sub_opts);
        manual_control_sub_ = create_subscription<mavros_msgs::msg::ManualControl>(
            mavros_ + "/manual_control/control", 1,
            [this](const mavros_msgs::msg::ManualControl::SharedPtr msg) {
                std::lock_guard<std::mutex> lock(telemetry_mutex_); manual_control_ = *msg; }, sub_opts);
        local_pos_sub_ = create_subscription<PoseStamped>(
            mavros_ + "/local_position/pose", sub_qos,
            [this](const PoseStamped::SharedPtr msg) { handleLocalPosition(*msg); }, sub_opts);

        if (!body_.child_frame_id.empty() && !terrain_.child_frame_id.empty()) {
            if (terrain_frame_mode_ == "altitude") {
                altitude_sub_ = create_subscription<Altitude>(
                    mavros_ + "/altitude", 1,
                    [this](const Altitude::SharedPtr msg) { handleAltitude(*msg); }, sub_opts);
            } else if (terrain_frame_mode_ == "range") {
                string range_topic = declare_parameter("range_topic", string("rangefinder/range"));
                range_sub_ = create_subscription<Range>(
                    range_topic, 1,
                    [this](const Range::SharedPtr msg) { handleRange(*msg); }, sub_opts);
            } else {
                RCLCPP_FATAL(get_logger(), "Unknown terrain_frame_mode: %s, valid: altitude, range",
                             terrain_frame_mode_.c_str());
                throw std::runtime_error("Invalid terrain_frame_mode");
            }
        }

        // Publishers
        position_pub_ = create_publisher<PoseStamped>(mavros_ + "/setpoint_position/local", 1);
        position_raw_pub_ = create_publisher<PositionTarget>(mavros_ + "/setpoint_raw/local", 1);
        attitude_pub_ = create_publisher<PoseStamped>(mavros_ + "/setpoint_attitude/attitude", 1);
        attitude_raw_pub_ = create_publisher<AttitudeTarget>(mavros_ + "/setpoint_raw/attitude", 1);
        rates_pub_ = create_publisher<TwistStamped>(mavros_ + "/setpoint_attitude/cmd_vel", 1);
        thrust_pub_ = create_publisher<Thrust>(mavros_ + "/setpoint_attitude/thrust", 1);
        state_pub_ = create_publisher<bumblebee::msg::State>("state", rclcpp::QoS(1).transient_local());

        // Service servers (in cb_grp_srvs_ so they can block without starving subscriptions)
        auto srv_qos = rclcpp::ServicesQoS();
        gt_srv_ = create_service<bumblebee::srv::GetTelemetry>("get_telemetry",
            [this](const bumblebee::srv::GetTelemetry::Request::SharedPtr req,
                   bumblebee::srv::GetTelemetry::Response::SharedPtr res) { getTelemetry(req, res); },
            srv_qos, cb_grp_telemetry_);
        na_srv_ = create_service<bumblebee::srv::Navigate>("navigate",
            [this](const bumblebee::srv::Navigate::Request::SharedPtr req,
                   bumblebee::srv::Navigate::Response::SharedPtr res) {
                serve(NAVIGATE, req->x, req->y, req->z, NAN, NAN, NAN, NAN, NAN, req->yaw,
                      NAN, NAN, NAN, NAN, NAN, NAN, req->speed, req->frame_id, req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        ng_srv_ = create_service<bumblebee::srv::NavigateGlobal>("navigate_global",
            [this](const bumblebee::srv::NavigateGlobal::Request::SharedPtr req,
                   bumblebee::srv::NavigateGlobal::Response::SharedPtr res) {
                serve(NAVIGATE_GLOBAL, NAN, NAN, req->z, NAN, NAN, NAN, NAN, NAN, req->yaw,
                      NAN, NAN, NAN, req->lat, req->lon, NAN, req->speed, req->frame_id, req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        sl_srv_ = create_service<bumblebee::srv::SetAltitude>("set_altitude",
            [this](const bumblebee::srv::SetAltitude::Request::SharedPtr req,
                   bumblebee::srv::SetAltitude::Response::SharedPtr res) {
                serve(_ALTITUDE, NAN, NAN, req->z, NAN, NAN, NAN, NAN, NAN, NAN,
                      NAN, NAN, NAN, NAN, NAN, NAN, NAN, req->frame_id, false,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        ya_srv_ = create_service<bumblebee::srv::SetYaw>("set_yaw",
            [this](const bumblebee::srv::SetYaw::Request::SharedPtr req,
                   bumblebee::srv::SetYaw::Response::SharedPtr res) {
                serve(_YAW, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, req->yaw,
                      NAN, NAN, NAN, NAN, NAN, NAN, NAN, req->frame_id, false,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        yr_srv_ = create_service<bumblebee::srv::SetYawRate>("set_yaw_rate",
            [this](const bumblebee::srv::SetYawRate::Request::SharedPtr req,
                   bumblebee::srv::SetYawRate::Response::SharedPtr res) {
                serve(_YAW_RATE, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN,
                      NAN, NAN, req->yaw_rate, NAN, NAN, NAN, NAN, "", false,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        sp_srv_ = create_service<bumblebee::srv::SetPosition>("set_position",
            [this](const bumblebee::srv::SetPosition::Request::SharedPtr req,
                   bumblebee::srv::SetPosition::Response::SharedPtr res) {
                serve(POSITION, req->x, req->y, req->z, NAN, NAN, NAN, NAN, NAN, req->yaw,
                      NAN, NAN, NAN, NAN, NAN, NAN, NAN, req->frame_id, req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        sv_srv_ = create_service<bumblebee::srv::SetVelocity>("set_velocity",
            [this](const bumblebee::srv::SetVelocity::Request::SharedPtr req,
                   bumblebee::srv::SetVelocity::Response::SharedPtr res) {
                serve(VELOCITY, NAN, NAN, NAN, req->vx, req->vy, req->vz, NAN, NAN, req->yaw,
                      NAN, NAN, NAN, NAN, NAN, NAN, NAN, req->frame_id, req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        sa_srv_ = create_service<bumblebee::srv::SetAttitude>("set_attitude",
            [this](const bumblebee::srv::SetAttitude::Request::SharedPtr req,
                   bumblebee::srv::SetAttitude::Response::SharedPtr res) {
                serve(ATTITUDE, NAN, NAN, NAN, NAN, NAN, NAN, req->roll, req->pitch, req->yaw,
                      NAN, NAN, NAN, NAN, NAN, req->thrust, NAN, req->frame_id, req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        sr_srv_ = create_service<bumblebee::srv::SetRates>("set_rates",
            [this](const bumblebee::srv::SetRates::Request::SharedPtr req,
                   bumblebee::srv::SetRates::Response::SharedPtr res) {
                serve(RATES, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN, NAN,
                      req->roll_rate, req->pitch_rate, req->yaw_rate, NAN, NAN, req->thrust, NAN, "", req->auto_arm,
                      res->success, res->message); },
            srv_qos, cb_grp_srvs_);
        ld_srv_ = create_service<std_srvs::srv::Trigger>("land",
            [this](const std_srvs::srv::Trigger::Request::SharedPtr req,
                   std_srvs::srv::Trigger::Response::SharedPtr res) { land(req, res); },
            srv_qos, cb_grp_land_);
        rl_srv_ = create_service<std_srvs::srv::Trigger>("release",
            [this](const std_srvs::srv::Trigger::Request::SharedPtr req,
                   std_srvs::srv::Trigger::Response::SharedPtr res) { release(req, res); },
            srv_qos, cb_grp_srvs_);

        // Setpoint timer (in cb_grp_concurrent_ so it fires even while service callbacks block)
        setpoint_timer_ = create_wall_timer(
            std::chrono::duration<double>(1.0 / setpoint_rate_),
            [this]() { publishSetpoint(); }, cb_grp_concurrent_);
        setpoint_timer_->cancel();

        position_msg_.header.frame_id = local_frame_;
        position_raw_msg_.header.frame_id = local_frame_;
        position_raw_msg_.coordinate_frame = PositionTarget::FRAME_LOCAL_NED;

        RCLCPP_INFO(get_logger(), "ready");
    }

private:
    // Parameters
    string mavros_;
    string local_frame_;
    string fcu_frame_;
    rclcpp::Duration transform_timeout_{0, 0};
    rclcpp::Duration telemetry_transform_timeout_{0, 0};
    rclcpp::Duration offboard_timeout_{0, 0};
    rclcpp::Duration land_timeout_{0, 0};
    rclcpp::Duration arming_timeout_{0, 0};
    rclcpp::Duration arm_settle_time_{0, 0};
    rclcpp::Duration arm_hold_after_land_{0, 0};
    rclcpp::Duration local_position_timeout_{0, 0};
    rclcpp::Duration state_timeout_{0, 0};
    rclcpp::Duration state_watchdog_timeout_{0, 0};
    rclcpp::Duration velocity_timeout_{0, 0};
    rclcpp::Duration global_position_timeout_{0, 0};
    rclcpp::Duration battery_timeout_{0, 0};
    rclcpp::Duration manual_control_timeout_{0, 0};
    double default_speed_;
    bool auto_release_;
    bool land_only_in_offboard_;
    bool nav_from_sp_;
    bool check_kill_switch_;
    double setpoint_rate_;
    double setpoint_smooth_alpha_;
    bool smooth_initialized_ = false;
    double smoothed_x_ = 0.0, smoothed_y_ = 0.0, smoothed_z_ = 0.0;
    double smoothed_yaw_ = 0.0;
    std::map<string, string> reference_frames_;
    string terrain_frame_mode_;

    // tf2
    tf2_ros::Buffer tf_buffer_;
    tf2_ros::TransformListener tf_listener_;
    std::shared_ptr<tf2_ros::TransformBroadcaster> transform_broadcaster_;
    std::shared_ptr<tf2_ros::StaticTransformBroadcaster> static_transform_broadcaster_;

    // Publishers
    rclcpp::Publisher<PoseStamped>::SharedPtr attitude_pub_, position_pub_;
    rclcpp::Publisher<PositionTarget>::SharedPtr position_raw_pub_;
    rclcpp::Publisher<AttitudeTarget>::SharedPtr attitude_raw_pub_;
    rclcpp::Publisher<TwistStamped>::SharedPtr rates_pub_;
    rclcpp::Publisher<Thrust>::SharedPtr thrust_pub_;
    rclcpp::Publisher<bumblebee::msg::State>::SharedPtr state_pub_;

    // Service clients
    rclcpp::Client<mavros_msgs::srv::CommandBool>::SharedPtr arming_;
    rclcpp::Client<mavros_msgs::srv::SetMode>::SharedPtr set_mode_;

    // Subscribers
    rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr state_sub_;
    rclcpp::Subscription<TwistStamped>::SharedPtr velocity_sub_;
    rclcpp::Subscription<NavSatFix>::SharedPtr global_pos_sub_;
    rclcpp::Subscription<BatteryState>::SharedPtr battery_sub_;
    rclcpp::Subscription<mavros_msgs::msg::StatusText>::SharedPtr statustext_sub_;
    rclcpp::Subscription<mavros_msgs::msg::ManualControl>::SharedPtr manual_control_sub_;
    rclcpp::Subscription<PoseStamped>::SharedPtr local_pos_sub_;
    rclcpp::Subscription<Altitude>::SharedPtr altitude_sub_;
    rclcpp::Subscription<Range>::SharedPtr range_sub_;

    // Service servers
    rclcpp::Service<bumblebee::srv::GetTelemetry>::SharedPtr gt_srv_;
    rclcpp::Service<bumblebee::srv::Navigate>::SharedPtr na_srv_;
    rclcpp::Service<bumblebee::srv::NavigateGlobal>::SharedPtr ng_srv_;
    rclcpp::Service<bumblebee::srv::SetAltitude>::SharedPtr sl_srv_;
    rclcpp::Service<bumblebee::srv::SetYaw>::SharedPtr ya_srv_;
    rclcpp::Service<bumblebee::srv::SetYawRate>::SharedPtr yr_srv_;
    rclcpp::Service<bumblebee::srv::SetPosition>::SharedPtr sp_srv_;
    rclcpp::Service<bumblebee::srv::SetVelocity>::SharedPtr sv_srv_;
    rclcpp::Service<bumblebee::srv::SetAttitude>::SharedPtr sa_srv_;
    rclcpp::Service<bumblebee::srv::SetRates>::SharedPtr sr_srv_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr ld_srv_, rl_srv_;

    // Timer
    rclcpp::TimerBase::SharedPtr setpoint_timer_;

    // Callback groups: srvs and land can block; concurrent runs alongside them
    rclcpp::CallbackGroup::SharedPtr cb_grp_telemetry_;
    rclcpp::CallbackGroup::SharedPtr cb_grp_srvs_;
    rclcpp::CallbackGroup::SharedPtr cb_grp_land_;
    rclcpp::CallbackGroup::SharedPtr cb_grp_concurrent_;

    // Guards the setpoint state and state_, local_position_, statustext_ shared
    // between serve()/release() (srvs group), land() (land group) and
    // handleState()/the setpoint timer (concurrent group). Never held while
    // waiting for the FCU, so the setpoint stream keeps flowing.
    std::mutex mutex_;

    // Setpoint state
    TransformStamped target_, setpoint_;
    geometry_msgs::msg::TransformStamped body_;
    geometry_msgs::msg::TransformStamped terrain_;
    PoseStamped nav_start_;
    PointStamped setpoint_position_;
    PointStamped setpoint_altitude_;
    Vector3Stamped setpoint_velocity_;
    float setpoint_yaw_ = 0, setpoint_roll_ = 0, setpoint_pitch_ = 0;
    Vector3 setpoint_rates_;
    string yaw_frame_id_;
    float setpoint_thrust_ = 0;
    float nav_speed_ = 0;
    float setpoint_lat_ = NAN, setpoint_lon_ = NAN;
    // serve() and land() run in different callback groups: only one may command at a time
    std::atomic<bool> busy_{false};
    // Persistent /land sequence cancels the original auto_arm run even if land() times out.
    std::atomic<uint64_t> land_seq_{0};
    uint64_t serve_land_seq_ = 0;  // only the mutually exclusive serve callbacks write this
    std::atomic<bool> arm_in_doubt_{false};
    // monotonicNs() when the last /land finished, 0 = none: auto_arm stays
    // cancelled for arm_hold_after_land_ after it (checkArmCancel())
    std::atomic<int64_t> land_done_ns_{0};
    // Set while land() switches to AUTO.LAND: that exit from OFFBOARD is our own
    std::atomic<bool> landing_{false};
    bool wait_armed_ = false;
    // monotonicNs() when the current navigate segment started (when nav_start_ was set)
    int64_t nav_start_ns_ = 0;
    // monotonicNs() when the last FCU state arrived (the state watchdog in publishSetpoint())
    int64_t state_rx_ns_ = 0;
    // steadyNs() at the active publisher's last tick or explicit stream start.
    // Unlike state_rx_ns_, this never depends on /clock or HEARTBEAT delivery.
    int64_t last_setpoint_tick_ns_ = 0;  // mutex_ only
    int64_t state_rx_steady_ns_ = 0;     // valid State receipt, mutex_ only
    int64_t publisher_stopped_steady_ns_ = 0; // post-stall resume gate, mutex_ only
    // monotonicNs() when offboardAndArm() last completed, 0 = none. While
    // (now - this) < arm_settle_time_, nav interpolation is held at nav_start_ so
    // motor spin-up vibration and the resulting noisy single-marker ArUco pose
    // don't trick the controller into thinking the drone is already climbing
    // while it's still on the ground.
    int64_t arm_complete_ns_ = 0;
    bool nav_from_sp_flag_ = false;
    enum setpoint_type_t setpoint_type_ = NONE;
    enum yaw_type_t setpoint_yaw_type_ = YAW;

    // Last published
    PoseStamped setpoint_pose_local_;
    Vector3Stamped setpoint_velocity_local_;
    float yaw_local_ = 0;
    PoseStamped position_msg_;
    PositionTarget position_raw_msg_;

    // Telemetry
    mavros_msgs::msg::State state_;
    bool prev_armed_ = false;
    mavros_msgs::msg::StatusText statustext_;
    mavros_msgs::msg::ManualControl manual_control_;
    PoseStamped local_position_;
    TwistStamped velocity_;
    NavSatFix global_position_;
    // Leaf lock: never wait under it and never acquire it while holding mutex_.
    std::mutex telemetry_mutex_;
    builtin_interfaces::msg::Time battery_stamp_;
    double battery_voltage_ = NAN, battery_cell0_ = NAN;
    int64_t srvs_run_start_ns_ = 0, srvs_last_exit_ns_ = 0; // srvs group only
    struct FlightRunGuard {
        SimpleOffboard* owner;
        ~FlightRunGuard() { owner->srvs_last_exit_ns_ = owner->monotonicNs(); }
    };
    FlightRunGuard beginFlightRun() {
        srvs_run_start_ns_ = flightRunStart(srvs_run_start_ns_, srvs_last_exit_ns_, monotonicNs());
        return FlightRunGuard{this};
    }
    NavSatFix globalSnapshot() {
        std::lock_guard<std::mutex> lock(telemetry_mutex_);
        return global_position_;
    }

    bool timeout(const builtin_interfaces::msg::Time& stamp, const rclcpp::Duration& dur) {
        if (stampIsZero(stamp)) return true;
        return (now() - rclcpp::Time(stamp, RCL_ROS_TIME)) > dur;
    }

    // Clock for navigate segment progress, arm settle and the FCU state watchdog:
    // the steady clock on the drone (immune to NTP steps), the simulation clock
    // under use_sim_time. Gazebo runs at ~25% of real time and PX4 SITL in lockstep
    // with it, so wall seconds would fly 4x the requested speed there; the
    // simulation clock never steps.
    int64_t monotonicNs() {
        return get_clock()->ros_time_is_active() ? now().nanoseconds() : steadyNs();
    }

    // Copy of the latest FCU state, safe to read from any callback group
    mavros_msgs::msg::State fcuState() {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_;
    }

    // Latest FCU status text received after start, or "" (explains a timeout)
    string statusTextSince(const rclcpp::Time& start) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stampIsZero(statustext_.header.stamp) ||
            rclcpp::Time(statustext_.header.stamp, RCL_ROS_TIME) <= start) return "";
        return statustext_.text;
    }

    // Stop the setpoint stream and forget the target. Caller holds mutex_.
    void resetSetpoint() {
        if (setpoint_timer_) setpoint_timer_->cancel();
        setpoint_type_ = NONE;
        last_setpoint_tick_ns_ = 0;
        setpoint_position_.header.frame_id = "";
        setpoint_altitude_.header.frame_id = "";
        yaw_frame_id_ = "";
    }

    // The pilot or the failsafe has control now, or PX4 lost our stream: stop
    // streaming, so that a returning stream (e.g. after a MAVROS restart) cannot
    // pull the vehicle back into OFFBOARD in the middle of a landing or a pilot
    // takeover (S4). Caller holds mutex_.
    void stopStream(const string& reason, bool warn = true) {
        bool streaming = setpoint_timer_ && !setpoint_timer_->is_canceled();
        resetSetpoint();
        nav_from_sp_flag_ = false;
        arm_complete_ns_ = 0;
        publishState();
        if (streaming) {
            if (warn) RCLCPP_WARN(get_logger(), "%s: setpoint stream stopped", reason.c_str());
            else RCLCPP_INFO(get_logger(), "%s: setpoint stream stopped", reason.c_str());
        }
    }

    // Caller holds mutex_. Shared by the timer and serve()'s direct publish path,
    // so a queued service cannot bypass the first post-stall timer callback.
    bool stopOnPublisherResume(bool include_starting_stream = false) {
        const int64_t tick_ns = steadyNs();
        const bool active = setpoint_type_ != NONE && setpoint_timer_ &&
                            (include_starting_stream || !setpoint_timer_->is_canceled());
        if (!setpointResumeBlocked(active, state_.armed || arm_in_doubt_.load(),
                                   last_setpoint_tick_ns_, tick_ns)) return false;
        char reason[176];
        std::snprintf(reason, sizeof(reason),
                      "Setpoint publisher paused for %.2f wall s while armed or ARM unresolved; "
                      "not resuming an old stream, send a fresh command",
                      (tick_ns - last_setpoint_tick_ns_) * 1e-9);
        publisher_stopped_steady_ns_ = tick_ns;
        stopStream(reason);
        return true;
    }

    void handleState(const mavros_msgs::msg::State& s) {
        std::lock_guard<std::mutex> lock(mutex_);
        // Receipt time is authoritative, but reject already old latched State replays.
        const bool valid_stamp = !timeout(s.header.stamp, state_timeout_);
        state_rx_ns_ = valid_stamp ? monotonicNs() : 0;
        state_rx_steady_ns_ = valid_stamp ? steadyNs() : 0;
        bool armed_edge_off = prev_armed_ && !s.armed;
        // PX4 left OFFBOARD by itself in the air: the pilot switched mode or moved
        // the sticks, or a failsafe fired (or a script's guard called set_mode
        // AUTO.LAND directly). Our own /land (AUTO.LAND) is the only exit we ask for.
        bool from_offboard = state_.mode == "OFFBOARD" && s.mode != "OFFBOARD";
        bool own_land = from_offboard && landing_ && s.mode == "AUTO.LAND";
        bool left_offboard = from_offboard && s.armed && !own_land;
        prev_armed_ = s.armed;
        state_ = s;
        if (s.mode != "OFFBOARD") {
            nav_from_sp_flag_ = false;
        }
        // Disarm while still in OFFBOARD = either /land cancelled the timer
        // itself or PX4 emergency-disarmed us. In the second case the timer
        // would otherwise keep streaming a stale setpoint forever, leaving
        // PX4 glued to OFFBOARD and re-arming the next flight on a phantom
        // target. Reset internal state to the post-boot baseline.
        if (armed_edge_off) {
            resetSetpoint();
            nav_from_sp_flag_ = false;
            arm_complete_ns_ = 0;
        }
        if (own_land) stopStream("Own /land confirmed AUTO.LAND", false);
        if (left_offboard) {
            stopStream("PX4 left OFFBOARD for " + s.mode + " while armed, not through /land "
                       "(the pilot, a failsafe or a direct set_mode)");
        }
    }

    void publishBodyFrame() {
        if (body_.child_frame_id.empty()) return;
        if (!stampIsZero(body_.header.stamp) &&
            body_.header.stamp.sec == local_position_.header.stamp.sec &&
            body_.header.stamp.nanosec == local_position_.header.stamp.nanosec) {
            return; // avoid TF_REPEATED_DATA
        }
        tf2::Quaternion q;
        q.setRPY(0, 0, tf2::getYaw(local_position_.pose.orientation));
        body_.transform.rotation = tf2::toMsg(q);
        body_.transform.translation.x = local_position_.pose.position.x;
        body_.transform.translation.y = local_position_.pose.position.y;
        body_.transform.translation.z = local_position_.pose.position.z;
        body_.header.frame_id = local_position_.header.frame_id;
        body_.header.stamp = local_position_.header.stamp;
        transform_broadcaster_->sendTransform(body_);
    }

    void handleLocalPosition(const PoseStamped& pose) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            local_position_ = pose;
        }
        publishBodyFrame(); // reads local_position_ on the only thread that writes it
    }

    bool waitTransform(const string& target, const string& source,
                       const rclcpp::Time& /*stamp*/, const rclcpp::Duration& dur) {
        // Use tf2::TimePointZero (t=0) to check for the latest available transform.
        // Checking against the exact stamp fails when TF data lags behind ROS clock
        // by even a few milliseconds, as tf2 does not extrapolate.
        const rclcpp::Time t0(0, 0, RCL_ROS_TIME);
        rclcpp::Rate r(100);
        auto start = now();
        while (rclcpp::ok()) {
            if (now() - start > dur) return false;
            if (tf_buffer_.canTransform(target, source, t0)) return true;
            r.sleep();
        }
        return false;
    }

    void publishTerrain(double distance, const builtin_interfaces::msg::Time& stamp_msg) {
        rclcpp::Time stamp(stamp_msg, RCL_ROS_TIME);
        if (!waitTransform(local_frame_, body_.child_frame_id, stamp, rclcpp::Duration::from_seconds(0.1))) return;
        auto t = tf_buffer_.lookupTransform(local_frame_, body_.child_frame_id, stamp);
        t.child_frame_id = terrain_.child_frame_id;
        t.transform.translation.z -= distance;
        std::lock_guard<std::mutex> lock(mutex_); // the static broadcaster is shared with publishTarget()
        static_transform_broadcaster_->sendTransform(t);
    }

    void handleAltitude(const Altitude& alt) {
        if (!std::isfinite(alt.bottom_clearance)) return;
        publishTerrain(alt.bottom_clearance, alt.header.stamp);
    }

    void handleRange(const Range& range) {
        if (!std::isfinite(range.range)) return;
        publishTerrain(range.range, range.header.stamp);
    }

    void getTelemetry(const bumblebee::srv::GetTelemetry::Request::SharedPtr req,
                      bumblebee::srv::GetTelemetry::Response::SharedPtr res) {
        const rclcpp::Time stamp(0, 0, RCL_ROS_TIME); // use latest available transform

        string frame_id = req->frame_id.empty() ? local_frame_ : req->frame_id;
        res->frame_id = frame_id;
        res->x = res->y = res->z = NAN;
        res->lat = res->lon = res->alt = NAN;
        res->vx = res->vy = res->vz = NAN;
        res->roll = res->pitch = res->yaw = NAN;
        res->roll_rate = res->pitch_rate = res->yaw_rate = NAN;
        res->voltage = res->cell_voltage = NAN;

        TwistStamped velocity;
        NavSatFix global_position;
        builtin_interfaces::msg::Time battery_stamp;
        double battery_voltage, battery_cell0;
        {
            std::lock_guard<std::mutex> lock(telemetry_mutex_);
            velocity = velocity_; global_position = global_position_;
            battery_stamp = battery_stamp_; battery_voltage = battery_voltage_; battery_cell0 = battery_cell0_;
        }
        auto state = fcuState();
        if (stateFresh()) {
            res->connected = state.connected;
            res->armed = state.armed;
            res->mode = state.mode;
        }

        try {
            waitTransform(frame_id, fcu_frame_, stamp, telemetry_transform_timeout_);
            auto transform = tf_buffer_.lookupTransform(frame_id, fcu_frame_, stamp);
            res->x = transform.transform.translation.x;
            res->y = transform.transform.translation.y;
            res->z = transform.transform.translation.z;
            double yaw, pitch, roll;
            tf2::getEulerYPR(transform.transform.rotation, yaw, pitch, roll);
            res->yaw = yaw;
            res->pitch = pitch;
            res->roll = roll;
        } catch (const tf2::TransformException& e) {
            RCLCPP_DEBUG(get_logger(), "%s", e.what());
        }

        if (!timeout(velocity.header.stamp, velocity_timeout_)) {
            try {
                waitTransform(frame_id, fcu_frame_, rclcpp::Time(velocity.header.stamp, RCL_ROS_TIME),
                              telemetry_transform_timeout_);
                Vector3Stamped vec, vec_out;
                vec.header = velocity.header;
                vec.vector = velocity.twist.linear;
                tf_buffer_.transform(vec, vec_out, frame_id);
                res->vx = vec_out.vector.x;
                res->vy = vec_out.vector.y;
                res->vz = vec_out.vector.z;
            } catch (const tf2::TransformException&) {}
            res->yaw_rate = velocity.twist.angular.z;
            res->pitch_rate = velocity.twist.angular.y;
            res->roll_rate = velocity.twist.angular.x;
        }

        if (!timeout(global_position.header.stamp, global_position_timeout_)) {
            res->lat = global_position.latitude;
            res->lon = global_position.longitude;
            res->alt = global_position.altitude;
        }

        if (!timeout(battery_stamp, battery_timeout_)) {
            res->voltage = battery_voltage;
            res->cell_voltage = battery_cell0;
        }
    }

    // Throws while /land is running and for arm_hold_after_land_ after it: auto_arm
    // must not start the motors then. The hold covers a navigate(auto_arm) sent
    // before /land that still waited in the srvs queue (e.g. behind a get_telemetry
    // blocked on TF) while /land ran in its own group, failed on the ground ("not
    // in OFFBOARD") and returned: it would arm right after the land request.
    void checkArmCancel() {
        if (land_seq_.load() != serve_land_seq_) throw std::runtime_error("Auto-arm cancelled: land requested");
        int64_t done = land_done_ns_;
        if (done == 0) return;
        int64_t ago = monotonicNs() - done;
        if (ago >= 0 && ago < arm_hold_after_land_.nanoseconds()) { // < 0: simulation restarted
            char msg[96];
            std::snprintf(msg, sizeof(msg), "Auto-arm cancelled: land requested %.1f s ago, not arming",
                          ago * 1e-9);
            throw std::runtime_error(msg);
        }
    }

    // Wait for a service response, giving up early when auto_arm is cancelled
    template <typename FutureT>
    bool waitFuture(FutureT& future, std::chrono::milliseconds timeout) {
        auto deadline = std::chrono::steady_clock::now() + timeout;
        while (future.wait_for(std::chrono::milliseconds(50)) != std::future_status::ready) {
            checkArmCancel();
            if (std::chrono::steady_clock::now() > deadline) return false;
        }
        return true;
    }

    void offboardAndArm() {
        rclcpp::Rate r(10);

        auto state = fcuState();
        if (state.armed && state.mode == "OFFBOARD") return; // flying already, nothing to switch
        // The pilot may have armed with the RC since serve() checked: never take over
        checkPilot(state);
        checkArmCancel();

        if (state.mode != "OFFBOARD") {
            auto start = now();
            const int64_t mode_start_ns = monotonicNs();
            RCLCPP_INFO(get_logger(), "switch to OFFBOARD");
            auto sm_req = std::make_shared<mavros_msgs::srv::SetMode::Request>();
            sm_req->custom_mode = "OFFBOARD";
            auto future = set_mode_->async_send_request(sm_req);
            if (!waitFuture(future, std::chrono::seconds(10))) {
                throw std::runtime_error("Error calling set_mode service");
            }

            while (rclcpp::ok()) {
                state = fcuState();
                if (state.mode == "OFFBOARD") break;
                checkArmCancel();
                checkPilot(state);
                if (monotonicNs() - mode_start_ns > offboard_timeout_.nanoseconds()) {
                    string report = "OFFBOARD timed out";
                    string text = statusTextSince(start);
                    if (!text.empty()) report += ": " + text;
                    throw std::runtime_error(report);
                }
                r.sleep();
            }
        }

        if (!state.armed) {
            const auto start = now();
            int64_t deadline_ns = monotonicNs() + arming_timeout_.nanoseconds();
            int64_t last_send_ns = 0, last_reply_ns = 0;
            ArmReply last_reply = ArmReply::REJECTED;
            auto arm_req = std::make_shared<mavros_msgs::srv::CommandBool::Request>();
            arm_req->value = true;
            try {
                while (rclcpp::ok()) {
                    checkArmCancel();  // a cancellation wins even if State now reports armed
                    int64_t rx_ns;
                    {
                        std::lock_guard<std::mutex> lock(mutex_);
                        state = state_;
                        rx_ns = state_rx_ns_;
                    }
                    const int64_t t = monotonicNs();
                    // A stale or disconnected State sends nothing; wait until the deadline.
                    const bool fresh = state.connected && rx_ns > 0 && t >= rx_ns &&
                                       t - rx_ns <= state_timeout_.nanoseconds();
                    if (fresh && state.armed) {
                        checkPilot(state);
                        arm_in_doubt_ = false;
                        break;
                    }
                    if (fresh && state.mode != "OFFBOARD")
                        throw std::runtime_error("Copter left OFFBOARD for " + state.mode + " before arming, not arming");
                    if (t > deadline_ns) {
                        string report = last_reply == ArmReply::ACCEPTED ?
                            "ARM accepted but vehicle not reported armed" : "Arming timed out";
                        string text = statusTextSince(start);
                        if (!text.empty()) report += ": " + text;
                        throw std::runtime_error(report);
                    }
                    if (armSendAllowed(state, rx_ns, t, last_reply, last_send_ns, last_reply_ns)) {
                        last_send_ns = t;
                        arm_in_doubt_ = true;
                        auto future = arming_->async_send_request(arm_req);
                        // MAVROS 2.14 waits 5 seconds for ACK. Never queue another ARM behind it.
                        const bool replied = future.wait_for(std::chrono::seconds(6)) == std::future_status::ready;
                        bool success = false;
                        uint8_t result = 0;
                        if (replied) { auto res = future.get(); success = res->success; result = res->result; }
                        last_reply_ns = monotonicNs();
                        last_reply = classifyArmReply(replied, success, result);
                        if (last_reply == ArmReply::REJECTED) arm_in_doubt_ = false;
                        if (last_reply == ArmReply::ACCEPTED)
                            deadline_ns = std::max(deadline_ns, last_reply_ns + int64_t{2500000000});
                        RCLCPP_INFO(get_logger(), "arm response: replied=%d success=%d result=%d", replied, success, result);
                    }
                    r.sleep();
                }
                if (!rclcpp::ok()) throw std::runtime_error("Auto-arm cancelled: node shutting down");
            } catch (const std::exception& e) {
                string report = e.what();
                if (arm_in_doubt_) report += "; " + settleArm();
                arm_in_doubt_ = false;
                throw std::runtime_error(report);
            }
        }
    }

    string settleArm() {
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(6);
        while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline) {
            const auto state = fcuState();
            if (!disarmAllowed(state))
                return "armed in " + state.mode + ": pilot or PX4 failsafe has control, not disarming";
            auto request = std::make_shared<mavros_msgs::srv::CommandBool::Request>();
            request->value = false;  // non-forced; PX4 must independently confirm landed
            auto future = arming_->async_send_request(request);
            const auto remaining = std::max(std::chrono::steady_clock::duration::zero(),
                                            deadline - std::chrono::steady_clock::now());
            if (future.wait_for(remaining) == std::future_status::ready && future.get()->success)
                return "disarmed on the ground";
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
        return "DISARM not confirmed: motors may be running until PX4 auto-disarms; hard stop = RC kill switch";
    }

    // Caller holds mutex_ (runs inside publish())
    void getNavigateSetpoint(float speed, Point& nav_setpoint) {
        // Segment progress runs on monotonicNs(), not on the stamp: serve()
        // publishes with Time(0) (latest TF), which put the first setpoint ~1e8 m
        // behind the start (A1), and the ROS clock follows NTP steps.
        int64_t now_ns = monotonicNs();
        bool in_arm_settle = arm_complete_ns_ != 0 &&
                             now_ns - arm_complete_ns_ < arm_settle_time_.nanoseconds();
        if (wait_armed_ || in_arm_settle) {
            nav_start_ns_ = now_ns; // hold the start until the motors have spun up
        }
        nav_setpoint = navigateSetpoint(nav_start_.pose.position, setpoint_pose_local_.pose.position,
                                        speed, nav_start_ns_, now_ns);
    }

    PoseStamped globalToLocal(const NavSatFix& global_position, double lat, double lon) {
        auto earth = GeographicLib::Geodesic::WGS84();
        double _, distance, azimuth;
        earth.Inverse(global_position.latitude, global_position.longitude, lat, lon, distance, _, azimuth);
        double azimuth_radians = azimuth * M_PI / 180;
        double x_offset = distance * sin(azimuth_radians);
        double y_offset = distance * cos(azimuth_radians);

        rclcpp::Time gp_stamp(global_position.header.stamp, RCL_ROS_TIME);
        if (!waitTransform(local_frame_, fcu_frame_, gp_stamp, rclcpp::Duration::from_seconds(0.2))) {
            throw std::runtime_error("No local position");
        }
        auto local = tf_buffer_.lookupTransform(local_frame_, fcu_frame_, gp_stamp);

        PoseStamped pose;
        pose.header.stamp = global_position.header.stamp;
        pose.header.frame_id = local_frame_;
        pose.pose.position.x = local.transform.translation.x + x_offset;
        pose.pose.position.y = local.transform.translation.y + y_offset;
        pose.pose.orientation.w = 1;
        return pose;
    }

    void publishTarget(rclcpp::Time stamp, bool _static = false) {
        bool single_frame = (setpoint_position_.header.frame_id == setpoint_altitude_.header.frame_id);

        if (setpoint_yaw_type_ == YAW || setpoint_yaw_type_ == YAW_RATE) {
            if (setpoint_altitude_.header.frame_id == yaw_frame_id_) {
                target_.transform.rotation = quatFromYaw(setpoint_yaw_);
            } else {
                single_frame = false;
                target_.transform.rotation = quatFromYaw(yaw_local_);
            }
        } else if (setpoint_yaw_type_ == TOWARDS) {
            single_frame = false;
            target_.transform.rotation = quatFromYaw(yaw_local_);
        }

        if (_static && single_frame) {
            target_.header.frame_id = setpoint_position_.header.frame_id;
            target_.header.stamp = stamp;
            target_.transform.translation.x = setpoint_position_.point.x;
            target_.transform.translation.y = setpoint_position_.point.y;
            target_.transform.translation.z = setpoint_position_.point.z;
        } else if (!_static) {
            target_.header = setpoint_pose_local_.header;
            target_.transform.translation.x = setpoint_pose_local_.pose.position.x;
            target_.transform.translation.y = setpoint_pose_local_.pose.position.y;
            target_.transform.translation.z = setpoint_pose_local_.pose.position.z;
        }
        static_transform_broadcaster_->sendTransform(target_);
    }

    // Caller holds mutex_. The ROS stamp is captured by the caller before this
    // final wall guard. A pause before stamp capture is detected here because
    // last_setpoint_tick_ns_ contains the earlier captured wall checkpoint; a
    // pause after this guard retains the old stamp for the independent filter.
    bool publish(const rclcpp::Time stamp) {
        if (setpoint_type_ == NONE || stopOnPublisherResume(true)) return false;

        position_raw_msg_.header.stamp = stamp;

        if (setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL || setpoint_type_ == POSITION) {
            setpoint_position_.header.stamp = stamp;
            setpoint_altitude_.header.stamp = stamp;
            try {
                auto xy = tf_buffer_.transform(setpoint_position_, local_frame_,
                                               tf2::durationFromSec(0.05));
                setpoint_pose_local_.header = xy.header;
                setpoint_pose_local_.pose.position.x = xy.point.x;
                setpoint_pose_local_.pose.position.y = xy.point.y;
            } catch (tf2::TransformException& ex) {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000, "can't transform: %s", ex.what());
            }
            try {
                setpoint_pose_local_.pose.position.z = tf_buffer_.transform(
                    setpoint_altitude_, local_frame_, tf2::durationFromSec(0.05)).point.z;
            } catch (tf2::TransformException& ex) {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000, "can't transform: %s", ex.what());
            }
        }

        if (setpoint_yaw_type_ == YAW) {
            try {
                QuaternionStamped q;
                q.header.stamp = stamp;
                q.header.frame_id = yaw_frame_id_;
                q.quaternion = quatFromYaw(setpoint_yaw_);
                yaw_local_ = tf2::getYaw(tf_buffer_.transform(q, local_frame_,
                                                               tf2::durationFromSec(0.05)).quaternion);
            } catch (tf2::TransformException& ex) {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000, "can't transform: %s", ex.what());
            }
        }

        if (setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL) {
            getNavigateSetpoint(nav_speed_, position_msg_.pose.position);
            if (setpoint_yaw_type_ == TOWARDS) {
                yaw_local_ = atan2(position_msg_.pose.position.y - nav_start_.pose.position.y,
                                   position_msg_.pose.position.x - nav_start_.pose.position.x);
            }
            position_msg_.pose.orientation = quatFromYaw(yaw_local_);
        }

        if (setpoint_type_ == POSITION) {
            position_msg_ = setpoint_pose_local_;
            position_msg_.pose.orientation = quatFromYaw(yaw_local_);
        }

        if (setpoint_type_ == POSITION || setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL) {
            position_msg_.header.stamp = stamp;

            if (!smooth_initialized_) {
                smoothed_x_ = position_msg_.pose.position.x;
                smoothed_y_ = position_msg_.pose.position.y;
                smoothed_z_ = position_msg_.pose.position.z;
                smoothed_yaw_ = yaw_local_;
                smooth_initialized_ = true;
            } else {
                const double a = setpoint_smooth_alpha_;
                smoothed_x_ = a * position_msg_.pose.position.x + (1.0 - a) * smoothed_x_;
                smoothed_y_ = a * position_msg_.pose.position.y + (1.0 - a) * smoothed_y_;
                smoothed_z_ = a * position_msg_.pose.position.z + (1.0 - a) * smoothed_z_;
                double dy = std::atan2(std::sin(yaw_local_ - smoothed_yaw_),
                                       std::cos(yaw_local_ - smoothed_yaw_));
                smoothed_yaw_ += a * dy;
            }
            position_msg_.pose.position.x = smoothed_x_;
            position_msg_.pose.position.y = smoothed_y_;
            position_msg_.pose.position.z = smoothed_z_;
            position_msg_.pose.orientation = quatFromYaw(smoothed_yaw_);

            if (setpoint_yaw_type_ == YAW || setpoint_yaw_type_ == TOWARDS) {
                position_pub_->publish(position_msg_);
            } else {
                position_raw_msg_.type_mask = PositionTarget::IGNORE_VX + PositionTarget::IGNORE_VY +
                                              PositionTarget::IGNORE_VZ + PositionTarget::IGNORE_AFX +
                                              PositionTarget::IGNORE_AFY + PositionTarget::IGNORE_AFZ +
                                              PositionTarget::IGNORE_YAW;
                position_raw_msg_.yaw_rate = setpoint_rates_.z;
                position_raw_msg_.position = position_msg_.pose.position;
                position_raw_pub_->publish(position_raw_msg_);
            }

            if (!setpoint_.child_frame_id.empty()) {
                if (rclcpp::Time(setpoint_.header.stamp, RCL_ROS_TIME) >= rclcpp::Time(position_msg_.header.stamp, RCL_ROS_TIME)) {
                    return true;
                }
                setpoint_.transform.translation.x = position_msg_.pose.position.x;
                setpoint_.transform.translation.y = position_msg_.pose.position.y;
                setpoint_.transform.translation.z = position_msg_.pose.position.z;
                setpoint_.transform.rotation = position_msg_.pose.orientation;
                setpoint_.header = position_msg_.header;
                transform_broadcaster_->sendTransform(setpoint_);
            }
            publishTarget(stamp);
        }

        if (setpoint_type_ == VELOCITY) {
            setpoint_velocity_.header.stamp = stamp;
            try {
                setpoint_velocity_local_ = tf_buffer_.transform(setpoint_velocity_, local_frame_,
                                                                 tf2::durationFromSec(0.05));
            } catch (tf2::TransformException& ex) {
                RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000, "can't transform: %s", ex.what());
            }
            position_raw_msg_.type_mask = PositionTarget::IGNORE_PX + PositionTarget::IGNORE_PY +
                                          PositionTarget::IGNORE_PZ + PositionTarget::IGNORE_AFX +
                                          PositionTarget::IGNORE_AFY + PositionTarget::IGNORE_AFZ;
            position_raw_msg_.type_mask += setpoint_yaw_type_ == YAW ? PositionTarget::IGNORE_YAW_RATE
                                                                      : PositionTarget::IGNORE_YAW;
            position_raw_msg_.velocity = setpoint_velocity_local_.vector;
            position_raw_msg_.yaw = yaw_local_;
            position_raw_msg_.yaw_rate = setpoint_rates_.z;
            position_raw_pub_->publish(position_raw_msg_);
        }

        if (setpoint_type_ == ATTITUDE) {
            PoseStamped msg;
            msg.header.stamp = stamp;
            msg.header.frame_id = local_frame_;
            msg.pose.orientation = quatFromRPY(setpoint_roll_, setpoint_pitch_, yaw_local_);
            attitude_pub_->publish(msg);

            Thrust thrust_msg;
            thrust_msg.header.stamp = stamp;
            thrust_msg.thrust = setpoint_thrust_;
            thrust_pub_->publish(thrust_msg);
        }

        if (setpoint_type_ == RATES) {
            AttitudeTarget att_raw_msg;
            att_raw_msg.header.stamp = stamp;
            att_raw_msg.header.frame_id = fcu_frame_;
            att_raw_msg.type_mask = AttitudeTarget::IGNORE_ATTITUDE;
            att_raw_msg.body_rate = setpoint_rates_;
            att_raw_msg.thrust = setpoint_thrust_;
            attitude_raw_pub_->publish(att_raw_msg);
        }
        return true;
    }

    void publishSetpoint() {
        std::lock_guard<std::mutex> lock(mutex_);
        const int64_t captured_tick_ns = steadyNs();
        // Check before any FCU setpoint is published, even if ROS time is stale.
        if (stopOnPublisherResume()) return;
        if (setpoint_type_ == NONE || setpoint_timer_->is_canceled()) return;
        // Never refresh this checkpoint after the guard: SIGSTOP can happen
        // between the two statements and hide a stalled publisher on SIGCONT.
        last_setpoint_tick_ns_ = captured_tick_ns;
        // No FCU state for state_watchdog_timeout while armed: MAVROS restarted or
        // the FCU link dropped, so PX4 got no setpoints either and left OFFBOARD
        // (COM_OF_LOSS_T). It returns to OFFBOARD by itself as soon as the stream
        // reaches it again, usually before MAVROS reports a State, so handleState()
        // never sees the exit: stop here as for a seen one (S4). MAVROS reports
        // State once per FCU heartbeat (1 Hz), so state_timeout (3 s) would fire on
        // two lost heartbeats and a late third, and stopping in the air is a
        // failsafe. The 4.5 s default rides out three lost ones plus jitter and
        // still fires before a respawned MAVROS (respawn_delay 5 s plus startup)
        // passes the stream on.
        int64_t silent_ns = monotonicNs() - state_rx_ns_;
        if (state_.armed && silent_ns > state_watchdog_timeout_.nanoseconds()) {
            char reason[160];
            std::snprintf(reason, sizeof(reason), "No FCU state for %.1f s while armed (MAVROS restart "
                          "or FCU link loss, PX4 has left OFFBOARD)", silent_ns * 1e-9);
            stopStream(reason);
            return;
        }
        publish(now());
    }

    void checkManualControl() {
        mavros_msgs::msg::ManualControl manual_control;
        { std::lock_guard<std::mutex> lock(telemetry_mutex_); manual_control = manual_control_; }
        rclcpp::Duration zero_dur(0, 0);
        if (manual_control_timeout_ > zero_dur && timeout(manual_control.header.stamp, manual_control_timeout_)) {
            throw std::runtime_error("Manual control timeout, RC is switched off?");
        }
        if (check_kill_switch_) {
            const uint8_t SWITCH_POS_ON = 1;
            const int KILL_SWITCH_BIT = 12;
            uint8_t kill_switch = (manual_control.buttons & (0b11 << KILL_SWITCH_BIT)) >> KILL_SWITCH_BIT;
            if (kill_switch == SWITCH_POS_ON)
                throw std::runtime_error("Kill switch is on");
        }
    }

    bool stateFresh() {
        std::lock_guard<std::mutex> lock(mutex_);
        const int64_t t = monotonicNs();
        return state_.connected && state_rx_ns_ > 0 && t >= state_rx_ns_ &&
               t - state_rx_ns_ <= state_timeout_.nanoseconds();
    }

    void checkState(const mavros_msgs::msg::State& state) {
        if (!state.connected)
            throw std::runtime_error("No connection to FCU, https://bumblebee.coex.tech/connection");
        if (!stateFresh())
            throw std::runtime_error("State timeout, check mavros settings");
    }

    // The pilot (or a PX4 failsafe) wins: a vehicle armed in any mode but OFFBOARD
    // is flown by the pilot's RC or by PX4 itself, never switch it to OFFBOARD
    void checkPilot(const mavros_msgs::msg::State& state) {
        if (state.armed && state.mode != "OFFBOARD")
            throw std::runtime_error("Copter is armed in " + state.mode + " mode: the pilot or "
                                     "a PX4 failsafe has control, not taking over");
    }

    void publishState() {
        bumblebee::msg::State msg;
        msg.mode = setpoint_type_;
        msg.yaw_mode = setpoint_yaw_type_;

        if (setpoint_position_.header.frame_id.empty()) {
            msg.x = msg.y = msg.z = NAN;
        } else {
            msg.x = setpoint_position_.point.x;
            msg.y = setpoint_position_.point.y;
            msg.z = setpoint_altitude_.point.z;
        }
        msg.speed = nav_speed_;
        msg.lat = setpoint_lat_;
        msg.lon = setpoint_lon_;
        msg.vx = setpoint_velocity_.vector.x;
        msg.vy = setpoint_velocity_.vector.y;
        msg.vz = setpoint_velocity_.vector.z;
        msg.roll = setpoint_roll_;
        msg.pitch = setpoint_pitch_;
        msg.yaw = !yaw_frame_id_.empty() ? setpoint_yaw_ : NAN;
        msg.roll_rate = setpoint_rates_.x;
        msg.pitch_rate = setpoint_rates_.y;
        msg.yaw_rate = setpoint_rates_.z;
        msg.thrust = setpoint_thrust_;

        if (setpoint_type_ == VELOCITY) {
            msg.xy_frame_id = setpoint_velocity_.header.frame_id;
            msg.z_frame_id = setpoint_velocity_.header.frame_id;
        } else {
            msg.xy_frame_id = setpoint_position_.header.frame_id;
            msg.z_frame_id = setpoint_altitude_.header.frame_id;
        }
        msg.yaw_frame_id = yaw_frame_id_;
        state_pub_->publish(msg);
    }

    inline float safe_val(float value) {
        return std::isfinite(value) ? value : 0.0f;
    }

    void serve(enum setpoint_type_t sp_type, float x, float y, float z, float vx, float vy, float vz,
               float roll, float pitch, float yaw, float roll_rate, float pitch_rate, float yaw_rate,
               float lat, float lon, float thrust, float speed, string frame_id, bool auto_arm,
               bool& success, string& message)
    {
        auto flight_run = beginFlightRun();
#define ENSURE_FINITE(var) { if (!std::isfinite(var)) { message = #var " argument cannot be NaN or Inf"; busy_ = false; return; } }
#define ENSURE_NON_INF(var) { if (std::isinf(var)) { message = #var " argument cannot be Inf"; busy_ = false; return; } }

        const rclcpp::Time stamp(0, 0, RCL_ROS_TIME); // use latest available transform

        // Velocity, attitude, rates and yaw rate setpoints make PX4 leave OFFBOARD
        // after ~1 s (A8): refuse them before touching any state
        if (sp_type == VELOCITY || sp_type == ATTITUDE || sp_type == RATES || sp_type == _YAW_RATE) {
            const char* name = sp_type == VELOCITY ? "set_velocity" : sp_type == ATTITUDE ? "set_attitude" :
                               sp_type == RATES ? "set_rates" : "set_yaw_rate";
            message = string(name) + " is disabled until its MAVROS path works "
                      "(PX4 leaves OFFBOARD after ~1 s); use navigate or set_position";
            RCLCPP_WARN(get_logger(), "%s", message.c_str());
            return;
        }

        // Never start OFFBOARD control while the pilot or a PX4 failsafe flies the
        // vehicle, nor while its state is unknown (a stale state looks disarmed) (A4).
        // Checked before touching any state.
        if (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL || sp_type == POSITION) {
            try {
                auto state = fcuState();
                checkState(state);
                checkPilot(state);
                if (auto_arm) {
                    serve_land_seq_ = land_seq_.load(); checkArmCancel();
                    if (queuedArmBlocked(monotonicNs(), srvs_run_start_ns_, land_done_ns_.load()))
                        throw std::runtime_error("Auto-arm cancelled: request waited behind flight commands before the last /land; send it again");
                } // a /land since: also one this request queued behind (S5)
            } catch (const std::exception& e) {
                message = e.what();
                RCLCPP_WARN(get_logger(), "%s", message.c_str());
                return;
            }
        }

        // Acquire busy_ outside the try: the catch below releases it, and a failed
        // acquire must not release the busy_ that land() holds
        bool idle = false;
        if (!busy_.compare_exchange_strong(idle, true)) {
            message = "Busy";
            RCLCPP_INFO(get_logger(), "%s", message.c_str());
            return;
        }

        bool arming = false; // inside offboardAndArm(): a failure there stops the stream
        try {
            checkState(fcuState());
            if (auto_arm) checkManualControl();

            if (frame_id.empty()) frame_id = local_frame_;

            auto search = reference_frames_.find(frame_id);
            const string& reference_frame = search == reference_frames_.end() ? frame_id : search->second;

            ENSURE_NON_INF(x); ENSURE_NON_INF(y); ENSURE_NON_INF(z);
            ENSURE_NON_INF(speed); ENSURE_NON_INF(vx); ENSURE_NON_INF(vy); ENSURE_NON_INF(vz);
            ENSURE_NON_INF(roll); ENSURE_NON_INF(pitch);
            ENSURE_NON_INF(roll_rate); ENSURE_NON_INF(pitch_rate); ENSURE_NON_INF(yaw_rate);
            ENSURE_NON_INF(thrust);

            if (sp_type == NAVIGATE_GLOBAL) {
                ENSURE_FINITE(lat); ENSURE_FINITE(lon);
            }

            if (isfinite(x) != isfinite(y))
                throw std::runtime_error("x and y can be set only together");

            {
                std::lock_guard<std::mutex> lock(mutex_);
                if (isfinite(yaw_rate) && sp_type > RATES && setpoint_type_ == ATTITUDE)
                    throw std::runtime_error("Yaw rate cannot be set in attitude mode.");

                if (sp_type == _ALTITUDE &&
                    (setpoint_type_ == VELOCITY || setpoint_type_ == ATTITUDE || setpoint_type_ == RATES))
                    throw std::runtime_error("Altitude cannot be set in velocity, attitude or rates mode.");

                if ((sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL) &&
                    timeout(local_position_.header.stamp, local_position_timeout_))
                    throw std::runtime_error("No local position, check settings");
            }

            if (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL) {
                if (speed < 0)
                    throw std::runtime_error("Navigate speed must be positive, " + std::to_string(speed) + " passed");
                if (speed == 0) speed = default_speed_;
            }

            const NavSatFix global_position = globalSnapshot();
            if (sp_type == NAVIGATE_GLOBAL && timeout(global_position.header.stamp, global_position_timeout_))
                throw std::runtime_error("No global position");

            if (isfinite(x) || isfinite(y) || isfinite(z) || isfinite(vx) || isfinite(vy) || isfinite(vz) || isfinite(yaw)) {
                if (!waitTransform(reference_frame, frame_id, stamp, transform_timeout_))
                    throw std::runtime_error("Can't transform from " + frame_id + " to " + reference_frame);
                if (!waitTransform(local_frame_, reference_frame, stamp, transform_timeout_))
                    throw std::runtime_error("Can't transform from " + reference_frame + " to " + local_frame_);
            }

            if (sp_type == NAVIGATE_GLOBAL) {
                auto pose_local = globalToLocal(global_position, lat, lon);
                pose_local.header.stamp = stamp;
                auto xy_in_req_frame = tf_buffer_.transform(pose_local, frame_id);
                x = xy_in_req_frame.pose.position.x;
                y = xy_in_req_frame.pose.position.y;
            }

            std::optional<PointStamped> desired_point;
            if (isfinite(x) || isfinite(y) || isfinite(z)) {
                PointStamped desired;
                desired.header.frame_id = frame_id; desired.header.stamp = stamp;
                desired.point.x = safe_val(x); desired.point.y = safe_val(y); desired.point.z = safe_val(z);
                desired_point = tf_buffer_.transform(desired, reference_frame);
            }
            std::optional<double> desired_yaw;
            if (isfinite(yaw) && (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL || sp_type == POSITION ||
                                 sp_type == VELOCITY || sp_type == ATTITUDE || sp_type == _YAW)) {
                QuaternionStamped desired;
                desired.header.frame_id = frame_id; desired.header.stamp = stamp;
                desired.quaternion = quatFromYaw(yaw);
                desired = tf_buffer_.transform(desired, reference_frame);
                desired_yaw = tf2::getYaw(desired.quaternion);
            }

            // From here on the setpoint state changes: hold the lock that handleState()
            // and the setpoint timer take (never while waiting for the FCU)
            std::unique_lock<std::mutex> lock(mutex_);
            const int64_t captured_tick_ns = steadyNs();
            if (stopOnPublisherResume())
                throw std::runtime_error("Setpoint publisher stalled: old command cancelled; send a fresh command");
            if (!publisherResumeStateAllowed(state_.connected, state_.armed, state_.mode == "OFFBOARD",
                                             state_rx_steady_ns_, publisher_stopped_steady_ns_))
                throw std::runtime_error("Setpoint publisher stalled: waiting for a fresh FCU state in OFFBOARD or disarmed");
            if (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL || sp_type == POSITION) {
                checkPilot(state_); // the pilot may have taken over since the check above
                smooth_initialized_ = false;
            }

            if (sp_type == NAVIGATE_GLOBAL) {
                setpoint_lat_ = lat;
                setpoint_lon_ = lon;
            }

            if (sp_type <= RATES) setpoint_type_ = sp_type;
            if (setpoint_type_ != NAVIGATE && setpoint_type_ != NAVIGATE_GLOBAL) nav_from_sp_flag_ = false;

            bool to_auto_arm = auto_arm && (state_.mode != "OFFBOARD" || !state_.armed);
            if (to_auto_arm || setpoint_type_ == VELOCITY || setpoint_type_ == ATTITUDE || setpoint_type_ == RATES) {
                setpoint_position_.header.frame_id = "";
                setpoint_altitude_.header.frame_id = "";
                yaw_frame_id_ = "";
            }

            if (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL) {
                if (nav_from_sp_ && nav_from_sp_flag_) {
                    message = "Navigating from current setpoint";
                    nav_start_ = position_msg_;
                } else {
                    nav_start_ = local_position_;
                }
                nav_start_ns_ = monotonicNs();
                if (!isnan(speed)) nav_speed_ = speed;
                nav_from_sp_flag_ = true;
            }

            if (setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL || setpoint_type_ == POSITION) {
                if (isfinite(x) && isfinite(y)) {
                    setpoint_position_ = *desired_point;
                } else if (setpoint_position_.header.frame_id.empty()) {
                    setpoint_position_.header = local_position_.header;
                    setpoint_position_.point = local_position_.pose.position;
                }

                if (isfinite(z)) {
                    setpoint_altitude_ = *desired_point;
                } else if (setpoint_altitude_.header.frame_id.empty()) {
                    setpoint_altitude_.header = local_position_.header;
                    setpoint_altitude_.point = local_position_.pose.position;
                }
            }

            if (sp_type == VELOCITY) {
                Vector3Stamped desired;
                desired.header.frame_id = frame_id;
                desired.header.stamp = stamp;
                desired.vector.x = safe_val(vx);
                desired.vector.y = safe_val(vy);
                desired.vector.z = safe_val(vz);
                desired = tf_buffer_.transform(desired, reference_frame);
                setpoint_velocity_.header = desired.header;
                if (isfinite(vx) && isfinite(vy)) {
                    setpoint_velocity_.vector.x = desired.vector.x;
                    setpoint_velocity_.vector.y = desired.vector.y;
                }
                if (isfinite(vz)) setpoint_velocity_.vector.z = desired.vector.z;
            }

            if (sp_type == NAVIGATE || sp_type == NAVIGATE_GLOBAL || sp_type == POSITION ||
                sp_type == VELOCITY || sp_type == ATTITUDE || sp_type == _YAW) {
                if (isfinite(yaw)) {
                    setpoint_yaw_type_ = YAW;
                    setpoint_yaw_ = *desired_yaw;
                    yaw_frame_id_ = reference_frame;
                } else if (isinf(yaw) && yaw > 0) {
                    setpoint_yaw_type_ = TOWARDS;
                } else if (yaw_frame_id_.empty() || sp_type == _YAW) {
                    setpoint_yaw_type_ = YAW;
                    setpoint_yaw_ = tf2::getYaw(local_position_.pose.orientation);
                    yaw_frame_id_ = local_position_.header.frame_id;
                }
            }

            if (isfinite(roll)) setpoint_roll_ = roll;
            if (isfinite(pitch)) setpoint_pitch_ = pitch;
            if (isfinite(yaw_rate)) { setpoint_yaw_type_ = YAW_RATE; setpoint_rates_.z = yaw_rate; }
            if (isfinite(roll_rate)) setpoint_rates_.x = roll_rate;
            if (isfinite(pitch_rate)) setpoint_rates_.y = pitch_rate;
            if (isfinite(thrust)) setpoint_thrust_ = thrust;

            wait_armed_ = auto_arm;
            publisher_stopped_steady_ns_ = 0; // only this explicit, state-checked command resumes control
            // Commit the pre-guard checkpoint before direct publication, even
            // while the timer is canceled for a newly accepted explicit stream.
            last_setpoint_tick_ns_ = captured_tick_ns;
            if (!publish(stamp)) {
                wait_armed_ = false; // no ARM was attempted by this refused direct publication
                throw std::runtime_error("Setpoint publisher stalled before direct publication; send a fresh command");
            }
            setpoint_timer_->reset();

            if (setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL || setpoint_type_ == POSITION) {
                publishTarget(stamp, true);
            }
            publishState();

            if (auto_arm) {
                lock.unlock(); // offboardAndArm() waits for state updates from handleState()
                arming = true;
                offboardAndArm();
                arming = false;
                lock.lock();
                wait_armed_ = false;
                // PX4 left OFFBOARD or the FCU state was lost right as the motors
                // started: handleState() or the state watchdog stopped the stream
                if (setpoint_type_ == NONE)
                    throw std::runtime_error("Setpoint stream stopped while arming, not flying");
                arm_complete_ns_ = monotonicNs();
            } else if (state_.mode != "OFFBOARD") {
                setpoint_timer_->cancel();
                throw std::runtime_error("Copter is not in OFFBOARD mode, use auto_arm?");
            } else if (!state_.armed) {
                setpoint_timer_->cancel();
                throw std::runtime_error("Copter is not armed, use auto_arm?");
            }

        } catch (const std::exception& e) {
            if (arming) {
                // auto_arm failed or was cancelled before we got control: stop the
                // stream, so PX4 does not sit in OFFBOARD with a target that an
                // RC arm would then fly to
                std::lock_guard<std::mutex> lock(mutex_);
                wait_armed_ = false;
                resetSetpoint();
                publishState();
            }
            message = e.what();
            RCLCPP_INFO(get_logger(), "%s", message.c_str());
            busy_ = false;
            return;
        }

        success = true;
        busy_ = false;

#undef ENSURE_FINITE
#undef ENSURE_NON_INF
    }

    void land(const std_srvs::srv::Trigger::Request::SharedPtr,
              std_srvs::srv::Trigger::Response::SharedPtr res) {
        // /land has its own callback group, so it runs even while serve() is busy.
        // If serve() is in auto_arm (Ctrl+C during takeoff), cancel it first: the
        // motors must not start after the script asked to land. Wait (bounded) for
        // serve() to give up, then land as usual.
        ++land_seq_;
        bool acquired = false;
        try {
            auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
            bool idle = false;
            bool pending_arm_seen = arm_in_doubt_.load();
            const auto busy_start = std::chrono::steady_clock::now();
            while (!busy_.compare_exchange_strong(idle, true)) {
                pending_arm_seen = pending_arm_seen || arm_in_doubt_.load();
                if (pending_arm_seen) deadline = busy_start + std::chrono::seconds(13);
                idle = false;
                if (std::chrono::steady_clock::now() > deadline) throw std::runtime_error("Busy");
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            acquired = true;
            auto state = fcuState();
            checkState(state);

            if (state.armed && state.mode == "AUTO.LAND")
                throw std::runtime_error("Already landing (AUTO.LAND)");
            checkPilot(state);

            if (land_only_in_offboard_ && state.mode != "OFFBOARD")
                throw std::runtime_error("Copter is not in OFFBOARD mode");

            landing_ = true; // OFFBOARD -> AUTO.LAND is ours, not a pilot takeover
            auto sm_req = std::make_shared<mavros_msgs::srv::SetMode::Request>();
            sm_req->custom_mode = "AUTO.LAND";
            auto future = set_mode_->async_send_request(sm_req);
            if (future.wait_for(std::chrono::seconds(10)) != std::future_status::ready)
                throw std::runtime_error("Can't call set_mode service");
            if (!future.get()->mode_sent)
                throw std::runtime_error("Can't send set_mode request");

            rclcpp::Rate r(10);
            const int64_t land_start_ns = monotonicNs();
            while (rclcpp::ok()) {
                if (fcuState().mode == "AUTO.LAND") break;
                if (monotonicNs() - land_start_ns > land_timeout_.nanoseconds())
                    throw std::runtime_error("Land request timed out");
                r.sleep();
            }

            std::lock_guard<std::mutex> lock(mutex_);
            resetSetpoint();
            publishState();

            res->success = true;
        } catch (const std::exception& e) {
            res->message = e.what();
            RCLCPP_INFO(get_logger(), "%s", e.what());
        }
        landing_ = false;
        land_done_ns_ = monotonicNs(); // the sequence token never clears
        if (acquired) busy_ = false;
    }

    void release(const std_srvs::srv::Trigger::Request::SharedPtr,
                 std_srvs::srv::Trigger::Response::SharedPtr res) {
        auto flight_run = beginFlightRun();
        std::lock_guard<std::mutex> lock(mutex_);
        resetSetpoint();
        publishState();
        res->success = true;
    }
};

// SIMPLE_OFFBOARD_NO_MAIN: test/test_simple_offboard.cpp includes this file to
// unit-test the pure helpers above
#ifndef SIMPLE_OFFBOARD_NO_MAIN
int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<SimpleOffboard>();
    // MultiThreadedExecutor: service callbacks (srvs and land groups) can block
    // while subscriptions and the setpoint timer (concurrent group) still fire.
    // One thread per group, so /land runs while serve() waits in auto_arm.
    rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
    executor.add_node(node);
    executor.spin();
    rclcpp::shutdown();
    return 0;
}
#endif
