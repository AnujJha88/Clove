#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "metrics/metrics.hpp"
#include "runtime/agent/manager.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void MetricsSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_METRICS_SYSTEM,
        [this](const ipc::Message& msg) { return handle_metrics_system(msg); });
    router.register_handler(ipc::SyscallOp::SYS_METRICS_AGENT,
        [this](const ipc::Message& msg) { return handle_metrics_agent(msg); });
    router.register_handler(ipc::SyscallOp::SYS_METRICS_ALL_AGENTS,
        [this](const ipc::Message& msg) { return handle_metrics_all_agents(msg); });
    router.register_handler(ipc::SyscallOp::SYS_METRICS_CGROUP,
        [this](const ipc::Message& msg) { return handle_metrics_cgroup(msg); });
}

ipc::Message MetricsSyscalls::handle_metrics_system(const ipc::Message& msg) {
    auto metrics = context_.metrics.collect_system();

    json response;
    response["success"] = true;
    response["metrics"] = metrics.to_json();

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_SYSTEM, response.dump());
}

ipc::Message MetricsSyscalls::handle_metrics_agent(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        json response;
        response["success"] = false;
        response["error"] = "Invalid JSON payload";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_AGENT, response.dump());
    }

    uint32_t target_agent_id = request.value("agent_id", msg.agent_id);
    auto target_agent = context_.agent_manager.get_agent(target_agent_id);

    if (!target_agent) {
        json response;
        response["success"] = false;
        response["error"] = "Agent not found";
        response["agent_id"] = target_agent_id;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_AGENT, response.dump());
    }

    auto agent_metrics = target_agent->get_metrics();

    std::string cgroup_path;
    if (target_agent->is_running()) {
        cgroup_path = "clove/" + target_agent->name() + "_" + std::to_string(target_agent->id());
    }

    auto metrics = context_.metrics.collect_agent(
        target_agent->id(),
        target_agent->pid(),
        cgroup_path,
        target_agent->name(),
        runtime::agent_state_to_string(target_agent->state()),
        agent_metrics.uptime_seconds * 1000
    );

    json response;
    response["success"] = true;
    response["metrics"] = metrics.to_json();

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_AGENT, response.dump());
}

ipc::Message MetricsSyscalls::handle_metrics_all_agents(const ipc::Message& msg) {
    auto agents = context_.agent_manager.list_agents();

    json agent_metrics_list = json::array();

    for (const auto& agent : agents) {
        auto agent_info = agent->get_metrics();

        std::string cgroup_path;
        if (agent->is_running()) {
            cgroup_path = "clove/" + agent->name() + "_" + std::to_string(agent->id());
        }

        auto metrics = context_.metrics.collect_agent(
            agent->id(),
            agent->pid(),
            cgroup_path,
            agent->name(),
            runtime::agent_state_to_string(agent->state()),
            agent_info.uptime_seconds * 1000
        );

        agent_metrics_list.push_back(metrics.to_json());
    }

    json response;
    response["success"] = true;
    response["agents"] = agent_metrics_list;
    response["count"] = agent_metrics_list.size();

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_ALL_AGENTS, response.dump());
}

ipc::Message MetricsSyscalls::handle_metrics_cgroup(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        json response;
        response["success"] = false;
        response["error"] = "Invalid JSON payload";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_CGROUP, response.dump());
    }

    std::string cgroup_path = request.value("cgroup_path", "");

    if (cgroup_path.empty()) {
        auto agent = context_.agent_manager.get_agent(msg.agent_id);
        if (agent) {
            cgroup_path = "clove/" + agent->name() + "_" + std::to_string(agent->id());
        } else {
            cgroup_path = "clove/agent-" + std::to_string(msg.agent_id);
        }
    }

    auto metrics = context_.metrics.collect_cgroup(cgroup_path);

    json response;
    response["success"] = metrics.valid;
    if (metrics.valid) {
        response["metrics"] = metrics.to_json();
    } else {
        response["error"] = "Cgroup not found or not readable";
        response["cgroup_path"] = cgroup_path;
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_METRICS_CGROUP, response.dump());
}

} // namespace clove::kernel
