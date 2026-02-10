#pragma once
#include <filesystem>
#include <string>
#include <vector>

namespace clove::core::config {

// Load environment variables from a .env file (idempotent).
void load_dotenv(const std::vector<std::filesystem::path>& extra_search_paths = {});

// Get environment variable, empty string if missing.
std::string get_env(const std::string& key);

// Get environment variable with default fallback.
std::string get_env_or(const std::string& key, const std::string& fallback);

} // namespace clove::core::config
