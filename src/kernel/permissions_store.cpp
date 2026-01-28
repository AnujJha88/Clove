#include "kernel/permissions_store.hpp"

namespace clove::kernel {

AgentPermissions& PermissionsStore::get_or_create(uint32_t agent_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = permissions_.find(agent_id);
    if (it == permissions_.end()) {
        permissions_[agent_id] = AgentPermissions::from_level(PermissionLevel::STANDARD);
    }
    return permissions_[agent_id];
}

void PermissionsStore::set_permissions(uint32_t agent_id, const AgentPermissions& perms) {
    std::lock_guard<std::mutex> lock(mutex_);
    permissions_[agent_id] = perms;
}

void PermissionsStore::set_level(uint32_t agent_id, PermissionLevel level) {
    std::lock_guard<std::mutex> lock(mutex_);
    permissions_[agent_id] = AgentPermissions::from_level(level);
}

} // namespace clove::kernel
