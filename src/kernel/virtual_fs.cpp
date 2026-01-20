/**
 * AgentOS Virtual Filesystem Implementation
 */
#include "virtual_fs.hpp"
#include <spdlog/spdlog.h>
#include <algorithm>
#include <sstream>

namespace agentos::kernel {

void VirtualFilesystem::configure(const nlohmann::json& config) {
    std::lock_guard<std::mutex> lock(mutex_);

    // Load initial files
    if (config.contains("initial_files") && config["initial_files"].is_object()) {
        for (auto& [path, file_config] : config["initial_files"].items()) {
            std::string content;
            std::string mode = "rw";

            if (file_config.is_string()) {
                content = file_config.get<std::string>();
            } else if (file_config.is_object()) {
                content = file_config.value("content", "");
                mode = file_config.value("mode", "rw");
            }

            std::string normalized = normalize_path(path);
            files_[normalized] = VirtualFile(content, mode);
            spdlog::debug("VFS: Added initial file {} (mode={})", normalized, mode);
        }
    }

    // Load patterns
    if (config.contains("readonly_patterns") && config["readonly_patterns"].is_array()) {
        for (const auto& p : config["readonly_patterns"]) {
            readonly_patterns_.push_back(p.get<std::string>());
        }
    }

    if (config.contains("writable_patterns") && config["writable_patterns"].is_array()) {
        for (const auto& p : config["writable_patterns"]) {
            writable_patterns_.push_back(p.get<std::string>());
        }
    }

    // Intercept patterns default to all paths that have files or patterns
    if (config.contains("intercept_patterns") && config["intercept_patterns"].is_array()) {
        for (const auto& p : config["intercept_patterns"]) {
            intercept_patterns_.push_back(p.get<std::string>());
        }
    } else {
        // Default: intercept everything if we have any configuration
        if (!files_.empty() || !readonly_patterns_.empty() || !writable_patterns_.empty()) {
            intercept_patterns_.push_back("/**");
        }
    }

    spdlog::info("VFS: Configured with {} files, {} readonly patterns, {} writable patterns",
                 files_.size(), readonly_patterns_.size(), writable_patterns_.size());
}

bool VirtualFilesystem::is_enabled() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !files_.empty() || !readonly_patterns_.empty() ||
           !writable_patterns_.empty() || !intercept_patterns_.empty();
}

bool VirtualFilesystem::exists(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);
    return files_.find(normalized) != files_.end();
}

std::optional<std::string> VirtualFilesystem::read(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    auto it = files_.find(normalized);
    if (it == files_.end()) {
        spdlog::debug("VFS: File not found: {}", normalized);
        return std::nullopt;
    }

    read_count_++;
    bytes_read_ += it->second.content.size();
    spdlog::debug("VFS: Read {} bytes from {}", it->second.content.size(), normalized);
    return it->second.content;
}

bool VirtualFilesystem::write(const std::string& path, const std::string& content, bool append) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    // Check if file exists and is read-only
    auto it = files_.find(normalized);
    if (it != files_.end() && it->second.mode == "r") {
        spdlog::warn("VFS: Attempted write to read-only file: {}", normalized);
        return false;
    }

    // Check writable patterns
    if (!matches_any(normalized, writable_patterns_) && it == files_.end()) {
        // File doesn't exist and path doesn't match writable patterns
        // Allow creation only if there are no writable patterns (open access)
        if (!writable_patterns_.empty()) {
            spdlog::warn("VFS: Path not writable: {}", normalized);
            return false;
        }
    }

    // Create or update file
    if (it == files_.end()) {
        files_[normalized] = VirtualFile(content, "rw");
    } else {
        if (append) {
            it->second.content += content;
        } else {
            it->second.content = content;
        }
        it->second.modified_at = std::chrono::steady_clock::now();
    }

    write_count_++;
    bytes_written_ += content.size();
    spdlog::debug("VFS: Wrote {} bytes to {} (append={})", content.size(), normalized, append);
    return true;
}

bool VirtualFilesystem::remove(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    auto it = files_.find(normalized);
    if (it == files_.end()) {
        return false;
    }

    if (it->second.mode == "r") {
        spdlog::warn("VFS: Attempted delete of read-only file: {}", normalized);
        return false;
    }

    files_.erase(it);
    spdlog::debug("VFS: Deleted file: {}", normalized);
    return true;
}

std::vector<std::string> VirtualFilesystem::list(const std::string& pattern) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> result;

    for (const auto& [path, _] : files_) {
        if (pattern == "*" || pattern == "/**" || matches_pattern(path, pattern)) {
            result.push_back(path);
        }
    }

    std::sort(result.begin(), result.end());
    return result;
}

std::optional<nlohmann::json> VirtualFilesystem::stat(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    auto it = files_.find(normalized);
    if (it == files_.end()) {
        return std::nullopt;
    }

    nlohmann::json info;
    info["path"] = normalized;
    info["size"] = it->second.content.size();
    info["mode"] = it->second.mode;

    auto created_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        it->second.created_at.time_since_epoch()).count();
    auto modified_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        it->second.modified_at.time_since_epoch()).count();

    info["created_at"] = created_ms;
    info["modified_at"] = modified_ms;

    return info;
}

bool VirtualFilesystem::is_writable(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    // Check if file exists and is read-only
    auto it = files_.find(normalized);
    if (it != files_.end()) {
        return it->second.mode != "r";
    }

    // Check writable patterns
    if (writable_patterns_.empty()) {
        return true;  // No restrictions = all writable
    }

    return matches_any(normalized, writable_patterns_);
}

bool VirtualFilesystem::is_readable(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    // All existing files are readable
    if (files_.find(normalized) != files_.end()) {
        return true;
    }

    // If file doesn't exist, check if it would be in a readable location
    return matches_any(normalized, readonly_patterns_) ||
           matches_any(normalized, writable_patterns_);
}

bool VirtualFilesystem::should_intercept(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string normalized = normalize_path(path);

    // If file exists in VFS, always intercept
    if (files_.find(normalized) != files_.end()) {
        return true;
    }

    // Check intercept patterns
    return matches_any(normalized, intercept_patterns_);
}

nlohmann::json VirtualFilesystem::to_json() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json j;
    nlohmann::json files_json = nlohmann::json::object();

    for (const auto& [path, file] : files_) {
        nlohmann::json file_json;
        file_json["content"] = file.content;
        file_json["mode"] = file.mode;
        file_json["created_at"] = std::chrono::duration_cast<std::chrono::milliseconds>(
            file.created_at.time_since_epoch()).count();
        file_json["modified_at"] = std::chrono::duration_cast<std::chrono::milliseconds>(
            file.modified_at.time_since_epoch()).count();
        files_json[path] = file_json;
    }

    j["files"] = files_json;
    j["readonly_patterns"] = readonly_patterns_;
    j["writable_patterns"] = writable_patterns_;
    j["intercept_patterns"] = intercept_patterns_;

    return j;
}

void VirtualFilesystem::from_json(const nlohmann::json& j) {
    std::lock_guard<std::mutex> lock(mutex_);

    files_.clear();
    readonly_patterns_.clear();
    writable_patterns_.clear();
    intercept_patterns_.clear();

    if (j.contains("files") && j["files"].is_object()) {
        for (auto& [path, file_json] : j["files"].items()) {
            VirtualFile file;
            file.content = file_json.value("content", "");
            file.mode = file_json.value("mode", "rw");
            // Timestamps from JSON or use current time
            files_[path] = file;
        }
    }

    if (j.contains("readonly_patterns") && j["readonly_patterns"].is_array()) {
        for (const auto& p : j["readonly_patterns"]) {
            readonly_patterns_.push_back(p.get<std::string>());
        }
    }

    if (j.contains("writable_patterns") && j["writable_patterns"].is_array()) {
        for (const auto& p : j["writable_patterns"]) {
            writable_patterns_.push_back(p.get<std::string>());
        }
    }

    if (j.contains("intercept_patterns") && j["intercept_patterns"].is_array()) {
        for (const auto& p : j["intercept_patterns"]) {
            intercept_patterns_.push_back(p.get<std::string>());
        }
    }

    spdlog::info("VFS: Restored {} files from snapshot", files_.size());
}

void VirtualFilesystem::clear() {
    std::lock_guard<std::mutex> lock(mutex_);
    files_.clear();
    readonly_patterns_.clear();
    writable_patterns_.clear();
    intercept_patterns_.clear();
    read_count_ = 0;
    write_count_ = 0;
    bytes_read_ = 0;
    bytes_written_ = 0;
}

nlohmann::json VirtualFilesystem::get_metrics() const {
    std::lock_guard<std::mutex> lock(mutex_);

    nlohmann::json metrics;
    metrics["file_count"] = files_.size();
    metrics["read_count"] = read_count_;
    metrics["write_count"] = write_count_;
    metrics["bytes_read"] = bytes_read_;
    metrics["bytes_written"] = bytes_written_;

    uint64_t total_size = 0;
    for (const auto& [_, file] : files_) {
        total_size += file.content.size();
    }
    metrics["total_size_bytes"] = total_size;

    return metrics;
}

bool VirtualFilesystem::matches_pattern(const std::string& path, const std::string& pattern) const {
    // Convert glob pattern to regex
    std::string regex_str;
    regex_str.reserve(pattern.size() * 2);

    for (size_t i = 0; i < pattern.size(); ++i) {
        char c = pattern[i];
        switch (c) {
            case '*':
                if (i + 1 < pattern.size() && pattern[i + 1] == '*') {
                    // ** matches anything including /
                    regex_str += ".*";
                    ++i;  // Skip next *
                } else {
                    // * matches anything except /
                    regex_str += "[^/]*";
                }
                break;
            case '?':
                regex_str += "[^/]";
                break;
            case '.':
            case '(':
            case ')':
            case '[':
            case ']':
            case '{':
            case '}':
            case '^':
            case '$':
            case '|':
            case '\\':
            case '+':
                regex_str += '\\';
                regex_str += c;
                break;
            default:
                regex_str += c;
                break;
        }
    }

    try {
        std::regex re(regex_str, std::regex::icase);
        return std::regex_match(path, re);
    } catch (const std::regex_error& e) {
        spdlog::error("VFS: Invalid pattern '{}': {}", pattern, e.what());
        return false;
    }
}

bool VirtualFilesystem::matches_any(const std::string& path,
                                    const std::vector<std::string>& patterns) const {
    for (const auto& pattern : patterns) {
        if (matches_pattern(path, pattern)) {
            return true;
        }
    }
    return false;
}

std::string VirtualFilesystem::normalize_path(const std::string& path) const {
    if (path.empty()) {
        return "/";
    }

    std::string result;
    std::vector<std::string> parts;
    std::stringstream ss(path);
    std::string part;

    // Split by /
    while (std::getline(ss, part, '/')) {
        if (part.empty() || part == ".") {
            continue;
        }
        if (part == "..") {
            if (!parts.empty()) {
                parts.pop_back();
            }
        } else {
            parts.push_back(part);
        }
    }

    // Rebuild path
    result = "/";
    for (size_t i = 0; i < parts.size(); ++i) {
        result += parts[i];
        if (i < parts.size() - 1) {
            result += "/";
        }
    }

    return result;
}

} // namespace agentos::kernel
