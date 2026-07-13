import Foundation
import Testing

@testable import EDRAgentCore

private func event(_ index: Int, padding: Int = 0) -> TelemetryEvent {
    TelemetryEvent(
        eventId: String(format: "00000000-0000-4000-8000-%012d", index),
        eventType: "PROCESS_EXECUTION",
        occurredAt: "2026-07-12T00:00:00.000Z",
        payload: ["processName": .string("test" + String(repeating: "x", count: padding)), "pid": .integer(index)]
    )
}

private func temporaryBuffer(maxEvents: Int = 1000) throws -> EventBuffer {
    let path = FileManager.default.temporaryDirectory
        .appendingPathComponent("edr-buffer-\(UUID().uuidString)")
        .appendingPathComponent("events.sqlite3").path
    return try EventBuffer(path: path, maxEvents: maxEvents)
}

@Test func collectorContractUsesCamelCaseUtcAndUniqueIds() throws {
    let first = event(1), second = event(2)
    let batch = TelemetryBatch(agentId: "agent-mac-001", events: [first, second])
    let json = try #require(try JSONSerialization.jsonObject(with: contractEncoder().encode(batch)) as? [String: Any])
    #expect(json["schemaVersion"] as? Int == 1)
    #expect(json["agentId"] as? String == "agent-mac-001")
    #expect((json["sentAt"] as? String)?.hasSuffix("Z") == true)
    #expect(batch.batchId != first.eventId)
    #expect(Set(batch.events.map(\.eventId)).count == 2)
}

@Test func microBatchStopsAtOneHundredAndFiveMiB() throws {
    let rows = (1...101).map { BufferedEvent(rowId: Int64($0), endpointId: 1, batchId: nil, event: event($0), retryCount: 0) }
    let countSelection = try #require(try MicroBatcher.select(agentId: "agent-mac-001", rows: rows))
    #expect(countSelection.rows.count == 100)
    #expect(MicroBatcher.flushIntervalSeconds == 5)

    let largeRows = (1...2).map { BufferedEvent(rowId: Int64($0), endpointId: 1, batchId: nil, event: event($0, padding: 3 * 1024 * 1024), retryCount: 0) }
    let sizeSelection = try #require(try MicroBatcher.select(agentId: "agent-mac-001", rows: largeRows))
    #expect(sizeSelection.rows.count == 1)
    #expect(sizeSelection.body.count <= MicroBatcher.maxBodyBytes)
}

@Test func acceptedAndPartialResultsUpdatePhysicalRows() throws {
    let buffer = try temporaryBuffer()
    for index in 1...3 { try buffer.enqueue(event(index), endpointId: 1) }
    let rows = try buffer.pending()
    try buffer.assign(batchId: "00000000-0000-4000-8000-000000000099", rowIds: rows.map(\.rowId))
    try buffer.apply(
        result: TelemetryResult(
            batchId: "00000000-0000-4000-8000-000000000099",
            acceptedEventIds: [event(1).eventId],
            rejectedEvents: [
                RejectedEvent(eventId: event(2).eventId, code: "TEMPORARY", message: "retry", retryable: true),
                RejectedEvent(eventId: event(3).eventId, code: "INVALID", message: "stop", retryable: false),
            ]
        ),
        backoffSeconds: { _ in 1 }
    )
    let metrics = try buffer.metrics()
    #expect(metrics.pending == 1)
    #expect(metrics.failed == 1)
    #expect(metrics.retryCount == 2)
}

@Test func queueHasConfiguredUpperBound() throws {
    let buffer = try temporaryBuffer(maxEvents: 1)
    try buffer.enqueue(event(1))
    #expect(throws: AgentError.queueFull) { try buffer.enqueue(event(2)) }
}

private final class OfflineThenAcceptCurl: CurlExecuting, @unchecked Sendable {
    private let lock = NSLock()
    var offline = true
    var batchIds: [String] = []

    func post(url: String, body: Data, certificate: String, privateKey: String, caCertificate: String) throws -> HTTPResult {
        lock.lock(); defer { lock.unlock() }
        let batch = try JSONDecoder().decode(TelemetryBatch.self, from: body)
        batchIds.append(batch.batchId)
        if offline { throw AgentError.transport("offline") }
        let data = try JSONSerialization.data(withJSONObject: [
            "data": ["batchId": batch.batchId, "acceptedEventIds": batch.events.map(\.eventId), "rejectedEvents": []],
            "meta": ["requestId": "req_agent_test"],
        ])
        return HTTPResult(status: 200, body: data)
    }
}

private func testConfiguration() -> AgentConfiguration {
    AgentConfiguration(
        agentId: "agent-mac-001", collectorBaseUrl: "https://127.0.0.1:8443/api/v1",
        certificatePath: "/secret/agent.crt", privateKeyPath: "/secret/agent.key", caCertificatePath: "/secret/ca.crt",
        stateDirectory: "/tmp/edr-agent", watchDirectory: "/tmp/edr-watch", captureInterface: "lo0",
        queueMaxEvents: 10, retryBaseSeconds: 1, retryMaxSeconds: 4
    )
}

@Test func offlineRestartReconnectKeepsThenDeletesAcknowledgedRows() throws {
    let buffer = try temporaryBuffer()
    try buffer.enqueue(event(1))
    let curl = OfflineThenAcceptCurl()
    let sender = AgentSender(
        agentId: "agent-mac-001", buffer: buffer,
        client: CollectorClient(configuration: testConfiguration(), curl: curl), retryBase: 1, retryCap: 4
    )
    let offline = sender.sendAvailable()
    #expect(offline.failedAttempts == 1)
    #expect(try buffer.metrics().pending == 1)
    #expect(try buffer.metrics().retryCount == 1)

    curl.offline = false
    try buffer.makeRetryableNow()
    let recovered = sender.sendAvailable()
    #expect(recovered.accepted == 1)
    #expect(curl.batchIds.count == 2)
    #expect(curl.batchIds.first == curl.batchIds.last)
    #expect(try buffer.metrics().pending == 0)
    #expect(try buffer.metrics().failed == 0)
}

private struct RetiredCurl: CurlExecuting {
    func post(url: String, body: Data, certificate: String, privateKey: String, caCertificate: String) throws -> HTTPResult {
        HTTPResult(status: 403, body: Data("{\"error\":{\"code\":\"ENDPOINT_RETIRED\",\"message\":\"retired\",\"retryable\":false}}".utf8))
    }
}

@Test func retiredAndMtlsFailuresDoNotAcknowledgeRows() throws {
    let buffer = try temporaryBuffer()
    try buffer.enqueue(event(1))
    let retired = AgentSender(
        agentId: "agent-mac-001", buffer: buffer,
        client: CollectorClient(configuration: testConfiguration(), curl: RetiredCurl()), retryBase: 1, retryCap: 4
    )
    #expect(retired.sendAvailable().failedAttempts == 1)
    #expect(try buffer.metrics().pending == 1)

    try buffer.makeRetryableNow()
    let offline = OfflineThenAcceptCurl()
    let mtlsFailure = AgentSender(
        agentId: "agent-mac-001", buffer: buffer,
        client: CollectorClient(configuration: testConfiguration(), curl: offline), retryBase: 1, retryCap: 4
    )
    #expect(mtlsFailure.sendAvailable().failedAttempts == 1)
    #expect(try buffer.metrics().pending == 1)
}

@Test func logsRedactSecrets() {
    let output = SafeLogger().sanitize("authorization=Bearer-abc privateKey=/secret/key token=qwerty password=hunter2")
    #expect(!output.contains("Bearer-abc"))
    #expect(!output.contains("/secret/key"))
    #expect(!output.contains("qwerty"))
    #expect(!output.contains("hunter2"))
}
