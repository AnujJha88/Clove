#pragma once
#include <cstdint>
#include <queue>
#include <set>
#include <unordered_map>
#include <mutex>
#include <chrono>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace clove::kernel {

// Kernel event types for pub/sub system (not to be confused with reactor EventType)
enum class KernelEventType {
    AGENT_SPAWNED,      // New agent started
    AGENT_EXITED,       // Agent terminated
    AGENT_PAUSED,       // Agent paused
    AGENT_RESUMED,      // Agent resumed
    AGENT_RESTARTING,   // Agent is being restarted (hot reload)
    AGENT_ESCALATED,    // Agent exceeded max restarts, escalating
    MESSAGE_RECEIVED,   // New IPC message arrived
    STATE_CHANGED,      // State store key modified
    SYSCALL_BLOCKED,    // Permission denied
    RESOURCE_WARNING,   // Approaching resource limits
    CUSTOM              // User-defined event
};

// Kernel event
struct KernelEvent {
    KernelEventType type;
    nlohmann::json data;
    std::chrono::steady_clock::time_point timestamp;
    uint32_t source_agent_id;  // 0 = kernel
};

// Convert KernelEventType to string
inline std::string kernel_event_type_to_string(KernelEventType type) {
    switch (type) {
        case KernelEventType::AGENT_SPAWNED:    return "AGENT_SPAWNED";
        case KernelEventType::AGENT_EXITED:     return "AGENT_EXITED";
        case KernelEventType::AGENT_PAUSED:     return "AGENT_PAUSED";
        case KernelEventType::AGENT_RESUMED:    return "AGENT_RESUMED";
        case KernelEventType::AGENT_RESTARTING: return "AGENT_RESTARTING";
        case KernelEventType::AGENT_ESCALATED:  return "AGENT_ESCALATED";
        case KernelEventType::MESSAGE_RECEIVED: return "MESSAGE_RECEIVED";
        case KernelEventType::STATE_CHANGED:    return "STATE_CHANGED";
        case KernelEventType::SYSCALL_BLOCKED:  return "SYSCALL_BLOCKED";
        case KernelEventType::RESOURCE_WARNING: return "RESOURCE_WARNING";
        case KernelEventType::CUSTOM:           return "CUSTOM";
        default: return "UNKNOWN";
    }
}

// Parse KernelEventType from string
inline KernelEventType kernel_event_type_from_string(const std::string& str) {
    if (str == "AGENT_SPAWNED")    return KernelEventType::AGENT_SPAWNED;
    if (str == "AGENT_EXITED")     return KernelEventType::AGENT_EXITED;
    if (str == "AGENT_PAUSED")     return KernelEventType::AGENT_PAUSED;
    if (str == "AGENT_RESUMED")    return KernelEventType::AGENT_RESUMED;
    if (str == "AGENT_RESTARTING") return KernelEventType::AGENT_RESTARTING;
    if (str == "AGENT_ESCALATED")  return KernelEventType::AGENT_ESCALATED;
    if (str == "MESSAGE_RECEIVED") return KernelEventType::MESSAGE_RECEIVED;
    if (str == "STATE_CHANGED")    return KernelEventType::STATE_CHANGED;
    if (str == "SYSCALL_BLOCKED")  return KernelEventType::SYSCALL_BLOCKED;
    if (str == "RESOURCE_WARNING") return KernelEventType::RESOURCE_WARNING;
    return KernelEventType::CUSTOM;
}

class EventBus {
public:
    void emit(KernelEventType type, const nlohmann::json& data, uint32_t source_agent_id);
    void subscribe(uint32_t agent_id, const std::vector<KernelEventType>& types);
    void unsubscribe(uint32_t agent_id, const std::vector<KernelEventType>& types, bool unsubscribe_all);
    nlohmann::json poll(uint32_t agent_id, int max_events);

private:
    std::unordered_map<uint32_t, std::set<KernelEventType>> subscriptions_;
    std::unordered_map<uint32_t, std::queue<KernelEvent>> queues_;
    std::mutex mutex_;
};

} // namespace clove::kernel
