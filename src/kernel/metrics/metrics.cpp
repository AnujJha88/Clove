/**
 * Clove Metrics Subsystem - Implementation
 *
 * Reads metrics from Linux /proc and /sys filesystems.
 */

#include "metrics.hpp"
#include <fstream>
#include <sstream>
#include <filesystem>
#include <algorithm>
#include <cstring>
#include <dirent.h>
#include <unistd.h>
#include <sys/sysinfo.h>

namespace fs = std::filesystem;

namespace clove::metrics {

// ============================================================================
// JSON Conversion
// ============================================================================

nlohmann::json SystemMetrics::to_json() const {
    return nlohmann::json{
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            timestamp.time_since_epoch()).count()},
        {"cpu", {
            {"percent", cpu_percent},
            {"per_core", cpu_per_core},
            {"count", cpu_count},
            {"freq_mhz", cpu_freq_mhz},
            {"load_avg", {load_avg_1m, load_avg_5m, load_avg_15m}}
        }},
        {"memory", {
            {"total", mem_total},
            {"available", mem_available},
            {"used", mem_used},
            {"percent", mem_percent},
            {"buffers", mem_buffers},
            {"cached", mem_cached}
        }},
        {"swap", {
            {"total", swap_total},
            {"used", swap_used},
            {"free", swap_free}
        }},
        {"disk", {
            {"read_bytes", disk_read_bytes},
            {"write_bytes", disk_write_bytes},
            {"read_ops", disk_read_ops},
            {"write_ops", disk_write_ops}
        }},
        {"network", {
            {"bytes_sent", net_bytes_sent},
            {"bytes_recv", net_bytes_recv},
            {"packets_sent", net_packets_sent},
            {"packets_recv", net_packets_recv},
            {"errors_in", net_errors_in},
            {"errors_out", net_errors_out}
        }}
    };
}

nlohmann::json ProcessMetrics::to_json() const {
    return nlohmann::json{
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            timestamp.time_since_epoch()).count()},
        {"pid", pid},
        {"ppid", ppid},
        {"name", name},
        {"state", state},
        {"cmdline", cmdline},
        {"cpu", {
            {"percent", cpu_percent},
            {"time_user_ms", cpu_time_user_ms},
            {"time_system_ms", cpu_time_system_ms},
            {"priority", priority},
            {"nice", nice}
        }},
        {"memory", {
            {"rss", mem_rss},
            {"vms", mem_vms},
            {"shared", mem_shared},
            {"data", mem_data},
            {"percent", mem_percent}
        }},
        {"io", {
            {"read_bytes", io_read_bytes},
            {"write_bytes", io_write_bytes},
            {"read_ops", io_read_ops},
            {"write_ops", io_write_ops}
        }},
        {"threads", num_threads},
        {"fds", num_fds}
    };
}

nlohmann::json CgroupMetrics::to_json() const {
    return nlohmann::json{
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            timestamp.time_since_epoch()).count()},
        {"cgroup_path", cgroup_path},
        {"valid", valid},
        {"cpu", {
            {"usage_usec", cpu_usage_usec},
            {"user_usec", cpu_user_usec},
            {"system_usec", cpu_system_usec},
            {"throttled_usec", cpu_throttled_usec},
            {"nr_periods", cpu_nr_periods},
            {"nr_throttled", cpu_nr_throttled},
            {"quota_usec", cpu_quota_usec},
            {"period_usec", cpu_period_usec}
        }},
        {"memory", {
            {"current", mem_current},
            {"min", mem_min},
            {"low", mem_low},
            {"high", mem_high},
            {"max", mem_max},
            {"peak", mem_peak},
            {"swap_current", mem_swap_current},
            {"swap_max", mem_swap_max},
            {"oom_kills", mem_oom_kills}
        }},
        {"pids", {
            {"current", pids_current},
            {"max", pids_max}
        }},
        {"io", {
            {"read_bytes", io_read_bytes},
            {"write_bytes", io_write_bytes},
            {"read_ops", io_read_ops},
            {"write_ops", io_write_ops}
        }}
    };
}

nlohmann::json AgentMetrics::to_json() const {
    return nlohmann::json{
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            timestamp.time_since_epoch()).count()},
        {"agent_id", agent_id},
        {"name", name},
        {"pid", pid},
        {"status", status},
        {"uptime_ms", uptime_ms},
        {"sandboxed", sandboxed},
        {"process", process.to_json()},
        {"cgroup", sandboxed ? cgroup.to_json() : nlohmann::json(nullptr)},
        {"kernel_stats", {
            {"syscall_count", syscall_count},
            {"llm_calls", llm_calls},
            {"llm_tokens_used", llm_tokens_used},
            {"messages_sent", messages_sent},
            {"messages_recv", messages_recv},
            {"bytes_read", bytes_read},
            {"bytes_written", bytes_written}
        }}
    };
}

// ============================================================================
// MetricsCollector Implementation
// ============================================================================

MetricsCollector::MetricsCollector() {
    cpu_count_ = sysconf(_SC_NPROCESSORS_ONLN);
    if (cpu_count_ < 1) cpu_count_ = 1;

    prev_cpu_per_core_total_.resize(cpu_count_, 0);
    prev_cpu_per_core_idle_.resize(cpu_count_, 0);
    prev_time_ = std::chrono::steady_clock::now();

    // Initialize CPU stats
    std::vector<uint64_t> dummy_total(cpu_count_), dummy_idle(cpu_count_);
    read_cpu_stats(prev_cpu_total_, prev_cpu_idle_, dummy_total, dummy_idle);
    prev_cpu_per_core_total_ = dummy_total;
    prev_cpu_per_core_idle_ = dummy_idle;
}

MetricsCollector::~MetricsCollector() = default;

std::string MetricsCollector::read_file(const std::string& path) {
    std::ifstream file(path);
    if (!file) return "";
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

std::vector<std::string> MetricsCollector::read_file_lines(const std::string& path) {
    std::vector<std::string> lines;
    std::ifstream file(path);
    if (!file) return lines;
    std::string line;
    while (std::getline(file, line)) {
        lines.push_back(line);
    }
    return lines;
}

uint64_t MetricsCollector::parse_uint64(const std::string& str, uint64_t default_val) {
    try {
        return std::stoull(str);
    } catch (...) {
        return default_val;
    }
}

void MetricsCollector::read_cpu_stats(uint64_t& total, uint64_t& idle,
                                       std::vector<uint64_t>& per_core_total,
                                       std::vector<uint64_t>& per_core_idle) {
    auto lines = read_file_lines("/proc/stat");
    per_core_total.resize(cpu_count_, 0);
    per_core_idle.resize(cpu_count_, 0);

    for (const auto& line : lines) {
        if (line.substr(0, 3) == "cpu") {
            std::istringstream iss(line);
            std::string cpu_name;
            uint64_t user, nice, system, idle_val, iowait, irq, softirq, steal;
            iss >> cpu_name >> user >> nice >> system >> idle_val >> iowait >> irq >> softirq >> steal;

            uint64_t total_val = user + nice + system + idle_val + iowait + irq + softirq + steal;
            uint64_t idle_all = idle_val + iowait;

            if (cpu_name == "cpu") {
                total = total_val;
                idle = idle_all;
            } else if (cpu_name.length() > 3) {
                // cpuN
                int core_id = std::stoi(cpu_name.substr(3));
                if (core_id >= 0 && core_id < cpu_count_) {
                    per_core_total[core_id] = total_val;
                    per_core_idle[core_id] = idle_all;
                }
            }
        }
    }
}

void MetricsCollector::read_meminfo(SystemMetrics& metrics) {
    auto lines = read_file_lines("/proc/meminfo");

    for (const auto& line : lines) {
        std::istringstream iss(line);
        std::string key;
        uint64_t value;
        iss >> key >> value;

        // Values are in kB, convert to bytes
        value *= 1024;

        if (key == "MemTotal:") metrics.mem_total = value;
        else if (key == "MemAvailable:") metrics.mem_available = value;
        else if (key == "MemFree:") metrics.mem_used = metrics.mem_total - value; // Updated below
        else if (key == "Buffers:") metrics.mem_buffers = value;
        else if (key == "Cached:") metrics.mem_cached = value;
        else if (key == "SwapTotal:") metrics.swap_total = value;
        else if (key == "SwapFree:") metrics.swap_free = value;
    }

    metrics.mem_used = metrics.mem_total - metrics.mem_available;
    metrics.swap_used = metrics.swap_total - metrics.swap_free;
    metrics.mem_percent = metrics.mem_total > 0 ?
        100.0 * metrics.mem_used / metrics.mem_total : 0.0;
}

void MetricsCollector::read_loadavg(SystemMetrics& metrics) {
    std::string content = read_file("/proc/loadavg");
    std::istringstream iss(content);
    iss >> metrics.load_avg_1m >> metrics.load_avg_5m >> metrics.load_avg_15m;
}

void MetricsCollector::read_diskstats(SystemMetrics& metrics) {
    auto lines = read_file_lines("/proc/diskstats");

    metrics.disk_read_bytes = 0;
    metrics.disk_write_bytes = 0;
    metrics.disk_read_ops = 0;
    metrics.disk_write_ops = 0;

    for (const auto& line : lines) {
        std::istringstream iss(line);
        int major, minor;
        std::string name;
        uint64_t reads_completed, reads_merged, sectors_read, read_time;
        uint64_t writes_completed, writes_merged, sectors_written, write_time;

        iss >> major >> minor >> name
            >> reads_completed >> reads_merged >> sectors_read >> read_time
            >> writes_completed >> writes_merged >> sectors_written >> write_time;

        // Only count physical disks (sd*, nvme*, vd*), not partitions
        if (name.find("loop") == 0) continue;
        if (name.find("ram") == 0) continue;
        if (name.find("dm-") == 0) continue;
        // Skip partitions (names ending in digits for sd*, or containing 'p' followed by digit for nvme)
        if (!name.empty() && std::isdigit(name.back())) {
            if (name.find("nvme") != 0 || name.find('p') != std::string::npos) {
                // Likely a partition
                continue;
            }
        }

        metrics.disk_read_ops += reads_completed;
        metrics.disk_write_ops += writes_completed;
        metrics.disk_read_bytes += sectors_read * 512;  // Sector size = 512 bytes
        metrics.disk_write_bytes += sectors_written * 512;
    }
}

void MetricsCollector::read_netdev(SystemMetrics& metrics) {
    auto lines = read_file_lines("/proc/net/dev");

    metrics.net_bytes_recv = 0;
    metrics.net_bytes_sent = 0;
    metrics.net_packets_recv = 0;
    metrics.net_packets_sent = 0;
    metrics.net_errors_in = 0;
    metrics.net_errors_out = 0;

    for (size_t i = 2; i < lines.size(); ++i) {  // Skip header lines
        std::string line = lines[i];
        // Replace ':' with space for easier parsing
        std::replace(line.begin(), line.end(), ':', ' ');

        std::istringstream iss(line);
        std::string iface;
        uint64_t rx_bytes, rx_packets, rx_errs, rx_drop, rx_fifo, rx_frame, rx_compressed, rx_multicast;
        uint64_t tx_bytes, tx_packets, tx_errs, tx_drop, tx_fifo, tx_colls, tx_carrier, tx_compressed;

        iss >> iface >> rx_bytes >> rx_packets >> rx_errs >> rx_drop >> rx_fifo >> rx_frame >> rx_compressed >> rx_multicast
            >> tx_bytes >> tx_packets >> tx_errs >> tx_drop >> tx_fifo >> tx_colls >> tx_carrier >> tx_compressed;

        // Skip loopback
        if (iface == "lo") continue;

        metrics.net_bytes_recv += rx_bytes;
        metrics.net_bytes_sent += tx_bytes;
        metrics.net_packets_recv += rx_packets;
        metrics.net_packets_sent += tx_packets;
        metrics.net_errors_in += rx_errs;
        metrics.net_errors_out += tx_errs;
    }
}

int MetricsCollector::count_fds(pid_t pid) {
    std::string path = "/proc/" + std::to_string(pid) + "/fd";
    DIR* dir = opendir(path.c_str());
    if (!dir) return 0;

    int count = 0;
    while (readdir(dir)) count++;
    closedir(dir);
    return count - 2;  // Subtract . and ..
}

SystemMetrics MetricsCollector::collect_system() {
    SystemMetrics metrics;
    metrics.timestamp = std::chrono::system_clock::now();

    // CPU
    uint64_t cpu_total, cpu_idle;
    std::vector<uint64_t> per_core_total(cpu_count_), per_core_idle(cpu_count_);
    read_cpu_stats(cpu_total, cpu_idle, per_core_total, per_core_idle);

    // Calculate CPU percent
    uint64_t total_diff = cpu_total - prev_cpu_total_;
    uint64_t idle_diff = cpu_idle - prev_cpu_idle_;

    if (total_diff > 0) {
        metrics.cpu_percent = 100.0 * (1.0 - static_cast<double>(idle_diff) / total_diff);
    } else {
        metrics.cpu_percent = 0.0;
    }

    // Per-core CPU percent
    metrics.cpu_per_core.resize(cpu_count_);
    for (int i = 0; i < cpu_count_; ++i) {
        uint64_t core_total_diff = per_core_total[i] - prev_cpu_per_core_total_[i];
        uint64_t core_idle_diff = per_core_idle[i] - prev_cpu_per_core_idle_[i];
        if (core_total_diff > 0) {
            metrics.cpu_per_core[i] = 100.0 * (1.0 - static_cast<double>(core_idle_diff) / core_total_diff);
        } else {
            metrics.cpu_per_core[i] = 0.0;
        }
    }

    prev_cpu_total_ = cpu_total;
    prev_cpu_idle_ = cpu_idle;
    prev_cpu_per_core_total_ = per_core_total;
    prev_cpu_per_core_idle_ = per_core_idle;

    metrics.cpu_count = cpu_count_;

    // CPU frequency (from first core)
    std::string freq_str = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq");
    metrics.cpu_freq_mhz = parse_uint64(freq_str, 0) / 1000.0;

    // Memory
    read_meminfo(metrics);

    // Load average
    read_loadavg(metrics);

    // Disk I/O
    read_diskstats(metrics);

    // Network
    read_netdev(metrics);

    return metrics;
}

std::optional<ProcessMetrics> MetricsCollector::collect_process(pid_t pid) {
    std::string proc_path = "/proc/" + std::to_string(pid);

    // Check if process exists
    if (!fs::exists(proc_path)) {
        return std::nullopt;
    }

    ProcessMetrics metrics;
    metrics.timestamp = std::chrono::system_clock::now();
    metrics.pid = pid;

    // Read /proc/[pid]/stat
    std::string stat_content = read_file(proc_path + "/stat");
    if (stat_content.empty()) return std::nullopt;

    // Parse stat - format is complex because comm can contain spaces and parentheses
    // Find the last ')' to locate end of comm field
    size_t comm_end = stat_content.rfind(')');
    if (comm_end == std::string::npos) return std::nullopt;

    // Extract comm (name)
    size_t comm_start = stat_content.find('(');
    if (comm_start != std::string::npos && comm_end > comm_start) {
        metrics.name = stat_content.substr(comm_start + 1, comm_end - comm_start - 1);
    }

    // Parse fields after comm
    std::istringstream iss(stat_content.substr(comm_end + 2));
    char state;
    int ppid, pgrp, session, tty_nr, tpgid;
    unsigned int flags;
    uint64_t minflt, cminflt, majflt, cmajflt, utime, stime;
    int64_t cutime, cstime, priority, nice;
    int64_t num_threads, itrealvalue;
    uint64_t starttime, vsize, rss;

    iss >> state >> ppid >> pgrp >> session >> tty_nr >> tpgid >> flags
        >> minflt >> cminflt >> majflt >> cmajflt >> utime >> stime
        >> cutime >> cstime >> priority >> nice >> num_threads >> itrealvalue
        >> starttime >> vsize >> rss;

    metrics.state = std::string(1, state);
    metrics.ppid = ppid;
    metrics.priority = priority;
    metrics.nice = nice;
    metrics.num_threads = num_threads;
    metrics.mem_vms = vsize;
    metrics.mem_rss = rss * sysconf(_SC_PAGESIZE);

    // Calculate CPU percent
    auto now = std::chrono::steady_clock::now();
    uint64_t total_time = utime + stime;
    auto& cpu_state = process_cpu_state_[pid];

    if (cpu_state.prev_time.time_since_epoch().count() > 0) {
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - cpu_state.prev_time).count();
        if (elapsed > 0) {
            uint64_t time_diff = total_time - (cpu_state.prev_utime + cpu_state.prev_stime);
            // Convert from clock ticks to milliseconds
            long ticks_per_sec = sysconf(_SC_CLK_TCK);
            double time_diff_ms = (time_diff * 1000.0) / ticks_per_sec;
            metrics.cpu_percent = 100.0 * time_diff_ms / elapsed;
        }
    }

    cpu_state.prev_utime = utime;
    cpu_state.prev_stime = stime;
    cpu_state.prev_time = now;

    // Convert clock ticks to milliseconds
    long ticks_per_sec = sysconf(_SC_CLK_TCK);
    metrics.cpu_time_user_ms = (utime * 1000) / ticks_per_sec;
    metrics.cpu_time_system_ms = (stime * 1000) / ticks_per_sec;

    // Read /proc/[pid]/statm for more memory info
    std::string statm_content = read_file(proc_path + "/statm");
    if (!statm_content.empty()) {
        std::istringstream statm_iss(statm_content);
        uint64_t size, resident, shared, text, lib, data, dt;
        statm_iss >> size >> resident >> shared >> text >> lib >> data >> dt;
        metrics.mem_shared = shared * sysconf(_SC_PAGESIZE);
        metrics.mem_data = data * sysconf(_SC_PAGESIZE);
    }

    // Calculate memory percent
    struct sysinfo si;
    if (sysinfo(&si) == 0) {
        metrics.mem_percent = 100.0 * metrics.mem_rss / (si.totalram * si.mem_unit);
    }

    // Read /proc/[pid]/io for I/O stats
    auto io_lines = read_file_lines(proc_path + "/io");
    for (const auto& line : io_lines) {
        std::istringstream io_iss(line);
        std::string key;
        uint64_t value;
        io_iss >> key >> value;
        if (key == "read_bytes:") metrics.io_read_bytes = value;
        else if (key == "write_bytes:") metrics.io_write_bytes = value;
        else if (key == "syscr:") metrics.io_read_ops = value;
        else if (key == "syscw:") metrics.io_write_ops = value;
    }

    // Read /proc/[pid]/cmdline
    metrics.cmdline = read_file(proc_path + "/cmdline");
    // Replace null bytes with spaces
    std::replace(metrics.cmdline.begin(), metrics.cmdline.end(), '\0', ' ');
    if (!metrics.cmdline.empty() && metrics.cmdline.back() == ' ') {
        metrics.cmdline.pop_back();
    }

    // Count file descriptors
    metrics.num_fds = count_fds(pid);

    return metrics;
}

CgroupMetrics MetricsCollector::collect_cgroup(const std::string& cgroup_path) {
    CgroupMetrics metrics;
    metrics.timestamp = std::chrono::system_clock::now();
    metrics.cgroup_path = cgroup_path;
    metrics.valid = false;

    std::string base_path = "/sys/fs/cgroup/" + cgroup_path;

    if (!fs::exists(base_path)) {
        return metrics;
    }

    metrics.valid = true;

    // CPU stats (cpu.stat)
    auto cpu_stat_lines = read_file_lines(base_path + "/cpu.stat");
    for (const auto& line : cpu_stat_lines) {
        std::istringstream iss(line);
        std::string key;
        uint64_t value;
        iss >> key >> value;
        if (key == "usage_usec") metrics.cpu_usage_usec = value;
        else if (key == "user_usec") metrics.cpu_user_usec = value;
        else if (key == "system_usec") metrics.cpu_system_usec = value;
        else if (key == "throttled_usec") metrics.cpu_throttled_usec = value;
        else if (key == "nr_periods") metrics.cpu_nr_periods = value;
        else if (key == "nr_throttled") metrics.cpu_nr_throttled = value;
    }

    // CPU max (cpu.max)
    std::string cpu_max = read_file(base_path + "/cpu.max");
    if (!cpu_max.empty()) {
        std::istringstream iss(cpu_max);
        std::string quota_str;
        iss >> quota_str >> metrics.cpu_period_usec;
        if (quota_str == "max") {
            metrics.cpu_quota_usec = 0;  // Unlimited
        } else {
            metrics.cpu_quota_usec = parse_uint64(quota_str, 0);
        }
    }

    // Memory current
    metrics.mem_current = parse_uint64(read_file(base_path + "/memory.current"), 0);

    // Memory limits
    std::string mem_max = read_file(base_path + "/memory.max");
    if (mem_max.find("max") != std::string::npos) {
        metrics.mem_max = UINT64_MAX;
    } else {
        metrics.mem_max = parse_uint64(mem_max, UINT64_MAX);
    }

    metrics.mem_min = parse_uint64(read_file(base_path + "/memory.min"), 0);
    metrics.mem_low = parse_uint64(read_file(base_path + "/memory.low"), 0);

    std::string mem_high = read_file(base_path + "/memory.high");
    if (mem_high.find("max") != std::string::npos) {
        metrics.mem_high = UINT64_MAX;
    } else {
        metrics.mem_high = parse_uint64(mem_high, UINT64_MAX);
    }

    metrics.mem_peak = parse_uint64(read_file(base_path + "/memory.peak"), 0);
    metrics.mem_swap_current = parse_uint64(read_file(base_path + "/memory.swap.current"), 0);

    std::string swap_max = read_file(base_path + "/memory.swap.max");
    if (swap_max.find("max") != std::string::npos) {
        metrics.mem_swap_max = UINT64_MAX;
    } else {
        metrics.mem_swap_max = parse_uint64(swap_max, UINT64_MAX);
    }

    // Memory events
    auto mem_events_lines = read_file_lines(base_path + "/memory.events");
    for (const auto& line : mem_events_lines) {
        std::istringstream iss(line);
        std::string key;
        uint64_t value;
        iss >> key >> value;
        if (key == "oom_kill") metrics.mem_oom_kills = value;
        else if (key == "oom_group_kill") metrics.mem_oom_group_kills = value;
    }

    // PIDs
    metrics.pids_current = static_cast<int>(parse_uint64(read_file(base_path + "/pids.current"), 0));
    std::string pids_max = read_file(base_path + "/pids.max");
    if (pids_max.find("max") != std::string::npos) {
        metrics.pids_max = -1;  // Unlimited
    } else {
        metrics.pids_max = static_cast<int>(parse_uint64(pids_max, -1));
    }

    // I/O stats (io.stat) - aggregate across all devices
    auto io_stat_lines = read_file_lines(base_path + "/io.stat");
    metrics.io_read_bytes = 0;
    metrics.io_write_bytes = 0;
    metrics.io_read_ops = 0;
    metrics.io_write_ops = 0;

    for (const auto& line : io_stat_lines) {
        // Format: "8:0 rbytes=1234 wbytes=5678 rios=10 wios=20 ..."
        std::istringstream iss(line);
        std::string device;
        iss >> device;

        std::string kv;
        while (iss >> kv) {
            size_t eq = kv.find('=');
            if (eq != std::string::npos) {
                std::string key = kv.substr(0, eq);
                uint64_t value = parse_uint64(kv.substr(eq + 1), 0);
                if (key == "rbytes") metrics.io_read_bytes += value;
                else if (key == "wbytes") metrics.io_write_bytes += value;
                else if (key == "rios") metrics.io_read_ops += value;
                else if (key == "wios") metrics.io_write_ops += value;
            }
        }
    }

    return metrics;
}

AgentMetrics MetricsCollector::collect_agent(
    uint32_t agent_id,
    pid_t pid,
    const std::string& cgroup_path,
    const std::string& name,
    const std::string& status,
    uint64_t uptime_ms
) {
    AgentMetrics metrics;
    metrics.timestamp = std::chrono::system_clock::now();
    metrics.agent_id = agent_id;
    metrics.name = name;
    metrics.pid = pid;
    metrics.status = status;
    metrics.uptime_ms = uptime_ms;
    metrics.sandboxed = !cgroup_path.empty();

    // Collect process metrics
    auto proc_metrics = collect_process(pid);
    if (proc_metrics) {
        metrics.process = *proc_metrics;
    } else {
        metrics.process.pid = pid;
        metrics.process.name = name;
        metrics.process.state = "?";
    }

    // Collect cgroup metrics if sandboxed
    if (metrics.sandboxed) {
        metrics.cgroup = collect_cgroup(cgroup_path);
    }

    // Kernel-tracked stats are set by the caller (kernel has this info)
    metrics.syscall_count = 0;
    metrics.llm_calls = 0;
    metrics.llm_tokens_used = 0;
    metrics.messages_sent = 0;
    metrics.messages_recv = 0;
    metrics.bytes_read = 0;
    metrics.bytes_written = 0;

    return metrics;
}

} // namespace clove::metrics
