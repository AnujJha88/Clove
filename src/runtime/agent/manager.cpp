#include "runtime/agent/manager.hpp"
#include <spdlog/spdlog.h>

namespace clove::runtime {

AgentManager::AgentManager(const std::string& kernel_socket)
    : kernel_socket_(kernel_socket) {
    spdlog::debug("AgentManager initialized (socket={})", kernel_socket);
}

AgentManager::~AgentManager() {
    stop_all();
}

std::shared_ptr<AgentProcess> AgentManager::spawn_agent(const AgentConfig& config) {
    if (agents_by_name_.count(config.name)) {
        spdlog::error("Agent {} already exists", config.name);
        return nullptr;
    }

    // Set kernel socket if not specified
    AgentConfig final_config = config;
    if (final_config.socket_path.empty()) {
        final_config.socket_path = kernel_socket_;
    }

    auto agent = std::make_shared<AgentProcess>(final_config);

    if (!agent->start()) {
        return nullptr;
    }

    agents_by_name_[config.name] = agent;
    agents_by_id_[agent->id()] = agent;

    // Save config for potential restart if policy != NEVER
    if (config.restart.policy != RestartPolicy::NEVER) {
        saved_configs_[config.name] = final_config;

        // Initialize restart state if not exists
        if (restart_states_.find(config.name) == restart_states_.end()) {
            RestartState state;
            state.window_start = std::chrono::steady_clock::now();
            restart_states_[config.name] = state;
        }
    }

    return agent;
}

std::shared_ptr<AgentProcess> AgentManager::get_agent(const std::string& name) {
    auto it = agents_by_name_.find(name);
    return (it != agents_by_name_.end()) ? it->second : nullptr;
}

std::shared_ptr<AgentProcess> AgentManager::get_agent(uint32_t id) {
    auto it = agents_by_id_.find(id);
    return (it != agents_by_id_.end()) ? it->second : nullptr;
}

bool AgentManager::kill_agent(const std::string& name) {
    auto it = agents_by_name_.find(name);
    if (it == agents_by_name_.end()) {
        return false;
    }

    auto agent = it->second;
    agent->stop();

    agents_by_id_.erase(agent->id());
    agents_by_name_.erase(it);

    return true;
}

bool AgentManager::kill_agent(uint32_t id) {
    auto it = agents_by_id_.find(id);
    if (it == agents_by_id_.end()) {
        return false;
    }

    auto agent = it->second;
    agent->stop();

    agents_by_name_.erase(agent->name());
    agents_by_id_.erase(it);

    return true;
}

bool AgentManager::pause_agent(const std::string& name) {
    auto it = agents_by_name_.find(name);
    if (it == agents_by_name_.end()) {
        spdlog::error("Agent {} not found", name);
        return false;
    }
    return it->second->pause();
}

bool AgentManager::pause_agent(uint32_t id) {
    auto it = agents_by_id_.find(id);
    if (it == agents_by_id_.end()) {
        spdlog::error("Agent {} not found", id);
        return false;
    }
    return it->second->pause();
}

bool AgentManager::resume_agent(const std::string& name) {
    auto it = agents_by_name_.find(name);
    if (it == agents_by_name_.end()) {
        spdlog::error("Agent {} not found", name);
        return false;
    }
    return it->second->resume();
}

bool AgentManager::resume_agent(uint32_t id) {
    auto it = agents_by_id_.find(id);
    if (it == agents_by_id_.end()) {
        spdlog::error("Agent {} not found", id);
        return false;
    }
    return it->second->resume();
}

std::vector<std::shared_ptr<AgentProcess>> AgentManager::list_agents() const {
    std::vector<std::shared_ptr<AgentProcess>> result;
    for (const auto& [_, agent] : agents_by_name_) {
        result.push_back(agent);
    }
    return result;
}

void AgentManager::stop_all() {
    spdlog::info("Stopping all agents...");

    for (auto& [_, agent] : agents_by_name_) {
        agent->stop();
    }

    agents_by_name_.clear();
    agents_by_id_.clear();
}

void AgentManager::set_restart_event_callback(RestartEventCallback callback) {
    restart_event_callback_ = std::move(callback);
}

uint32_t AgentManager::calculate_backoff_delay(const RestartConfig& config, uint32_t consecutive_failures) {
    if (consecutive_failures == 0) {
        return config.backoff_initial_ms;
    }

    // Calculate exponential backoff: initial * multiplier^failures
    double delay = config.backoff_initial_ms;
    for (uint32_t i = 0; i < consecutive_failures; ++i) {
        delay *= config.backoff_multiplier;
        if (delay >= config.backoff_max_ms) {
            return config.backoff_max_ms;
        }
    }

    return static_cast<uint32_t>(delay);
}

void AgentManager::reap_and_restart_agents() {
    std::vector<std::string> dead_agents;

    for (auto& [name, agent] : agents_by_name_) {
        if (!agent->is_running() && agent->state() == AgentState::RUNNING) {
            // Agent died unexpectedly
            spdlog::warn("Agent {} died unexpectedly (exit_code={})", name, agent->exit_code());
            dead_agents.push_back(name);
        }
    }

    for (const auto& name : dead_agents) {
        auto agent = agents_by_name_[name];
        int exit_code = agent->exit_code();

        // Remove from active agents
        agents_by_id_.erase(agent->id());
        agents_by_name_.erase(name);

        // Check if we should restart
        auto config_it = saved_configs_.find(name);
        if (config_it == saved_configs_.end()) {
            // No restart policy configured
            spdlog::info("Agent {} exited, no restart policy", name);
            continue;
        }

        const AgentConfig& config = config_it->second;
        RestartState& state = restart_states_[name];

        // Check restart policy
        bool should_restart = false;
        switch (config.restart.policy) {
            case RestartPolicy::ALWAYS:
                should_restart = true;
                break;
            case RestartPolicy::ON_FAILURE:
                should_restart = (exit_code != 0);
                break;
            case RestartPolicy::NEVER:
            default:
                should_restart = false;
                break;
        }

        if (!should_restart) {
            spdlog::info("Agent {} exited with code {}, restart policy says no restart",
                name, exit_code);
            // Clean up saved config
            saved_configs_.erase(name);
            restart_states_.erase(name);
            continue;
        }

        // Check if we're within the restart window
        auto now = std::chrono::steady_clock::now();
        auto window_elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            now - state.window_start).count();

        if (window_elapsed >= config.restart.restart_window_sec) {
            // Reset window
            state.window_start = now;
            state.restart_count = 0;
            state.consecutive_failures = 0;
            spdlog::debug("Agent {} restart window reset", name);
        }

        // Check if we've exceeded max restarts
        if (state.restart_count >= config.restart.max_restarts) {
            if (!state.escalated) {
                spdlog::error("Agent {} exceeded max_restarts ({}) within window, escalating",
                    name, config.restart.max_restarts);
                state.escalated = true;

                // Emit escalation event
                if (restart_event_callback_) {
                    restart_event_callback_("AGENT_ESCALATED", name, state.restart_count, exit_code);
                }
            }
            continue;
        }

        // Calculate backoff delay
        uint32_t backoff_ms = calculate_backoff_delay(config.restart, state.consecutive_failures);

        spdlog::info("Agent {} will restart in {}ms (attempt {}/{})",
            name, backoff_ms, state.restart_count + 1, config.restart.max_restarts);

        // Queue the restart
        PendingRestart pending;
        pending.agent_name = name;
        pending.scheduled_time = now + std::chrono::milliseconds(backoff_ms);
        pending.config = config;
        pending_restarts_.push_back(pending);

        // Update state
        state.restart_count++;
        state.consecutive_failures++;

        // Emit restarting event
        if (restart_event_callback_) {
            restart_event_callback_("AGENT_RESTARTING", name, state.restart_count, exit_code);
        }
    }
}

void AgentManager::process_pending_restarts() {
    if (pending_restarts_.empty()) {
        return;
    }

    auto now = std::chrono::steady_clock::now();
    std::vector<PendingRestart> still_pending;

    for (auto& pending : pending_restarts_) {
        if (now >= pending.scheduled_time) {
            // Time to restart this agent
            spdlog::info("Restarting agent: {} (scheduled restart)", pending.agent_name);

            auto agent = std::make_shared<AgentProcess>(pending.config);

            if (agent->start()) {
                agents_by_name_[pending.agent_name] = agent;
                agents_by_id_[agent->id()] = agent;

                spdlog::info("Agent {} restarted successfully (new id={}, pid={})",
                    pending.agent_name, agent->id(), agent->pid());

                // Reset consecutive failures on successful start
                auto state_it = restart_states_.find(pending.agent_name);
                if (state_it != restart_states_.end()) {
                    // Note: We don't reset consecutive_failures here because
                    // we want to track consecutive failures across restarts
                    // It gets reset when the window expires
                }
            } else {
                spdlog::error("Failed to restart agent {}", pending.agent_name);

                // The agent will be detected as dead again on next reap cycle
                // if the restart failed immediately
            }
        } else {
            // Not yet time, keep in pending
            still_pending.push_back(pending);
        }
    }

    pending_restarts_ = std::move(still_pending);
}

} // namespace clove::runtime
