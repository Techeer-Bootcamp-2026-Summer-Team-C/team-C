#ifdef _WIN32

#include "edr_agent/windows_agent.hpp"
#include "edr_agent/packet_parser.hpp"

#include <winsock2.h>
#include <ws2tcpip.h>

#include <Windows.h>
#include <bcrypt.h>
#include <iphlpapi.h>
#include <tdh.h>
#include <tlhelp32.h>
#include <wincrypt.h>

#include <array>
#include <fstream>
#include <mutex>
#include <thread>

#ifdef EDR_HAS_NPCAP
#include <pcap.h>
#endif

namespace edr {
namespace {

std::string narrow(const std::wstring& value) {
    if (value.empty()) return {};
    const int size = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string output(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), output.data(), size, nullptr, nullptr);
    return output;
}

std::string sha256_file(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return {};
    BCRYPT_ALG_HANDLE algorithm{}; BCRYPT_HASH_HANDLE hash{};
    DWORD object_size{}, result_size{};
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) != 0) return {};
    BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_size), sizeof(object_size), &result_size, 0);
    std::vector<UCHAR> object(object_size), digest(32);
    if (BCryptCreateHash(algorithm, &hash, object.data(), object_size, nullptr, 0, 0) != 0) { BCryptCloseAlgorithmProvider(algorithm, 0); return {}; }
    std::array<char, 64 * 1024> chunk{};
    while (file.read(chunk.data(), chunk.size()) || file.gcount() > 0) BCryptHashData(hash, reinterpret_cast<PUCHAR>(chunk.data()), static_cast<ULONG>(file.gcount()), 0);
    BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0);
    BCryptDestroyHash(hash); BCryptCloseAlgorithmProvider(algorithm, 0);
    static constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (const auto byte : digest) { result += hex[byte >> 4]; result += hex[byte & 0xf]; }
    return result;
}

std::string sha256_bytes(std::span<const std::uint8_t> bytes) {
    BCRYPT_ALG_HANDLE algorithm{};
    BCRYPT_HASH_HANDLE hash{};
    DWORD object_size{}, result_size{};
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) != 0) return {};
    BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_size), sizeof(object_size), &result_size, 0);
    std::vector<UCHAR> object(object_size), digest(32);
    if (BCryptCreateHash(algorithm, &hash, object.data(), object_size, nullptr, 0, 0) != 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0);
        return {};
    }
    BCryptHashData(hash, const_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0);
    BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0);
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    static constexpr char hex[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (const auto byte : digest) { result += hex[byte >> 4]; result += hex[byte & 0xf]; }
    return result;
}

std::optional<std::size_t> u24(std::span<const std::uint8_t> bytes, std::size_t offset) {
    if (offset + 2 >= bytes.size()) return std::nullopt;
    return (static_cast<std::size_t>(bytes[offset]) << 16) |
           (static_cast<std::size_t>(bytes[offset + 1]) << 8) |
           static_cast<std::size_t>(bytes[offset + 2]);
}

std::optional<Event> tls_certificate_event(std::span<const std::uint8_t> packet) {
    if (packet.size() < 14 + 20 || packet[12] != 0x08 || packet[13] != 0x00) return std::nullopt;
    const std::size_t ip = 14;
    const std::size_t ip_header = static_cast<std::size_t>(packet[ip] & 0x0f) * 4;
    if (ip_header < 20 || packet.size() < ip + ip_header + 20 || packet[ip + 9] != 6) return std::nullopt;
    const std::size_t tcp = ip + ip_header;
    const std::size_t tcp_header = static_cast<std::size_t>((packet[tcp + 12] >> 4) & 0x0f) * 4;
    if (tcp_header < 20 || packet.size() <= tcp + tcp_header) return std::nullopt;
    const auto tls = packet.subspan(tcp + tcp_header);
    if (tls.size() < 15 || tls[0] != 22 || tls[5] != 11) return std::nullopt;

    std::size_t certificate_length_offset = 12;
    auto certificate_length = u24(tls, certificate_length_offset);
    if (!certificate_length || certificate_length_offset + 3 + *certificate_length > tls.size()) {
        const std::size_t context_end = 10 + tls[9];
        if (context_end + 6 > tls.size()) return std::nullopt;
        certificate_length_offset = context_end + 3;
        certificate_length = u24(tls, certificate_length_offset);
    }
    if (!certificate_length || *certificate_length == 0 ||
        certificate_length_offset + 3 + *certificate_length > tls.size()) return std::nullopt;
    const auto certificate_bytes = tls.subspan(certificate_length_offset + 3, *certificate_length);
    PCCERT_CONTEXT certificate = CertCreateCertificateContext(
        X509_ASN_ENCODING | PKCS_7_ASN_ENCODING,
        certificate_bytes.data(),
        static_cast<DWORD>(certificate_bytes.size())
    );
    if (!certificate) return std::nullopt;
    const auto certificate_name = [certificate](DWORD flags) {
        const DWORD size = CertGetNameStringA(certificate, CERT_NAME_SIMPLE_DISPLAY_TYPE, flags, nullptr, nullptr, 0);
        if (size <= 1) return std::string{};
        std::string value(size, '\0');
        CertGetNameStringA(certificate, CERT_NAME_SIMPLE_DISPLAY_TYPE, flags, nullptr, value.data(), size);
        value.resize(size - 1);
        return value;
    };
    std::map<std::string, JsonValue> payload{{"l7Protocol", std::string("TLS")}};
    const auto subject = certificate_name(0), issuer = certificate_name(CERT_NAME_ISSUER_FLAG);
    if (!subject.empty()) payload["tlsSubject"] = subject;
    if (!issuer.empty()) payload["tlsIssuer"] = issuer;
    const auto checksum = sha256_bytes(certificate_bytes);
    if (!checksum.empty()) payload["tlsSha256"] = checksum;
    CertFreeCertificateContext(certificate);
    return Event{uuid_string(), "L7_EVENT", utc_now(), std::move(payload)};
}

struct DnsEtwContext { std::mutex mutex; std::vector<Event> events; int parse_errors{}; };

std::optional<std::wstring> tdh_string(PEVENT_RECORD record, const wchar_t* name) {
    PROPERTY_DATA_DESCRIPTOR descriptor{};
    descriptor.PropertyName = reinterpret_cast<ULONGLONG>(name); descriptor.ArrayIndex = ULONG_MAX;
    ULONG size{};
    if (TdhGetPropertySize(record, 0, nullptr, 1, &descriptor, &size) != ERROR_SUCCESS || size < sizeof(wchar_t)) return std::nullopt;
    std::vector<std::byte> bytes(size);
    if (TdhGetProperty(record, 0, nullptr, 1, &descriptor, size, reinterpret_cast<PBYTE>(bytes.data())) != ERROR_SUCCESS) return std::nullopt;
    return std::wstring(reinterpret_cast<wchar_t*>(bytes.data()));
}

VOID WINAPI dns_event_callback(PEVENT_RECORD record) {
    auto* context = static_cast<DnsEtwContext*>(record->UserContext);
    if (!context) return;
    auto query = tdh_string(record, L"QueryName");
    if (!query) query = tdh_string(record, L"Name");
    if (!query || query->empty()) { ++context->parse_errors; return; }
    auto type = tdh_string(record, L"QueryType");
    std::scoped_lock lock(context->mutex);
    context->events.push_back({uuid_string(), "DNS_QUERY", utc_now(), {
        {"query", narrow(*query)}, {"recordType", type ? narrow(*type) : std::string("UNKNOWN")}
    }});
}

}  // namespace

Collection collect_processes() {
    Collection result{{}, {"PROCESS", "HEALTHY"}};
    const HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) { result.health.status = "DEGRADED"; return result; }
    PROCESSENTRY32W entry{.dwSize = sizeof(entry)};
    if (Process32FirstW(snapshot, &entry)) do {
        result.events.push_back({uuid_string(), "PROCESS_EXECUTION", utc_now(), {
            {"processName", narrow(entry.szExeFile)}, {"pid", static_cast<std::int64_t>(entry.th32ProcessID)},
            {"ppid", static_cast<std::int64_t>(entry.th32ParentProcessID)}
        }});
    } while (Process32NextW(snapshot, &entry));
    CloseHandle(snapshot);
    return result;
}

Collection collect_network_connections() {
    Collection result{{}, {"NETWORK", "HEALTHY"}};
    ULONG size = 0;
    GetExtendedTcpTable(nullptr, &size, FALSE, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0);
    std::vector<std::byte> storage(size);
    if (GetExtendedTcpTable(storage.data(), &size, FALSE, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0) != NO_ERROR) {
        result.health.status = "DEGRADED"; return result;
    }
    const auto* table = reinterpret_cast<PMIB_TCPTABLE_OWNER_PID>(storage.data());
    for (DWORD index = 0; index < table->dwNumEntries; ++index) {
        const auto& row = table->table[index];
        IN_ADDR address{};
        address.S_un.S_addr = row.dwRemoteAddr;
        char remote[INET_ADDRSTRLEN]{};
        InetNtopA(AF_INET, &address, remote, sizeof(remote));
        result.events.push_back({uuid_string(), "NETWORK_CONNECTION", utc_now(), {
            {"protocol", std::string("TCP")}, {"remoteIp", std::string(remote)},
            {"remotePort", static_cast<std::int64_t>(ntohs(static_cast<u_short>(row.dwRemotePort)))},
            {"pid", static_cast<std::int64_t>(row.dwOwningPid)}
        }});
    }
    return result;
}

Collection collect_file_events(const std::filesystem::path& path, std::chrono::milliseconds duration) {
    std::filesystem::create_directories(path);
    Collection result{{}, {"FILE", "HEALTHY"}};
    const HANDLE directory = CreateFileW(path.c_str(), FILE_LIST_DIRECTORY, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                         nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED, nullptr);
    if (directory == INVALID_HANDLE_VALUE) { result.health.status = "DEGRADED"; return result; }
    std::array<std::byte, 64 * 1024> buffer{};
    OVERLAPPED overlap{}; overlap.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ReadDirectoryChangesW(directory, buffer.data(), static_cast<DWORD>(buffer.size()), TRUE,
                               FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SIZE,
                               nullptr, &overlap, nullptr)) {
        result.health.status = "DEGRADED"; CloseHandle(overlap.hEvent); CloseHandle(directory); return result;
    }
    if (WaitForSingleObject(overlap.hEvent, static_cast<DWORD>(duration.count())) == WAIT_OBJECT_0) {
        DWORD transferred{};
        if (GetOverlappedResult(directory, &overlap, &transferred, FALSE)) {
            auto* item = reinterpret_cast<FILE_NOTIFY_INFORMATION*>(buffer.data());
            while (item) {
                const std::wstring name(item->FileName, item->FileNameLength / sizeof(wchar_t));
                const auto full_path = path / name;
                const std::map<DWORD, std::string> actions{{FILE_ACTION_ADDED, "CREATED"}, {FILE_ACTION_REMOVED, "DELETED"},
                    {FILE_ACTION_MODIFIED, "MODIFIED"}, {FILE_ACTION_RENAMED_OLD_NAME, "RENAMED"}, {FILE_ACTION_RENAMED_NEW_NAME, "RENAMED"}};
                std::map<std::string, JsonValue> payload{{"filePath", narrow(full_path.wstring())}, {"action", actions.at(item->Action)}};
                const auto checksum = sha256_file(full_path); if (!checksum.empty()) payload["sha256"] = checksum;
                result.events.push_back({uuid_string(), "FILE_EVENT", utc_now(), std::move(payload)});
                item = item->NextEntryOffset ? reinterpret_cast<FILE_NOTIFY_INFORMATION*>(reinterpret_cast<std::byte*>(item) + item->NextEntryOffset) : nullptr;
            }
        }
    } else CancelIoEx(directory, &overlap);
    CloseHandle(overlap.hEvent); CloseHandle(directory);
    return result;
}

Collection collect_dns_etw(std::chrono::milliseconds duration) {
    // Microsoft-Windows-DNS-Client provider는 이 짧은 수집 구간에만 활성화한다.
    // TDH schema 지원 여부는 Windows build마다 다르며, 사용할 수 없으면 DNS sensor만 DEGRADED로 처리한다.
    static const GUID provider{0x1c95126e, 0x7eea, 0x49a9, {0xa3, 0xfe, 0xa3, 0x78, 0xb0, 0x3d, 0xdb, 0x4d}};
    const std::wstring session_name = L"EDR-C-DNS-" + std::to_wstring(GetCurrentProcessId());
    std::vector<std::byte> properties(sizeof(EVENT_TRACE_PROPERTIES) + 2 * 1024);
    auto* trace = reinterpret_cast<EVENT_TRACE_PROPERTIES*>(properties.data());
    trace->Wnode.BufferSize = static_cast<ULONG>(properties.size()); trace->Wnode.Flags = WNODE_FLAG_TRACED_GUID;
    trace->LogFileMode = EVENT_TRACE_REAL_TIME_MODE; trace->LoggerNameOffset = sizeof(EVENT_TRACE_PROPERTIES);
    TRACEHANDLE session{};
    Collection result{{}, {"DNS", "HEALTHY", std::string("DNS_CLIENT_ETW")}};
    if (StartTraceW(&session, session_name.c_str(), trace) != ERROR_SUCCESS ||
        EnableTraceEx2(session, &provider, EVENT_CONTROL_CODE_ENABLE_PROVIDER, TRACE_LEVEL_INFORMATION, ~0ULL, 0, 0, nullptr) != ERROR_SUCCESS) {
        result.health.status = "DEGRADED"; return result;
    }
    DnsEtwContext context;
    EVENT_TRACE_LOGFILEW log{};
    log.LoggerName = const_cast<LPWSTR>(session_name.c_str());
    log.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD;
    log.EventRecordCallback = dns_event_callback;
    log.Context = &context;
    const TRACEHANDLE consumer = OpenTraceW(&log);
    if (consumer == INVALID_PROCESSTRACE_HANDLE) {
        result.health.status = "DEGRADED";
        EnableTraceEx2(session, &provider, EVENT_CONTROL_CODE_DISABLE_PROVIDER, 0, 0, 0, 0, nullptr);
        ControlTraceW(session, session_name.c_str(), trace, EVENT_TRACE_CONTROL_STOP);
        return result;
    }
    std::thread processing([consumer] { TRACEHANDLE value = consumer; ProcessTrace(&value, 1, nullptr, nullptr); });
    std::this_thread::sleep_for(duration);
    EnableTraceEx2(session, &provider, EVENT_CONTROL_CODE_DISABLE_PROVIDER, 0, 0, 0, 0, nullptr);
    ControlTraceW(session, session_name.c_str(), trace, EVENT_TRACE_CONTROL_STOP);
    CloseTrace(consumer);
    processing.join();
    result.events = std::move(context.events);
    result.health.parse_error_count = context.parse_errors;
    return result;
}

Collection collect_npcap(const std::string& interface_name, std::chrono::milliseconds duration) {
#ifdef EDR_HAS_NPCAP
    char error[PCAP_ERRBUF_SIZE]{};
    pcap_t* handle = pcap_open_live(interface_name.c_str(), 65535, 0, 100, error);
    if (!handle) return {{}, {"PACKET_METADATA", "DEGRADED", std::string("NPCAP")}};
    PacketParser parser;
    Collection result{{}, {"PACKET_METADATA", "HEALTHY", std::string("NPCAP")}};
    const auto end = std::chrono::steady_clock::now() + duration;
    while (std::chrono::steady_clock::now() < end) {
        pcap_pkthdr* header{}; const u_char* bytes{};
        const int status = pcap_next_ex(handle, &header, &bytes);
        if (status == 1) {
            auto parsed = parser.parse_ethernet({bytes, header->caplen});
            if (auto certificate = tls_certificate_event({bytes, header->caplen})) parsed.push_back(std::move(*certificate));
            result.events.insert(result.events.end(), parsed.begin(), parsed.end());
        } else if (status < 0) { result.health.status = "DEGRADED"; break; }
    }
    pcap_stat stats{}; if (pcap_stats(handle, &stats) == 0) result.health.packet_drop_count = static_cast<int>(stats.ps_drop);
    result.health.parse_error_count = parser.parse_error_count(); pcap_close(handle); return result;
#else
    (void)interface_name; (void)duration;
    return {{}, {"PACKET_METADATA", "DEGRADED", std::string("NPCAP")}};
#endif
}

}  // namespace edr

#endif
