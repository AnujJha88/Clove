#pragma once
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace clove::core::paths {

// Best-effort path to current executable; empty if unavailable.
std::filesystem::path executable_path();

// Best-effort directory of the current executable; empty if unavailable.
std::filesystem::path executable_dir();

// Common search roots for project-relative assets.
std::vector<std::filesystem::path> project_search_paths();

// Find a relative path under any of the search roots.
std::optional<std::filesystem::path> find_relative(const std::string& relative);

} // namespace clove::core::paths
