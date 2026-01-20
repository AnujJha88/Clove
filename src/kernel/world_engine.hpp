/**
 * AgentOS World Simulation Engine
 *
 * Provides isolated, configurable environments ("worlds") where agents operate
 * without affecting real systems. Agents in a world see virtualized filesystems
 * and mocked network responses.
 */
#pragma once
#include "virtual_fs.hpp"
#include <string>
#include <unordered_map>
#include <set>
#include <memory>
#include <mutex>
#include <random>
#include <optional>
#include <chrono>
#include <functional>
#include <nlohmann/json.hpp>

namespace agentos::kernel {

// Forward declarations
class World;
class WorldEngine;

// Type aliases
using WorldId = std::string;

/**
 * Mocked network response
 */
struct MockResponse {
    int status_code = 200;
    std::string body;
    std::unordered_map<std::string, std::string> headers;
    uint32_t latency_ms = 0;  // Simulated network delay
};

/**
 * Network mocking for a world
 * Intercepts HTTP requests and returns configured mock responses
 */
class NetworkMock {
public:
    /**
     * Configure from JSON
     * {
     *   "mode": "mock" | "passthrough" | "record",
     *   "mock_responses": {
     *     "https://api.example.com/data": {
     *       "status": 200, "body": "...", "latency_ms": 100
     *     }
     *   },
     *   "default_response": {...},  // For unmatched URLs
     *   "allowed_domains": ["api.example.com"],  // Passthrough allowlist
     *   "fail_unmatched": true  // Return error for unmatched
     * }
     */
    void configure(const nlohmann::json& config);

    /**
     * Check if a URL should be intercepted
     */
    bool should_intercept(const std::string& url) const;

    /**
     * Get mock response for a URL
     * Returns nullopt if URL not configured and fail_unmatched is false
     */
    std::optional<MockResponse> get_response(const std::string& url,
                                              const std::string& method = "GET") const;

    /**
     * Add a mock response
     */
    void add_mock(const std::string& url_pattern, const MockResponse& response);

    /**
     * Remove a mock response
     */
    void remove_mock(const std::string& url_pattern);

    /**
     * Record a response (for record mode)
     */
    void record(const std::string& url, const std::string& method,
                int status, const std::string& body);

    /**
     * Get recorded responses
     */
    nlohmann::json get_recorded() const;

    /**
     * Check if mocking is enabled
     */
    bool is_enabled() const;

    /**
     * Serialize to JSON
     */
    nlohmann::json to_json() const;

    /**
     * Restore from JSON
     */
    void from_json(const nlohmann::json& j);

    /**
     * Get metrics
     */
    nlohmann::json get_metrics() const;

private:
    std::string mode_ = "passthrough";  // mock, passthrough, record
    std::unordered_map<std::string, MockResponse> mocks_;  // URL pattern -> response
    std::optional<MockResponse> default_response_;
    std::vector<std::string> allowed_domains_;
    bool fail_unmatched_ = false;

    // Recording mode storage
    std::vector<nlohmann::json> recorded_;

    // Metrics
    mutable uint64_t requests_intercepted_ = 0;
    mutable uint64_t requests_passed_through_ = 0;
    mutable uint64_t requests_failed_ = 0;

    mutable std::mutex mutex_;

    /**
     * Check if URL matches pattern (supports wildcards)
     */
    bool matches_url(const std::string& url, const std::string& pattern) const;

    /**
     * Extract domain from URL
     */
    std::string extract_domain(const std::string& url) const;
};

/**
 * Chaos engineering for a world
 * Injects failures, delays, and other adverse conditions
 */
class ChaosEngine {
public:
    /**
     * Configure from JSON
     * {
     *   "enabled": true,
     *   "failure_rate": 0.1,  // 10% of operations fail
     *   "latency": {"min_ms": 10, "max_ms": 1000},
     *   "rules": [
     *     {"type": "file_read_fail", "path_pattern": "/critical/*", "probability": 0.5},
     *     {"type": "network_timeout", "url_pattern": "https://slow.api/*", "probability": 0.3}
     *   ]
     * }
     */
    void configure(const nlohmann::json& config);

    /**
     * Check if a file read should fail
     */
    bool should_fail_read(const std::string& path) const;

    /**
     * Check if a file write should fail
     */
    bool should_fail_write(const std::string& path) const;

    /**
     * Check if a network request should fail/timeout
     */
    bool should_fail_network(const std::string& url) const;

    /**
     * Get random latency to inject (ms)
     */
    uint32_t get_latency() const;

    /**
     * Inject a specific chaos event
     * Types: "file_corruption", "network_partition", "slow_io", "disk_full"
     */
    void inject_event(const std::string& event_type, const nlohmann::json& params);

    /**
     * Clear all active chaos conditions
     */
    void clear_events();

    /**
     * Check if chaos is enabled
     */
    bool is_enabled() const;

    /**
     * Serialize to JSON
     */
    nlohmann::json to_json() const;

    /**
     * Restore from JSON
     */
    void from_json(const nlohmann::json& j);

    /**
     * Get metrics
     */
    nlohmann::json get_metrics() const;

private:
    bool enabled_ = false;
    double failure_rate_ = 0.0;
    uint32_t latency_min_ms_ = 0;
    uint32_t latency_max_ms_ = 0;

    struct ChaosRule {
        std::string type;
        std::string pattern;
        double probability;
    };
    std::vector<ChaosRule> rules_;

    // Active injected events
    std::set<std::string> active_events_;
    nlohmann::json event_params_;

    // Metrics
    mutable uint64_t failures_injected_ = 0;
    mutable uint64_t latency_injected_ = 0;

    mutable std::mutex mutex_;
    mutable std::mt19937 rng_{std::random_device{}()};

    bool should_fail(double probability) const;
    bool matches_pattern(const std::string& str, const std::string& pattern) const;
};

/**
 * World metrics
 */
struct WorldMetrics {
    uint64_t agent_count = 0;
    uint64_t syscall_count = 0;
    uint64_t vfs_reads = 0;
    uint64_t vfs_writes = 0;
    uint64_t network_requests = 0;
    uint64_t chaos_failures = 0;
    std::chrono::steady_clock::time_point created_at;
    std::chrono::steady_clock::time_point last_activity;
};

/**
 * A simulated world environment
 */
class World {
public:
    explicit World(const WorldId& id);

    /**
     * Configure world from JSON
     * {
     *   "virtual_filesystem": {...},
     *   "network": {...},
     *   "chaos": {...},
     *   "name": "optional display name",
     *   "description": "optional description"
     * }
     */
    void configure(const nlohmann::json& config);

    // Getters
    const WorldId& id() const { return id_; }
    const std::string& name() const { return name_; }
    const std::string& description() const { return description_; }

    // Subsystems
    VirtualFilesystem& vfs() { return vfs_; }
    const VirtualFilesystem& vfs() const { return vfs_; }

    NetworkMock& network() { return network_; }
    const NetworkMock& network() const { return network_; }

    ChaosEngine& chaos() { return chaos_; }
    const ChaosEngine& chaos() const { return chaos_; }

    // Agent management
    void add_agent(uint32_t agent_id);
    void remove_agent(uint32_t agent_id);
    bool has_agent(uint32_t agent_id) const;
    std::set<uint32_t> get_agents() const;
    size_t agent_count() const;

    // Metrics
    void record_syscall();
    WorldMetrics get_metrics() const;

    // Serialization
    nlohmann::json to_json() const;
    void from_json(const nlohmann::json& j);

    // Configuration
    nlohmann::json get_config() const { return config_; }

private:
    WorldId id_;
    std::string name_;
    std::string description_;
    nlohmann::json config_;

    VirtualFilesystem vfs_;
    NetworkMock network_;
    ChaosEngine chaos_;

    std::set<uint32_t> agents_;
    mutable WorldMetrics metrics_;
    mutable std::mutex mutex_;
};

/**
 * World Engine - manages all world instances
 */
class WorldEngine {
public:
    WorldEngine() = default;

    /**
     * Create a new world
     * Returns world ID on success, nullopt on failure
     */
    std::optional<WorldId> create_world(const std::string& name,
                                         const nlohmann::json& config);

    /**
     * Destroy a world
     * Returns false if world doesn't exist or has agents
     */
    bool destroy_world(const WorldId& world_id, bool force = false);

    /**
     * List all worlds
     */
    std::vector<nlohmann::json> list_worlds() const;

    /**
     * Get world by ID
     */
    World* get_world(const WorldId& world_id);
    const World* get_world(const WorldId& world_id) const;

    /**
     * Join an agent to a world
     */
    bool join_world(uint32_t agent_id, const WorldId& world_id);

    /**
     * Remove an agent from its world
     */
    bool leave_world(uint32_t agent_id);

    /**
     * Check if agent is in a world
     */
    bool is_agent_in_world(uint32_t agent_id) const;

    /**
     * Get the world an agent is in
     */
    std::optional<WorldId> get_agent_world(uint32_t agent_id) const;

    /**
     * Inject a chaos event into a world
     */
    bool inject_event(const WorldId& world_id, const std::string& event_type,
                      const nlohmann::json& params);

    /**
     * Get world state/metrics
     */
    std::optional<nlohmann::json> get_world_state(const WorldId& world_id) const;

    /**
     * Create a snapshot of a world
     */
    std::optional<nlohmann::json> snapshot_world(const WorldId& world_id) const;

    /**
     * Restore a world from snapshot
     * Can either restore to existing world or create new one
     */
    std::optional<WorldId> restore_world(const nlohmann::json& snapshot,
                                          const std::string& new_world_id = "");

    /**
     * Get overall engine metrics
     */
    nlohmann::json get_metrics() const;

private:
    std::unordered_map<WorldId, std::unique_ptr<World>> worlds_;
    std::unordered_map<uint32_t, WorldId> agent_to_world_;
    mutable std::mutex mutex_;

    uint64_t next_world_num_ = 1;

    /**
     * Generate a unique world ID
     */
    WorldId generate_world_id(const std::string& name);
};

} // namespace agentos::kernel
