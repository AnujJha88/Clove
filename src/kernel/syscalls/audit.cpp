#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/audit_log.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void AuditSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_GET_AUDIT_LOG,
        [this](const ipc::Message& msg) { return handle_get_audit_log(msg); });
    router.register_handler(ipc::SyscallOp::SYS_SET_AUDIT_CONFIG,
        [this](const ipc::Message& msg) { return handle_set_audit_config(msg); });
}

ipc::Message AuditSyscalls::handle_get_audit_log(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        request = json::object();
    }

    std::string category_str = request.value("category", "");
    uint32_t agent_filter = request.value("agent_id", 0);
    uint64_t since_id = request.value("since_id", 0);
    size_t limit = request.value("limit", 100);

    std::vector<AuditLogEntry> entries;
    if (!category_str.empty()) {
        AuditCategory cat = audit_category_from_string(category_str);
        if (agent_filter > 0) {
            entries = context_.audit_logger.get_entries(&cat, &agent_filter, since_id, limit);
        } else {
            entries = context_.audit_logger.get_entries(&cat, nullptr, since_id, limit);
        }
    } else {
        if (agent_filter > 0) {
            entries = context_.audit_logger.get_entries(nullptr, &agent_filter, since_id, limit);
        } else {
            entries = context_.audit_logger.get_entries(nullptr, nullptr, since_id, limit);
        }
    }

    json response;
    response["success"] = true;
    response["count"] = entries.size();
    response["entries"] = json::array();

    for (const auto& entry : entries) {
        response["entries"].push_back(entry.to_json());
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_GET_AUDIT_LOG, response.dump());
}

ipc::Message AuditSyscalls::handle_set_audit_config(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        json response;
        response["success"] = false;
        response["error"] = "Invalid JSON payload";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SET_AUDIT_CONFIG, response.dump());
    }

    AuditConfig config = context_.audit_logger.get_config();

    if (request.contains("max_entries")) {
        config.max_entries = request["max_entries"].get<size_t>();
    }
    if (request.contains("log_syscalls")) {
        config.log_syscalls = request["log_syscalls"].get<bool>();
    }
    if (request.contains("log_security")) {
        config.log_security = request["log_security"].get<bool>();
    }
    if (request.contains("log_lifecycle")) {
        config.log_lifecycle = request["log_lifecycle"].get<bool>();
    }
    if (request.contains("log_ipc")) {
        config.log_ipc = request["log_ipc"].get<bool>();
    }
    if (request.contains("log_state")) {
        config.log_state = request["log_state"].get<bool>();
    }
    if (request.contains("log_resource")) {
        config.log_resource = request["log_resource"].get<bool>();
    }
    if (request.contains("log_network")) {
        config.log_network = request["log_network"].get<bool>();
    }
    if (request.contains("log_world")) {
        config.log_world = request["log_world"].get<bool>();
    }

    context_.audit_logger.set_config(config);

    json audit_details;
    audit_details["changed_by"] = msg.agent_id;
    audit_details["new_config"] = request;
    context_.audit_logger.log(AuditCategory::SECURITY, "AUDIT_CONFIG_CHANGED", msg.agent_id, "", audit_details, true);

    json response;
    response["success"] = true;
    response["config"]["max_entries"] = config.max_entries;
    response["config"]["log_syscalls"] = config.log_syscalls;
    response["config"]["log_security"] = config.log_security;
    response["config"]["log_lifecycle"] = config.log_lifecycle;
    response["config"]["log_ipc"] = config.log_ipc;
    response["config"]["log_state"] = config.log_state;
    response["config"]["log_resource"] = config.log_resource;
    response["config"]["log_network"] = config.log_network;
    response["config"]["log_world"] = config.log_world;

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_SET_AUDIT_CONFIG, response.dump());
}

} // namespace clove::kernel
