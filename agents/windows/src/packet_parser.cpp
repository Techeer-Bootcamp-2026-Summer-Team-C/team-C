#include "edr_agent/packet_parser.hpp"

#include <algorithm>
#include <set>
#include <sstream>

namespace edr {
namespace {

std::optional<std::uint16_t> u16(std::span<const std::uint8_t> bytes, std::size_t offset) {
    if (offset + 1 >= bytes.size()) return std::nullopt;
    return static_cast<std::uint16_t>((bytes[offset] << 8) | bytes[offset + 1]);
}

std::string tls_version(std::uint16_t value) {
    switch (value) {
        case 0x0301: return "TLS1.0";
        case 0x0302: return "TLS1.1";
        case 0x0303: return "TLS1.2";
        case 0x0304: return "TLS1.3";
        default: return "UNKNOWN";
    }
}

}  // namespace

std::vector<Event> PacketParser::parse_ethernet(std::span<const std::uint8_t> packet) {
    if (packet.size() < 34 || !u16(packet, 12) || *u16(packet, 12) != 0x0800) return {};
    const std::size_t ip = 14;
    const std::size_t ip_header = static_cast<std::size_t>(packet[ip] & 0x0f) * 4;
    if (ip_header < 20 || packet.size() < ip + ip_header) { ++parse_errors_; return {}; }
    if (packet[ip + 9] == 17) return parse_udp(packet, ip + ip_header);
    if (packet[ip + 9] == 6) return parse_tcp(packet, ip + ip_header);
    return {};
}

std::vector<Event> PacketParser::parse_udp(std::span<const std::uint8_t> packet, std::size_t offset) {
    if (packet.size() < offset + 20) { ++parse_errors_; return {}; }
    const auto source = u16(packet, offset), destination = u16(packet, offset + 2);
    if (!source || !destination || (*source != 53 && *destination != 53)) return {};
    const auto dns = packet.subspan(offset + 8);
    std::size_t cursor = 12;
    std::vector<std::string> labels;
    while (cursor < dns.size()) {
        const std::size_t length = dns[cursor++];
        if (length == 0) break;
        if (length > 63 || cursor + length > dns.size()) { ++parse_errors_; return {}; }
        labels.emplace_back(reinterpret_cast<const char*>(dns.data() + cursor), length);
        cursor += length;
    }
    const auto query_type = u16(dns, cursor);
    if (labels.empty() || !query_type) { ++parse_errors_; return {}; }
    std::string query;
    for (const auto& label : labels) { if (!query.empty()) query += '.'; query += label; }
    const std::map<int, std::string> types{{1, "A"}, {5, "CNAME"}, {12, "PTR"}, {28, "AAAA"}};
    const auto found = types.find(*query_type);
    return {{uuid_string(), "DNS_QUERY", utc_now(), {
        {"query", query}, {"recordType", found == types.end() ? std::to_string(*query_type) : found->second}
    }}};
}

std::vector<Event> PacketParser::parse_tcp(std::span<const std::uint8_t> packet, std::size_t offset) {
    if (packet.size() < offset + 20) { ++parse_errors_; return {}; }
    const std::size_t tcp_header = static_cast<std::size_t>((packet[offset + 12] >> 4) & 0x0f) * 4;
    if (tcp_header < 20 || packet.size() <= offset + tcp_header) return {};
    const auto payload = packet.subspan(offset + tcp_header);
    const std::string text(reinterpret_cast<const char*>(payload.data()), std::min<std::size_t>(payload.size(), 16384));
    const auto line_end = text.find("\r\n");
    const std::string first = text.substr(0, line_end);
    const std::set<std::string> methods{"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"};
    const auto space = first.find(' ');
    if (space != std::string::npos && methods.contains(first.substr(0, space))) {
        const auto next = first.find(' ', space + 1);
        std::map<std::string, JsonValue> result{
            {"l7Protocol", std::string("HTTP")}, {"httpMethod", first.substr(0, space)},
            {"url", sanitize_url(first.substr(space + 1, next - space - 1))}
        };
        std::istringstream lines(text);
        std::string line;
        while (std::getline(lines, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.rfind("Host:", 0) == 0) result["httpHost"] = line.substr(5 + (line.size() > 5 && line[5] == ' '));
            else if (line.rfind("User-Agent:", 0) == 0) result["httpUserAgent"] = line.substr(11 + (line.size() > 11 && line[11] == ' '));
        }
        return {{uuid_string(), "L7_EVENT", utc_now(), std::move(result)}};
    }
    if (payload.size() < 9 || payload[0] != 22 || payload[5] != 1) return {};
    std::size_t cursor = 9;
    if (cursor + 34 > payload.size()) { ++parse_errors_; return {}; }
    const auto version = u16(payload, cursor).value_or(0x0303);
    cursor += 34;
    if (cursor >= payload.size()) return {};
    cursor += 1 + payload[cursor];
    const auto cipher_length = u16(payload, cursor); if (!cipher_length) return {};
    cursor += 2 + *cipher_length; if (cursor >= payload.size()) return {};
    cursor += 1 + payload[cursor];
    const auto extension_length = u16(payload, cursor); if (!extension_length) return {};
    cursor += 2;
    const auto end = std::min(payload.size(), cursor + *extension_length);
    std::optional<std::string> sni;
    while (cursor + 4 <= end) {
        const auto type = u16(payload, cursor), length = u16(payload, cursor + 2); cursor += 4;
        if (!type || !length || cursor + *length > end) { ++parse_errors_; break; }
        if (*type == 0 && *length >= 5) {
            const auto name_length = u16(payload, cursor + 3);
            if (name_length && cursor + 5 + *name_length <= end) {
                sni = std::string(reinterpret_cast<const char*>(payload.data() + cursor + 5), *name_length);
            }
        }
        cursor += *length;
    }
    std::map<std::string, JsonValue> result{{"l7Protocol", std::string("TLS")}, {"tlsVersion", tls_version(version)}};
    if (sni) result["tlsSni"] = *sni;
    return {{uuid_string(), "L7_EVENT", utc_now(), std::move(result)}};
}

}  // namespace edr
