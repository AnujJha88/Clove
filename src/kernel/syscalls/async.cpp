#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/async_task_manager.hpp"
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void AsyncSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_ASYNC_POLL,
        [this](const ipc::Message& msg) { return handle_async_poll(msg); });
}

ipc::Message AsyncSyscalls::handle_async_poll(const ipc::Message& msg) {
    json request;
    try {
        request = json::parse(msg.payload_str());
    } catch (...) {
        request = json::object();
    }

    int max_results = request.value("max", 10);
    auto results = context_.async_tasks.poll(msg.agent_id, max_results);

    json response;
    response["success"] = true;
    response["results"] = json::array();

    for (const auto& result : results) {
        json entry;
        entry["request_id"] = result.request_id;
        entry["opcode"] = static_cast<uint8_t>(result.opcode);
        entry["opcode_name"] = ipc::opcode_to_string(result.opcode);
        entry["payload"] = result.payload;
        response["results"].push_back(entry);
    }

    response["count"] = response["results"].size();
    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_ASYNC_POLL, response.dump());
}

} // namespace clove::kernel
