import EDRAgentCore
import Foundation

struct Arguments {
    let config: String
    let once: Bool
    let collectionSeconds: TimeInterval

    static func parse() throws -> Arguments {
        var config: String?
        var once = false
        var seconds: TimeInterval = 5
        var index = 1
        let values = CommandLine.arguments
        while index < values.count {
            switch values[index] {
            case "--config":
                index += 1
                guard index < values.count else { throw AgentError.invalidConfiguration("--config requires a path") }
                config = values[index]
            case "--once": once = true
            case "--collect-seconds":
                index += 1
                guard index < values.count, let parsed = TimeInterval(values[index]), parsed > 0 else {
                    throw AgentError.invalidConfiguration("--collect-seconds requires a positive number")
                }
                seconds = parsed
            case "--help", "-h":
                print("Usage: edr-macos-agent --config <path> [--once] [--collect-seconds <seconds>]")
                exit(0)
            default: throw AgentError.invalidConfiguration("unknown argument \(values[index])")
            }
            index += 1
        }
        guard let config else { throw AgentError.invalidConfiguration("--config is required") }
        return Arguments(config: config, once: once, collectionSeconds: seconds)
    }
}

do {
    let arguments = try Arguments.parse()
    let configuration = try AgentConfiguration.load(path: arguments.config)
    let runtime = try AgentRuntime(configuration: configuration)
    if arguments.once {
        let report = runtime.runOnce(collectionSeconds: arguments.collectionSeconds)
        print("agent_run collected=\(report.collected) accepted=\(report.transmission.accepted) rejected=\(report.transmission.rejected) sendFailures=\(report.transmission.failedAttempts) pending=\(report.buffer.pending) failed=\(report.buffer.failed) retryCount=\(report.buffer.retryCount)")
        for sensor in report.sensorHealth {
            print("sensor name=\(sensor.sensor) status=\(sensor.status) packetDropCount=\(sensor.packetDropCount ?? 0) parseErrorCount=\(sensor.parseErrorCount ?? 0)")
        }
    } else {
        runtime.runContinuously()
    }
} catch {
    FileHandle.standardError.write(Data("agent_start_failed reason=invalid_configuration\n".utf8))
    exit(2)
}
