#pragma once
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include <functional>
#include <chrono>
#include "runtime/agent/process.hpp"

namespace clove::runtime {

// Agent manager - handles multiple agents
class AgentManager {
public:
    AgentManager(const std::string& kernel_socket);
    ~AgentManager();

    // Create and start an agent
    std::shared_ptr<AgentProcess> spawn_agent(const AgentConfig& config);

    // Get agent by name or ID
    std::shared_ptr<AgentProcess> get_agent(const std::string& name);
    std::shared_ptr<AgentProcess> get_agent(uint32_t id);

    // Stop and remove agent
    bool kill_agent(const std::string& name);
    bool kill_agent(uint32_t id);

    // Pause and resume agent
    bool pause_agent(const std::string& name);
    bool pause_agent(uint32_t id);
    bool resume_agent(const std::string& name);
    bool resume_agent(uint32_t id);

    // List agents
    std::vector<std::shared_ptr<AgentProcess>> list_agents() const;

    // Stop all agents
    void stop_all();

    // Check for dead agents and handle restarts
    void reap_and_restart_agents();

    // Process pending restarts (called from main loop)
    void process_pending_restarts();

    // Set event callback for restart events (AGENT_RESTARTING, AGENT_ESCALATED)
    using RestartEventCallback = std::function<void(const std::string& event_type,
                                                     const std::string& agent_name,
                                                     uint32_t restart_count,
                                                     int exit_code)>;
    void set_restart_event_callback(RestartEventCallback callback);

    // Legacy method (now calls reap_and_restart_agents)
    void reap_agents() { reap_and_restart_agents(); }

private:
    std::string kernel_socket_;
    std::unordered_map<std::string, std::shared_ptr<AgentProcess>> agents_by_name_;
    std::unordered_map<uint32_t, std::shared_ptr<AgentProcess>> agents_by_id_;
    SandboxManager sandbox_manager_;

    // Restart state tracking (survives agent death)
    struct RestartState {
        uint32_t restart_count = 0;
        std::chrono::steady_clock::time_point window_start;
        uint32_t consecutive_failures = 0;
        bool escalated = false;
    };
    std::unordered_map<std::string, RestartState> restart_states_;
    std::unordered_map<std::string, AgentConfig> saved_configs_;

    // Pending restart queue
    struct PendingRestart {
        std::string agent_name;
        std::chrono::steady_clock::time_point scheduled_time;
        AgentConfig config;
    };
    std::vector<PendingRestart> pending_restarts_;

    // Event callback for restart notifications
    RestartEventCallback restart_event_callback_;

    // Helper to calculate backoff delay
    uint32_t calculate_backoff_delay(const RestartConfig& config, uint32_t consecutive_failures);
};

} // namespace clove::runtime
