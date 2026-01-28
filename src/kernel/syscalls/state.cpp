#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/state_store.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void StateSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_STORE,
        [this](const ipc::Message& msg) { return handle_store(msg); });
    router.register_handler(ipc::SyscallOp::SYS_FETCH,
        [this](const ipc::Message& msg) { return handle_fetch(msg); });
    router.register_handler(ipc::SyscallOp::SYS_DELETE,
        [this](const ipc::Message& msg) { return handle_delete(msg); });
    router.register_handler(ipc::SyscallOp::SYS_KEYS,
        [this](const ipc::Message& msg) { return handle_keys(msg); });
}

ipc::Message StateSyscalls::handle_store(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string key = j.value("key", "");
        if (key.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "key is required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_STORE, response.dump());
        }

        std::string scope = j.value("scope", "global");
        std::optional<int> ttl_secs;
        if (j.contains("ttl") && j["ttl"].is_number()) {
            ttl_secs = j["ttl"].get<int>();
        }

        auto result = context_.state_store.store(msg.agent_id, key, j.value("value", json{}), scope, ttl_secs);

        if (!result.success) {
            json response;
            response["success"] = false;
            response["error"] = "failed to store key";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_STORE, response.dump());
        }

        spdlog::debug("Agent {} stored key '{}' (scope={})", msg.agent_id, result.key, result.scope);

        if (result.scope == "global") {
            json event_data;
            event_data["key"] = key;
            event_data["action"] = "store";
            event_data["agent_id"] = msg.agent_id;
            context_.event_bus.emit(KernelEventType::STATE_CHANGED, event_data, msg.agent_id);
        }

        json response;
        response["success"] = true;
        response["key"] = key;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_STORE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_STORE, response.dump());
    }
}

ipc::Message StateSyscalls::handle_fetch(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string key = j.value("key", "");
        if (key.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "key is required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_FETCH, response.dump());
        }

        auto result = context_.state_store.fetch(msg.agent_id, key);

        if (!result.success) {
            json response;
            response["success"] = false;
            response["error"] = "failed to fetch key";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_FETCH, response.dump());
        }

        json response;
        response["success"] = true;
        response["exists"] = result.exists;
        response["value"] = result.value;
        if (result.exists) {
            response["scope"] = result.scope;
        }
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_FETCH, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_FETCH, response.dump());
    }
}

ipc::Message StateSyscalls::handle_delete(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string key = j.value("key", "");
        if (key.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "key is required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_DELETE, response.dump());
        }

        auto result = context_.state_store.erase(msg.agent_id, key);
        if (result.deleted) {
            spdlog::debug("Agent {} deleted key '{}'", msg.agent_id, key);
        }

        json response;
        response["success"] = result.success;
        response["deleted"] = result.deleted;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_DELETE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_DELETE, response.dump());
    }
}

ipc::Message StateSyscalls::handle_keys(const ipc::Message& msg) {
    try {
        json j;
        if (!msg.payload.empty()) {
            j = json::parse(msg.payload_str());
        }

        std::string prefix = j.value("prefix", "");
        std::vector<std::string> keys = context_.state_store.keys(msg.agent_id, prefix);

        json response;
        response["success"] = true;
        response["keys"] = keys;
        response["count"] = keys.size();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_KEYS, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_KEYS, response.dump());
    }
}

} // namespace clove::kernel
