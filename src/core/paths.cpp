#include "core/paths.hpp"
#include <unistd.h>
#include <limits.h>

namespace clove::core::paths {

std::filesystem::path executable_path() {
    char buf[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (len <= 0) {
        return {};
    }
    buf[len] = '\0';
    return std::filesystem::path(buf);
}

std::filesystem::path executable_dir() {
    auto exe = executable_path();
    if (exe.empty()) {
        return {};
    }
    return exe.parent_path();
}

std::vector<std::filesystem::path> project_search_paths() {
    std::vector<std::filesystem::path> roots;
    auto cwd = std::filesystem::current_path();
    roots.push_back(cwd);
    roots.push_back(cwd.parent_path());
    roots.push_back(cwd.parent_path().parent_path());

    auto exe_dir = executable_dir();
    if (!exe_dir.empty()) {
        roots.push_back(exe_dir);
        roots.push_back(exe_dir.parent_path());
        roots.push_back(exe_dir.parent_path().parent_path());
    }

    // De-duplicate while preserving order.
    std::vector<std::filesystem::path> unique;
    for (const auto& p : roots) {
        if (p.empty()) continue;
        bool seen = false;
        for (const auto& u : unique) {
            if (u == p) {
                seen = true;
                break;
            }
        }
        if (!seen) {
            unique.push_back(p);
        }
    }
    return unique;
}

std::optional<std::filesystem::path> find_relative(const std::string& relative) {
    for (const auto& base : project_search_paths()) {
        auto candidate = base / relative;
        if (std::filesystem::exists(candidate)) {
            return std::filesystem::canonical(candidate);
        }
    }
    return std::nullopt;
}

} // namespace clove::core::paths
