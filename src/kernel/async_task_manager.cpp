#include "kernel/async_task_manager.hpp"

namespace clove::kernel {

AsyncTaskManager::AsyncTaskManager(size_t worker_count) {
    if (worker_count == 0) {
        worker_count = 1;
    }
    workers_.reserve(worker_count);
    for (size_t i = 0; i < worker_count; ++i) {
        workers_.emplace_back([this]() { worker_loop(); });
    }
}

AsyncTaskManager::~AsyncTaskManager() {
    stopping_ = true;
    queue_cv_.notify_all();
    for (auto& worker : workers_) {
        if (worker.joinable()) {
            worker.join();
        }
    }
}

uint64_t AsyncTaskManager::next_request_id() {
    return next_request_id_.fetch_add(1, std::memory_order_relaxed);
}

bool AsyncTaskManager::submit(uint32_t agent_id, ipc::SyscallOp opcode, uint64_t request_id, TaskFn task) {
    if (stopping_) {
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        queue_.push_back(Task{agent_id, request_id, opcode, std::move(task)});
    }
    queue_cv_.notify_one();
    return true;
}

std::vector<AsyncTaskManager::AsyncResult> AsyncTaskManager::poll(uint32_t agent_id, int max_results) {
    std::vector<AsyncResult> results;
    if (max_results <= 0) {
        return results;
    }

    std::lock_guard<std::mutex> lock(results_mutex_);
    auto it = results_.find(agent_id);
    if (it == results_.end()) {
        return results;
    }

    auto& queue = it->second;
    while (!queue.empty() && static_cast<int>(results.size()) < max_results) {
        results.push_back(queue.front());
        queue.pop_front();
    }

    return results;
}

void AsyncTaskManager::worker_loop() {
    while (true) {
        Task task;
        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait(lock, [this]() { return stopping_ || !queue_.empty(); });
            if (stopping_ && queue_.empty()) {
                return;
            }
            task = std::move(queue_.front());
            queue_.pop_front();
        }

        ipc::Message response = task.fn();
        AsyncResult result{task.request_id, response.opcode, response.payload_str()};

        {
            std::lock_guard<std::mutex> lock(results_mutex_);
            results_[task.agent_id].push_back(std::move(result));
        }
    }
}

} // namespace clove::kernel
