/**
 * AgentOS Virtual Filesystem
 *
 * Provides isolated file storage for world simulation.
 * Agents in a world see this virtual filesystem instead of the real one.
 */
#pragma once
#include <string>
#include <unordered_map>
#include <vector>
#include <chrono>
#include <optional>
#include <mutex>
#include <regex>
#include <nlohmann/json.hpp>

namespace agentos::kernel {

/**
 * A virtual file stored in memory
 */
struct VirtualFile {
    std::string content;
    std::string mode;  // "r" = readonly, "rw" = read-write
    std::chrono::steady_clock::time_point created_at;
    std::chrono::steady_clock::time_point modified_at;

    VirtualFile()
        : mode("rw")
        , created_at(std::chrono::steady_clock::now())
        , modified_at(std::chrono::steady_clock::now()) {}

    VirtualFile(const std::string& content_, const std::string& mode_ = "rw")
        : content(content_)
        , mode(mode_)
        , created_at(std::chrono::steady_clock::now())
        , modified_at(std::chrono::steady_clock::now()) {}
};

/**
 * Virtual filesystem for a world
 * Provides in-memory file storage with path-based access control
 */
class VirtualFilesystem {
public:
    VirtualFilesystem() = default;

    /**
     * Initialize from JSON configuration
     * Expected format:
     * {
     *   "initial_files": {
     *     "/path/to/file": {"content": "...", "mode": "r"}
     *   },
     *   "readonly_patterns": ["/etc/*"],
     *   "writable_patterns": ["/data/*", "/tmp/*"]
     * }
     */
    void configure(const nlohmann::json& config);

    /**
     * Check if VFS is enabled (has any files or patterns configured)
     */
    bool is_enabled() const;

    /**
     * Check if a path exists in the virtual filesystem
     */
    bool exists(const std::string& path) const;

    /**
     * Read a file from the virtual filesystem
     * Returns nullopt if file doesn't exist
     */
    std::optional<std::string> read(const std::string& path) const;

    /**
     * Write content to a virtual file
     * Creates the file if it doesn't exist
     * Returns false if path is read-only or not writable
     */
    bool write(const std::string& path, const std::string& content, bool append = false);

    /**
     * Delete a file from the virtual filesystem
     * Returns false if file doesn't exist or is read-only
     */
    bool remove(const std::string& path);

    /**
     * List files matching a pattern (glob-style)
     * Pattern supports * and ** wildcards
     */
    std::vector<std::string> list(const std::string& pattern = "*") const;

    /**
     * Get file info (size, mode, timestamps)
     */
    std::optional<nlohmann::json> stat(const std::string& path) const;

    /**
     * Check if a path is writable according to patterns
     */
    bool is_writable(const std::string& path) const;

    /**
     * Check if a path is readable (exists or matches readable pattern)
     */
    bool is_readable(const std::string& path) const;

    /**
     * Check if path should be handled by VFS (vs passthrough to real FS)
     */
    bool should_intercept(const std::string& path) const;

    /**
     * Get all files for serialization
     */
    nlohmann::json to_json() const;

    /**
     * Restore from JSON snapshot
     */
    void from_json(const nlohmann::json& j);

    /**
     * Clear all files and patterns
     */
    void clear();

    /**
     * Get metrics about VFS usage
     */
    nlohmann::json get_metrics() const;

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, VirtualFile> files_;
    std::vector<std::string> readonly_patterns_;
    std::vector<std::string> writable_patterns_;
    std::vector<std::string> intercept_patterns_;  // Paths to intercept

    // Metrics
    mutable uint64_t read_count_ = 0;
    mutable uint64_t write_count_ = 0;
    mutable uint64_t bytes_read_ = 0;
    mutable uint64_t bytes_written_ = 0;

    /**
     * Check if path matches a glob pattern
     * Supports: * (any chars except /), ** (any chars including /)
     */
    bool matches_pattern(const std::string& path, const std::string& pattern) const;

    /**
     * Check if path matches any pattern in a list
     */
    bool matches_any(const std::string& path, const std::vector<std::string>& patterns) const;

    /**
     * Normalize a path (remove ./, resolve ../, ensure leading /)
     */
    std::string normalize_path(const std::string& path) const;
};

} // namespace agentos::kernel
