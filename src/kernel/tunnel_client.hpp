/**
 * Clove Tunnel Client
 *
 * Manages connection to a relay server for remote agent connectivity.
 * Runs a Python subprocess (tunnel_client.py) and communicates via JSON.
 */
#pragma once
#include <string>
#include <memory>
#include <atomic>
#include <queue>
#include <mutex>
#include <functional>
#include <thread>
#include <unordered_map>
#include <condition_variable>
#include <nlohmann/json.hpp>

namespace clove::kernel {

// Configuration for tunnel connection
struct TunnelConfig {
    std::string relay_url;
    std::string machine_id;
    std::string token;
    int reconnect_interval = 5;
    bool auto_connect = false;
};

// Information about a connected remote agent
struct RemoteAgentInfo {
    uint32_t agent_id;
    std::string name;
    std::string connected_at;
};

// Tunnel status
struct TunnelStatus {
    bool connected = false;
    std::string relay_url;
    std::string machine_id;
    int remote_agent_count = 0;
    std::string error;
};

// Event from tunnel (syscall from remote agent)
struct TunnelEvent {
    enum class Type {
        AGENT_CONNECTED,
        AGENT_DISCONNECTED,
        SYSCALL,
        ERROR,
        DISCONNECTED,
        RECONNECTED
    };

    Type type;
    uint32_t agent_id = 0;
    std::string agent_name;
    uint8_t opcode = 0;
    std::vector<uint8_t> payload;
    std::string error;
};

class TunnelClient {
public:
    TunnelClient();
    ~TunnelClient();

    // Non-copyable
    TunnelClient(const TunnelClient&) = delete;
    TunnelClient& operator=(const TunnelClient&) = delete;

    // Initialize the tunnel subprocess
    bool init(const std::string& scripts_dir = "");

    // Configure tunnel settings
    bool configure(const TunnelConfig& config);

    // Connect to relay server
    bool connect();

    // Disconnect from relay server
    void disconnect();

    // Check if connected
    bool is_connected() const { return connected_; }

    // Get current status
    TunnelStatus get_status() const;

    // Get list of connected remote agents
    std::vector<RemoteAgentInfo> list_remote_agents() const;

    // Send response to a remote agent's syscall
    bool send_response(uint32_t agent_id, uint8_t opcode,
                      const std::vector<uint8_t>& payload);

    // Poll for pending events (non-blocking)
    std::vector<TunnelEvent> poll_events();

    // Set event callback (called when events arrive)
    void set_event_callback(std::function<void(const TunnelEvent&)> callback);

    // Shutdown the tunnel client
    void shutdown();

private:
    TunnelConfig config_;
    std::atomic<bool> running_{false};
    std::atomic<bool> connected_{false};

    // Subprocess handles
    pid_t subprocess_pid_ = -1;
    int stdin_fd_ = -1;
    int stdout_fd_ = -1;

    // Event handling
    std::queue<TunnelEvent> event_queue_;
    mutable std::mutex event_mutex_;
    std::function<void(const TunnelEvent&)> event_callback_;

    // Remote agents
    std::unordered_map<uint32_t, RemoteAgentInfo> remote_agents_;
    mutable std::mutex agents_mutex_;

    // Reader thread
    std::thread reader_thread_;

    // Request-response tracking
    int next_request_id_ = 1;
    std::unordered_map<int, nlohmann::json> pending_responses_;
    std::mutex response_mutex_;
    std::condition_variable response_cv_;

    // Internal methods
    bool spawn_subprocess(const std::string& scripts_dir);
    bool send_request(const nlohmann::json& request);
    std::optional<nlohmann::json> send_request_and_wait(
        const nlohmann::json& request, int timeout_ms = 5000);
    void reader_loop();
    void handle_event(const nlohmann::json& event);
    void handle_response(const nlohmann::json& response);
};

} // namespace clove::kernel
