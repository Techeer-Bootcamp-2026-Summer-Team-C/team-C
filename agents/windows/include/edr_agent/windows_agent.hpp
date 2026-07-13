#pragma once

#ifdef _WIN32

#include "edr_agent/core.hpp"

#include <atomic>
#include <chrono>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace edr {

struct SensorHealth {
    std::string sensor;
    std::string status;
    std::optional<std::string> provider;
    int packet_drop_count{};
    int parse_error_count{};
};

struct Collection {
    std::vector<Event> events;
    SensorHealth health;
};

struct AgentConfig {
    std::optional<std::string> agent_id;
    std::string collector_base_url;
    std::filesystem::path certificate_pfx_path;
    std::filesystem::path state_directory;
    std::filesystem::path watch_directory;
    std::string capture_interface;
    int queue_max_events{5000};
    int retry_base_seconds{1};
    int retry_max_seconds{60};

    static AgentConfig load(const std::filesystem::path& path);
};

Collection collect_processes();
Collection collect_network_connections();
Collection collect_file_events(const std::filesystem::path& path, std::chrono::milliseconds duration);
Collection collect_dns_etw(std::chrono::milliseconds duration);
Collection collect_npcap(const std::string& interface_name, std::chrono::milliseconds duration);

struct HttpResponse { int status{}; std::string body; };

class WinHttpCollectorClient {
  public:
    explicit WinHttpCollectorClient(AgentConfig config);
    ~WinHttpCollectorClient();
    WinHttpCollectorClient(const WinHttpCollectorClient&) = delete;
    WinHttpCollectorClient& operator=(const WinHttpCollectorClient&) = delete;
    HttpResponse post(const std::string& path, const std::string& body) const;

  private:
    struct CertificateState;
    AgentConfig config_;
    std::unique_ptr<CertificateState> certificate_;
};

int run_foreground(const AgentConfig& config, bool once, std::atomic_bool* stop = nullptr);

}  // namespace edr

#endif
