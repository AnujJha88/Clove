#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/audit_log.hpp"
#include "kernel/execution_log.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void ReplaySyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_RECORD_START,
        [this](const ipc::Message& msg) { return handle_record_start(msg); });
    router.register_handler(ipc::SyscallOp::SYS_RECORD_STOP,
        [this](const ipc::Message& msg) { return handle_record_stop(msg); });
    router.register_handler(ipc::SyscallOp::SYS_RECORD_STATUS,
        [this](const ipc::Message& msg) { return handle_record_status(msg); });
    router.register_handler(ipc::SyscallOp::SYS_REPLAY_START,
        [this](const ipc::Message& msg) { return handle_replay_start(msg); });
    router.register_handler(ipc::SyscallOp::SYS_REPLAY_STATUS,
        [this](const ipc::Message& msg) { return handle_replay_status(msg); });
}

ipc::Message ReplaySyscalls::handle_record_start(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        request = json::object();
    }

    RecordingConfig config = context_.execution_logger.get_config();
    if (request.contains("include_think")) {
        config.include_think = request["include_think"].get<bool>();
    }
    if (request.contains("include_http")) {
        config.include_http = request["include_http"].get<bool>();
    }
    if (request.contains("include_exec")) {
        config.include_exec = request["include_exec"].get<bool>();
    }
    if (request.contains("max_entries")) {
        config.max_entries = request["max_entries"].get<size_t>();
    }
    if (request.contains("filter_agents") && request["filter_agents"].is_array()) {
        config.filter_agents.clear();
        for (const auto& id : request["filter_agents"]) {
            config.filter_agents.push_back(id.get<uint32_t>());
        }
    }

    context_.execution_logger.set_config(config);
    bool success = context_.execution_logger.start_recording();

    json response;
    response["success"] = success;
    response["recording"] = success;

    if (success) {
        json audit_details;
        audit_details["started_by"] = msg.agent_id;
        context_.audit_logger.log(AuditCategory::SYSCALL, "RECORDING_STARTED", msg.agent_id, "", audit_details, true);
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_RECORD_START, response.dump());
}

ipc::Message ReplaySyscalls::handle_record_stop(const ipc::Message& msg) {
    bool success = context_.execution_logger.stop_recording();

    json response;
    response["success"] = success;
    response["recording"] = false;
    response["entries_recorded"] = context_.execution_logger.entry_count();

    if (success) {
        json audit_details;
        audit_details["stopped_by"] = msg.agent_id;
        audit_details["entries_recorded"] = context_.execution_logger.entry_count();
        context_.audit_logger.log(AuditCategory::SYSCALL, "RECORDING_STOPPED", msg.agent_id, "", audit_details, true);
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_RECORD_STOP, response.dump());
}

ipc::Message ReplaySyscalls::handle_record_status(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        request = json::object();
    }

    json response;
    response["success"] = true;

    auto state = context_.execution_logger.recording_state();
    response["recording"] = (state == RecordingState::RECORDING);
    response["paused"] = (state == RecordingState::PAUSED);
    response["entry_count"] = context_.execution_logger.entry_count();
    response["last_sequence_id"] = context_.execution_logger.last_sequence_id();

    if (request.value("export", false)) {
        response["recording_data"] = context_.execution_logger.export_recording();
    }

    if (request.contains("get_entries")) {
        size_t limit = request.value("limit", 100);
        uint64_t since = request.value("since_id", 0);
        auto entries = context_.execution_logger.get_entries(since, limit);

        response["entries"] = json::array();
        for (const auto& entry : entries) {
            response["entries"].push_back(entry.to_json());
        }
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_RECORD_STATUS, response.dump());
}

ipc::Message ReplaySyscalls::handle_replay_start(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        json response;
        response["success"] = false;
        response["error"] = "Invalid JSON payload";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REPLAY_START, response.dump());
    }

    if (request.contains("recording_data")) {
        std::string data = request["recording_data"].is_string()
            ? request["recording_data"].get<std::string>()
            : request["recording_data"].dump();

        if (!context_.execution_logger.import_recording(data)) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to import recording data";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REPLAY_START, response.dump());
        }
    }

    bool success = context_.execution_logger.start_replay();

    json response;
    response["success"] = success;
    if (!success) {
        auto progress = context_.execution_logger.get_replay_progress();
        response["error"] = progress.last_error;
    } else {
        auto progress = context_.execution_logger.get_replay_progress();
        response["total_entries"] = progress.total_entries;
    }

    if (success) {
        json audit_details;
        audit_details["started_by"] = msg.agent_id;
        auto progress = context_.execution_logger.get_replay_progress();
        audit_details["total_entries"] = progress.total_entries;
        context_.audit_logger.log(AuditCategory::SYSCALL, "REPLAY_STARTED", msg.agent_id, "", audit_details, true);
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REPLAY_START, response.dump());
}

ipc::Message ReplaySyscalls::handle_replay_status(const ipc::Message& msg) {
    auto progress = context_.execution_logger.get_replay_progress();

    json response;
    response["success"] = true;

    std::string state_str;
    switch (progress.state) {
        case ReplayState::IDLE:      state_str = "idle"; break;
        case ReplayState::RUNNING:   state_str = "running"; break;
        case ReplayState::PAUSED:    state_str = "paused"; break;
        case ReplayState::COMPLETED: state_str = "completed"; break;
        case ReplayState::ERROR:     state_str = "error"; break;
        default: state_str = "unknown"; break;
    }

    response["state"] = state_str;
    response["total_entries"] = progress.total_entries;
    response["current_entry"] = progress.current_entry;
    response["entries_replayed"] = progress.entries_replayed;
    response["entries_skipped"] = progress.entries_skipped;

    if (!progress.last_error.empty()) {
        response["last_error"] = progress.last_error;
    }

    if (progress.total_entries > 0) {
        double percent = 100.0 * progress.current_entry / progress.total_entries;
        response["progress_percent"] = static_cast<int>(percent);
    } else {
        response["progress_percent"] = 0;
    }

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_REPLAY_STATUS, response.dump());
}

} // namespace clove::kernel
