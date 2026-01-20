#include "kernel/tunnel_client.hpp"
#include <spdlog/spdlog.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <poll.h>
#include <cstring>
#include <chrono>
#include <filesystem>

namespace fs = std::filesystem;
using json = nlohmann::json;

namespace agentos::kernel {

TunnelClient::TunnelClient() = default;

TunnelClient::~TunnelClient() {
    shutdown();
}

bool TunnelClient::init(const std::string& scripts_dir) {
    if (running_) {
        return true;
    }

    std::string dir = scripts_dir;
    if (dir.empty()) {
        // Try to find scripts directory relative to executable
        char exe_path[PATH_MAX];
        ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
        if (len > 0) {
            exe_path[len] = '\0';
            fs::path exe_dir = fs::path(exe_path).parent_path();

            // Check common locations
            std::vector<fs::path> search_paths = {
                exe_dir / "scripts",
                exe_dir / ".." / "scripts",
                exe_dir / ".." / ".." / "scripts",
                fs::path("/usr/share/agentos/scripts")
            };

            for (const auto& path : search_paths) {
                if (fs::exists(path / "tunnel_client.py")) {
                    dir = path.string();
                    break;
                }
            }
        }
    }

    if (dir.empty()) {
        spdlog::warn("Could not find tunnel_client.py - tunnel disabled");
        return false;
    }

    return spawn_subprocess(dir);
}

bool TunnelClient::spawn_subprocess(const std::string& scripts_dir) {
    std::string script_path = scripts_dir + "/tunnel_client.py";

    if (!fs::exists(script_path)) {
        spdlog::error("Tunnel client script not found: {}", script_path);
        return false;
    }

    // Create pipes for stdin/stdout
    int stdin_pipe[2];
    int stdout_pipe[2];

    if (pipe(stdin_pipe) < 0 || pipe(stdout_pipe) < 0) {
        spdlog::error("Failed to create pipes for tunnel subprocess");
        return false;
    }

    pid_t pid = fork();
    if (pid < 0) {
        spdlog::error("Failed to fork tunnel subprocess");
        close(stdin_pipe[0]);
        close(stdin_pipe[1]);
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        return false;
    }

    if (pid == 0) {
        // Child process
        close(stdin_pipe[1]);   // Close write end of stdin
        close(stdout_pipe[0]);  // Close read end of stdout

        // Redirect stdin/stdout
        dup2(stdin_pipe[0], STDIN_FILENO);
        dup2(stdout_pipe[1], STDOUT_FILENO);

        close(stdin_pipe[0]);
        close(stdout_pipe[1]);

        // Execute Python script
        execlp("python3", "python3", script_path.c_str(), nullptr);

        // If exec fails
        _exit(1);
    }

    // Parent process
    close(stdin_pipe[0]);   // Close read end of stdin
    close(stdout_pipe[1]);  // Close write end of stdout

    subprocess_pid_ = pid;
    stdin_fd_ = stdin_pipe[1];
    stdout_fd_ = stdout_pipe[0];

    // Set stdout to non-blocking for polling
    int flags = fcntl(stdout_fd_, F_GETFL, 0);
    fcntl(stdout_fd_, F_SETFL, flags | O_NONBLOCK);

    running_ = true;

    // Start reader thread
    reader_thread_ = std::thread(&TunnelClient::reader_loop, this);

    // Wait for ready event
    auto start = std::chrono::steady_clock::now();
    while (running_) {
        auto events = poll_events();
        for (const auto& ev : events) {
            if (ev.type == TunnelEvent::Type::ERROR) {
                spdlog::info("Tunnel client ready");
                return true;
            }
        }

        auto elapsed = std::chrono::steady_clock::now() - start;
        if (elapsed > std::chrono::seconds(5)) {
            spdlog::warn("Timeout waiting for tunnel client ready");
            break;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    spdlog::info("Tunnel client subprocess started (pid={})", subprocess_pid_);
    return true;
}

bool TunnelClient::configure(const TunnelConfig& config) {
    config_ = config;

    json request;
    request["id"] = next_request_id_++;
    request["method"] = "configure";
    request["params"] = {
        {"relay_url", config.relay_url},
        {"machine_id", config.machine_id},
        {"token", config.token},
        {"reconnect_interval", config.reconnect_interval}
    };

    auto response = send_request_and_wait(request);
    if (!response) {
        return false;
    }

    return response->value("result", json{}).value("success", false);
}

bool TunnelClient::connect() {
    if (!running_) {
        return false;
    }

    json request;
    request["id"] = next_request_id_++;
    request["method"] = "connect";
    request["params"] = json::object();

    auto response = send_request_and_wait(request, 30000);  // 30s timeout
    if (!response) {
        return false;
    }

    if (response->value("result", json{}).value("success", false)) {
        connected_ = true;
        spdlog::info("Tunnel connected to {}", config_.relay_url);
        return true;
    }

    auto error = response->value("error", json{}).value("message", "Unknown error");
    spdlog::error("Tunnel connect failed: {}", error);
    return false;
}

void TunnelClient::disconnect() {
    if (!running_) {
        return;
    }

    json request;
    request["id"] = next_request_id_++;
    request["method"] = "disconnect";
    request["params"] = json::object();

    send_request_and_wait(request);
    connected_ = false;

    // Clear remote agents
    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        remote_agents_.clear();
    }

    spdlog::info("Tunnel disconnected");
}

TunnelStatus TunnelClient::get_status() const {
    TunnelStatus status;
    status.connected = connected_;
    status.relay_url = config_.relay_url;
    status.machine_id = config_.machine_id;

    {
        std::lock_guard<std::mutex> lock(agents_mutex_);
        status.remote_agent_count = remote_agents_.size();
    }

    return status;
}

std::vector<RemoteAgentInfo> TunnelClient::list_remote_agents() const {
    std::lock_guard<std::mutex> lock(agents_mutex_);
    std::vector<RemoteAgentInfo> result;
    result.reserve(remote_agents_.size());
    for (const auto& [id, info] : remote_agents_) {
        result.push_back(info);
    }
    return result;
}

bool TunnelClient::send_response(uint32_t agent_id, uint8_t opcode,
                                const std::vector<uint8_t>& payload) {
    if (!connected_) {
        return false;
    }

    // Base64 encode payload
    std::string payload_b64;
    if (!payload.empty()) {
        static const char base64_chars[] =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

        payload_b64.reserve(((payload.size() + 2) / 3) * 4);
        for (size_t i = 0; i < payload.size(); i += 3) {
            uint32_t n = (static_cast<uint32_t>(payload[i]) << 16);
            if (i + 1 < payload.size()) n |= (static_cast<uint32_t>(payload[i + 1]) << 8);
            if (i + 2 < payload.size()) n |= static_cast<uint32_t>(payload[i + 2]);

            payload_b64 += base64_chars[(n >> 18) & 0x3F];
            payload_b64 += base64_chars[(n >> 12) & 0x3F];
            payload_b64 += (i + 1 < payload.size()) ? base64_chars[(n >> 6) & 0x3F] : '=';
            payload_b64 += (i + 2 < payload.size()) ? base64_chars[n & 0x3F] : '=';
        }
    }

    json request;
    request["id"] = next_request_id_++;
    request["method"] = "send_response";
    request["params"] = {
        {"agent_id", agent_id},
        {"opcode", opcode},
        {"payload", payload_b64}
    };

    auto response = send_request_and_wait(request);
    return response && response->value("result", json{}).value("success", false);
}

std::vector<TunnelEvent> TunnelClient::poll_events() {
    std::lock_guard<std::mutex> lock(event_mutex_);
    std::vector<TunnelEvent> events;

    while (!event_queue_.empty()) {
        events.push_back(std::move(event_queue_.front()));
        event_queue_.pop();
    }

    return events;
}

void TunnelClient::set_event_callback(std::function<void(const TunnelEvent&)> callback) {
    event_callback_ = std::move(callback);
}

void TunnelClient::shutdown() {
    if (!running_) {
        return;
    }

    running_ = false;

    // Send shutdown request
    json request;
    request["id"] = next_request_id_++;
    request["method"] = "shutdown";
    request["params"] = json::object();
    send_request(request);

    // Wait for reader thread
    if (reader_thread_.joinable()) {
        reader_thread_.join();
    }

    // Close pipes
    if (stdin_fd_ >= 0) {
        close(stdin_fd_);
        stdin_fd_ = -1;
    }
    if (stdout_fd_ >= 0) {
        close(stdout_fd_);
        stdout_fd_ = -1;
    }

    // Kill subprocess
    if (subprocess_pid_ > 0) {
        kill(subprocess_pid_, SIGTERM);
        int status;
        waitpid(subprocess_pid_, &status, 0);
        subprocess_pid_ = -1;
    }

    connected_ = false;
    spdlog::info("Tunnel client shutdown");
}

bool TunnelClient::send_request(const nlohmann::json& request) {
    if (stdin_fd_ < 0) {
        return false;
    }

    std::string line = request.dump() + "\n";
    ssize_t written = write(stdin_fd_, line.c_str(), line.size());
    return written == static_cast<ssize_t>(line.size());
}

std::optional<nlohmann::json> TunnelClient::send_request_and_wait(
    const nlohmann::json& request, int timeout_ms) {

    int req_id = request.value("id", 0);

    // Prepare for response
    {
        std::lock_guard<std::mutex> lock(response_mutex_);
        pending_responses_[req_id] = json{};
    }

    // Send request
    if (!send_request(request)) {
        std::lock_guard<std::mutex> lock(response_mutex_);
        pending_responses_.erase(req_id);
        return std::nullopt;
    }

    // Wait for response
    std::unique_lock<std::mutex> lock(response_mutex_);
    auto deadline = std::chrono::steady_clock::now() +
                   std::chrono::milliseconds(timeout_ms);

    while (running_) {
        if (response_cv_.wait_until(lock, deadline,
            [&]() { return !pending_responses_[req_id].empty(); })) {

            auto response = std::move(pending_responses_[req_id]);
            pending_responses_.erase(req_id);
            return response;
        }

        if (std::chrono::steady_clock::now() >= deadline) {
            pending_responses_.erase(req_id);
            return std::nullopt;
        }
    }

    return std::nullopt;
}

void TunnelClient::reader_loop() {
    std::string buffer;
    char chunk[4096];

    while (running_) {
        // Poll for data
        struct pollfd pfd;
        pfd.fd = stdout_fd_;
        pfd.events = POLLIN;

        int ret = poll(&pfd, 1, 100);  // 100ms timeout
        if (ret <= 0) {
            continue;
        }

        if (!(pfd.revents & POLLIN)) {
            continue;
        }

        ssize_t n = read(stdout_fd_, chunk, sizeof(chunk) - 1);
        if (n <= 0) {
            if (n < 0 && errno == EAGAIN) {
                continue;
            }
            break;  // EOF or error
        }

        chunk[n] = '\0';
        buffer += chunk;

        // Process complete lines
        size_t pos;
        while ((pos = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, pos);
            buffer.erase(0, pos + 1);

            if (line.empty()) continue;

            try {
                json data = json::parse(line);

                if (data.contains("event")) {
                    handle_event(data);
                } else if (data.contains("id")) {
                    handle_response(data);
                }
            } catch (const json::exception& e) {
                spdlog::debug("Invalid JSON from tunnel: {}", line);
            }
        }
    }
}

void TunnelClient::handle_event(const nlohmann::json& data) {
    std::string event_type = data.value("event", "");
    json event_data = data.value("data", json{});

    TunnelEvent event;

    if (event_type == "agent_connected") {
        event.type = TunnelEvent::Type::AGENT_CONNECTED;
        event.agent_id = event_data.value("agent_id", 0);
        event.agent_name = event_data.value("name", "");

        // Track remote agent
        {
            std::lock_guard<std::mutex> lock(agents_mutex_);
            remote_agents_[event.agent_id] = RemoteAgentInfo{
                event.agent_id,
                event.agent_name,
                ""  // connected_at
            };
        }

        spdlog::info("Remote agent connected: {} (id={})",
                    event.agent_name, event.agent_id);

    } else if (event_type == "agent_disconnected") {
        event.type = TunnelEvent::Type::AGENT_DISCONNECTED;
        event.agent_id = event_data.value("agent_id", 0);

        // Remove from tracking
        {
            std::lock_guard<std::mutex> lock(agents_mutex_);
            remote_agents_.erase(event.agent_id);
        }

        spdlog::info("Remote agent disconnected: id={}", event.agent_id);

    } else if (event_type == "syscall") {
        event.type = TunnelEvent::Type::SYSCALL;
        event.agent_id = event_data.value("agent_id", 0);
        event.opcode = event_data.value("opcode", 0);

        // Base64 decode payload
        std::string payload_b64 = event_data.value("payload", "");
        if (!payload_b64.empty()) {
            static const std::string base64_chars =
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

            event.payload.reserve(payload_b64.size() * 3 / 4);
            uint32_t val = 0;
            int bits = -8;

            for (char c : payload_b64) {
                if (c == '=') break;
                auto pos = base64_chars.find(c);
                if (pos == std::string::npos) continue;

                val = (val << 6) | pos;
                bits += 6;

                if (bits >= 0) {
                    event.payload.push_back((val >> bits) & 0xFF);
                    bits -= 8;
                }
            }
        }

        spdlog::debug("Syscall from remote agent {}: opcode=0x{:02x}",
                     event.agent_id, event.opcode);

    } else if (event_type == "disconnected") {
        event.type = TunnelEvent::Type::DISCONNECTED;
        connected_ = false;
        spdlog::warn("Tunnel disconnected from relay");

    } else if (event_type == "reconnected") {
        event.type = TunnelEvent::Type::RECONNECTED;
        connected_ = true;
        spdlog::info("Tunnel reconnected to relay");

    } else if (event_type == "error") {
        event.type = TunnelEvent::Type::ERROR;
        event.error = event_data.value("message", "Unknown error");
        spdlog::error("Tunnel error: {}", event.error);

    } else if (event_type == "ready") {
        // Tunnel subprocess ready
        spdlog::debug("Tunnel subprocess ready");
        event.type = TunnelEvent::Type::ERROR;  // Reuse for ready signal
        event.error = "";
    } else {
        return;  // Unknown event, ignore
    }

    // Queue event
    {
        std::lock_guard<std::mutex> lock(event_mutex_);
        event_queue_.push(event);
    }

    // Call callback if set
    if (event_callback_) {
        event_callback_(event);
    }
}

void TunnelClient::handle_response(const nlohmann::json& response) {
    int req_id = response.value("id", 0);

    std::lock_guard<std::mutex> lock(response_mutex_);
    if (pending_responses_.count(req_id)) {
        pending_responses_[req_id] = response;
        response_cv_.notify_all();
    }
}

} // namespace agentos::kernel
