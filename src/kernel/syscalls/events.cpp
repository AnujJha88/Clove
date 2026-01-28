#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void EventSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_SUBSCRIBE,
        [this](const ipc::Message& msg) { return handle_subscribe(msg); });
    router.register_handler(ipc::SyscallOp::SYS_UNSUBSCRIBE,
        [this](const ipc::Message& msg) { return handle_unsubscribe(msg); });
    router.register_handler(ipc::SyscallOp::SYS_POLL_EVENTS,
        [this](const ipc::Message& msg) { return handle_poll_events(msg); });
    router.register_handler(ipc::SyscallOp::SYS_EMIT,
        [this](const ipc::Message& msg) { return handle_emit(msg); });
}

void EventSyscalls::emit_event(KernelEventType type, const nlohmann::json& data, uint32_t source_agent_id) {
    context_.event_bus.emit(type, data, source_agent_id);
}

ipc::Message EventSyscalls::handle_subscribe(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::vector<std::string> event_types;
        if (j.contains("event_types") && j["event_types"].is_array()) {
            for (const auto& e : j["event_types"]) {
                event_types.push_back(e.get<std::string>());
            }
        } else if (j.contains("events") && j["events"].is_array()) {
            for (const auto& e : j["events"]) {
                event_types.push_back(e.get<std::string>());
            }
        } else if (j.contains("event")) {
            event_types.push_back(j["event"].get<std::string>());
        }

        if (event_types.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "No events specified";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SUBSCRIBE, response.dump());
        }

        std::vector<KernelEventType> types;
        types.reserve(event_types.size());
        for (const auto& event_str : event_types) {
            types.push_back(kernel_event_type_from_string(event_str));
        }
        context_.event_bus.subscribe(msg.agent_id, types);

        spdlog::debug("Agent {} subscribed to {} event type(s)", msg.agent_id, event_types.size());

        json response;
        response["success"] = true;
        response["subscribed"] = event_types;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SUBSCRIBE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SUBSCRIBE, response.dump());
    }
}

ipc::Message EventSyscalls::handle_unsubscribe(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::vector<std::string> event_types;
        bool unsubscribe_all = j.value("all", false);

        if (!unsubscribe_all) {
            if (j.contains("event_types") && j["event_types"].is_array()) {
                for (const auto& e : j["event_types"]) {
                    event_types.push_back(e.get<std::string>());
                }
            } else if (j.contains("events") && j["events"].is_array()) {
                for (const auto& e : j["events"]) {
                    event_types.push_back(e.get<std::string>());
                }
            } else if (j.contains("event")) {
                event_types.push_back(j["event"].get<std::string>());
            }
        }

        std::vector<KernelEventType> types;
        types.reserve(event_types.size());
        for (const auto& event_str : event_types) {
            types.push_back(kernel_event_type_from_string(event_str));
        }

        context_.event_bus.unsubscribe(msg.agent_id, types, unsubscribe_all);

        if (unsubscribe_all) {
            spdlog::debug("Agent {} unsubscribed from all events", msg.agent_id);
        } else {
            spdlog::debug("Agent {} unsubscribed from {} event type(s)", msg.agent_id, event_types.size());
        }

        json response;
        response["success"] = true;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_UNSUBSCRIBE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_UNSUBSCRIBE, response.dump());
    }
}

ipc::Message EventSyscalls::handle_poll_events(const ipc::Message& msg) {
    try {
        json j;
        if (!msg.payload.empty()) {
            j = json::parse(msg.payload_str());
        }

        int max_events = j.value("max", 100);
        json events_array = context_.event_bus.poll(msg.agent_id, max_events);

        json response;
        response["success"] = true;
        response["events"] = events_array;
        response["count"] = events_array.size();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_POLL_EVENTS, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_POLL_EVENTS, response.dump());
    }
}

ipc::Message EventSyscalls::handle_emit(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string event_name = j.value("event", "CUSTOM");
        json event_data = j.value("data", json{});

        KernelEventType type = KernelEventType::CUSTOM;
        if (event_name != "CUSTOM") {
            event_data["custom_type"] = event_name;
        }

        emit_event(type, event_data, msg.agent_id);

        spdlog::debug("Agent {} emitted event: {}", msg.agent_id, event_name);

        json response;
        response["success"] = true;
        response["event"] = event_name;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_EMIT, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_EMIT, response.dump());
    }
}

} // namespace clove::kernel
