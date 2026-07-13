import Foundation

private extension Data {
    func u16(_ offset: Int) -> Int? {
        guard offset >= 0, offset + 1 < count else { return nil }
        return (Int(self[offset]) << 8) | Int(self[offset + 1])
    }

    func u32(_ offset: Int, littleEndian: Bool) -> Int? {
        guard offset >= 0, offset + 3 < count else { return nil }
        let bytes = (0..<4).map { Int(self[offset + $0]) }
        return littleEndian
            ? bytes[0] | (bytes[1] << 8) | (bytes[2] << 16) | (bytes[3] << 24)
            : (bytes[0] << 24) | (bytes[1] << 16) | (bytes[2] << 8) | bytes[3]
    }
}

public final class PacketStreamParser: @unchecked Sendable {
    private var buffer = Data()
    private var headerParsed = false
    private var littleEndian = true
    public private(set) var parseErrorCount = 0

    public init() {}

    public func append(_ data: Data) -> [TelemetryEvent] {
        buffer.append(data)
        var events: [TelemetryEvent] = []
        if !headerParsed {
            guard buffer.count >= 24 else { return [] }
            let magic = Array(buffer.prefix(4))
            if magic == [0xd4, 0xc3, 0xb2, 0xa1] { littleEndian = true }
            else if magic == [0xa1, 0xb2, 0xc3, 0xd4] { littleEndian = false }
            else { parseErrorCount += 1; buffer.removeAll(); return [] }
            buffer.removeFirst(24)
            headerParsed = true
        }
        while buffer.count >= 16 {
            guard let includedLength = buffer.u32(8, littleEndian: littleEndian), includedLength >= 0, includedLength <= 1_048_576 else {
                parseErrorCount += 1; buffer.removeAll(); break
            }
            guard buffer.count >= 16 + includedLength else { break }
            let packet = Data(buffer[16..<(16 + includedLength)])
            buffer.removeFirst(16 + includedLength)
            events.append(contentsOf: parseEthernet(packet))
        }
        return events
    }

    public func parseEthernet(_ packet: Data) -> [TelemetryEvent] {
        guard packet.count >= 34, packet.u16(12) == 0x0800 else { return [] }
        let ipOffset = 14
        let headerLength = Int(packet[ipOffset] & 0x0f) * 4
        guard headerLength >= 20, packet.count >= ipOffset + headerLength else { parseErrorCount += 1; return [] }
        let protocolNumber = packet[ipOffset + 9]
        let transportOffset = ipOffset + headerLength
        if protocolNumber == 17 { return parseUDP(packet, offset: transportOffset) }
        if protocolNumber == 6 { return parseTCP(packet, offset: transportOffset) }
        return []
    }

    private func parseUDP(_ packet: Data, offset: Int) -> [TelemetryEvent] {
        guard packet.count >= offset + 8, let sourcePort = packet.u16(offset), let destinationPort = packet.u16(offset + 2) else {
            parseErrorCount += 1; return []
        }
        guard sourcePort == 53 || destinationPort == 53 else { return [] }
        let dns = Data(packet[(offset + 8)...])
        guard dns.count >= 12 else { parseErrorCount += 1; return [] }
        var cursor = 12
        var labels: [String] = []
        while cursor < dns.count {
            let length = Int(dns[cursor]); cursor += 1
            if length == 0 { break }
            guard length <= 63, cursor + length <= dns.count else { parseErrorCount += 1; return [] }
            labels.append(String(decoding: dns[cursor..<(cursor + length)], as: UTF8.self))
            cursor += length
        }
        guard !labels.isEmpty, let queryType = dns.u16(cursor) else { parseErrorCount += 1; return [] }
        let recordType = [1: "A", 2: "NS", 5: "CNAME", 12: "PTR", 15: "MX", 16: "TXT", 28: "AAAA"][queryType] ?? String(queryType)
        let responseCode = Int(dns[3] & 0x0f)
        var payload: [String: JSONValue] = ["query": .string(labels.joined(separator: ".")), "recordType": .string(recordType)]
        if dns[2] & 0x80 != 0 { payload["responseCode"] = .string(responseCode == 0 ? "NOERROR" : String(responseCode)) }
        return [TelemetryEvent(eventType: "DNS_QUERY", payload: payload)]
    }

    private func parseTCP(_ packet: Data, offset: Int) -> [TelemetryEvent] {
        guard packet.count >= offset + 20 else { parseErrorCount += 1; return [] }
        let headerLength = Int((packet[offset + 12] >> 4) & 0x0f) * 4
        guard headerLength >= 20, packet.count > offset + headerLength else { return [] }
        let payload = Data(packet[(offset + headerLength)...])
        if let http = parseHTTP(payload) { return [http] }
        if let tls = parseTLSClientHello(payload) { return [tls] }
        return []
    }

    private func parseHTTP(_ payload: Data) -> TelemetryEvent? {
        guard let text = String(data: payload.prefix(16_384), encoding: .utf8) else { return nil }
        let lines = text.components(separatedBy: "\r\n")
        guard let first = lines.first else { return nil }
        var result: [String: JSONValue] = ["l7Protocol": .string("HTTP")]
        if first.hasPrefix("HTTP/") {
            let fields = first.split(separator: " ")
            if fields.count >= 2, let status = Int(fields[1]) { result["httpStatusCode"] = .integer(status) }
        } else {
            let fields = first.split(separator: " ")
            let methods = Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
            guard fields.count >= 2, methods.contains(String(fields[0])) else { return nil }
            result["httpMethod"] = .string(String(fields[0]))
            result["url"] = .string(sanitizeURL(String(fields[1])))
        }
        for line in lines.dropFirst() {
            let lower = line.lowercased()
            if lower.hasPrefix("host:") { result["httpHost"] = .string(line.dropFirst(5).trimmingCharacters(in: .whitespaces)) }
            else if lower.hasPrefix("user-agent:") { result["httpUserAgent"] = .string(line.dropFirst(11).trimmingCharacters(in: .whitespaces)) }
        }
        return TelemetryEvent(eventType: "L7_EVENT", payload: result)
    }

    private func parseTLSClientHello(_ payload: Data) -> TelemetryEvent? {
        guard payload.count >= 9, payload[0] == 22, payload[5] == 1 else { return nil }
        var cursor = 9
        guard cursor + 34 <= payload.count else { parseErrorCount += 1; return nil }
        let legacyVersion = payload.u16(cursor) ?? 0x0303
        cursor += 34
        guard cursor < payload.count else { return nil }
        let sessionLength = Int(payload[cursor]); cursor += 1 + sessionLength
        guard let cipherLength = payload.u16(cursor) else { return nil }
        cursor += 2 + cipherLength
        guard cursor < payload.count else { return nil }
        let compressionLength = Int(payload[cursor]); cursor += 1 + compressionLength
        guard let extensionsLength = payload.u16(cursor) else { return nil }
        cursor += 2
        let extensionsEnd = min(payload.count, cursor + extensionsLength)
        var sni: String?
        while cursor + 4 <= extensionsEnd {
            guard let type = payload.u16(cursor), let length = payload.u16(cursor + 2) else { break }
            cursor += 4
            guard cursor + length <= extensionsEnd else { parseErrorCount += 1; break }
            if type == 0, length >= 5, let nameLength = payload.u16(cursor + 3), cursor + 5 + nameLength <= extensionsEnd {
                sni = String(decoding: payload[(cursor + 5)..<(cursor + 5 + nameLength)], as: UTF8.self)
            }
            cursor += length
        }
        var result: [String: JSONValue] = ["l7Protocol": .string("TLS"), "tlsVersion": .string(tlsVersion(legacyVersion))]
        if let sni, !sni.isEmpty { result["tlsSni"] = .string(sni) }
        return TelemetryEvent(eventType: "L7_EVENT", payload: result)
    }

    private func sanitizeURL(_ value: String) -> String {
        String(value.prefix { $0 != "?" && $0 != "#" })
    }

    private func tlsVersion(_ value: Int) -> String {
        switch value { case 0x0301: "TLS1.0"; case 0x0302: "TLS1.1"; case 0x0303: "TLS1.2"; case 0x0304: "TLS1.3"; default: String(format: "0x%04x", value) }
    }
}

public struct PacketCollection: Sendable {
    public let events: [TelemetryEvent]
    public let health: [SensorSnapshot]
}

public enum TcpdumpCollector {
    public static let executable = "/usr/sbin/tcpdump"

    public static func collect(interface: String, seconds: TimeInterval) -> PacketCollection {
        let process = Process(), output = Pipe(), error = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = ["-i", interface, "-U", "-n", "-s", "0", "-w", "-"]
        process.standardOutput = output
        process.standardError = error
        do { try process.run() } catch { return degraded(parseErrors: 0) }
        Thread.sleep(forTimeInterval: max(0.2, seconds))
        if process.isRunning { process.interrupt() }
        let bytes = output.fileHandleForReading.readDataToEndOfFile()
        let diagnostic = String(decoding: error.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        process.waitUntilExit()
        let denied = diagnostic.localizedCaseInsensitiveContains("permission denied") || diagnostic.localizedCaseInsensitiveContains("BIOCSETIF")
        guard !denied, process.terminationStatus == 0 || !bytes.isEmpty else { return degraded(parseErrors: 0) }
        let parser = PacketStreamParser()
        let events = parser.append(bytes)
        let drops = packetDrops(diagnostic)
        return PacketCollection(events: events, health: [
            SensorSnapshot(sensor: "PACKET_METADATA", status: "HEALTHY", provider: "TCPDUMP", packetDropCount: drops),
            SensorSnapshot(sensor: "L7", status: "HEALTHY", parseErrorCount: parser.parseErrorCount),
        ])
    }

    private static func degraded(parseErrors: Int) -> PacketCollection {
        PacketCollection(events: [], health: [
            SensorSnapshot(sensor: "PACKET_METADATA", status: "DEGRADED", provider: "TCPDUMP", packetDropCount: 0),
            SensorSnapshot(sensor: "L7", status: "DEGRADED", parseErrorCount: parseErrors),
        ])
    }

    private static func packetDrops(_ diagnostic: String) -> Int {
        let expression = try? NSRegularExpression(pattern: "([0-9]+) packets dropped by kernel")
        let range = NSRange(diagnostic.startIndex..., in: diagnostic)
        guard let match = expression?.firstMatch(in: diagnostic, range: range),
              let valueRange = Range(match.range(at: 1), in: diagnostic) else { return 0 }
        return Int(diagnostic[valueRange]) ?? 0
    }
}
