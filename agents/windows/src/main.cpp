#ifdef _WIN32

#include "edr_agent/windows_agent.hpp"

#include <Windows.h>

#include <fstream>
#include <iostream>
#include <random>
#include <regex>
#include <thread>

namespace edr {
namespace {

std::string persistent_agent_id(const AgentConfig& config) {
    if (config.agent_id) return *config.agent_id;
    std::filesystem::create_directories(config.state_directory);
    const auto path = config.state_directory / "agent-id";
    std::ifstream input(path); std::string value;
    if (input >> value) return value;
    value = "agent-win-" + uuid_string();
    std::ofstream(path) << value;
    return value;
}

std::string hostname() {
    char value[MAX_COMPUTERNAME_LENGTH + 1]{}; DWORD length = sizeof(value);
    return GetComputerNameA(value, &length) ? std::string(value, length) : "WINDOWS-ENDPOINT";
}

std::string os_version() {
    OSVERSIONINFOW version{.dwOSVersionInfoSize = sizeof(version)};
    using RtlGetVersion = LONG(WINAPI*)(OSVERSIONINFOW*);
    const auto module = GetModuleHandleW(L"ntdll.dll");
    const auto get_version = module ? reinterpret_cast<RtlGetVersion>(GetProcAddress(module, "RtlGetVersion")) : nullptr;
    if (!get_version || get_version(&version) != 0) return "Windows";
    return std::to_string(version.dwMajorVersion) + '.' + std::to_string(version.dwMinorVersion) + '.' +
           std::to_string(version.dwBuildNumber);
}

std::string string_array(const std::vector<std::string>& values) {
    std::string result = "[";
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) result += ',';
        result += '"' + json_escape(values[index]) + '"';
    }
    return result + ']';
}

std::string sensor_json(const std::vector<SensorHealth>& health) {
    std::string result = "[";
    for (std::size_t index = 0; index < health.size(); ++index) {
        if (index) result += ',';
        const auto& item = health[index];
        result += "{\"sensor\":\"" + json_escape(item.sensor) + "\",\"status\":\"" + item.status + '"';
        if (item.provider) result += ",\"provider\":\"" + json_escape(*item.provider) + '"';
        if (item.sensor == "PACKET_METADATA") result += ",\"packetDropCount\":" + std::to_string(item.packet_drop_count);
        if (item.sensor == "L7" || item.parse_error_count > 0) result += ",\"parseErrorCount\":" + std::to_string(item.parse_error_count);
        result += '}';
    }
    return result + ']';
}

std::optional<std::int64_t> endpoint_id(const HttpResponse& response) {
    std::smatch match;
    if (response.status >= 200 && response.status < 300 &&
        std::regex_search(response.body, match, std::regex("\\\"endpointId\\\"\\s*:\\s*([0-9]+)"))) return std::stoll(match[1]);
    return std::nullopt;
}

std::string error_code(const HttpResponse& response) {
    std::smatch match;
    return std::regex_search(response.body, match, std::regex("\\\"code\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"")) ? match[1].str() : "INVALID_ERROR_ENVELOPE";
}

std::vector<std::string> accepted_ids(const HttpResponse& response) {
    const auto begin = response.body.find("\"acceptedEventIds\"");
    if (begin == std::string::npos) return {};
    const auto end = response.body.find(']', begin);
    const std::string section = response.body.substr(begin, end - begin);
    std::regex id_expression("[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}");
    std::vector<std::string> ids;
    for (std::sregex_iterator iterator(section.begin(), section.end(), id_expression), last; iterator != last; ++iterator) ids.push_back(iterator->str());
    return ids;
}

std::vector<Rejection> rejected_events(const HttpResponse& response) {
    std::vector<Rejection> result;
    const std::regex item(
        "\\{[^{}]*\\\"eventId\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"[^{}]*\\\"code\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"[^{}]*\\\"retryable\\\"\\s*:\\s*(true|false)[^{}]*\\}"
    );
    for (std::sregex_iterator iterator(response.body.begin(), response.body.end(), item), last; iterator != last; ++iterator) {
        result.push_back({(*iterator)[1], (*iterator)[2], (*iterator)[3] == "true"});
    }
    return result;
}

void safe_log(const std::string& level, const std::string& message) {
    std::cout << "level=" << level << ' ' << message << '\n';
}

}  // namespace

int run_foreground(const AgentConfig& config, bool once, std::atomic_bool* stop) {
    const auto agent_id = persistent_agent_id(config);
    EventBuffer buffer(config.state_directory / "events.sqlite3", config.queue_max_events);
    buffer.retry_now();
    WinHttpCollectorClient client(config);
    std::mt19937 generator(std::random_device{}()); std::uniform_real_distribution<double> jitter(0.9, 1.1);
    auto next_heartbeat = std::chrono::steady_clock::now();
    do {
        auto process = collect_processes();
        auto network = collect_network_connections();
        auto file = collect_file_events(config.watch_directory, std::chrono::milliseconds(500));
        auto dns = collect_dns_etw(std::chrono::milliseconds(500));
        auto packet = collect_npcap(config.capture_interface, std::chrono::milliseconds(500));
        std::vector<SensorHealth> health{process.health, network.health, file.health, dns.health, packet.health};
        health.push_back({"L7", packet.health.status, std::nullopt, 0, packet.health.parse_error_count});
        std::vector<std::string> capabilities{"PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT", "DNS_QUERY"};
        if (packet.health.status == "HEALTHY") capabilities.insert(capabilities.end(), {"L7_EVENT", "PACKET_METADATA_V1"});

        const std::string registration = "{\"agentId\":\"" + agent_id + "\",\"hostname\":\"" + json_escape(hostname()) +
            "\",\"osType\":\"WINDOWS\",\"osVersion\":\"" + json_escape(os_version()) + "\",\"agentVersion\":\"0.1.0\","
            "\"agentBuildId\":\"win-x64-20260712.1\",\"agentArch\":\"X64\",\"capabilityCodes\":" + string_array(capabilities) + '}';
        std::optional<std::int64_t> endpoint;
        try {
            const auto response = client.post("/collector/agents/register", registration);
            endpoint = endpoint_id(response);
            if (endpoint) { buffer.set_endpoint_id(*endpoint); safe_log("INFO", "registration status=success endpointId=" + std::to_string(*endpoint)); }
            else safe_log("ERROR", "registration status=failed code=" + error_code(response));
        } catch (const std::exception& error) {
            safe_log("ERROR", "registration status=failed code=NETWORK_OR_TLS_FAILURE detail=" + std::string(error.what()));
        }

        for (auto* collection : {&process, &network, &file, &dns, &packet}) {
            for (const auto& event : collection->events) {
                try { buffer.enqueue(event, endpoint); } catch (const std::overflow_error&) { safe_log("ERROR", "buffer status=full"); break; }
            }
        }

        if (std::chrono::steady_clock::now() >= next_heartbeat) {
            const auto metrics = buffer.metrics();
            const std::string heartbeat = "{\"agentId\":\"" + agent_id + "\",\"agentVersion\":\"0.1.0\","
                "\"agentBuildId\":\"win-x64-20260712.1\",\"agentArch\":\"X64\",\"capabilityCodes\":" +
                string_array(capabilities) + ",\"bufferDepth\":" + std::to_string(metrics.pending + metrics.failed) +
                ",\"sensorHealth\":" + sensor_json(health) + ",\"sentAt\":\"" + utc_now() + "\"}";
            try {
                const auto response = client.post("/collector/agents/heartbeat", heartbeat);
                safe_log(response.status == 200 ? "INFO" : "ERROR", response.status == 200 ? "heartbeat status=success" : "heartbeat status=failed code=" + error_code(response));
            } catch (const std::exception& error) {
                safe_log("ERROR", "heartbeat status=failed code=NETWORK_OR_TLS_FAILURE detail=" + std::string(error.what()));
            }
            next_heartbeat = std::chrono::steady_clock::now() + std::chrono::milliseconds(static_cast<int>(30000 * jitter(generator)));
        }

        for (int batch_attempt = 0; batch_attempt < 50; ++batch_attempt) {
            const auto rows = buffer.pending();
            const auto batch = make_batch(agent_id, rows);
            if (!batch) break;
            buffer.assign_batch(batch->batch_id, batch->rows);
            try {
                const auto response = client.post("/collector/telemetry/batches", batch->body);
                if (response.status == 200) {
                    const auto accepted = accepted_ids(response);
                    const auto rejected = rejected_events(response);
                    buffer.apply_result(accepted, rejected, config.retry_base_seconds, config.retry_max_seconds);
                    if (accepted.empty()) break;
                } else {
                    buffer.transport_failure(batch->rows, error_code(response), config.retry_base_seconds, config.retry_max_seconds);
                    safe_log("ERROR", "telemetry status=failed code=" + error_code(response)); break;
                }
            } catch (const std::exception& error) {
                buffer.transport_failure(batch->rows, "NETWORK_OR_TLS_FAILURE", config.retry_base_seconds, config.retry_max_seconds);
                safe_log("ERROR", "telemetry status=failed code=NETWORK_OR_TLS_FAILURE detail=" + std::string(error.what())); break;
            }
        }
        const auto metrics = buffer.metrics();
        safe_log("INFO", "cycle pending=" + std::to_string(metrics.pending) + " failed=" + std::to_string(metrics.failed) +
                           " retryCount=" + std::to_string(metrics.retry_count));
        if (once) break;
        std::this_thread::sleep_for(std::chrono::seconds(kFlushIntervalSeconds));
    } while (!stop || !stop->load());
    return 0;
}

}  // namespace edr

namespace {
SERVICE_STATUS_HANDLE service_handle{};
SERVICE_STATUS service_status{.dwServiceType = SERVICE_WIN32_OWN_PROCESS};
std::atomic_bool stop_service{false};

void WINAPI service_control(DWORD control) {
    if (control == SERVICE_CONTROL_STOP) {
        stop_service = true; service_status.dwCurrentState = SERVICE_STOP_PENDING;
        SetServiceStatus(service_handle, &service_status);
    }
}

void WINAPI service_main(DWORD, wchar_t**) {
    service_handle = RegisterServiceCtrlHandlerW(L"EDR-C-Agent", service_control);
    service_status.dwControlsAccepted = SERVICE_ACCEPT_STOP; service_status.dwCurrentState = SERVICE_RUNNING;
    SetServiceStatus(service_handle, &service_status);
    try { edr::run_foreground(edr::AgentConfig::load(L"C:\\ProgramData\\EDR-C-Agent\\config.json"), false, &stop_service); } catch (...) {}
    service_status.dwCurrentState = SERVICE_STOPPED; SetServiceStatus(service_handle, &service_status);
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc >= 2 && std::wstring(argv[1]) == L"--service") {
            SERVICE_TABLE_ENTRYW table[]{{const_cast<LPWSTR>(L"EDR-C-Agent"), service_main}, {nullptr, nullptr}};
            return StartServiceCtrlDispatcherW(table) ? 0 : 2;
        }
        std::filesystem::path config; bool once = false;
        for (int index = 1; index < argc; ++index) {
            const std::wstring argument = argv[index];
            if (argument == L"--config" && index + 1 < argc) config = argv[++index];
            else if (argument == L"--once") once = true;
            else if (argument == L"--help" || argument == L"-h") {
                std::wcout << L"Usage: edr-windows-agent.exe --config <path> [--once|--service]\n"; return 0;
            }
        }
        if (config.empty()) throw std::runtime_error("--config is required");
        return edr::run_foreground(edr::AgentConfig::load(config), once);
    } catch (const std::exception& error) {
        std::cerr << "agent_start_failed reason=" << error.what() << '\n'; return 2;
    }
}

#endif
