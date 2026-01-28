#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/ipc_mailbox.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void IpcSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_REGISTER,
        [this](const ipc::Message& msg) { return handle_register(msg); });
    router.register_handler(ipc::SyscallOp::SYS_SEND,
        [this](const ipc::Message& msg) { return handle_send(msg); });
    router.register_handler(ipc::SyscallOp::SYS_RECV,
        [this](const ipc::Message& msg) { return handle_recv(msg); });
    router.register_handler(ipc::SyscallOp::SYS_BROADCAST,
        [this](const ipc::Message& msg) { return handle_broadcast(msg); });
}

ipc::Message IpcSyscalls::handle_register(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());
        std::string name = j.value("name", "");

        if (name.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "name required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REGISTER, response.dump());
        }

        auto result = context_.mailbox_registry.register_name(msg.agent_id, name);
        if (!result.success) {
            json response;
            response["success"] = false;
            response["error"] = result.error.empty() ? "name already registered" : result.error;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REGISTER, response.dump());
        }

        spdlog::info("Agent {} registered as '{}'", msg.agent_id, name);

        json response;
        response["success"] = true;
        response["agent_id"] = msg.agent_id;
        response["name"] = name;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REGISTER, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse register request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REGISTER, response.dump());
    }
}

ipc::Message IpcSyscalls::handle_send(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        uint32_t target_id = j.value("to", 0u);
        std::string target_name = j.value("to_name", "");
        json message_content = j.value("message", json::object());

        if (target_id == 0 && !target_name.empty()) {
            auto resolved = context_.mailbox_registry.resolve_name(target_name);
            if (!resolved.has_value()) {
                json response;
                response["success"] = false;
                response["error"] = "target agent not found: " + target_name;
                return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SEND, response.dump());
            }
            target_id = *resolved;
        }

        if (target_id == 0) {
            json response;
            response["success"] = false;
            response["error"] = "target agent required (to or to_name)";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SEND, response.dump());
        }

        std::string sender_name = context_.mailbox_registry.get_name(msg.agent_id);

        IPCMessage ipc_msg;
        ipc_msg.from_id = msg.agent_id;
        ipc_msg.from_name = sender_name;
        ipc_msg.message = message_content;
        ipc_msg.timestamp = std::chrono::steady_clock::now();

        context_.mailbox_registry.enqueue(target_id, ipc_msg);

        spdlog::debug("Agent {} sent message to agent {}", msg.agent_id, target_id);

        json response;
        response["success"] = true;
        response["delivered_to"] = target_id;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SEND, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse send request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SEND, response.dump());
    }
}

ipc::Message IpcSyscalls::handle_recv(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());
        int max_messages = j.value("max", 10);
        bool wait = j.value("wait", false);
        (void)wait;

        auto messages = context_.mailbox_registry.dequeue(msg.agent_id, max_messages);
        json messages_array = json::array();

        for (const auto& ipc_msg : messages) {
            auto now = std::chrono::steady_clock::now();
            auto age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - ipc_msg.timestamp).count();

            json msg_json;
            msg_json["from"] = ipc_msg.from_id;
            msg_json["from_name"] = ipc_msg.from_name;
            msg_json["message"] = ipc_msg.message;
            msg_json["age_ms"] = age_ms;
            messages_array.push_back(msg_json);
        }

        json response;
        response["success"] = true;
        response["messages"] = messages_array;
        response["count"] = messages_array.size();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_RECV, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse recv request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["messages"] = json::array();
        response["count"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_RECV, response.dump());
    }
}

ipc::Message IpcSyscalls::handle_broadcast(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());
        json message_content = j.value("message", json::object());
        bool include_self = j.value("include_self", false);

        std::string sender_name = context_.mailbox_registry.get_name(msg.agent_id);

        IPCMessage ipc_msg;
        ipc_msg.from_id = msg.agent_id;
        ipc_msg.from_name = sender_name;
        ipc_msg.message = message_content;
        ipc_msg.timestamp = std::chrono::steady_clock::now();

        int delivered_count = context_.mailbox_registry.broadcast(ipc_msg, include_self);

        spdlog::debug("Agent {} broadcast message to {} agents", msg.agent_id, delivered_count);

        json response;
        response["success"] = true;
        response["delivered_count"] = delivered_count;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_BROADCAST, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse broadcast request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["delivered_count"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_BROADCAST, response.dump());
    }
}

} // namespace clove::kernel
