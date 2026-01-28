#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/permissions_store.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void PermissionSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_GET_PERMS,
        [this](const ipc::Message& msg) { return handle_get_perms(msg); });
    router.register_handler(ipc::SyscallOp::SYS_SET_PERMS,
        [this](const ipc::Message& msg) { return handle_set_perms(msg); });
}

AgentPermissions& PermissionSyscalls::get_agent_permissions(uint32_t agent_id) {
    return context_.permissions_store.get_or_create(agent_id);
}

ipc::Message PermissionSyscalls::handle_get_perms(const ipc::Message& msg) {
    auto& perms = get_agent_permissions(msg.agent_id);

    json response;
    response["success"] = true;
    response["permissions"] = perms.to_json();

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_GET_PERMS, response.dump());
}

ipc::Message PermissionSyscalls::handle_set_perms(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        uint32_t target_id = j.value("agent_id", msg.agent_id);
        auto& caller_perms = get_agent_permissions(msg.agent_id);

        // Only agents with can_spawn permission can set other agents' permissions
        if (target_id != msg.agent_id && !caller_perms.can_spawn) {
            json response;
            response["success"] = false;
            response["error"] = "Permission denied: cannot modify other agent's permissions";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SET_PERMS, response.dump());
        }

        // Parse and set new permissions
        if (j.contains("permissions")) {
            context_.permissions_store.set_permissions(target_id, AgentPermissions::from_json(j["permissions"]));
            spdlog::info("Agent {} set permissions for agent {}", msg.agent_id, target_id);
        } else if (j.contains("level")) {
            std::string level_str = j["level"].get<std::string>();
            PermissionLevel level = PermissionLevel::STANDARD;

            if (level_str == "unrestricted") level = PermissionLevel::UNRESTRICTED;
            else if (level_str == "standard") level = PermissionLevel::STANDARD;
            else if (level_str == "sandboxed") level = PermissionLevel::SANDBOXED;
            else if (level_str == "readonly") level = PermissionLevel::READONLY;
            else if (level_str == "minimal") level = PermissionLevel::MINIMAL;

            context_.permissions_store.set_level(target_id, level);
            spdlog::info("Agent {} set permission level {} for agent {}", msg.agent_id, level_str, target_id);
        }

        json response;
        response["success"] = true;
        response["agent_id"] = target_id;

        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SET_PERMS, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse set_perms request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SET_PERMS, response.dump());
    }
}

} // namespace clove::kernel
