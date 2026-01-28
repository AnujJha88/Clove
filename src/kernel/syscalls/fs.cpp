#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "kernel/permissions_store.hpp"
#include "worlds/world_engine.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <thread>

using json = nlohmann::json;

namespace clove::kernel {

void FileSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_READ,
        [this](const ipc::Message& msg) { return handle_read(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WRITE,
        [this](const ipc::Message& msg) { return handle_write(msg); });
}

ipc::Message FileSyscalls::handle_read(const ipc::Message& msg) {
    if (context_.world_engine.is_agent_in_world(msg.agent_id)) {
        auto world_id = context_.world_engine.get_agent_world(msg.agent_id);
        if (world_id) {
            auto* world = context_.world_engine.get_world(*world_id);
            if (world && world->vfs().is_enabled()) {
                try {
                    json j = json::parse(msg.payload_str());
                    std::string path = j.value("path", "");
                    if (world->vfs().should_intercept(path)) {
                        return handle_read_virtual(msg, world);
                    }
                } catch (...) {
                }
            }
        }
    }

    auto& perms = context_.permissions_store.get_or_create(msg.agent_id);

    try {
        json j = json::parse(msg.payload_str());
        std::string path = j.value("path", "");

        if (path.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "path required";
            response["content"] = "";
            response["size"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
        }

        if (!perms.can_read_path(path)) {
            spdlog::warn("Agent {} denied read access to: {}", msg.agent_id, path);
            json response;
            response["success"] = false;
            response["error"] = "Permission denied: path not allowed for reading";
            response["content"] = "";
            response["size"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
        }

        spdlog::debug("Agent {} reading file: {}", msg.agent_id, path);

        std::ifstream file(path, std::ios::binary);
        if (!file.is_open()) {
            json response;
            response["success"] = false;
            response["error"] = "failed to open file";
            response["content"] = "";
            response["size"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
        }

        file.seekg(0, std::ios::end);
        size_t size = file.tellg();
        file.seekg(0, std::ios::beg);

        std::string content(size, '\0');
        file.read(&content[0], size);
        file.close();

        json response;
        response["success"] = true;
        response["content"] = content;
        response["size"] = size;

        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse read request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["content"] = "";
        response["size"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
    }
}

ipc::Message FileSyscalls::handle_write(const ipc::Message& msg) {
    if (context_.world_engine.is_agent_in_world(msg.agent_id)) {
        auto world_id = context_.world_engine.get_agent_world(msg.agent_id);
        if (world_id) {
            auto* world = context_.world_engine.get_world(*world_id);
            if (world && world->vfs().is_enabled()) {
                try {
                    json j = json::parse(msg.payload_str());
                    std::string path = j.value("path", "");
                    if (world->vfs().should_intercept(path)) {
                        return handle_write_virtual(msg, world);
                    }
                } catch (...) {
                }
            }
        }
    }

    auto& perms = context_.permissions_store.get_or_create(msg.agent_id);

    try {
        json j = json::parse(msg.payload_str());
        std::string path = j.value("path", "");
        std::string content = j.value("content", "");
        std::string mode = j.value("mode", "write");

        if (path.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "path required";
            response["bytes_written"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
        }

        if (!perms.can_write_path(path)) {
            spdlog::warn("Agent {} denied write access to: {}", msg.agent_id, path);
            json response;
            response["success"] = false;
            response["error"] = "Permission denied: path not allowed for writing";
            response["bytes_written"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
        }

        spdlog::debug("Agent {} writing file: {} (mode={})", msg.agent_id, path, mode);

        std::ios_base::openmode file_mode = std::ios::binary;
        if (mode == "append") {
            file_mode |= std::ios::app;
        } else {
            file_mode |= std::ios::trunc;
        }

        std::ofstream file(path, file_mode);
        if (!file.is_open()) {
            json response;
            response["success"] = false;
            response["error"] = "failed to open file for writing";
            response["bytes_written"] = 0;
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
        }

        file.write(content.data(), content.size());
        file.close();

        json response;
        response["success"] = true;
        response["bytes_written"] = content.size();

        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());

    } catch (const std::exception& e) {
        spdlog::error("Failed to parse write request: {}", e.what());
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["bytes_written"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
    }
}

// ============================================================================
// World-Aware I/O Helpers
// ============================================================================

ipc::Message FileSyscalls::handle_read_virtual(const ipc::Message& msg, clove::worlds::World* world) {
    try {
        json j = json::parse(msg.payload_str());
        std::string path = j.value("path", "");

        world->record_syscall();

        if (world->chaos().should_fail_read(path)) {
            spdlog::debug("Chaos: Injected read failure for {} in world '{}'", path, world->id());
            json response;
            response["success"] = false;
            response["error"] = "Simulated read failure (chaos)";
            response["content"] = "";
            response["size"] = 0;
            response["world"] = world->id();
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
        }

        auto content_opt = world->vfs().read(path);
        if (!content_opt.has_value()) {
            json response;
            response["success"] = false;
            response["error"] = "File not found in virtual filesystem";
            response["content"] = "";
            response["size"] = 0;
            response["world"] = world->id();
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
        }
        const std::string& content = *content_opt;

        json response;
        response["success"] = true;
        response["content"] = content;
        response["size"] = content.size();
        response["world"] = world->id();
        response["virtual"] = true;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["content"] = "";
        response["size"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_READ, response.dump());
    }
}

ipc::Message FileSyscalls::handle_write_virtual(const ipc::Message& msg, clove::worlds::World* world) {
    try {
        json j = json::parse(msg.payload_str());
        std::string path = j.value("path", "");
        std::string content = j.value("content", "");
        std::string mode = j.value("mode", "write");

        world->record_syscall();

        if (world->chaos().should_fail_write(path)) {
            spdlog::debug("Chaos: Injected write failure for {} in world '{}'", path, world->id());
            json response;
            response["success"] = false;
            response["error"] = "Simulated write failure (chaos)";
            response["bytes_written"] = 0;
            response["world"] = world->id();
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
        }

        bool ok = world->vfs().write(path, content, mode == "append");
        if (!ok) {
            json response;
            response["success"] = false;
            response["error"] = "Virtual filesystem write denied";
            response["bytes_written"] = 0;
            response["world"] = world->id();
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
        }

        json response;
        response["success"] = true;
        response["bytes_written"] = content.size();
        response["world"] = world->id();
        response["virtual"] = true;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        response["bytes_written"] = 0;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WRITE, response.dump());
    }
}

} // namespace clove::kernel
