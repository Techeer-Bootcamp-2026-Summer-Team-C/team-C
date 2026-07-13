import Foundation
import Testing

@testable import EDRAgentCore

@Test func processPathWithSpacesKeepsExecutableIdentity() throws {
    let event = try #require(
        ProcessCollector.parse(
            "42 1 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome"[...],
            commandLines: [42: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --type=renderer"]
        )
    )
    #expect(event.payload["processName"] == .string("Google Chrome"))
    #expect(event.payload["processPath"] == .string("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
}

private func ethernetIPv4(protocolNumber: UInt8, transport: [UInt8]) -> Data {
    var packet = Array(repeating: UInt8(0), count: 14 + 20)
    packet[12] = 0x08; packet[13] = 0x00
    packet[14] = 0x45
    packet[23] = protocolNumber
    packet.append(contentsOf: transport)
    return Data(packet)
}

private func dnsPacket() -> Data {
    var udp: [UInt8] = [0x30, 0x39, 0x00, 0x35, 0, 0, 0, 0]
    udp += [0x12, 0x34, 0x01, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0]
    udp += [7] + Array("example".utf8) + [3] + Array("com".utf8) + [0, 0, 1, 0, 1]
    return ethernetIPv4(protocolNumber: 17, transport: udp)
}

private func tcpPacket(payload: [UInt8]) -> Data {
    var tcp = Array(repeating: UInt8(0), count: 20)
    tcp[12] = 0x50
    tcp.append(contentsOf: payload)
    return ethernetIPv4(protocolNumber: 6, transport: tcp)
}

private func tlsClientHello(host: String) -> [UInt8] {
    let name = Array(host.utf8)
    let serverName = [UInt8(0)] + [UInt8(name.count >> 8), UInt8(name.count & 0xff)] + name
    let serverNameList = [UInt8(serverName.count >> 8), UInt8(serverName.count & 0xff)] + serverName
    let extensionData = [UInt8(0), 0, UInt8(serverNameList.count >> 8), UInt8(serverNameList.count & 0xff)] + serverNameList
    var hello: [UInt8] = [0x03, 0x03] + Array(repeating: 0, count: 32)
    hello += [0, 0, 2, 0x13, 0x01, 1, 0]
    hello += [UInt8(extensionData.count >> 8), UInt8(extensionData.count & 0xff)] + extensionData
    let handshake = [UInt8(1), 0, UInt8(hello.count >> 8), UInt8(hello.count & 0xff)] + hello
    return [22, 0x03, 0x03, UInt8(handshake.count >> 8), UInt8(handshake.count & 0xff)] + handshake
}

@Test func parsesDnsHttpAndTlsWithoutPacketBytesOrSensitiveHeaders() throws {
    let parser = PacketStreamParser()
    let dns = try #require(parser.parseEthernet(dnsPacket()).first)
    #expect(dns.eventType == "DNS_QUERY")
    #expect(dns.payload["query"] == .string("example.com"))

    let request = "GET /path?q=secret#fragment HTTP/1.1\r\nHost: example.com\r\nAuthorization: no\r\nCookie: no\r\nUser-Agent: AgentTest\r\n\r\n"
    let http = try #require(parser.parseEthernet(tcpPacket(payload: Array(request.utf8))).first)
    #expect(http.eventType == "L7_EVENT")
    #expect(http.payload["url"] == .string("/path"))
    #expect(http.payload["httpHost"] == .string("example.com"))
    #expect(http.payload["authorization"] == nil)
    #expect(http.payload["cookie"] == nil)

    let tls = try #require(parser.parseEthernet(tcpPacket(payload: tlsClientHello(host: "secure.example.com"))).first)
    #expect(tls.payload["l7Protocol"] == .string("TLS"))
    #expect(tls.payload["tlsSni"] == .string("secure.example.com"))
    #expect(tls.payload["packetBytes"] == nil)
}

@Test func processNetworkAndFileCollectorsUsePlatformSources() async throws {
    #expect(!ProcessCollector.collect().events.isEmpty)
    let network = NetworkCollector.collect()
    #expect(network.health.sensor == "NETWORK")

    let directory = URL(fileURLWithPath: "/tmp/edr-fsevents-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    Task.detached {
        try? await Task.sleep(for: .milliseconds(500))
        try? Data("metadata".utf8).write(to: directory.appendingPathComponent("observed.txt"))
    }
    let file = FileEventCollector(watchPath: directory.path).collect(seconds: 3)
    #expect(file.health.status == "HEALTHY")
    #expect(file.events.contains {
        if case let .string(path) = $0.payload["filePath"] { return URL(fileURLWithPath: path).lastPathComponent == "observed.txt" }
        return false
    })
}

@Test func unavailableTcpdumpInterfaceDegradesOnlyPacketSensors() {
    let result = TcpdumpCollector.collect(interface: "edr-no-such-interface", seconds: 0.2)
    #expect(result.events.isEmpty)
    #expect(result.health.allSatisfy { $0.status == "DEGRADED" })
    #expect(ProcessCollector.collect().health.status == "HEALTHY")
}
