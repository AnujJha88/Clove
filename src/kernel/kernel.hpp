/**
 * AgentOS Kernel
 *
 * Main kernel class that orchestrates all subsystems:
 * - Reactor (epoll event loop)
 * - SocketServer (Unix domain socket IPC)
 * - AgentManager (process lifecycle)
 * - LLMClient (Gemini API subprocess)
 * - Permissions (access control)
 */
#pragma once
#include <string>
#include <memory>
#include <atomic>
#include <queue>
#include <unordered_map>
#include <set>
#include <mutex>
#include <chrono>
#include "kernel/reactor.hpp"
#include "kernel/llm_client.hpp"
#include "kernel/permissions.hpp"
#include "ipc/socket_server.hpp"
#include "runtime/agent_process.hpp"
#include <nlohmann/json.hpp>

namespace agentos::kernel {

// IPC Message for agent-to-agent communication
struct IPCMessage {
    uint32_t from_id;
    std::string from_name;
    nlohmann::json message;
    std::chrono::steady_clock::time_point timestamp;
};

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

// Kernel event types for pub/sub system (not to be confused with reactor EventType)
enum class KernelEventType {
    AGENT_SPAWNED,      // New agent started
    AGENT_EXITED,       // Agent terminated
    MESSAGE_RECEIVED,   // New IPC message arrived
    STATE_CHANGED,      // State store key modified
    SYSCALL_BLOCKED,    // Permission denied
    RESOURCE_WARNING,   // Approaching resource limits
    CUSTOM              // User-defined event
};

// Convert KernelEventType to string
inline std::string kernel_event_type_to_string(KernelEventType type) {
    switch (type) {
        case KernelEventType::AGENT_SPAWNED:    return "AGENT_SPAWNED";
        case KernelEventType::AGENT_EXITED:     return "AGENT_EXITED";
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
    if (str == "MESSAGE_RECEIVED") return KernelEventType::MESSAGE_RECEIVED;
    if (str == "STATE_CHANGED")    return KernelEventType::STATE_CHANGED;
    if (str == "SYSCALL_BLOCKED")  return KernelEventType::SYSCALL_BLOCKED;
    if (str == "RESOURCE_WARNING") return KernelEventType::RESOURCE_WARNING;
    return KernelEventType::CUSTOM;
}

// Kernel event
struct KernelEvent {
    KernelEventType type;
    nlohmann::json data;
    std::chrono::steady_clock::time_point timestamp;
    uint32_t source_agent_id;  // 0 = kernel
};

// Kernel configuration
struct KernelConfig {
    std::string socket_path = "/tmp/agentos.sock";
    bool enable_sandboxing = true;
    std::string gemini_api_key;          // Gemini API key (or from env)
    std::string llm_model = "gemini-2.0-flash";
};

class Kernel {
public:
    using Config = KernelConfig;

    Kernel();
    explicit Kernel(const Config& config);
    ~Kernel();

    // Non-copyable
    Kernel(const Kernel&) = delete;
    Kernel& operator=(const Kernel&) = delete;

    // Initialize all subsystems
    bool init();

    // Run the kernel (blocks until shutdown)
    void run();

    // Request shutdown
    void shutdown();

    // Check if running
    bool is_running() const { return running_; }

    // Access to agent manager
    runtime::AgentManager& agents() { return *agent_manager_; }

    // Get actual LLM model (after env loading)
    std::string get_llm_model() const;

    // Get config
    const Config& get_config() const { return config_; }

private:
    Config config_;
    std::atomic<bool> running_{false};

    std::unique_ptr<Reactor> reactor_;
    std::unique_ptr<ipc::SocketServer> socket_server_;
    std::unique_ptr<runtime::AgentManager> agent_manager_;
    std::unique_ptr<LLMClient> llm_client_;

    // IPC: Agent mailboxes (message queues per agent)
    std::unordered_map<uint32_t, std::queue<IPCMessage>> agent_mailboxes_;
    std::mutex mailbox_mutex_;

    // IPC: Agent name registry (name -> agent_id)
    std::unordered_map<std::string, uint32_t> agent_names_;
    std::unordered_map<uint32_t, std::string> agent_ids_to_names_;
    std::mutex registry_mutex_;

    // Permissions: Per-agent permissions
    std::unordered_map<uint32_t, AgentPermissions> agent_permissions_;
    std::mutex permissions_mutex_;

    // State Store: shared key-value storage
    std::unordered_map<std::string, StoredValue> state_store_;
    std::mutex state_store_mutex_;

    // Events: subscriptions (agent_id -> set of event types)
    std::unordered_map<uint32_t, std::set<KernelEventType>> event_subscriptions_;
    // Events: queues per agent
    std::unordered_map<uint32_t, std::queue<KernelEvent>> event_queues_;
    std::mutex events_mutex_;

    // Get or create permissions for an agent
    AgentPermissions& get_agent_permissions(uint32_t agent_id);

    // Emit an event to all subscribed agents
    void emit_event(KernelEventType type, const nlohmann::json& data, uint32_t source_agent_id = 0);

    // Check if agent can access a key (based on scope)
    bool can_access_key(uint32_t agent_id, const std::string& key, const StoredValue& value) const;

    // Event handlers
    void on_server_event(int fd, uint32_t events);
    void on_client_event(int fd, uint32_t events);

    // Message handler
    ipc::Message handle_message(const ipc::Message& msg);

    // Syscall handlers
    ipc::Message handle_think(const ipc::Message& msg);
    ipc::Message handle_spawn(const ipc::Message& msg);
    ipc::Message handle_kill(const ipc::Message& msg);
    ipc::Message handle_list(const ipc::Message& msg);
    ipc::Message handle_exec(const ipc::Message& msg);
    ipc::Message handle_read(const ipc::Message& msg);
    ipc::Message handle_write(const ipc::Message& msg);

    // IPC syscall handlers
    ipc::Message handle_send(const ipc::Message& msg);
    ipc::Message handle_recv(const ipc::Message& msg);
    ipc::Message handle_broadcast(const ipc::Message& msg);
    ipc::Message handle_register(const ipc::Message& msg);

    // Permission syscall handlers
    ipc::Message handle_get_perms(const ipc::Message& msg);
    ipc::Message handle_set_perms(const ipc::Message& msg);

    // State Store syscall handlers
    ipc::Message handle_store(const ipc::Message& msg);
    ipc::Message handle_fetch(const ipc::Message& msg);
    ipc::Message handle_delete(const ipc::Message& msg);
    ipc::Message handle_keys(const ipc::Message& msg);

    // Network syscall handlers
    ipc::Message handle_http(const ipc::Message& msg);

    // Event syscall handlers
    ipc::Message handle_subscribe(const ipc::Message& msg);
    ipc::Message handle_unsubscribe(const ipc::Message& msg);
    ipc::Message handle_poll_events(const ipc::Message& msg);
    ipc::Message handle_emit(const ipc::Message& msg);

    // Update client in reactor (for write events)
    void update_client_events(int fd);
};

} // namespace agentos::kernel
