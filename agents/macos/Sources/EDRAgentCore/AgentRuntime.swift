import Foundation

public struct TransmissionMetrics: Equatable, Sendable {
    public var accepted = 0
    public var rejected = 0
    public var failedAttempts = 0
}

public final class AgentSender: @unchecked Sendable {
    private let agentId: String
    private let buffer: EventBuffer
    private let client: CollectorClient
    private let retryBase: Int
    private let retryCap: Int

    public init(agentId: String, buffer: EventBuffer, client: CollectorClient, retryBase: Int, retryCap: Int) {
        self.agentId = agentId
        self.buffer = buffer
        self.client = client
        self.retryBase = retryBase
        self.retryCap = retryCap
    }

    public func sendAvailable(maxBatches: Int = 50) -> TransmissionMetrics {
        var metrics = TransmissionMetrics()
        for _ in 0..<maxBatches {
            do {
                let rows = try buffer.pending(limit: MicroBatcher.maxEvents)
                guard let selection = try MicroBatcher.select(agentId: agentId, rows: rows) else { break }
                try buffer.assign(batchId: selection.batch.batchId, rowIds: selection.rows.map(\.rowId))
                let result = try client.telemetry(body: selection.body)
                try buffer.apply(result: result) { exponentialBackoff(attempt: $0, base: self.retryBase, cap: self.retryCap) }
                metrics.accepted += result.acceptedEventIds.count
                metrics.rejected += result.rejectedEvents.count
                if result.acceptedEventIds.isEmpty { break }
            } catch {
                let rows = (try? buffer.pending(limit: MicroBatcher.maxEvents)) ?? []
                try? buffer.markTransportFailure(rowIds: rows.map(\.rowId), error: errorCode(error)) {
                    exponentialBackoff(attempt: $0, base: self.retryBase, cap: self.retryCap)
                }
                metrics.failedAttempts += 1
                break
            }
        }
        return metrics
    }

    private func errorCode(_ error: Error) -> String {
        if case let AgentError.collector(_, code, _) = error { return code }
        return "NETWORK_OR_ENVELOPE_FAILURE"
    }
}

public struct AgentRunReport: Sendable {
    public let collected: Int
    public let transmission: TransmissionMetrics
    public let buffer: BufferMetrics
    public let sensorHealth: [SensorSnapshot]
}

public final class AgentRuntime: @unchecked Sendable {
    public static let version = "0.1.0"
    public static let buildId = "macos-arm64-20260712.1"

    private let configuration: AgentConfiguration
    private let agentId: String
    private let buffer: EventBuffer
    private let client: CollectorClient
    private let logger: SafeLogger

    public init(configuration: AgentConfiguration, logger: SafeLogger = SafeLogger()) throws {
        self.configuration = configuration
        self.agentId = try AgentIdentity.resolve(configuration: configuration)
        self.logger = logger
        let state = URL(fileURLWithPath: configuration.stateDirectory, isDirectory: true)
        try FileManager.default.createDirectory(at: state, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        self.buffer = try EventBuffer(path: state.appendingPathComponent("events.sqlite3").path, maxEvents: configuration.queueMaxEvents)
        try self.buffer.makeRetryableNow()
        self.client = CollectorClient(configuration: configuration)
    }

    public func runOnce(collectionSeconds: TimeInterval, sendHeartbeat: Bool = true) -> AgentRunReport {
        let process = ProcessCollector.collect()
        let network = NetworkCollector.collect()
        let file = FileEventCollector(watchPath: configuration.watchDirectory).collect(seconds: collectionSeconds)
        let packet = TcpdumpCollector.collect(interface: configuration.captureInterface, seconds: min(2, collectionSeconds))
        let health = [process.health, network.health, file.health] + packet.health
        let packetHealthy = packet.health.first?.status == "HEALTHY"
        var capabilities = ["PROCESS_EXECUTION", "NETWORK_CONNECTION", "FILE_EVENT"]
        if packetHealthy { capabilities += ["DNS_QUERY", "L7_EVENT", "PACKET_METADATA_V1"] }
        let events = process.events + network.events + file.events + packet.events

        var endpointId: Int64?
        do {
            let registration = try client.register(RegisterRequest(
                agentId: agentId,
                hostname: ProcessInfo.processInfo.hostName,
                osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                agentVersion: Self.version,
                agentBuildId: Self.buildId,
                agentArch: architecture,
                capabilityCodes: capabilities
            ))
            endpointId = registration.endpointId
            try buffer.setEndpointId(registration.endpointId)
            logger.info("registration status=success endpointId=\(registration.endpointId)")
        } catch {
            logCollectorError(error, operation: "registration")
        }

        var collected = 0
        for event in events {
            do { try buffer.enqueue(event, endpointId: endpointId); collected += 1 }
            catch AgentError.queueFull { logger.error("buffer status=full limit=\(configuration.queueMaxEvents)"); break }
            catch { logger.error("buffer status=enqueue_failed") }
        }

        if sendHeartbeat { do {
            let depth = try buffer.metrics().pending + buffer.metrics().failed
            _ = try client.heartbeat(HeartbeatRequest(
                agentId: agentId,
                agentVersion: Self.version,
                agentBuildId: Self.buildId,
                agentArch: architecture,
                capabilityCodes: capabilities,
                bufferDepth: depth,
                sensorHealth: health,
                sentAt: utcNow()
            ))
            logger.info("heartbeat status=success bufferDepth=\(depth)")
        } catch {
            logCollectorError(error, operation: "heartbeat")
        } }

        let sender = AgentSender(
            agentId: agentId, buffer: buffer, client: client,
            retryBase: configuration.retryBaseSeconds, retryCap: configuration.retryMaxSeconds
        )
        let transmission = sender.sendAvailable()
        let current = (try? buffer.metrics()) ?? BufferMetrics(pending: 0, failed: 0, retryCount: 0)
        return AgentRunReport(collected: collected, transmission: transmission, buffer: current, sensorHealth: health)
    }

    public func runContinuously() -> Never {
        var nextHeartbeat = Date()
        while true {
            let heartbeatDue = Date() >= nextHeartbeat
            let report = runOnce(collectionSeconds: MicroBatcher.flushIntervalSeconds, sendHeartbeat: heartbeatDue)
            logger.info("cycle collected=\(report.collected) accepted=\(report.transmission.accepted) pending=\(report.buffer.pending) failed=\(report.buffer.failed)")
            if heartbeatDue {
                nextHeartbeat = Date().addingTimeInterval(30 * Double.random(in: 0.9...1.1))
            }
            Thread.sleep(forTimeInterval: MicroBatcher.flushIntervalSeconds)
        }
    }

    private var architecture: String {
        #if arch(arm64)
        "ARM64"
        #else
        "X64"
        #endif
    }

    private func logCollectorError(_ error: Error, operation: String) {
        if case let AgentError.collector(status, code, _) = error {
            logger.error("\(operation) status=failed httpStatus=\(status) code=\(code)")
        } else {
            logger.error("\(operation) status=failed code=NETWORK_OR_TLS_FAILURE")
        }
    }
}
