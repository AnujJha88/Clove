#pragma once

namespace clove::kernel {

class SyscallRouter;

class KernelModule {
public:
    virtual ~KernelModule() = default;
    virtual void register_syscalls(SyscallRouter& router) = 0;
    virtual void on_tick() {}
};

} // namespace clove::kernel
