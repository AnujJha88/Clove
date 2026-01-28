#pragma once
#include <functional>
#include <unordered_map>
#include "ipc/protocol.hpp"

namespace clove::kernel {

// Centralized syscall dispatch table.
class SyscallRouter {
public:
    using Handler = std::function<ipc::Message(const ipc::Message&)>;

    SyscallRouter() = default;

    ipc::Message handle(const ipc::Message& msg) const;
    void register_handler(ipc::SyscallOp op, Handler handler);

private:
    std::unordered_map<ipc::SyscallOp, Handler> handlers_;
};

} // namespace clove::kernel
