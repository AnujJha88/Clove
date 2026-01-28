#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "services/tunnel/client.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void TunnelSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_TUNNEL_CONNECT,
        [this](const ipc::Message& msg) { return handle_tunnel_connect(msg); });
    router.register_handler(ipc::SyscallOp::SYS_TUNNEL_DISCONNECT,
        [this](const ipc::Message& msg) { return handle_tunnel_disconnect(msg); });
    router.register_handler(ipc::SyscallOp::SYS_TUNNEL_STATUS,
        [this](const ipc::Message& msg) { return handle_tunnel_status(msg); });
    router.register_handler(ipc::SyscallOp::SYS_TUNNEL_LIST_REMOTES,
        [this](const ipc::Message& msg) { return handle_tunnel_list_remotes(msg); });
    router.register_handler(ipc::SyscallOp::SYS_TUNNEL_CONFIG,
        [this](const ipc::Message& msg) { return handle_tunnel_config(msg); });
}

void TunnelSyscalls::on_tick() {
    process_tunnel_events();
}

ipc::Message TunnelSyscalls::handle_tunnel_connect(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string relay_url = j.value("relay_url", context_.config.relay_url);
        std::string machine_id = j.value("machine_id", context_.config.machine_id);
        std::string token = j.value("token", context_.config.machine_token);

        if (relay_url.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "relay_url required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONNECT, response.dump());
        }

        clove::services::tunnel::TunnelConfig tc;
        tc.relay_url = relay_url;
        tc.machine_id = machine_id;
        tc.token = token;
        context_.tunnel_client.configure(tc);

        if (context_.tunnel_client.connect()) {
            spdlog::info("Tunnel connected via syscall: {}", relay_url);
            json response;
            response["success"] = true;
            response["relay_url"] = relay_url;
            response["machine_id"] = machine_id;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONNECT, response.dump());
        } else {
            json response;
            response["success"] = false;
            response["error"] = "Failed to connect to relay server";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONNECT, response.dump());
        }

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONNECT, response.dump());
    }
}

ipc::Message TunnelSyscalls::handle_tunnel_disconnect(const ipc::Message& msg) {
    context_.tunnel_client.disconnect();

    json response;
    response["success"] = true;
    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_DISCONNECT, response.dump());
}

ipc::Message TunnelSyscalls::handle_tunnel_status(const ipc::Message& msg) {
    auto status = context_.tunnel_client.get_status();

    json response;
    response["success"] = true;
    response["connected"] = status.connected;
    response["relay_url"] = status.relay_url;
    response["machine_id"] = status.machine_id;
    response["remote_agent_count"] = status.remote_agent_count;

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_STATUS, response.dump());
}

ipc::Message TunnelSyscalls::handle_tunnel_list_remotes(const ipc::Message& msg) {
    auto agents = context_.tunnel_client.list_remote_agents();

    json response;
    response["success"] = true;
    response["agents"] = json::array();

    for (const auto& agent : agents) {
        json a;
        a["agent_id"] = agent.agent_id;
        a["name"] = agent.name;
        a["connected_at"] = agent.connected_at;
        response["agents"].push_back(a);
    }
    response["count"] = agents.size();

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_LIST_REMOTES, response.dump());
}

ipc::Message TunnelSyscalls::handle_tunnel_config(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        clove::services::tunnel::TunnelConfig tc;
        tc.relay_url = j.value("relay_url", context_.config.relay_url);
        tc.machine_id = j.value("machine_id", context_.config.machine_id);
        tc.token = j.value("token", context_.config.machine_token);
        tc.reconnect_interval = j.value("reconnect_interval", 5);

        if (context_.tunnel_client.configure(tc)) {
            context_.config.relay_url = tc.relay_url;
            context_.config.machine_id = tc.machine_id;
            context_.config.machine_token = tc.token;

            json response;
            response["success"] = true;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONFIG, response.dump());
        } else {
            json response;
            response["success"] = false;
            response["error"] = "Failed to configure tunnel";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONFIG, response.dump());
        }

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_TUNNEL_CONFIG, response.dump());
    }
}

void TunnelSyscalls::process_tunnel_events() {
    auto events = context_.tunnel_client.poll_events();

    for (const auto& event : events) {
        switch (event.type) {
            case clove::services::tunnel::TunnelEvent::Type::SYSCALL:
                handle_tunnel_syscall(event.agent_id, event.opcode, event.payload);
                break;

            case clove::services::tunnel::TunnelEvent::Type::AGENT_CONNECTED:
                spdlog::info("Remote agent connected: {} (id={})",
                            event.agent_name, event.agent_id);
                break;

            case clove::services::tunnel::TunnelEvent::Type::AGENT_DISCONNECTED:
                spdlog::info("Remote agent disconnected: id={}", event.agent_id);
                break;

            case clove::services::tunnel::TunnelEvent::Type::DISCONNECTED:
                spdlog::warn("Tunnel disconnected from relay");
                break;

            case clove::services::tunnel::TunnelEvent::Type::RECONNECTED:
                spdlog::info("Tunnel reconnected to relay");
                break;

            case clove::services::tunnel::TunnelEvent::Type::ERROR:
                spdlog::error("Tunnel error: {}", event.error);
                break;
        }
    }
}

void TunnelSyscalls::handle_tunnel_syscall(uint32_t agent_id, uint8_t opcode,
                                          const std::vector<uint8_t>& payload) {
    ipc::Message msg;
    msg.agent_id = agent_id;
    msg.opcode = static_cast<ipc::SyscallOp>(opcode);
    msg.payload = payload;

    spdlog::debug("Processing syscall from remote agent {}: opcode=0x{:02x}",
                  agent_id, opcode);

    auto response = dispatch_(msg);

    context_.tunnel_client.send_response(
        agent_id,
        static_cast<uint8_t>(response.opcode),
        response.payload
    );
}

} // namespace clove::kernel
