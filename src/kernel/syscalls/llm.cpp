#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void LlmSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_THINK,
        [this](const ipc::Message& msg) { return handle_think(msg); });
}

ipc::Message LlmSyscalls::think_sync(KernelContext& context, const ipc::Message& msg) {
    (void)context;
    json response;
    response["success"] = false;
    response["error"] = "LLM calls are handled outside the kernel; use an external LLM service/proxy";
    response["content"] = "";
    response["tokens"] = 0;
    spdlog::warn("Agent {} requested SYS_THINK but kernel LLM is disabled", msg.agent_id);

    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_THINK, response.dump());
}

ipc::Message LlmSyscalls::handle_think(const ipc::Message& msg) {
    json j;
    try {
        if (!msg.payload.empty()) {
            j = json::parse(msg.payload_str());
        } else {
            j = json::object();
        }
    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["content"] = "";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_THINK, response.dump());
    }

    (void)j;
    return think_sync(context_, msg);
}

} // namespace clove::kernel
