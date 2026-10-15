/*
 * High level control for the LED strip
 * Indicate flight events with the LED strip
 * Copyright (C) 2019 Copter Express Technologies
 *
 * Ported to ROS 2 (Jazzy):
 *   - ros:: → rclcpp::
 *   - rosgraph_msgs::Log → rcl_interfaces::msg::Log
 *   - boost::to_lower_copy → std::transform
 *   - ros::names::validate → simple alphanumeric check
 *   - ros::param::has / ros::param::param → has_parameter / get_parameter
 *   - ros::Time::now() → get_clock()->now()
 *   - ros::Duration → rclcpp::Duration + std::chrono
 *   - timer.setPeriod → cancel + create_wall_timer
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <rclcpp/rclcpp.hpp>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>
#include <functional>

#include "bumblebee/srv/set_led_effect.hpp"
#include <led_msgs/srv/set_le_ds.hpp>
#include <led_msgs/msg/led_state.hpp>
#include <led_msgs/msg/led_state_array.hpp>

#include <sensor_msgs/msg/battery_state.hpp>
#include <mavros_msgs/msg/state.hpp>
#include <rcl_interfaces/msg/log.hpp>

using namespace std::chrono_literals;
using SetLEDEffect = bumblebee::srv::SetLEDEffect;
using SetLEDs = led_msgs::srv::SetLeDs;

class Led : public rclcpp::Node
{
public:
    Led() : Node("led")
    {
        blink_rate_      = declare_parameter("blink_rate", 2.0);
        blink_fast_rate_ = declare_parameter("blink_fast_rate", blink_rate_ * 2);
        fade_period_     = declare_parameter("fade_period", 0.5);
        wipe_period_     = declare_parameter("wipe_period", 0.5);
        flash_delay_     = declare_parameter("flash_delay", 0.1);
        rainbow_period_  = declare_parameter("rainbow_period", 5.0);
        low_battery_threshold_ = declare_parameter("notify.low_battery.threshold", 3.7);

        // error_ignore list: declare as string vector
        declare_parameter("notify.error.ignore", std::vector<std::string>{});
        error_ignore_ = get_parameter("notify.error.ignore")
                            .as_string_array();

        // LED namespace prefix
        std::string led = declare_parameter("led", std::string("led"));
        if (!led.empty()) led += "/";
        led_prefix_ = led;

        // Wait for set_leds service
        set_leds_client_ = create_client<SetLEDs>(led_prefix_ + "set_leds");
        RCLCPP_INFO(get_logger(), "waiting for %sset_leds service...", led_prefix_.c_str());
        set_leds_client_->wait_for_service();

        // Subscribe to LED state (one-shot to get led_count, then continue)
        state_sub_ = create_subscription<led_msgs::msg::LedStateArray>(
            led_prefix_ + "state", rclcpp::QoS(1).transient_local(),
            [this](const led_msgs::msg::LedStateArray::SharedPtr msg) {
                handleState(*msg);
            });

        set_effect_srv_ = create_service<SetLEDEffect>(
            led_prefix_ + "set_effect",
            [this](const SetLEDEffect::Request::SharedPtr req,
                   SetLEDEffect::Response::SharedPtr res) {
                setEffect(*req, *res);
            });

        mavros_state_sub_ = create_subscription<mavros_msgs::msg::State>(
            "mavros/state", 1,
            [this](const mavros_msgs::msg::State::SharedPtr msg) {
                handleMavrosState(*msg);
            });

        battery_sub_ = create_subscription<sensor_msgs::msg::BatteryState>(
            "mavros/battery", 1,
            [this](const sensor_msgs::msg::BatteryState::SharedPtr msg) {
                handleBattery(*msg);
            });

        rosout_sub_ = create_subscription<rcl_interfaces::msg::Log>(
            "/rosout", rclcpp::QoS(10),
            [this](const rcl_interfaces::msg::Log::SharedPtr msg) {
                handleLog(*msg);
            });

        // Effect timer (initially inactive)
        timer_ = create_wall_timer(1h, [this]() { proceed(); });
        timer_->cancel();

        RCLCPP_INFO(get_logger(), "ready");
        notify("startup");
    }

private:
    // ── Parameters ───────────────────────────────────────────────────────────
    double blink_rate_, blink_fast_rate_, fade_period_, wipe_period_;
    double flash_delay_, rainbow_period_, low_battery_threshold_;
    std::vector<std::string> error_ignore_;
    std::string led_prefix_;

    // ── State ────────────────────────────────────────────────────────────────
    SetLEDEffect::Request current_effect_;
    int led_count_{0};
    int counter_{0};
    rclcpp::Time start_time_{0, 0, RCL_ROS_TIME};
    led_msgs::msg::LedStateArray state_, start_state_;
    mavros_msgs::msg::State mavros_state_;

    // ── ROS handles ──────────────────────────────────────────────────────────
    rclcpp::Client<SetLEDs>::SharedPtr set_leds_client_;
    rclcpp::Service<SetLEDEffect>::SharedPtr set_effect_srv_;
    rclcpp::Subscription<led_msgs::msg::LedStateArray>::SharedPtr state_sub_;
    rclcpp::Subscription<mavros_msgs::msg::State>::SharedPtr mavros_state_sub_;
    rclcpp::Subscription<sensor_msgs::msg::BatteryState>::SharedPtr battery_sub_;
    rclcpp::Subscription<rcl_interfaces::msg::Log>::SharedPtr rosout_sub_;
    rclcpp::TimerBase::SharedPtr timer_;

    // ─────────────────────────────────────────────────────────────────────────

    void callSetLeds(const std::vector<led_msgs::msg::LedState>& leds)
    {
        auto req = std::make_shared<SetLEDs::Request>();
        req->leds = leds;
        auto future = set_leds_client_->async_send_request(req);
        // Fire and forget — don't wait for response in hot path
    }

    static void rainbow(uint8_t n, uint8_t& r, uint8_t& g, uint8_t& b)
    {
        if (n < 255 / 3) {
            r = n * 3; g = 255 - n * 3; b = 0;
        } else if (n < 255 / 3 * 2) {
            n -= 255 / 3; r = 255 - n * 3; g = 0; b = n * 3;
        } else {
            n -= 255 / 3 * 2; r = 0; g = n * 3; b = 255 - n * 3;
        }
    }

    std::vector<led_msgs::msg::LedState> makeLeds(uint8_t r, uint8_t g, uint8_t b)
    {
        std::vector<led_msgs::msg::LedState> leds(led_count_);
        for (int i = 0; i < led_count_; i++) {
            leds[i].index = i;
            leds[i].r = r; leds[i].g = g; leds[i].b = b;
        }
        return leds;
    }

    void fill(uint8_t r, uint8_t g, uint8_t b)
    {
        callSetLeds(makeLeds(r, g, b));
    }

    void restartTimer(std::chrono::nanoseconds period)
    {
        timer_->cancel();
        timer_ = create_wall_timer(period, [this]() { proceed(); });
    }

    void proceed()
    {
        counter_++;
        uint8_t r, g, b;
        std::vector<led_msgs::msg::LedState> leds(led_count_);

        if (current_effect_.effect == "blink" || current_effect_.effect == "blink_fast") {
            if (counter_ % 2 != 0)
                fill(current_effect_.r, current_effect_.g, current_effect_.b);
            else
                fill(0, 0, 0);

        } else if (current_effect_.effect == "fade") {
            double passed = (get_clock()->now() - start_time_).seconds() / fade_period_;
            passed = std::min(passed, 1.0);
            double inv = 1.0 - passed;
            for (int i = 0; i < led_count_; i++) {
                leds[i].index = i;
                leds[i].r = static_cast<uint8_t>(inv * start_state_.leds[i].r + passed * current_effect_.r);
                leds[i].g = static_cast<uint8_t>(inv * start_state_.leds[i].g + passed * current_effect_.g);
                leds[i].b = static_cast<uint8_t>(inv * start_state_.leds[i].b + passed * current_effect_.b);
            }
            callSetLeds(leds);
            if (passed >= 1.0) timer_->cancel();

        } else if (current_effect_.effect == "wipe") {
            led_msgs::msg::LedState s;
            s.index = counter_ - 1;
            s.r = current_effect_.r; s.g = current_effect_.g; s.b = current_effect_.b;
            callSetLeds({s});
            if (counter_ == led_count_) timer_->cancel();

        } else if (current_effect_.effect == "rainbow_fill") {
            rainbow(counter_ % 255, r, g, b);
            fill(r, g, b);

        } else if (current_effect_.effect == "rainbow") {
            for (int i = 0; i < led_count_; i++) {
                int pos = (counter_ + static_cast<int>(255.0 * i / led_count_)) % 255;
                rainbow(pos, r, g, b);
                leds[i].index = i;
                leds[i].r = r; leds[i].g = g; leds[i].b = b;
            }
            callSetLeds(leds);
        }
    }

    void setEffect(const SetLEDEffect::Request& req, SetLEDEffect::Response& res)
    {
        res.success = true;
        auto eff = req;
        if (eff.effect.empty()) eff.effect = "fill";

        if (eff.effect != "flash" && eff.effect != "fill" &&
            current_effect_.effect == eff.effect &&
            current_effect_.r == eff.r && current_effect_.g == eff.g && current_effect_.b == eff.b) {
            res.message = "Effect already set, skip";
            return;
        }

        if (eff.effect == "fill") {
            fill(eff.r, eff.g, eff.b);

        } else if (eff.effect == "blink") {
            restartTimer(std::chrono::nanoseconds(
                static_cast<int64_t>(1e9 / blink_rate_)));

        } else if (eff.effect == "blink_fast") {
            restartTimer(std::chrono::nanoseconds(
                static_cast<int64_t>(1e9 / blink_fast_rate_)));

        } else if (eff.effect == "fade") {
            restartTimer(50ms);

        } else if (eff.effect == "wipe") {
            restartTimer(std::chrono::nanoseconds(
                static_cast<int64_t>(1e9 * wipe_period_ / led_count_)));

        } else if (eff.effect == "flash") {
            auto delay = std::chrono::nanoseconds(static_cast<int64_t>(flash_delay_ * 1e9));
            fill(0, 0, 0); std::this_thread::sleep_for(delay);
            fill(eff.r, eff.g, eff.b); std::this_thread::sleep_for(delay);
            fill(0, 0, 0); std::this_thread::sleep_for(delay);
            fill(eff.r, eff.g, eff.b); std::this_thread::sleep_for(delay);
            fill(0, 0, 0); std::this_thread::sleep_for(delay);
            // Restore previous fill effect
            const auto& ce = current_effect_;
            if (ce.effect == "fill" || ce.effect == "fade" || ce.effect == "wipe") {
                fill(ce.r, ce.g, ce.b);
            }
            return; // flash is one-shot, don't change current_effect_

        } else if (eff.effect == "rainbow_fill" || eff.effect == "rainbow") {
            restartTimer(std::chrono::nanoseconds(
                static_cast<int64_t>(1e9 * rainbow_period_ / 255)));

        } else {
            res.message = "Unknown effect: " + eff.effect +
                ". Available: fill, fade, wipe, blink, blink_fast, flash, rainbow, rainbow_fill.";
            RCLCPP_ERROR(get_logger(), "%s", res.message.c_str());
            res.success = false;
            return;
        }

        current_effect_ = eff;
        counter_ = 0;
        start_state_ = state_;
        start_time_ = get_clock()->now();
        proceed();
    }

    void handleState(const led_msgs::msg::LedStateArray& msg)
    {
        state_ = msg;
        led_count_ = static_cast<int>(state_.leds.size());
    }

    /// Check if a notify/<event>/* parameter is set and trigger the effect
    void notify(const std::string& event)
    {
        std::string eff_param  = "notify." + event + ".effect";
        std::string r_param    = "notify." + event + ".r";
        std::string g_param    = "notify." + event + ".g";
        std::string b_param    = "notify." + event + ".b";

        if (!has_parameter(eff_param) && !has_parameter(r_param) &&
            !has_parameter(g_param)   && !has_parameter(b_param)) return;

        RCLCPP_INFO_THROTTLE(get_logger(), *get_clock(), 5000,
                             "led: notify %s", event.c_str());
        SetLEDEffect::Request req;
        SetLEDEffect::Response res;

        if (has_parameter(eff_param))
            req.effect = get_parameter(eff_param).as_string();
        if (has_parameter(r_param))
            req.r = static_cast<uint8_t>(get_parameter(r_param).as_int());
        if (has_parameter(g_param))
            req.g = static_cast<uint8_t>(get_parameter(g_param).as_int());
        if (has_parameter(b_param))
            req.b = static_cast<uint8_t>(get_parameter(b_param).as_int());

        setEffect(req, res);
    }

    void handleMavrosState(const mavros_msgs::msg::State& msg)
    {
        if (msg.connected && !mavros_state_.connected)         notify("connected");
        else if (!msg.connected && mavros_state_.connected)    notify("disconnected");
        else if (msg.armed && !mavros_state_.armed)            notify("armed");
        else if (!msg.armed && mavros_state_.armed)            notify("disarmed");
        else if (msg.mode != mavros_state_.mode) {
            std::string mode = msg.mode;
            std::transform(mode.begin(), mode.end(), mode.begin(), ::tolower);
            auto dot = mode.find('.');
            if (dot != std::string::npos) mode = mode.substr(dot + 1);

            // Only notify if mode name is a valid ROS identifier (alphanumeric + _)
            bool valid = !mode.empty() &&
                std::all_of(mode.begin(), mode.end(),
                    [](char c){ return std::isalnum(c) || c == '_'; });
            if (valid) notify(mode);
        }
        mavros_state_ = msg;
    }

    void handleLog(const rcl_interfaces::msg::Log& log)
    {
        // rcl_interfaces::msg::Log severity levels: DEBUG=10, INFO=20, WARN=30, ERROR=40, FATAL=50
        if (log.level >= rcl_interfaces::msg::Log::ERROR) {
            for (const auto& str : error_ignore_) {
                if (log.msg.find(str) != std::string::npos) return;
            }
            notify("error");
        }
    }

    void handleBattery(const sensor_msgs::msg::BatteryState& msg)
    {
        for (auto voltage : msg.cell_voltage) {
            if (voltage < low_battery_threshold_ && voltage > 2.0) {
                notify("low_battery");
            }
        }
    }
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<Led>());
    rclcpp::shutdown();
    return 0;
}
