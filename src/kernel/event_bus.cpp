#include "kernel/event_bus.hpp"
#include <spdlog/spdlog.h>

namespace clove::kernel {

void EventBus::emit(KernelEventType type, const nlohmann::json& data, uint32_t source_agent_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    KernelEvent event;
    event.type = type;
    event.data = data;
    event.timestamp = std::chrono::steady_clock::now();
    event.source_agent_id = source_agent_id;

    for (const auto& [agent_id, subscriptions] : subscriptions_) {
        if (subscriptions.count(type) > 0) {
            queues_[agent_id].push(event);
            spdlog::debug("Event {} queued for agent {}", kernel_event_type_to_string(type), agent_id);
        }
    }
}

void EventBus::subscribe(uint32_t agent_id, const std::vector<KernelEventType>& types) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto& subs = subscriptions_[agent_id];
    for (auto type : types) {
        subs.insert(type);
    }
}

void EventBus::unsubscribe(uint32_t agent_id, const std::vector<KernelEventType>& types, bool unsubscribe_all) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (unsubscribe_all) {
        subscriptions_.erase(agent_id);
        return;
    }

    auto it = subscriptions_.find(agent_id);
    if (it == subscriptions_.end()) {
        return;
    }

    for (auto type : types) {
        it->second.erase(type);
    }
}

nlohmann::json EventBus::poll(uint32_t agent_id, int max_events) {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json events_array = nlohmann::json::array();
    auto it = queues_.find(agent_id);
    if (it == queues_.end()) {
        return events_array;
    }

    auto& queue = it->second;
    int count = 0;

    while (!queue.empty() && count < max_events) {
        const auto& event = queue.front();

        nlohmann::json event_json;
        event_json["type"] = kernel_event_type_to_string(event.type);
        event_json["data"] = event.data;
        event_json["source_agent_id"] = event.source_agent_id;

        auto duration = event.timestamp.time_since_epoch();
        auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(duration).count();
        event_json["timestamp"] = millis;

        events_array.push_back(event_json);
        queue.pop();
        count++;
    }

    return events_array;
}

} // namespace clove::kernel
