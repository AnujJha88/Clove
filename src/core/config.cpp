#include "core/config.hpp"
#include "core/paths.hpp"
#include <cstdlib>
#include <fstream>

namespace clove::core::config {

void load_dotenv(const std::vector<std::filesystem::path>& extra_search_paths) {
    static bool loaded = false;
    if (loaded) return;
    loaded = true;

    std::vector<std::filesystem::path> search_paths = paths::project_search_paths();
    for (const auto& p : extra_search_paths) {
        search_paths.push_back(p);
    }

    for (const auto& base : search_paths) {
        auto env_path = base / ".env";
        if (!std::filesystem::exists(env_path)) {
            continue;
        }

        std::ifstream file(env_path);
        std::string line;
        while (std::getline(file, line)) {
            // Trim whitespace
            size_t start = line.find_first_not_of(" \t\r\n");
            if (start == std::string::npos) continue;
            line = line.substr(start);

            // Skip comments
            if (line.empty() || line[0] == '#') continue;

            // Find = separator
            size_t eq_pos = line.find('=');
            if (eq_pos == std::string::npos) continue;

            std::string key = line.substr(0, eq_pos);
            std::string value = line.substr(eq_pos + 1);

            // Trim key
            size_t key_end = key.find_last_not_of(" \t");
            if (key_end != std::string::npos) key = key.substr(0, key_end + 1);

            // Trim value and remove quotes
            start = value.find_first_not_of(" \t");
            if (start != std::string::npos) value = value.substr(start);
            size_t val_end = value.find_last_not_of(" \t\r\n");
            if (val_end != std::string::npos) value = value.substr(0, val_end + 1);

            if (value.size() >= 2) {
                if ((value.front() == '"' && value.back() == '"') ||
                    (value.front() == '\'' && value.back() == '\'')) {
                    value = value.substr(1, value.size() - 2);
                }
            }

            if (!key.empty() && std::getenv(key.c_str()) == nullptr) {
                setenv(key.c_str(), value.c_str(), 0);
            }
        }
        break;
    }
}

std::string get_env(const std::string& key) {
    const char* value = std::getenv(key.c_str());
    return value ? std::string(value) : std::string();
}

std::string get_env_or(const std::string& key, const std::string& fallback) {
    auto value = get_env(key);
    return value.empty() ? fallback : value;
}

} // namespace clove::core::config
