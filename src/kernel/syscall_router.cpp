#include "kernel/syscall_router.hpp"
#include <spdlog/spdlog.h>

namespace clove::kernel {

ipc::Message SyscallRouter::handle(const ipc::Message& msg) const {
    auto it = handlers_.find(msg.opcode);
    if (it != handlers_.end()) {
        return it->second(msg);
    }

    spdlog::warn("Unknown opcode: 0x{:02x}", static_cast<uint8_t>(msg.opcode));
    return ipc::Message(msg.agent_id, msg.opcode, msg.payload);
}

void SyscallRouter::register_handler(ipc::SyscallOp op, Handler handler) {
    handlers_[op] = std::move(handler);
}

} // namespace clove::kernel
