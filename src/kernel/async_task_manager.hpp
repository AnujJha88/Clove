#pragma once
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>
#include "ipc/protocol.hpp"

namespace clove::kernel {

class AsyncTaskManager {
public:
    using TaskFn = std::function<ipc::Message()>;

    struct AsyncResult {
        uint64_t request_id;
        ipc::SyscallOp opcode;
        std::string payload;
    };

    explicit AsyncTaskManager(size_t worker_count = 4);
    ~AsyncTaskManager();

    uint64_t next_request_id();
    bool submit(uint32_t agent_id, ipc::SyscallOp opcode, uint64_t request_id, TaskFn task);
    std::vector<AsyncResult> poll(uint32_t agent_id, int max_results);

private:
    struct Task {
        uint32_t agent_id;
        uint64_t request_id;
        ipc::SyscallOp opcode;
        TaskFn fn;
    };

    void worker_loop();

    std::deque<Task> queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::vector<std::thread> workers_;
    std::atomic<bool> stopping_{false};

    std::unordered_map<uint32_t, std::deque<AsyncResult>> results_;
    std::mutex results_mutex_;

    std::atomic<uint64_t> next_request_id_{1};
};

} // namespace clove::kernel
