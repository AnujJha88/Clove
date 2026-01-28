/**
 * Clove Metrics Subsystem
 *
 * Provides real-time system and process metrics collection.
 * Used for monitoring, benchmarking, and TUI dashboards.
 */
#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <chrono>
#include <optional>
#include <unordered_map>
#include <sys/types.h>
#include <nlohmann/json.hpp>

namespace clove::metrics {

/**
 * System-wide metrics (CPU, memory, disk, network)
 */
struct SystemMetrics {
    std::chrono::system_clock::time_point timestamp;

    // CPU
    double cpu_percent;                     // Overall CPU usage (0-100)
    std::vector<double> cpu_per_core;       // Per-core usage
    int cpu_count;
    double cpu_freq_mhz;
    double load_avg_1m;
    double load_avg_5m;
    double load_avg_15m;

    // Memory (in bytes)
    uint64_t mem_total;
    uint64_t mem_available;
    uint64_t mem_used;
    double mem_percent;
    uint64_t mem_buffers;
    uint64_t mem_cached;
    uint64_t swap_total;
    uint64_t swap_used;
    uint64_t swap_free;

    // Disk I/O (cumulative since boot)
    uint64_t disk_read_bytes;
    uint64_t disk_write_bytes;
    uint64_t disk_read_ops;
    uint64_t disk_write_ops;

    // Network (cumulative since boot)
    uint64_t net_bytes_sent;
    uint64_t net_bytes_recv;
    uint64_t net_packets_sent;
    uint64_t net_packets_recv;
    uint64_t net_errors_in;
    uint64_t net_errors_out;

    // Convert to JSON
    nlohmann::json to_json() const;
};

/**
 * Per-process metrics
 */
struct ProcessMetrics {
    std::chrono::system_clock::time_point timestamp;
    pid_t pid;
    std::string name;
    std::string state;                      // R=running, S=sleeping, D=disk, Z=zombie, T=stopped
    std::string cmdline;

    // CPU
    double cpu_percent;
    uint64_t cpu_time_user_ms;
    uint64_t cpu_time_system_ms;
    int priority;
    int nice;

    // Memory (in bytes)
    uint64_t mem_rss;                       // Resident Set Size
    uint64_t mem_vms;                       // Virtual Memory Size
    uint64_t mem_shared;                    // Shared memory
    uint64_t mem_data;                      // Data segment
    double mem_percent;

    // I/O
    uint64_t io_read_bytes;
    uint64_t io_write_bytes;
    uint64_t io_read_ops;
    uint64_t io_write_ops;

    // Threads and file descriptors
    int num_threads;
    int num_fds;

    // Parent/child
    pid_t ppid;

    // Convert to JSON
    nlohmann::json to_json() const;
};

/**
 * Cgroups v2 metrics for sandboxed processes
 */
struct CgroupMetrics {
    std::chrono::system_clock::time_point timestamp;
    std::string cgroup_path;
    bool valid;                             // Whether cgroup exists and is readable

    // CPU (from cpu.stat)
    uint64_t cpu_usage_usec;                // Total CPU time used
    uint64_t cpu_user_usec;
    uint64_t cpu_system_usec;
    uint64_t cpu_throttled_usec;            // Time spent throttled
    uint64_t cpu_nr_periods;                // Number of periods
    uint64_t cpu_nr_throttled;              // Number of throttled periods

    // CPU limits (from cpu.max)
    uint64_t cpu_quota_usec;                // Quota per period (0 = unlimited)
    uint64_t cpu_period_usec;               // Period length

    // Memory (from memory.*)
    uint64_t mem_current;
    uint64_t mem_min;
    uint64_t mem_low;
    uint64_t mem_high;
    uint64_t mem_max;                       // Limit (UINT64_MAX = unlimited)
    uint64_t mem_peak;                      // High water mark
    uint64_t mem_swap_current;
    uint64_t mem_swap_max;

    // Memory events (from memory.events)
    uint64_t mem_oom_kills;
    uint64_t mem_oom_group_kills;

    // PIDs (from pids.*)
    int pids_current;
    int pids_max;                           // Limit (-1 = unlimited)

    // I/O (from io.stat) - aggregated across all devices
    uint64_t io_read_bytes;
    uint64_t io_write_bytes;
    uint64_t io_read_ops;
    uint64_t io_write_ops;

    // Convert to JSON
    nlohmann::json to_json() const;
};

/**
 * Combined agent metrics (process + cgroup + kernel-tracked stats)
 */
struct AgentMetrics {
    std::chrono::system_clock::time_point timestamp;

    // Identity
    uint32_t agent_id;
    std::string name;
    pid_t pid;
    std::string status;                     // "running", "stopped", "failed"
    uint64_t uptime_ms;

    // Process-level metrics
    ProcessMetrics process;

    // Cgroup metrics (if sandboxed)
    bool sandboxed;
    CgroupMetrics cgroup;

    // Kernel-tracked statistics
    uint64_t syscall_count;
    uint64_t llm_calls;
    uint64_t llm_tokens_used;
    uint64_t messages_sent;
    uint64_t messages_recv;
    uint64_t bytes_read;
    uint64_t bytes_written;

    // Convert to JSON
    nlohmann::json to_json() const;
};

/**
 * Metrics collector class
 *
 * Reads system metrics from /proc, /sys/fs/cgroup, etc.
 * Thread-safe for concurrent access.
 */
class MetricsCollector {
public:
    MetricsCollector();
    ~MetricsCollector();

    // Disable copy
    MetricsCollector(const MetricsCollector&) = delete;
    MetricsCollector& operator=(const MetricsCollector&) = delete;

    /**
     * Collect system-wide metrics
     */
    SystemMetrics collect_system();

    /**
     * Collect metrics for a specific process
     * @param pid Process ID
     * @return ProcessMetrics or nullopt if process doesn't exist
     */
    std::optional<ProcessMetrics> collect_process(pid_t pid);

    /**
     * Collect cgroup metrics
     * @param cgroup_path Path relative to /sys/fs/cgroup (e.g., "clove/agent-123")
     * @return CgroupMetrics (check .valid field)
     */
    CgroupMetrics collect_cgroup(const std::string& cgroup_path);

    /**
     * Collect combined agent metrics
     * @param agent_id Agent ID from kernel
     * @param pid Process ID
     * @param cgroup_path Cgroup path (empty if not sandboxed)
     * @param name Agent name
     * @param status Agent status string
     * @param uptime_ms Agent uptime in milliseconds
     * @return AgentMetrics
     */
    AgentMetrics collect_agent(
        uint32_t agent_id,
        pid_t pid,
        const std::string& cgroup_path,
        const std::string& name,
        const std::string& status,
        uint64_t uptime_ms
    );

    /**
     * Get the number of CPU cores
     */
    int get_cpu_count() const { return cpu_count_; }

private:
    // CPU calculation state
    int cpu_count_;
    uint64_t prev_cpu_total_ = 0;
    uint64_t prev_cpu_idle_ = 0;
    std::vector<uint64_t> prev_cpu_per_core_total_;
    std::vector<uint64_t> prev_cpu_per_core_idle_;
    std::chrono::steady_clock::time_point prev_time_;

    // Per-process CPU tracking
    struct ProcessCpuState {
        uint64_t prev_utime = 0;
        uint64_t prev_stime = 0;
        std::chrono::steady_clock::time_point prev_time;
    };
    std::unordered_map<pid_t, ProcessCpuState> process_cpu_state_;

    // Helper methods
    void read_cpu_stats(uint64_t& total, uint64_t& idle,
                        std::vector<uint64_t>& per_core_total,
                        std::vector<uint64_t>& per_core_idle);
    void read_meminfo(SystemMetrics& metrics);
    void read_loadavg(SystemMetrics& metrics);
    void read_diskstats(SystemMetrics& metrics);
    void read_netdev(SystemMetrics& metrics);

    std::string read_file(const std::string& path);
    std::vector<std::string> read_file_lines(const std::string& path);
    uint64_t parse_uint64(const std::string& str, uint64_t default_val = 0);
    int count_fds(pid_t pid);
};

} // namespace clove::metrics
