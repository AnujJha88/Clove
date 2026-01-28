#pragma once
#include <string>

namespace clove::kernel {

// Kernel configuration
struct KernelConfig {
    std::string socket_path = "/tmp/clove.sock";
    bool enable_sandboxing = true;
    // Tunnel configuration
    std::string relay_url;               // Relay server URL (ws://...)
    std::string machine_id;              // This machine's ID
    std::string machine_token;           // Authentication token
    bool tunnel_auto_connect = false;    // Auto-connect on startup
};

} // namespace clove::kernel
