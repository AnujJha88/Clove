#include "kernel/syscall_handlers.hpp"
#include "kernel/syscall_router.hpp"
#include "worlds/world_engine.hpp"
#include <spdlog/spdlog.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace clove::kernel {

void WorldSyscalls::register_syscalls(SyscallRouter& router) {
    router.register_handler(ipc::SyscallOp::SYS_WORLD_CREATE,
        [this](const ipc::Message& msg) { return handle_world_create(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_DESTROY,
        [this](const ipc::Message& msg) { return handle_world_destroy(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_LIST,
        [this](const ipc::Message& msg) { return handle_world_list(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_JOIN,
        [this](const ipc::Message& msg) { return handle_world_join(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_LEAVE,
        [this](const ipc::Message& msg) { return handle_world_leave(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_EVENT,
        [this](const ipc::Message& msg) { return handle_world_event(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_STATE,
        [this](const ipc::Message& msg) { return handle_world_state(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_SNAPSHOT,
        [this](const ipc::Message& msg) { return handle_world_snapshot(msg); });
    router.register_handler(ipc::SyscallOp::SYS_WORLD_RESTORE,
        [this](const ipc::Message& msg) { return handle_world_restore(msg); });
}

ipc::Message WorldSyscalls::handle_world_create(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string name = j.value("name", "unnamed");
        json config = j.value("config", json::object());

        auto world_id = context_.world_engine.create_world(name, config);
        if (!world_id) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to create world";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_CREATE, response.dump());
        }

        spdlog::info("Agent {} created world '{}' (name={})", msg.agent_id, *world_id, name);

        json response;
        response["success"] = true;
        response["world_id"] = *world_id;
        response["name"] = name;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_CREATE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_CREATE, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_destroy(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string world_id = j.value("world_id", "");
        bool force = j.value("force", false);

        if (world_id.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "world_id required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_DESTROY, response.dump());
        }

        bool destroyed = context_.world_engine.destroy_world(world_id, force);

        if (!destroyed) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to destroy world (not found or has active agents)";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_DESTROY, response.dump());
        }

        spdlog::info("Agent {} destroyed world '{}'", msg.agent_id, world_id);

        json response;
        response["success"] = true;
        response["world_id"] = world_id;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_DESTROY, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_DESTROY, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_list(const ipc::Message& msg) {
    auto worlds = context_.world_engine.list_worlds();

    json response;
    response["success"] = true;
    response["worlds"] = worlds;
    response["count"] = worlds.size();
    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_LIST, response.dump());
}

ipc::Message WorldSyscalls::handle_world_join(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string world_id = j.value("world_id", "");

        if (world_id.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "world_id required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_JOIN, response.dump());
        }

        bool joined = context_.world_engine.join_world(msg.agent_id, world_id);

        if (!joined) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to join world (not found or already in a world)";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_JOIN, response.dump());
        }

        spdlog::info("Agent {} joined world '{}'", msg.agent_id, world_id);

        json response;
        response["success"] = true;
        response["world_id"] = world_id;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_JOIN, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_JOIN, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_leave(const ipc::Message& msg) {
    bool left = context_.world_engine.leave_world(msg.agent_id);

    if (!left) {
        json response;
        response["success"] = false;
        response["error"] = "Not in any world";
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_LEAVE, response.dump());
    }

    spdlog::info("Agent {} left world", msg.agent_id);

    json response;
    response["success"] = true;
    return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_LEAVE, response.dump());
}

ipc::Message WorldSyscalls::handle_world_event(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string world_id = j.value("world_id", "");
        std::string event_type = j.value("event_type", "");
        json params = j.value("params", json::object());

        if (world_id.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "world_id required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_EVENT, response.dump());
        }

        if (event_type.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "event_type required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_EVENT, response.dump());
        }

        bool injected = context_.world_engine.inject_event(world_id, event_type, params);

        if (!injected) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to inject event (world not found)";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_EVENT, response.dump());
        }

        spdlog::info("Agent {} injected chaos event '{}' into world '{}'",
                     msg.agent_id, event_type, world_id);

        json response;
        response["success"] = true;
        response["world_id"] = world_id;
        response["event_type"] = event_type;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_EVENT, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_EVENT, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_state(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string world_id = j.value("world_id", "");

        if (world_id.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "world_id required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_STATE, response.dump());
        }

        auto state = context_.world_engine.get_world_state(world_id);

        if (!state) {
            json response;
            response["success"] = false;
            response["error"] = "World not found";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_STATE, response.dump());
        }

        json response;
        response["success"] = true;
        response["state"] = *state;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_STATE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_STATE, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_snapshot(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        std::string world_id = j.value("world_id", "");

        if (world_id.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "world_id required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_SNAPSHOT, response.dump());
        }

        auto snapshot = context_.world_engine.snapshot_world(world_id);

        if (!snapshot) {
            json response;
            response["success"] = false;
            response["error"] = "World not found";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_SNAPSHOT, response.dump());
        }

        spdlog::info("Agent {} created snapshot of world '{}'", msg.agent_id, world_id);

        json response;
        response["success"] = true;
        response["snapshot"] = *snapshot;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_SNAPSHOT, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_SNAPSHOT, response.dump());
    }
}

ipc::Message WorldSyscalls::handle_world_restore(const ipc::Message& msg) {
    try {
        json j = json::parse(msg.payload_str());

        json snapshot = j.value("snapshot", json{});
        std::string new_world_id = j.value("new_world_id", "");

        if (snapshot.empty()) {
            json response;
            response["success"] = false;
            response["error"] = "snapshot required";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_RESTORE, response.dump());
        }

        auto world_id = context_.world_engine.restore_world(snapshot, new_world_id);

        if (!world_id) {
            json response;
            response["success"] = false;
            response["error"] = "Failed to restore world";
            return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_RESTORE, response.dump());
        }

        spdlog::info("Agent {} restored world as '{}'", msg.agent_id, *world_id);

        json response;
        response["success"] = true;
        response["world_id"] = *world_id;
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_RESTORE, response.dump());

    } catch (const std::exception& e) {
        json response;
        response["success"] = false;
        response["error"] = std::string("invalid request: ") + e.what();
        return ipc::Message(msg.agent_id, ipc::SyscallOp::SYS_WORLD_RESTORE, response.dump());
    }
}

} // namespace clove::kernel
