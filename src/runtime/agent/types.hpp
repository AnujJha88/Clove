#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <sys/types.h>
#include "runtime/sandbox/sandbox.hpp"

namespace clove::runtime {

// Restart policy for automatic agent recovery
enum class RestartPolicy {
    NEVER,       // Never restart (default)
    ALWAYS,      // Always restart regardless of exit code
    ON_FAILURE   // Restart only on non-zero exit code
};

inline RestartPolicy restart_policy_from_string(const std::string& str) {
    if (str == "always") return RestartPolicy::ALWAYS;
    if (str == "on-failure" || str == "on_failure") return RestartPolicy::ON_FAILURE;
    return RestartPolicy::NEVER;
}

inline const char* restart_policy_to_string(RestartPolicy policy) {
    switch (policy) {
        case RestartPolicy::ALWAYS: return "always";
        case RestartPolicy::ON_FAILURE: return "on-failure";
        default: return "never";
    }
}

// Configuration for automatic restart behavior
struct RestartConfig {
    RestartPolicy policy = RestartPolicy::NEVER;
    uint32_t max_restarts = 5;            // Max restarts within window
    uint32_t restart_window_sec = 300;    // Window for counting restarts (seconds)
    uint32_t backoff_initial_ms = 1000;   // Initial backoff delay
    uint32_t backoff_max_ms = 60000;      // Maximum backoff delay
    double backoff_multiplier = 2.0;      // Exponential backoff multiplier
};

// Agent configuration
struct AgentConfig {
    std::string name;
    std::string script_path;               // Path to Python script
    std::string python_path = "python3";   // Python interpreter
    std::string socket_path;               // Kernel socket to connect to

    // Resource limits
    ResourceLimits limits;

    // Sandbox options
    bool sandboxed = true;
    bool enable_network = false;

    // Restart configuration
    RestartConfig restart;
};

// Agent state
enum class AgentState {
    CREATED,
    STARTING,
    RUNNING,
    PAUSED,
    STOPPING,
    STOPPED,
    FAILED
};

const char* agent_state_to_string(AgentState state);

// Agent metrics snapshot
struct AgentMetrics {
    uint32_t id;
    std::string name;
    pid_t pid;
    AgentState state;

    // Resource usage (populated from cgroups)
    uint64_t memory_bytes;
    double cpu_percent;
    uint64_t uptime_seconds;

    // LLM activity
    uint64_t llm_request_count;
    uint64_t llm_tokens_used;

    // Hierarchy
    uint32_t parent_id;  // 0 = kernel-spawned
    std::vector<uint32_t> child_ids;

    // Timestamps
    uint64_t created_at_ms;
};

} // namespace clove::runtime
