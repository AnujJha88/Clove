#pragma once
#include <chrono>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>
#include <nlohmann/json.hpp>

namespace clove::kernel {

// State Store entry
struct StoredValue {
    nlohmann::json value;
    std::chrono::steady_clock::time_point expires_at;
    uint32_t owner_agent_id;
    std::string scope;  // "global", "agent", "session"

    bool is_expired() const {
        if (expires_at == std::chrono::steady_clock::time_point{}) return false;
        return std::chrono::steady_clock::now() > expires_at;
    }
};

struct StoreResult {
    bool success = false;
    std::string key;
    std::string scope;
};

struct FetchResult {
    bool success = false;
    bool exists = false;
    nlohmann::json value;
    std::string scope;
};

struct DeleteResult {
    bool success = false;
    bool deleted = false;
};

class StateStore {
public:
    StoreResult store(uint32_t agent_id, const std::string& key,
                      const nlohmann::json& value, const std::string& scope,
                      std::optional<int> ttl_secs);

    FetchResult fetch(uint32_t agent_id, const std::string& key);
    DeleteResult erase(uint32_t agent_id, const std::string& key);
    std::vector<std::string> keys(uint32_t agent_id, const std::string& prefix);

private:
    std::unordered_map<std::string, StoredValue> store_;
    std::mutex mutex_;

    bool can_access_key(uint32_t agent_id, const StoredValue& value) const;
    static std::string make_agent_key(uint32_t agent_id, const std::string& key);
};

} // namespace clove::kernel
