import Foundation

public enum AgentError: Error, Equatable {
    case invalidConfiguration(String)
    case queueFull
    case eventTooLarge
    case transport(String)
    case collector(status: Int, code: String, retryable: Bool)
}

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case integer(Int)
    case boolean(Bool)
    case strings([String])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(Int.self) { self = .integer(value); return }
        if let value = try? container.decode(Bool.self) { self = .boolean(value); return }
        if let value = try? container.decode(String.self) { self = .string(value); return }
        self = .strings(try container.decode([String].self))
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .string(value): try container.encode(value)
        case let .integer(value): try container.encode(value)
        case let .boolean(value): try container.encode(value)
        case let .strings(value): try container.encode(value)
        }
    }
}

public struct TelemetryEvent: Codable, Equatable, Sendable {
    public let eventId: String
    public let eventType: String
    public let occurredAt: String
    public let payload: [String: JSONValue]

    public init(eventId: String = UUID().uuidString.lowercased(), eventType: String, occurredAt: String = utcNow(), payload: [String: JSONValue]) {
        self.eventId = eventId
        self.eventType = eventType
        self.occurredAt = occurredAt
        self.payload = payload
    }
}

public struct TelemetryBatch: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let batchId: String
    public let agentId: String
    public let sentAt: String
    public let events: [TelemetryEvent]

    public init(batchId: String = UUID().uuidString.lowercased(), agentId: String, sentAt: String = utcNow(), events: [TelemetryEvent]) {
        self.schemaVersion = 1
        self.batchId = batchId
        self.agentId = agentId
        self.sentAt = sentAt
        self.events = events
    }
}

public struct SensorSnapshot: Codable, Equatable, Sendable {
    public let sensor: String
    public let status: String
    public let provider: String?
    public let packetDropCount: Int?
    public let parseErrorCount: Int?

    public init(sensor: String, status: String, provider: String? = nil, packetDropCount: Int? = nil, parseErrorCount: Int? = nil) {
        self.sensor = sensor
        self.status = status
        self.provider = provider
        self.packetDropCount = packetDropCount
        self.parseErrorCount = parseErrorCount
    }

    enum CodingKeys: String, CodingKey { case sensor, status, provider, packetDropCount, parseErrorCount }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(sensor, forKey: .sensor)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(provider, forKey: .provider)
        try container.encodeIfPresent(packetDropCount, forKey: .packetDropCount)
        try container.encodeIfPresent(parseErrorCount, forKey: .parseErrorCount)
    }
}

public struct RegisterRequest: Codable, Sendable {
    public let agentId: String
    public let hostname: String
    public let osType: String
    public let osVersion: String
    public let agentVersion: String
    public let agentBuildId: String
    public let agentArch: String
    public let capabilityCodes: [String]

    public init(agentId: String, hostname: String, osVersion: String, agentVersion: String, agentBuildId: String, agentArch: String, capabilityCodes: [String]) {
        self.agentId = agentId
        self.hostname = hostname
        self.osType = "MACOS"
        self.osVersion = osVersion
        self.agentVersion = agentVersion
        self.agentBuildId = agentBuildId
        self.agentArch = agentArch
        self.capabilityCodes = capabilityCodes
    }
}

public struct HeartbeatRequest: Codable, Sendable {
    public let agentId: String
    public let agentVersion: String
    public let agentBuildId: String
    public let agentArch: String
    public let capabilityCodes: [String]
    public let bufferDepth: Int
    public let sensorHealth: [SensorSnapshot]
    public let sentAt: String
}

public struct RejectedEvent: Codable, Equatable, Sendable {
    public let eventId: String
    public let code: String
    public let message: String
    public let retryable: Bool
}

public struct TelemetryResult: Codable, Sendable {
    public let batchId: String
    public let acceptedEventIds: [String]
    public let rejectedEvents: [RejectedEvent]
}

public struct RegisterResult: Codable, Sendable {
    public let endpointId: Int64
    public let agentId: String
    public let status: String
    public let heartbeatIntervalSeconds: Int
    public let registeredAt: String
}

public struct HeartbeatResult: Codable, Sendable {
    public let serverTime: String
    public let nextHeartbeatSeconds: Int
    public let endpointStatus: String
}

public struct SuccessEnvelope<T: Codable & Sendable>: Codable, Sendable { public let data: T }

public struct ErrorData: Codable, Sendable {
    public let code: String
    public let message: String
    public let retryable: Bool
}

public struct ErrorEnvelope: Codable, Sendable { public let error: ErrorData }

public func utcNow(_ date: Date = Date()) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    return formatter.string(from: date)
}

public func contractEncoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return encoder
}
