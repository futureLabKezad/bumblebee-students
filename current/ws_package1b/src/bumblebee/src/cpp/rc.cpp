/*
 * Bumblebee mobile remote control backend
 * Receives ManualControl packets via UDP, forwards them to MAVROS
 * Copyright (C) 2019 Copter Express Technologies
 *
 * Ported to ROS 2 (Jazzy)
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <sys/socket.h>
#include <netinet/in.h>
#include <errno.h>
#include <cstring>
#include <thread>
#include <atomic>
#include <rclcpp/rclcpp.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <mavros_msgs/msg/manual_control.hpp>
#include <mavros_msgs/msg/mavlink.hpp>
#include "bumblebee/srv/get_telemetry.hpp"  // only for unused import avoidance

struct ControlMessage
{
    int16_t x, y, z, r;
} __attribute__((packed));

class RC : public rclcpp::Node
{
public:
    RC() : Node("rc")
    {
        bool use_fake_gcs = declare_parameter("use_fake_gcs", true);
        int port = declare_parameter("port", 35602);

        initLatchedState();

        socket_thread_ = std::thread(&RC::socketThread, this, port);
        socket_thread_.detach();

        if (use_fake_gcs) {
            gcs_thread_ = std::thread(&RC::fakeGCSThread, this);
            gcs_thread_.detach();
        }
    }

    ~RC()
    {
        // socket thread exits when the process dies
    }

private:
    rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr state_sub_;
    rclcpp::Publisher<mavros_msgs::msg::State>::SharedPtr state_pub_;
    rclcpp::Publisher<mavros_msgs::msg::ManualControl>::SharedPtr manual_control_pub_;
    rclcpp::Publisher<mavros_msgs::msg::Mavlink>::SharedPtr mavlink_pub_;
    rclcpp::TimerBase::SharedPtr state_timeout_timer_;

    mavros_msgs::msg::State::SharedPtr state_msg_;
    std::atomic<int64_t> last_manual_control_ns_{0};
    std::thread socket_thread_, gcs_thread_;

    void handleState(const mavros_msgs::msg::State::SharedPtr state)
    {
        // Reset/restart 3s timeout timer
        state_timeout_timer_->reset();

        if (!state_msg_ ||
            state->connected != state_msg_->connected ||
            state->mode != state_msg_->mode ||
            state->armed != state_msg_->armed) {
            state_msg_ = state;
            state_pub_->publish(*state_msg_);
        }
    }

    void stateTimedOut()
    {
        RCLCPP_INFO(get_logger(), "State timeout");
        mavros_msgs::msg::State unknown_state;
        state_pub_->publish(unknown_state);
        state_msg_ = nullptr;
        state_timeout_timer_->cancel();
    }

    void initLatchedState()
    {
        state_sub_ = create_subscription<mavros_msgs::msg::State>(
            "mavros/state", 1,
            [this](const mavros_msgs::msg::State::SharedPtr msg) { handleState(msg); });

        // Latched publisher (transient_local = latch equivalent)
        state_pub_ = create_publisher<mavros_msgs::msg::State>(
            "state_latched", rclcpp::QoS(1).transient_local());

        // Timeout timer: 3s one-shot, initially cancelled
        state_timeout_timer_ = create_wall_timer(
            std::chrono::seconds(3),
            [this]() { stateTimedOut(); });
        state_timeout_timer_->cancel();

        // Publish initial unknown state
        state_pub_->publish(mavros_msgs::msg::State{});
    }

    void fakeGCSThread()
    {
        // Workaround: send fake GCS heartbeats so PX4 sends STATUSTEXTs
        mavlink_pub_ = create_publisher<mavros_msgs::msg::Mavlink>("mavlink/to", 1);

        // HEARTBEAT from GCS (sysid=255, compid=0)
        mavros_msgs::msg::Mavlink hb;
        hb.framing_status = mavros_msgs::msg::Mavlink::FRAMING_OK;
        hb.magic = mavros_msgs::msg::Mavlink::MAVLINK_V20;
        hb.len = 9;
        hb.incompat_flags = 0;
        hb.compat_flags = 0;
        hb.seq = 0;
        hb.sysid = 255;
        hb.compid = 0;
        hb.checksum = 26460;
        hb.payload64.push_back(342282393542983680ULL);
        hb.payload64.push_back(3ULL);

        rclcpp::Rate rate(1);
        while (rclcpp::ok()) {
            int64_t now_ns = this->get_clock()->now().nanoseconds();
            int64_t last_ns = last_manual_control_ns_.load();
            if (now_ns - last_ns < 8'000'000'000LL) {
                mavlink_pub_->publish(hb);
            }
            rate.sleep();
        }
    }

    int createSocket(int port)
    {
        int sockfd = socket(AF_INET, SOCK_DGRAM, 0);

        sockaddr_in sin{};
        sin.sin_family = AF_INET;
        sin.sin_addr.s_addr = htonl(INADDR_ANY);
        sin.sin_port = htons(port);

        if (bind(sockfd, reinterpret_cast<sockaddr*>(&sin), sizeof(sin)) < 0) {
            RCLCPP_FATAL(get_logger(), "socket bind error: %s", strerror(errno));
            close(sockfd);
            rclcpp::shutdown();
            return -1;
        }

        return sockfd;
    }

    void socketThread(int port)
    {
        int sockfd = createSocket(port);
        if (sockfd < 0) return;

        manual_control_pub_ = create_publisher<mavros_msgs::msg::ManualControl>(
            "mavros/manual_control/send", 1);

        char buff[9999];
        sockaddr_in client_addr{};
        socklen_t client_addr_size = sizeof(client_addr);

        RCLCPP_INFO(get_logger(), "UDP RC initialized on port %d", port);

        while (true) {
            int bsize = recvfrom(sockfd, &buff[0], sizeof(buff) - 1, 0,
                                 reinterpret_cast<sockaddr*>(&client_addr), &client_addr_size);

            if (bsize < 0) {
                RCLCPP_ERROR(get_logger(), "recvfrom() error: %s", strerror(errno));
                continue;
            } else if (bsize != static_cast<int>(sizeof(ControlMessage))) {
                RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 30000,
                                      "Wrong UDP packet size: %d", bsize);
                continue;
            }

            const auto* msg = reinterpret_cast<const ControlMessage*>(buff);
            mavros_msgs::msg::ManualControl mc;
            mc.x = msg->x;
            mc.y = msg->y;
            mc.z = msg->z;
            mc.r = msg->r;
            manual_control_pub_->publish(mc);

            last_manual_control_ns_.store(this->get_clock()->now().nanoseconds());
        }
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RC>());
    rclcpp::shutdown();
    return 0;
}
