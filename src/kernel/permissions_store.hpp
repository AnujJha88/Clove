#pragma once
#include <cstdint>
#include <unordered_map>
#include <mutex>
#include "kernel/permissions.hpp"

namespace clove::kernel {

class PermissionsStore {
public:
    AgentPermissions& get_or_create(uint32_t agent_id);
    void set_permissions(uint32_t agent_id, const AgentPermissions& perms);
    void set_level(uint32_t agent_id, PermissionLevel level);

private:
    std::unordered_map<uint32_t, AgentPermissions> permissions_;
    std::mutex mutex_;
};

} // namespace clove::kernel
