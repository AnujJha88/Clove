#include "runtime/agent/types.hpp"

namespace clove::runtime {

const char* agent_state_to_string(AgentState state) {
    switch (state) {
        case AgentState::CREATED:  return "CREATED";
        case AgentState::STARTING: return "STARTING";
        case AgentState::RUNNING:  return "RUNNING";
        case AgentState::PAUSED:   return "PAUSED";
        case AgentState::STOPPING: return "STOPPING";
        case AgentState::STOPPED:  return "STOPPED";
        case AgentState::FAILED:   return "FAILED";
        default: return "UNKNOWN";
    }
}

} // namespace clove::runtime
