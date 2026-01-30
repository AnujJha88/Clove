#include "kernel/state_store.hpp"

namespace clove::kernel {

StoreResult StateStore::store(uint32_t agent_id, const std::string& key,
                              const nlohmann::json& value, const std::string& scope,
                              std::optional<int> ttl_secs) {
    StoreResult result;
    if (key.empty()) {
        return result;
    }

    StoredValue entry;
    entry.value = value;
    entry.owner_agent_id = agent_id;
    entry.scope = scope.empty() ? "global" : scope;

    if (ttl_secs.has_value()) {
        entry.expires_at = std::chrono::steady_clock::now() + std::chrono::seconds(*ttl_secs);
    }

    if (entry.scope != "global" && entry.scope != "agent" && entry.scope != "session") {
        entry.scope = "global";
    }

    std::string store_key = key;
    if (entry.scope == "agent") {
        store_key = make_agent_key(agent_id, key);
    }

    std::string final_scope = entry.scope;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        store_[store_key] = std::move(entry);
    }

    result.success = true;
    result.key = key;
    result.scope = final_scope;
    return result;
}

FetchResult StateStore::fetch(uint32_t agent_id, const std::string& key) {
    FetchResult result;
    if (key.empty()) {
        return result;
    }

    std::vector<std::string> keys_to_try = {
        key,
        make_agent_key(agent_id, key)
    };

    std::lock_guard<std::mutex> lock(mutex_);

    for (const auto& try_key : keys_to_try) {
        auto it = store_.find(try_key);
        if (it == store_.end()) {
            continue;
        }

        if (it->second.is_expired()) {
            store_.erase(it);
            continue;
        }

        if (!can_access_key(agent_id, it->second)) {
            continue;
        }

        result.success = true;
        result.exists = true;
        result.value = it->second.value;
        result.scope = it->second.scope;
        return result;
    }

    result.success = true;
    result.exists = false;
    result.value = nullptr;
    return result;
}

DeleteResult StateStore::erase(uint32_t agent_id, const std::string& key) {
    DeleteResult result;
    if (key.empty()) {
        return result;
    }  

    std::vector<std::string> keys_to_try = {
        key,
        make_agent_key(agent_id, key)
    };

    std::lock_guard<std::mutex> lock(mutex_);

    for (const auto& try_key : keys_to_try) {
        auto it = store_.find(try_key);
        if (it == store_.end()) {
            continue;
        }

        if (it->second.owner_agent_id == agent_id || it->second.scope == "global") {
            store_.erase(it);
            result.success = true;
            result.deleted = true;
            return result;
        }
    }

    result.success = true;
    result.deleted = false;
    return result;
}

std::vector<std::string> StateStore::keys(uint32_t agent_id, const std::string& prefix) {
    std::lock_guard<std::mutex> lock(mutex_);

    std::vector<std::string> keys;
    for (auto it = store_.begin(); it != store_.end(); ) {
        if (it->second.is_expired()) {
            it = store_.erase(it);
            continue;
        }

        if (!can_access_key(agent_id, it->second)) {
            ++it;
            continue;
        }

        const std::string& key = it->first;
        if (prefix.empty() || key.find(prefix) == 0) {
            if (key.find("agent:") == 0) {
                size_t second_colon = key.find(':', 6);
                if (second_colon != std::string::npos) {
                    keys.push_back(key.substr(second_colon + 1));
                } else {
                    keys.push_back(key);
                }
            } else {
                keys.push_back(key);
            }
        }

        ++it;
    }

    return keys;
}

bool StateStore::can_access_key(uint32_t agent_id, const StoredValue& value) const {
    if (value.scope == "global") return true;
    if (value.scope == "agent" && value.owner_agent_id == agent_id) return true;
    if (value.scope == "session") return true;
    return false;
}

std::string StateStore::make_agent_key(uint32_t agent_id, const std::string& key) {
    return "agent:" + std::to_string(agent_id) + ":" + key;
}

} // namespace clove::kernel
