/**
 * AgentOS World Simulation Engine Implementation
 */
#include "worlds/world_engine.hpp"
#include <spdlog/spdlog.h>
#include <algorithm>
#include <sstream>
#include <iomanip>
#include <regex>

namespace clove::worlds {

// ============================================================================
// NetworkMock Implementation
// ============================================================================

void NetworkMock::configure(const nlohmann::json& config) {
    std::lock_guard<std::mutex> lock(mutex_);

    mode_ = config.value("mode", "passthrough");

    // Load mock responses
    if (config.contains("mock_responses") && config["mock_responses"].is_object()) {
        for (auto& [url, response_config] : config["mock_responses"].items()) {
            MockResponse resp;
            if (response_config.is_string()) {
                resp.body = response_config.get<std::string>();
            } else if (response_config.is_object()) {
                resp.status_code = response_config.value("status", 200);
                resp.body = response_config.value("body", "");
                resp.latency_ms = response_config.value("latency_ms", 0);

                if (response_config.contains("headers") && response_config["headers"].is_object()) {
                    for (auto& [k, v] : response_config["headers"].items()) {
                        resp.headers[k] = v.get<std::string>();
                    }
                }
            }
            mocks_[url] = resp;
        }
    }

    // Default response
    if (config.contains("default_response") && config["default_response"].is_object()) {
        MockResponse resp;
        resp.status_code = config["default_response"].value("status", 404);
        resp.body = config["default_response"].value("body", "Not Found");
        resp.latency_ms = config["default_response"].value("latency_ms", 0);
        default_response_ = resp;
    }

    // Allowed domains for passthrough
    if (config.contains("allowed_domains") && config["allowed_domains"].is_array()) {
        for (const auto& domain : config["allowed_domains"]) {
            allowed_domains_.push_back(domain.get<std::string>());
        }
    }

    fail_unmatched_ = config.value("fail_unmatched", false);

    spdlog::info("NetworkMock: Configured with mode={}, {} mocks", mode_, mocks_.size());
}

bool NetworkMock::should_intercept(const std::string& url) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (mode_ == "passthrough") {
        return false;
    }

    if (mode_ == "mock") {
        // In mock mode, intercept everything
        return true;
    }

    // Record mode: check if we have a mock or should record
    return true;
}

std::optional<MockResponse> NetworkMock::get_response(const std::string& url,
                                                       const std::string& method) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (mode_ == "passthrough") {
        return std::nullopt;
    }

    // Check exact match first
    auto it = mocks_.find(url);
    if (it != mocks_.end()) {
        requests_intercepted_++;
        spdlog::debug("NetworkMock: Returning mock for exact URL: {}", url);
        return it->second;
    }

    // Check pattern matches
    for (const auto& [pattern, response] : mocks_) {
        if (matches_url(url, pattern)) {
            requests_intercepted_++;
            spdlog::debug("NetworkMock: Returning mock for pattern {} matching {}", pattern, url);
            return response;
        }
    }

    // Check allowed domains for passthrough
    std::string domain = extract_domain(url);
    for (const auto& allowed : allowed_domains_) {
        if (domain == allowed || matches_url(domain, allowed)) {
            requests_passed_through_++;
            spdlog::debug("NetworkMock: Passing through to allowed domain: {}", domain);
            return std::nullopt;  // Passthrough
        }
    }

    // Unmatched
    if (fail_unmatched_) {
        requests_failed_++;
        MockResponse error_resp;
        error_resp.status_code = 503;
        error_resp.body = "Network mock: URL not configured and fail_unmatched=true";
        return error_resp;
    }

    if (default_response_) {
        requests_intercepted_++;
        return *default_response_;
    }

    requests_passed_through_++;
    return std::nullopt;  // Passthrough
}

void NetworkMock::add_mock(const std::string& url_pattern, const MockResponse& response) {
    std::lock_guard<std::mutex> lock(mutex_);
    mocks_[url_pattern] = response;
    spdlog::debug("NetworkMock: Added mock for {}", url_pattern);
}

void NetworkMock::remove_mock(const std::string& url_pattern) {
    std::lock_guard<std::mutex> lock(mutex_);
    mocks_.erase(url_pattern);
}

void NetworkMock::record(const std::string& url, const std::string& method,
                         int status, const std::string& body) {
    std::lock_guard<std::mutex> lock(mutex_);
    nlohmann::json record;
    record["url"] = url;
    record["method"] = method;
    record["status"] = status;
    record["body"] = body;
    record["timestamp"] = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    recorded_.push_back(record);
}

nlohmann::json NetworkMock::get_recorded() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recorded_;
}

bool NetworkMock::is_enabled() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return mode_ != "passthrough";
}

nlohmann::json NetworkMock::to_json() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json j;
    j["mode"] = mode_;
    j["fail_unmatched"] = fail_unmatched_;

    nlohmann::json mocks_json = nlohmann::json::object();
    for (const auto& [url, resp] : mocks_) {
        nlohmann::json resp_json;
        resp_json["status"] = resp.status_code;
        resp_json["body"] = resp.body;
        resp_json["latency_ms"] = resp.latency_ms;
        resp_json["headers"] = resp.headers;
        mocks_json[url] = resp_json;
    }
    j["mock_responses"] = mocks_json;

    if (default_response_) {
        nlohmann::json def;
        def["status"] = default_response_->status_code;
        def["body"] = default_response_->body;
        j["default_response"] = def;
    }

    j["allowed_domains"] = allowed_domains_;
    j["recorded"] = recorded_;

    return j;
}

void NetworkMock::from_json(const nlohmann::json& j) {
    std::lock_guard<std::mutex> lock(mutex_);

    mode_ = j.value("mode", "passthrough");
    fail_unmatched_ = j.value("fail_unmatched", false);

    mocks_.clear();
    if (j.contains("mock_responses") && j["mock_responses"].is_object()) {
        for (auto& [url, resp_json] : j["mock_responses"].items()) {
            MockResponse resp;
            resp.status_code = resp_json.value("status", 200);
            resp.body = resp_json.value("body", "");
            resp.latency_ms = resp_json.value("latency_ms", 0);
            if (resp_json.contains("headers")) {
                for (auto& [k, v] : resp_json["headers"].items()) {
                    resp.headers[k] = v.get<std::string>();
                }
            }
            mocks_[url] = resp;
        }
    }

    allowed_domains_.clear();
    if (j.contains("allowed_domains") && j["allowed_domains"].is_array()) {
        for (const auto& d : j["allowed_domains"]) {
            allowed_domains_.push_back(d.get<std::string>());
        }
    }

    recorded_.clear();
    if (j.contains("recorded") && j["recorded"].is_array()) {
        recorded_ = j["recorded"].get<std::vector<nlohmann::json>>();
    }
}

nlohmann::json NetworkMock::get_metrics() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json m;
    m["mode"] = mode_;
    m["mock_count"] = mocks_.size();
    m["requests_intercepted"] = requests_intercepted_;
    m["requests_passed_through"] = requests_passed_through_;
    m["requests_failed"] = requests_failed_;
    m["recorded_count"] = recorded_.size();
    return m;
}

bool NetworkMock::matches_url(const std::string& url, const std::string& pattern) const {
    // Simple wildcard matching
    if (pattern.find('*') == std::string::npos) {
        return url == pattern;
    }

    // Convert to regex
    std::string regex_str;
    for (char c : pattern) {
        if (c == '*') {
            regex_str += ".*";
        } else if (c == '?' || c == '.' || c == '+' || c == '(' ||
                   c == ')' || c == '[' || c == ']' || c == '{' ||
                   c == '}' || c == '^' || c == '$' || c == '|' ||
                   c == '\\') {
            regex_str += '\\';
            regex_str += c;
        } else {
            regex_str += c;
        }
    }

    try {
        std::regex re(regex_str, std::regex::icase);
        return std::regex_match(url, re);
    } catch (...) {
        return false;
    }
}

std::string NetworkMock::extract_domain(const std::string& url) const {
    // Simple domain extraction
    size_t start = url.find("://");
    if (start == std::string::npos) {
        start = 0;
    } else {
        start += 3;
    }

    size_t end = url.find('/', start);
    if (end == std::string::npos) {
        end = url.length();
    }

    // Remove port if present
    std::string domain = url.substr(start, end - start);
    size_t port_pos = domain.find(':');
    if (port_pos != std::string::npos) {
        domain = domain.substr(0, port_pos);
    }

    return domain;
}

// ============================================================================
// ChaosEngine Implementation
// ============================================================================

void ChaosEngine::configure(const nlohmann::json& config) {
    std::lock_guard<std::mutex> lock(mutex_);

    enabled_ = config.value("enabled", false);
    failure_rate_ = config.value("failure_rate", 0.0);

    if (config.contains("latency") && config["latency"].is_object()) {
        latency_min_ms_ = config["latency"].value("min_ms", 0);
        latency_max_ms_ = config["latency"].value("max_ms", 0);
    }

    rules_.clear();
    if (config.contains("rules") && config["rules"].is_array()) {
        for (const auto& rule_json : config["rules"]) {
            ChaosRule rule;
            rule.type = rule_json.value("type", "");
            rule.pattern = rule_json.value("path_pattern",
                          rule_json.value("url_pattern", "*"));
            rule.probability = rule_json.value("probability", 0.0);
            rules_.push_back(rule);
        }
    }

    spdlog::info("ChaosEngine: Configured enabled={}, failure_rate={}, {} rules",
                 enabled_, failure_rate_, rules_.size());
}

bool ChaosEngine::should_fail_read(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!enabled_) return false;

    // Check active events
    if (active_events_.count("disk_fail") > 0) {
        failures_injected_++;
        return true;
    }

    // Check rules
    for (const auto& rule : rules_) {
        if (rule.type == "file_read_fail" && matches_pattern(path, rule.pattern)) {
            if (should_fail(rule.probability)) {
                failures_injected_++;
                spdlog::debug("ChaosEngine: Injecting read failure for {}", path);
                return true;
            }
        }
    }

    // Global failure rate
    if (should_fail(failure_rate_)) {
        failures_injected_++;
        return true;
    }

    return false;
}

bool ChaosEngine::should_fail_write(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!enabled_) return false;

    // Check active events
    if (active_events_.count("disk_full") > 0 || active_events_.count("disk_fail") > 0) {
        failures_injected_++;
        return true;
    }

    // Check rules
    for (const auto& rule : rules_) {
        if (rule.type == "file_write_fail" && matches_pattern(path, rule.pattern)) {
            if (should_fail(rule.probability)) {
                failures_injected_++;
                spdlog::debug("ChaosEngine: Injecting write failure for {}", path);
                return true;
            }
        }
    }

    // Global failure rate
    if (should_fail(failure_rate_)) {
        failures_injected_++;
        return true;
    }

    return false;
}

bool ChaosEngine::should_fail_network(const std::string& url) const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!enabled_) return false;

    // Check active events
    if (active_events_.count("network_partition") > 0) {
        failures_injected_++;
        return true;
    }

    // Check rules
    for (const auto& rule : rules_) {
        if ((rule.type == "network_timeout" || rule.type == "network_fail") &&
            matches_pattern(url, rule.pattern)) {
            if (should_fail(rule.probability)) {
                failures_injected_++;
                spdlog::debug("ChaosEngine: Injecting network failure for {}", url);
                return true;
            }
        }
    }

    // Global failure rate
    if (should_fail(failure_rate_)) {
        failures_injected_++;
        return true;
    }

    return false;
}

uint32_t ChaosEngine::get_latency() const {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!enabled_ || latency_max_ms_ == 0) return 0;

    // Check active events
    if (active_events_.count("slow_io") > 0) {
        uint32_t slow_latency = event_params_.value("slow_io_latency_ms", 1000);
        latency_injected_++;
        return slow_latency;
    }

    if (latency_min_ms_ >= latency_max_ms_) {
        return latency_min_ms_;
    }

    std::uniform_int_distribution<uint32_t> dist(latency_min_ms_, latency_max_ms_);
    uint32_t latency = dist(rng_);

    if (latency > 0) {
        latency_injected_++;
    }

    return latency;
}

void ChaosEngine::inject_event(const std::string& event_type, const nlohmann::json& params) {
    std::lock_guard<std::mutex> lock(mutex_);

    active_events_.insert(event_type);
    event_params_[event_type] = params;

    spdlog::info("ChaosEngine: Injected event '{}' with params: {}", event_type, params.dump());
}

void ChaosEngine::clear_events() {
    std::lock_guard<std::mutex> lock(mutex_);
    active_events_.clear();
    event_params_.clear();
    spdlog::info("ChaosEngine: Cleared all active events");
}

bool ChaosEngine::is_enabled() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return enabled_;
}

nlohmann::json ChaosEngine::to_json() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json j;
    j["enabled"] = enabled_;
    j["failure_rate"] = failure_rate_;
    j["latency"] = {{"min_ms", latency_min_ms_}, {"max_ms", latency_max_ms_}};

    nlohmann::json rules_json = nlohmann::json::array();
    for (const auto& rule : rules_) {
        nlohmann::json r;
        r["type"] = rule.type;
        r["pattern"] = rule.pattern;
        r["probability"] = rule.probability;
        rules_json.push_back(r);
    }
    j["rules"] = rules_json;

    j["active_events"] = active_events_;
    j["event_params"] = event_params_;

    return j;
}

void ChaosEngine::from_json(const nlohmann::json& j) {
    std::lock_guard<std::mutex> lock(mutex_);

    enabled_ = j.value("enabled", false);
    failure_rate_ = j.value("failure_rate", 0.0);

    if (j.contains("latency") && j["latency"].is_object()) {
        latency_min_ms_ = j["latency"].value("min_ms", 0);
        latency_max_ms_ = j["latency"].value("max_ms", 0);
    }

    rules_.clear();
    if (j.contains("rules") && j["rules"].is_array()) {
        for (const auto& r : j["rules"]) {
            ChaosRule rule;
            rule.type = r.value("type", "");
            rule.pattern = r.value("pattern", "*");
            rule.probability = r.value("probability", 0.0);
            rules_.push_back(rule);
        }
    }

    active_events_.clear();
    if (j.contains("active_events") && j["active_events"].is_array()) {
        for (const auto& e : j["active_events"]) {
            active_events_.insert(e.get<std::string>());
        }
    }

    if (j.contains("event_params")) {
        event_params_ = j["event_params"];
    }
}

nlohmann::json ChaosEngine::get_metrics() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json m;
    m["enabled"] = enabled_;
    m["failure_rate"] = failure_rate_;
    m["rule_count"] = rules_.size();
    m["active_event_count"] = active_events_.size();
    m["active_events"] = active_events_;
    m["failures_injected"] = failures_injected_;
    m["latency_injected"] = latency_injected_;
    return m;
}

bool ChaosEngine::should_fail(double probability) const {
    if (probability <= 0.0) return false;
    if (probability >= 1.0) return true;

    std::uniform_real_distribution<double> dist(0.0, 1.0);
    return dist(rng_) < probability;
}

bool ChaosEngine::matches_pattern(const std::string& str, const std::string& pattern) const {
    if (pattern == "*" || pattern == "**") return true;

    // Simple wildcard matching
    std::string regex_str;
    for (size_t i = 0; i < pattern.size(); ++i) {
        char c = pattern[i];
        if (c == '*') {
            if (i + 1 < pattern.size() && pattern[i + 1] == '*') {
                regex_str += ".*";
                ++i;
            } else {
                regex_str += "[^/]*";
            }
        } else if (c == '?' || c == '.' || c == '+' || c == '(' ||
                   c == ')' || c == '[' || c == ']' || c == '{' ||
                   c == '}' || c == '^' || c == '$' || c == '|' ||
                   c == '\\') {
            regex_str += '\\';
            regex_str += c;
        } else {
            regex_str += c;
        }
    }

    try {
        std::regex re(regex_str, std::regex::icase);
        return std::regex_match(str, re);
    } catch (...) {
        return false;
    }
}

// ============================================================================
// World Implementation
// ============================================================================

World::World(const WorldId& id)
    : id_(id)
    , name_(id) {
    metrics_.created_at = std::chrono::steady_clock::now();
    metrics_.last_activity = metrics_.created_at;
}

void World::configure(const nlohmann::json& config) {
    std::lock_guard<std::mutex> lock(mutex_);

    config_ = config;
    name_ = config.value("name", id_);
    description_ = config.value("description", "");

    if (config.contains("virtual_filesystem")) {
        vfs_.configure(config["virtual_filesystem"]);
    }

    if (config.contains("network")) {
        network_.configure(config["network"]);
    }

    if (config.contains("chaos")) {
        chaos_.configure(config["chaos"]);
    }

    spdlog::info("World '{}': Configured", id_);
}

void World::add_agent(uint32_t agent_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    agents_.insert(agent_id);
    metrics_.agent_count = agents_.size();
    metrics_.last_activity = std::chrono::steady_clock::now();
    spdlog::info("World '{}': Agent {} joined (total: {})", id_, agent_id, agents_.size());
}

void World::remove_agent(uint32_t agent_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    agents_.erase(agent_id);
    metrics_.agent_count = agents_.size();
    metrics_.last_activity = std::chrono::steady_clock::now();
    spdlog::info("World '{}': Agent {} left (total: {})", id_, agent_id, agents_.size());
}

bool World::has_agent(uint32_t agent_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return agents_.count(agent_id) > 0;
}

std::set<uint32_t> World::get_agents() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return agents_;
}

size_t World::agent_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return agents_.size();
}

void World::record_syscall() {
    std::lock_guard<std::mutex> lock(mutex_);
    metrics_.syscall_count++;
    metrics_.last_activity = std::chrono::steady_clock::now();
}

WorldMetrics World::get_metrics() const {
    std::lock_guard<std::mutex> lock(mutex_);

    // Update from subsystems
    auto vfs_metrics = vfs_.get_metrics();
    metrics_.vfs_reads = vfs_metrics.value("read_count", 0);
    metrics_.vfs_writes = vfs_metrics.value("write_count", 0);

    auto net_metrics = network_.get_metrics();
    metrics_.network_requests = net_metrics.value("requests_intercepted", 0) +
                                net_metrics.value("requests_passed_through", 0);

    auto chaos_metrics = chaos_.get_metrics();
    metrics_.chaos_failures = chaos_metrics.value("failures_injected", 0);

    return metrics_;
}

nlohmann::json World::to_json() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json j;
    j["id"] = id_;
    j["name"] = name_;
    j["description"] = description_;
    j["config"] = config_;
    j["vfs"] = vfs_.to_json();
    j["network"] = network_.to_json();
    j["chaos"] = chaos_.to_json();
    j["agents"] = agents_;

    return j;
}

void World::from_json(const nlohmann::json& j) {
    std::lock_guard<std::mutex> lock(mutex_);

    name_ = j.value("name", id_);
    description_ = j.value("description", "");

    if (j.contains("config")) {
        config_ = j["config"];
    }

    if (j.contains("vfs")) {
        vfs_.from_json(j["vfs"]);
    }

    if (j.contains("network")) {
        network_.from_json(j["network"]);
    }

    if (j.contains("chaos")) {
        chaos_.from_json(j["chaos"]);
    }

    agents_.clear();
    if (j.contains("agents") && j["agents"].is_array()) {
        for (const auto& a : j["agents"]) {
            agents_.insert(a.get<uint32_t>());
        }
    }

    metrics_.agent_count = agents_.size();
    spdlog::info("World '{}': Restored from snapshot", id_);
}

// ============================================================================
// WorldEngine Implementation
// ============================================================================

std::optional<WorldId> WorldEngine::create_world(const std::string& name,
                                                  const nlohmann::json& config) {
    std::lock_guard<std::mutex> lock(mutex_);

    WorldId id = generate_world_id(name);

    auto world = std::make_unique<World>(id);
    world->configure(config);

    worlds_[id] = std::move(world);

    spdlog::info("WorldEngine: Created world '{}' (name={})", id, name);
    return id;
}

bool WorldEngine::destroy_world(const WorldId& world_id, bool force) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = worlds_.find(world_id);
    if (it == worlds_.end()) {
        spdlog::warn("WorldEngine: World '{}' not found for destruction", world_id);
        return false;
    }

    // Check for active agents
    if (!force && it->second->agent_count() > 0) {
        spdlog::warn("WorldEngine: Cannot destroy world '{}' with active agents (use force=true)",
                     world_id);
        return false;
    }

    // Remove agent mappings
    auto agents = it->second->get_agents();
    for (uint32_t agent_id : agents) {
        agent_to_world_.erase(agent_id);
    }

    worlds_.erase(it);
    spdlog::info("WorldEngine: Destroyed world '{}'", world_id);
    return true;
}

std::vector<nlohmann::json> WorldEngine::list_worlds() const {
    std::lock_guard<std::mutex> lock(mutex_);

    std::vector<nlohmann::json> result;
    for (const auto& [id, world] : worlds_) {
        nlohmann::json info;
        info["id"] = id;
        info["name"] = world->name();
        info["description"] = world->description();
        info["agent_count"] = world->agent_count();

        auto metrics = world->get_metrics();
        info["syscall_count"] = metrics.syscall_count;
        info["vfs_enabled"] = world->vfs().is_enabled();
        info["network_mock_enabled"] = world->network().is_enabled();
        info["chaos_enabled"] = world->chaos().is_enabled();

        result.push_back(info);
    }

    return result;
}

World* WorldEngine::get_world(const WorldId& world_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = worlds_.find(world_id);
    return (it != worlds_.end()) ? it->second.get() : nullptr;
}

const World* WorldEngine::get_world(const WorldId& world_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = worlds_.find(world_id);
    return (it != worlds_.end()) ? it->second.get() : nullptr;
}

bool WorldEngine::join_world(uint32_t agent_id, const WorldId& world_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    // Check if agent is already in a world
    auto existing = agent_to_world_.find(agent_id);
    if (existing != agent_to_world_.end()) {
        spdlog::warn("WorldEngine: Agent {} already in world '{}'", agent_id, existing->second);
        return false;
    }

    auto world_it = worlds_.find(world_id);
    if (world_it == worlds_.end()) {
        spdlog::warn("WorldEngine: World '{}' not found", world_id);
        return false;
    }

    world_it->second->add_agent(agent_id);
    agent_to_world_[agent_id] = world_id;

    spdlog::info("WorldEngine: Agent {} joined world '{}'", agent_id, world_id);
    return true;
}

bool WorldEngine::leave_world(uint32_t agent_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = agent_to_world_.find(agent_id);
    if (it == agent_to_world_.end()) {
        spdlog::debug("WorldEngine: Agent {} not in any world", agent_id);
        return false;
    }

    WorldId world_id = it->second;
    agent_to_world_.erase(it);

    auto world_it = worlds_.find(world_id);
    if (world_it != worlds_.end()) {
        world_it->second->remove_agent(agent_id);
    }

    spdlog::info("WorldEngine: Agent {} left world '{}'", agent_id, world_id);
    return true;
}

bool WorldEngine::is_agent_in_world(uint32_t agent_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return agent_to_world_.find(agent_id) != agent_to_world_.end();
}

std::optional<WorldId> WorldEngine::get_agent_world(uint32_t agent_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = agent_to_world_.find(agent_id);
    if (it != agent_to_world_.end()) {
        return it->second;
    }
    return std::nullopt;
}

bool WorldEngine::inject_event(const WorldId& world_id, const std::string& event_type,
                               const nlohmann::json& params) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = worlds_.find(world_id);
    if (it == worlds_.end()) {
        spdlog::warn("WorldEngine: World '{}' not found for event injection", world_id);
        return false;
    }

    it->second->chaos().inject_event(event_type, params);
    return true;
}

std::optional<nlohmann::json> WorldEngine::get_world_state(const WorldId& world_id) const {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = worlds_.find(world_id);
    if (it == worlds_.end()) {
        return std::nullopt;
    }

    auto metrics = it->second->get_metrics();

    nlohmann::json state;
    state["world_id"] = world_id;
    state["name"] = it->second->name();
    state["agent_count"] = metrics.agent_count;
    state["syscall_count"] = metrics.syscall_count;
    state["vfs_metrics"] = it->second->vfs().get_metrics();
    state["network_metrics"] = it->second->network().get_metrics();
    state["chaos_metrics"] = it->second->chaos().get_metrics();
    state["agents"] = it->second->get_agents();

    return state;
}

std::optional<nlohmann::json> WorldEngine::snapshot_world(const WorldId& world_id) const {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = worlds_.find(world_id);
    if (it == worlds_.end()) {
        spdlog::warn("WorldEngine: World '{}' not found for snapshot", world_id);
        return std::nullopt;
    }

    nlohmann::json snapshot = it->second->to_json();
    snapshot["snapshot_time"] = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    spdlog::info("WorldEngine: Created snapshot of world '{}'", world_id);
    return snapshot;
}

std::optional<WorldId> WorldEngine::restore_world(const nlohmann::json& snapshot,
                                                   const std::string& new_world_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    WorldId id = new_world_id.empty() ?
                 generate_world_id(snapshot.value("name", "restored")) :
                 new_world_id;

    // Check if world already exists
    if (worlds_.find(id) != worlds_.end()) {
        spdlog::warn("WorldEngine: World '{}' already exists", id);
        return std::nullopt;
    }

    auto world = std::make_unique<World>(id);
    world->from_json(snapshot);

    worlds_[id] = std::move(world);

    spdlog::info("WorldEngine: Restored world as '{}'", id);
    return id;
}

nlohmann::json WorldEngine::get_metrics() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json m;
    m["world_count"] = worlds_.size();
    m["total_agents_in_worlds"] = agent_to_world_.size();

    uint64_t total_syscalls = 0;
    for (const auto& [_, world] : worlds_) {
        total_syscalls += world->get_metrics().syscall_count;
    }
    m["total_syscalls"] = total_syscalls;

    return m;
}

WorldId WorldEngine::generate_world_id(const std::string& name) {
    std::stringstream ss;

    // Sanitize name
    std::string safe_name;
    for (char c : name) {
        if (std::isalnum(c) || c == '-' || c == '_') {
            safe_name += std::tolower(c);
        } else if (c == ' ') {
            safe_name += '-';
        }
    }

    if (safe_name.empty()) {
        safe_name = "world";
    }

    // Truncate if too long
    if (safe_name.length() > 32) {
        safe_name = safe_name.substr(0, 32);
    }

    ss << safe_name << "-" << std::setfill('0') << std::setw(4) << next_world_num_++;
    return ss.str();
}

} // namespace clove::worlds
