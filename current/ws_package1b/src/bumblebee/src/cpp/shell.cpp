/*
 * Shell — execute arbitrary shell commands via ROS 2 service
 * Copyright (C) 2018 Copter Express Technologies
 *
 * Ported to ROS 2 (Jazzy)
 *
 * Distributed under MIT License (available at https://opensource.org/licenses/MIT).
 */

#include <rclcpp/rclcpp.hpp>
#include <cstdio>
#include <string>
#include <array>
#include "bumblebee/srv/execute.hpp"

class Shell : public rclcpp::Node
{
public:
    Shell() : Node("shell")
    {
        declare_parameter("timeout", 3.0);

        server_ = create_service<bumblebee::srv::Execute>(
            "exec",
            [this](const bumblebee::srv::Execute::Request::SharedPtr req,
                   bumblebee::srv::Execute::Response::SharedPtr res) {
                RCLCPP_INFO(get_logger(), "Execute: %s", req->cmd.c_str());

                std::array<char, 128> buffer;
                FILE *fp = popen(req->cmd.c_str(), "r");

                if (fp == nullptr) {
                    res->code = bumblebee::srv::Execute::Request::CODE_FAIL;
                    res->output = "popen() failed";
                    return;
                }

                while (fgets(buffer.data(), buffer.size(), fp) != nullptr) {
                    res->output += buffer.data();
                }
                res->code = pclose(fp);
            });

        RCLCPP_INFO(get_logger(), "shell: ready");
    }

private:
    rclcpp::Service<bumblebee::srv::Execute>::SharedPtr server_;
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<Shell>());
    rclcpp::shutdown();
    return 0;
}
