import Darwin
import Foundation

public struct AgentConfiguration: Codable, Sendable {
    public let agentId: String?
    public let collectorBaseUrl: String
    public let certificatePath: String
    public let privateKeyPath: String
    public let caCertificatePath: String
    public let stateDirectory: String
    public let watchDirectory: String
    public let captureInterface: String
    public let queueMaxEvents: Int
    public let retryBaseSeconds: Int
    public let retryMaxSeconds: Int
    public let logLevel: String

    public init(
        agentId: String?, collectorBaseUrl: String, certificatePath: String, privateKeyPath: String,
        caCertificatePath: String, stateDirectory: String, watchDirectory: String, captureInterface: String,
        queueMaxEvents: Int = 5000, retryBaseSeconds: Int = 1, retryMaxSeconds: Int = 60, logLevel: String = "INFO"
    ) {
        self.agentId = agentId
        self.collectorBaseUrl = collectorBaseUrl
        self.certificatePath = certificatePath
        self.privateKeyPath = privateKeyPath
        self.caCertificatePath = caCertificatePath
        self.stateDirectory = stateDirectory
        self.watchDirectory = watchDirectory
        self.captureInterface = captureInterface
        self.queueMaxEvents = queueMaxEvents
        self.retryBaseSeconds = retryBaseSeconds
        self.retryMaxSeconds = retryMaxSeconds
        self.logLevel = logLevel
    }

    public static func load(path: String) throws -> AgentConfiguration {
        let effectiveUserID = UInt32(geteuid())
        try PrivilegedFileSecurity.validateConfigurationFile(path: path, effectiveUserID: effectiveUserID)
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let configuration = try JSONDecoder().decode(AgentConfiguration.self, from: data)
        guard configuration.collectorBaseUrl.hasPrefix("https://") else {
            throw AgentError.invalidConfiguration("collectorBaseUrl must use https")
        }
        for (label, value) in [
            ("certificatePath", configuration.certificatePath),
            ("privateKeyPath", configuration.privateKeyPath),
            ("caCertificatePath", configuration.caCertificatePath),
            ("stateDirectory", configuration.stateDirectory),
            ("watchDirectory", configuration.watchDirectory),
        ] where !NSString(string: value).isAbsolutePath {
            throw AgentError.invalidConfiguration("\(label) must be an absolute path")
        }
        guard configuration.queueMaxEvents > 0, configuration.retryBaseSeconds > 0,
              configuration.retryMaxSeconds >= configuration.retryBaseSeconds else {
            throw AgentError.invalidConfiguration("queue and retry limits must be positive")
        }
        try PrivilegedFileSecurity.validateRuntimeFiles(
            configuration: configuration,
            effectiveUserID: effectiveUserID
        )
        return configuration
    }
}

enum PrivilegedFileSecurity {
    static func validateConfigurationFile(path: String, effectiveUserID: UInt32) throws {
        guard effectiveUserID == 0 else { return }
        try validateRegularFile(
            path: path,
            label: "configuration file",
            privatePermissions: true
        )
    }

    static func validateRuntimeFiles(configuration: AgentConfiguration, effectiveUserID: UInt32) throws {
        guard effectiveUserID == 0 else { return }
        try validateRegularFile(
            path: configuration.privateKeyPath,
            label: "private key",
            privatePermissions: true
        )
        try validateRegularFile(
            path: configuration.certificatePath,
            label: "client certificate",
            privatePermissions: false
        )
        try validateRegularFile(
            path: configuration.caCertificatePath,
            label: "CA certificate",
            privatePermissions: false
        )
        try validateDirectory(path: configuration.stateDirectory, label: "state directory")
    }

    static func validateRegularFile(
        path: String,
        label: String,
        privatePermissions: Bool,
        attributes: [FileAttributeKey: Any]? = nil,
        parentAttributes: [FileAttributeKey: Any]? = nil
    ) throws {
        let values = try attributes ?? FileManager.default.attributesOfItem(atPath: path)
        guard values[.type] as? FileAttributeType == .typeRegular else {
            throw AgentError.invalidConfiguration("\(label) must be a regular file")
        }
        try validateRootOwnership(values, label: label)
        let permissions = try permissions(from: values, label: label)
        let forbiddenMask: UInt16 = privatePermissions ? 0o077 : 0o022
        guard permissions & forbiddenMask == 0 else {
            let requirement = privatePermissions ? "root-only" : "not group/world-writable"
            throw AgentError.invalidConfiguration("\(label) permissions must be \(requirement)")
        }
        try validateDirectory(
            path: URL(fileURLWithPath: path).deletingLastPathComponent().path,
            label: "\(label) parent directory",
            requirePrivatePermissions: false,
            attributes: parentAttributes
        )
    }

    static func validateDirectory(
        path: String,
        label: String,
        requirePrivatePermissions: Bool = true,
        attributes: [FileAttributeKey: Any]? = nil
    ) throws {
        let values = try attributes ?? FileManager.default.attributesOfItem(atPath: path)
        guard values[.type] as? FileAttributeType == .typeDirectory else {
            throw AgentError.invalidConfiguration("\(label) must be a directory")
        }
        try validateRootOwnership(values, label: label)
        let permissions = try permissions(from: values, label: label)
        let forbiddenMask: UInt16 = requirePrivatePermissions ? 0o077 : 0o022
        guard permissions & forbiddenMask == 0 else {
            throw AgentError.invalidConfiguration("\(label) has unsafe permissions")
        }
    }

    private static func validateRootOwnership(_ attributes: [FileAttributeKey: Any], label: String) throws {
        guard let owner = attributes[.ownerAccountID] as? NSNumber, owner.uint32Value == 0 else {
            throw AgentError.invalidConfiguration("\(label) must be owned by root")
        }
    }

    private static func permissions(
        from attributes: [FileAttributeKey: Any],
        label: String
    ) throws -> UInt16 {
        guard let value = attributes[.posixPermissions] as? NSNumber else {
            throw AgentError.invalidConfiguration("\(label) permissions are unavailable")
        }
        return value.uint16Value
    }
}

public enum AgentIdentity {
    public static func resolve(configuration: AgentConfiguration) throws -> String {
        if let configured = configuration.agentId {
            try validate(configured)
            return configured
        }
        let directory = URL(fileURLWithPath: configuration.stateDirectory, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let identityFile = directory.appendingPathComponent("agent-id")
        if let existing = try? String(contentsOf: identityFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines), !existing.isEmpty {
            try validate(existing)
            return existing
        }
        let generated = "agent-mac-\(UUID().uuidString.lowercased())"
        try generated.write(to: identityFile, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: identityFile.path)
        return generated
    }

    public static func validate(_ value: String) throws {
        let expression = try NSRegularExpression(pattern: "^[a-z0-9][a-z0-9._-]{0,63}$")
        let range = NSRange(value.startIndex..., in: value)
        guard expression.firstMatch(in: value, range: range)?.range == range else {
            throw AgentError.invalidConfiguration("agentId does not match the Collector contract")
        }
    }
}

public struct SafeLogger: Sendable {
    public init() {}

    public func info(_ message: String) { print("level=INFO \(sanitize(message))") }
    public func error(_ message: String) { fputs("level=ERROR \(sanitize(message))\n", stderr) }

    public func sanitize(_ message: String) -> String {
        var result = message
        for marker in ["authorization", "privateKey", "private_key", "token", "password"] {
            let pattern = "(?i)\\b\(marker)\\b\\s*[:=]\\s*[^\\s,]+"
            result = result.replacingOccurrences(of: pattern, with: "\(marker)=<redacted>", options: .regularExpression)
        }
        return result
    }
}
