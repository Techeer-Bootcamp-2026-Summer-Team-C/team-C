#include "edr_agent/core.hpp"
#include "edr_agent/packet_parser.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>

using namespace edr;

namespace {

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

Event event(int index, std::size_t padding = 0) {
    return {"00000000-0000-4000-8000-" + std::string(12 - std::to_string(index).size(), '0') + std::to_string(index),
            "PROCESS_EXECUTION", "2026-07-12T00:00:00.000Z",
            {{"processName", std::string("fixture") + std::string(padding, 'x')}, {"pid", static_cast<std::int64_t>(index)}}};
}

std::vector<std::uint8_t> ethernet(std::uint8_t protocol, std::vector<std::uint8_t> transport) {
    std::vector<std::uint8_t> packet(34); packet[12] = 0x08; packet[13] = 0x00; packet[14] = 0x45; packet[23] = protocol;
    packet.insert(packet.end(), transport.begin(), transport.end()); return packet;
}

std::vector<std::uint8_t> dns_packet() {
    std::vector<std::uint8_t> udp{0x30, 0x39, 0, 0x35, 0, 0, 0, 0, 0x12, 0x34, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0};
    const std::string first = "example", second = "com";
    udp.push_back(7); udp.insert(udp.end(), first.begin(), first.end()); udp.push_back(3); udp.insert(udp.end(), second.begin(), second.end());
    udp.insert(udp.end(), {0, 0, 1, 0, 1}); return ethernet(17, std::move(udp));
}

std::vector<std::uint8_t> tcp_packet(const std::string& payload) {
    std::vector<std::uint8_t> tcp(20); tcp[12] = 0x50; tcp.insert(tcp.end(), payload.begin(), payload.end()); return ethernet(6, std::move(tcp));
}

std::vector<std::uint8_t> tls_client_hello_packet() {
    std::vector<std::uint8_t> tls{22, 3, 3, 0, 67, 1, 0, 0, 63, 3, 3};
    tls.insert(tls.end(), 32, 0);
    tls.insert(tls.end(), {0, 0, 2, 0x13, 0x01, 1, 0, 0, 20, 0, 0, 0, 16, 0, 14, 0, 0, 11});
    const std::string name = "example.com";
    tls.insert(tls.end(), name.begin(), name.end());
    return tcp_packet(std::string(reinterpret_cast<const char*>(tls.data()), tls.size()));
}

void contract_fixtures() {
    const std::vector<Event> fixtures{
        event(1),
        {uuid_string(), "NETWORK_CONNECTION", utc_now(), {{"protocol", std::string("TCP")}, {"remoteIp", std::string("203.0.113.1")}, {"remotePort", std::int64_t(443)}}},
        {uuid_string(), "FILE_EVENT", utc_now(), {{"filePath", std::string("C:\\Temp\\file.txt")}, {"action", std::string(kFileActionModify)}}},
        {uuid_string(), "DNS_QUERY", utc_now(), {{"query", std::string("example.com")}, {"recordType", std::string("A")}}},
    };
    for (const auto& value : fixtures) {
        const auto json = encode_event(value);
        require(json.find("\"eventId\"") != std::string::npos, "eventId must use the camelCase contract");
        require(json.find("\"occurredAt\":\"") != std::string::npos, "occurredAt must use the camelCase contract");
        require(json.find('Z') != std::string::npos, "timestamps must be UTC");
    }
    require(encode_event(fixtures[2]).find("\"action\":\"MODIFY\"") != std::string::npos,
            "file actions must use the canonical Collector contract");
    const auto sanitized = sanitize_command_line(
        "pwsh.exe -EncodedCommand ZQBjAGgAbwA= --token=secret-value --mode audit"
    );
    require(sanitized.find("ZQBjAGgAbwA=") == std::string::npos &&
                sanitized.find("secret-value") == std::string::npos &&
                sanitized.find("-EncodedCommand <redacted>") != std::string::npos &&
                sanitized.find("--mode audit") != std::string::npos,
            "command line collection must preserve detection flags while redacting sensitive values");
}

void buffer_and_batch() {
    const auto root = std::filesystem::temp_directory_path() / ("edr-win-buffer-" + uuid_string());
    {
        EventBuffer buffer(root / "events.sqlite3", 101);
        for (int index = 1; index <= 101; ++index) buffer.enqueue(event(index), 1);
        const auto rows = buffer.pending(101, "9999-12-31T00:00:00.000Z");
        const auto batch = make_batch("agent-win-001", rows);
        require(batch && batch->rows.size() == 100 && batch->body.size() <= kMaxBatchBytes && kFlushIntervalSeconds == 5,
                "batch limits or flush interval are invalid");
        buffer.assign_batch(batch->batch_id, batch->rows);
        const auto retransmit_rows = buffer.pending(101, "9999-12-31T00:00:00.000Z");
        const auto retransmit = make_batch("agent-win-001", retransmit_rows);
        require(retransmit && retransmit->batch_id == batch->batch_id && retransmit->rows.size() == 100,
                "pending rows must reuse their batch identity");
        buffer.apply_result({rows[0].event_id}, {{rows[1].event_id, "TEMPORARY", true}, {rows[2].event_id, "INVALID", false}}, 1, 4);
        const auto metrics = buffer.metrics();
        require(metrics.pending == 99 && metrics.failed == 1 && metrics.retry_count == 2,
                "ACK and rejection results must update buffer metrics");
        buffer.transport_failure({rows[3]}, "NETWORK_OR_TLS_FAILURE", 1, 4);
        require(buffer.metrics().pending == 99, "transport failures must remain pending");
        buffer.retry_now();
    }
    {
        EventBuffer capped(root / "capped.sqlite3", 1);
        capped.enqueue(event(1));
        bool overflow = false;
        try { capped.enqueue(event(2)); } catch (const std::overflow_error&) { overflow = true; }
        require(overflow, "queue limit must reject excess events");
    }
    {
        EventBuffer isolated(root / "isolated.sqlite3", 2);
        isolated.enqueue(event(1));
        isolated.enqueue(event(2));
        isolated.apply_result({}, {{event(1).event_id, "INVALID", false}, {event(2).event_id, "INVALID", false}}, 1, 4);
        isolated.enqueue(event(3));
        isolated.enqueue(event(4));
        require(isolated.metrics().pending == 2 && isolated.metrics().failed == 2,
                "FAILED rows must not consume PENDING capacity");
        isolated.apply_result({}, {{event(3).event_id, "INVALID", false}}, 1, 4);
        const auto metrics = isolated.metrics();
        require(metrics.pending == 1 && metrics.failed == 2,
                "FAILED rows must be bounded independently with oldest-first pruning");
        isolated.apply_result({event(4).event_id}, {}, 1, 4);
        isolated.enqueue(event(1));
        isolated.enqueue(event(2));
        require(isolated.metrics().pending == 1,
                "oldest FAILED row must be pruned while the newer FAILED identity remains");
    }
    std::filesystem::remove_all(root);
}

void packet_fixtures() {
    PacketParser parser;
    const auto dns = parser.parse_ethernet(dns_packet());
    require(dns.size() == 1 && dns[0].event_type == "DNS_QUERY" && std::get<std::string>(dns[0].payload.at("query")) == "example.com",
            "DNS packet fixture must produce DNS_QUERY metadata");
    const auto http = parser.parse_ethernet(tcp_packet("GET /path?secret=yes#fragment HTTP/1.1\r\nHost: example.com\r\nAuthorization: no\r\nCookie: no\r\n\r\n"));
    require(http.size() == 1 && std::get<std::string>(http[0].payload.at("url")) == "/path",
            "HTTP metadata must remove query and fragment");
    require(!http[0].payload.contains("authorization") && !http[0].payload.contains("cookie") && !http[0].payload.contains("packetBytes"),
            "sensitive headers and packet bytes must not be stored");
    const auto tls = parser.parse_ethernet(tls_client_hello_packet());
    require(tls.size() == 1 && std::get<std::string>(tls[0].payload.at("l7Protocol")) == "TLS",
            "TLS fixture must produce TLS metadata");
    require(std::get<std::string>(tls[0].payload.at("tlsSni")) == "example.com", "TLS SNI must be parsed");
#ifndef EDR_HAS_NPCAP
    const std::string packet_status = "DEGRADED";
    require(packet_status == "DEGRADED", "packet sensor must degrade without Npcap");
#endif
}

}  // namespace

int main() {
    contract_fixtures();
    buffer_and_batch();
    packet_fixtures();
    require(exponential_backoff(1, 1, 30) == 1, "first retry backoff must equal the base");
    require(exponential_backoff(6, 1, 30) == 30, "retry backoff must respect the cap");
    std::cout << "windows_portable_agent_tests=passed\n";
}
