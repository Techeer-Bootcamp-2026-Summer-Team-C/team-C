import CoreServices
import CryptoKit
import Foundation

public struct CollectorSnapshot: Sendable {
    public let events: [TelemetryEvent]
    public let health: SensorSnapshot
}

private func runCommand(_ executable: String, _ arguments: [String]) throws -> String {
    let process = Process(), output = Pipe()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    process.standardOutput = output
    process.standardError = Pipe()
    try process.run()
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { throw AgentError.transport("collector_process_failed") }
    return String(decoding: data, as: UTF8.self)
}

func sanitizeCommandLine(_ value: String) -> String {
    let pattern = #"((?:--?|/)(?:password|passwd|token|api[-_]?key|secret|client[-_]?secret|access[-_]?token|encodedcommand|enc)(?:[=:]|\s+))(?:"[^"]*"|'[^']*'|\S+)"#
    guard let expression = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
        return value
    }
    return expression.stringByReplacingMatches(
        in: value,
        range: NSRange(value.startIndex..., in: value),
        withTemplate: "$1<redacted>"
    )
}

public enum ProcessCollector {
    public static func collect() -> CollectorSnapshot {
        do {
            let pathOutput = try runCommand("/bin/ps", ["-axo", "pid=,ppid=,comm="])
            let commandLines: [Int: String]
            if let commandOutput = try? runCommand("/bin/ps", ["-axo", "pid=,command="]) {
                commandLines = Dictionary(
                    uniqueKeysWithValues: commandOutput.split(separator: "\n").compactMap(parseCommand)
                )
            } else {
                commandLines = [:]
            }
            let events = pathOutput.split(separator: "\n").compactMap { parse($0, commandLines: commandLines) }
            return CollectorSnapshot(events: events, health: SensorSnapshot(sensor: "PROCESS", status: "HEALTHY"))
        } catch {
            return CollectorSnapshot(events: [], health: SensorSnapshot(sensor: "PROCESS", status: "DEGRADED"))
        }
    }

    public static func parse(_ line: Substring, commandLines: [Int: String]) -> TelemetryEvent? {
        let fields = line.split(maxSplits: 2, whereSeparator: \.isWhitespace)
        guard fields.count == 3, let pid = Int(fields[0]), let ppid = Int(fields[1]) else { return nil }
        let processPath = String(fields[2])
        var payload: [String: JSONValue] = [
            "processName": .string(URL(fileURLWithPath: processPath).lastPathComponent),
            "pid": .integer(pid),
            "ppid": .integer(ppid),
            "processPath": .string(processPath),
        ]
        if let commandLine = commandLines[pid], !commandLine.isEmpty {
            payload["commandLine"] = .string(sanitizeCommandLine(commandLine))
        }
        return TelemetryEvent(eventType: "PROCESS_EXECUTION", payload: payload)
    }

    private static func parseCommand(_ line: Substring) -> (Int, String)? {
        let fields = line.split(maxSplits: 1, whereSeparator: \.isWhitespace)
        guard fields.count == 2, let pid = Int(fields[0]) else { return nil }
        return (pid, String(fields[1]))
    }
}

public enum NetworkCollector {
    public static func collect() -> CollectorSnapshot {
        do {
            let output = try runCommand("/usr/sbin/lsof", ["-nP", "-iTCP", "-iUDP"])
            let events = output.split(separator: "\n").dropFirst().compactMap(parse)
            return CollectorSnapshot(events: events, health: SensorSnapshot(sensor: "NETWORK", status: "HEALTHY"))
        } catch {
            return CollectorSnapshot(events: [], health: SensorSnapshot(sensor: "NETWORK", status: "DEGRADED"))
        }
    }

    public static func parse(_ line: Substring) -> TelemetryEvent? {
        let fields = line.split(whereSeparator: \.isWhitespace)
        guard fields.count >= 9, let pid = Int(fields[1]) else { return nil }
        let process = String(fields[0])
        let protocolName = String(fields[7]).uppercased()
        let connection = fields[8...].map(String.init).joined(separator: " ").components(separatedBy: " ").first ?? ""
        let remote = connection.components(separatedBy: "->").last ?? connection
        let clean = remote.components(separatedBy: "(").first ?? remote
        guard let colon = clean.lastIndex(of: ":"), let port = Int(clean[clean.index(after: colon)...]), port >= 0, port <= 65535 else { return nil }
        var address = String(clean[..<colon])
        address = address.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        guard !address.isEmpty, address != "*" else { return nil }
        return TelemetryEvent(eventType: "NETWORK_CONNECTION", payload: [
            "protocol": .string(protocolName.hasPrefix("UDP") ? "UDP" : "TCP"),
            "remoteIp": .string(address),
            "remotePort": .integer(port),
            "processName": .string(process),
            "pid": .integer(pid),
        ])
    }
}

public final class FileEventCollector: @unchecked Sendable {
    private let watchPath: String
    private let lock = NSLock()
    private var events: [TelemetryEvent] = []
    private var parseErrors = 0

    public init(watchPath: String) { self.watchPath = watchPath }

    public func collect(seconds: TimeInterval) -> CollectorSnapshot {
        do {
            try FileManager.default.createDirectory(atPath: watchPath, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o755])
            var context = FSEventStreamContext(
                version: 0,
                info: Unmanaged.passUnretained(self).toOpaque(),
                retain: nil,
                release: nil,
                copyDescription: nil
            )
            guard let stream = FSEventStreamCreate(
                nil,
                { _, info, count, pathsPointer, flagsPointer, _ in
                    guard let info else { return }
                    let collector = Unmanaged<FileEventCollector>.fromOpaque(info).takeUnretainedValue()
                    let paths = unsafeBitCast(pathsPointer, to: CFArray.self) as? [String] ?? []
                    collector.accept(paths: paths, flags: flagsPointer, count: count)
                },
                &context,
                [watchPath] as CFArray,
                FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
                0.1,
                UInt32(kFSEventStreamCreateFlagUseCFTypes | kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagNoDefer)
            ) else {
                throw AgentError.transport("fsevents_unavailable")
            }
            let queue = DispatchQueue(label: "edr.agent.fsevents")
            FSEventStreamSetDispatchQueue(stream, queue)
            guard FSEventStreamStart(stream) else {
                FSEventStreamInvalidate(stream)
                throw AgentError.transport("fsevents_start_failed")
            }
            Thread.sleep(forTimeInterval: max(0.1, seconds))
            FSEventStreamStop(stream)
            FSEventStreamInvalidate(stream)
            lock.lock(); defer { lock.unlock() }
            return CollectorSnapshot(
                events: events,
                health: SensorSnapshot(sensor: "FILE", status: "HEALTHY", parseErrorCount: parseErrors)
            )
        } catch {
            return CollectorSnapshot(events: [], health: SensorSnapshot(sensor: "FILE", status: "DEGRADED", parseErrorCount: parseErrors + 1))
        }
    }

    private func accept(paths: [String], flags: UnsafePointer<FSEventStreamEventFlags>, count: Int) {
        lock.lock(); defer { lock.unlock() }
        for index in 0..<min(count, paths.count) {
            let action = FileEventAction(flags: flags[index]).rawValue
            var payload: [String: JSONValue] = ["filePath": .string(paths[index]), "action": .string(action)]
            if action != FileEventAction.delete.rawValue,
               let data = try? Data(contentsOf: URL(fileURLWithPath: paths[index])),
               data.count <= 32 * 1024 * 1024 {
                payload["sha256"] = .string(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined())
            }
            events.append(TelemetryEvent(eventType: "FILE_EVENT", payload: payload))
        }
    }
}

public enum FileEventAction: String, Sendable {
    case create = "CREATE"
    case delete = "DELETE"
    case modify = "MODIFY"
    case rename = "RENAME"

    init(flags: FSEventStreamEventFlags) {
        if flags & UInt32(kFSEventStreamEventFlagItemRemoved) != 0 { self = .delete }
        else if flags & UInt32(kFSEventStreamEventFlagItemRenamed) != 0 { self = .rename }
        else if flags & UInt32(kFSEventStreamEventFlagItemCreated) != 0 { self = .create }
        else { self = .modify }
    }
}
