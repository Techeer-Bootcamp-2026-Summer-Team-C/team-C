import Foundation

public struct HTTPResult: Sendable {
    public let status: Int
    public let body: Data
}

public protocol CurlExecuting: Sendable {
    func post(url: String, body: Data, certificate: String, privateKey: String, caCertificate: String) throws -> HTTPResult
}

public struct ProcessCurl: CurlExecuting {
    public init() {}

    public func post(url: String, body: Data, certificate: String, privateKey: String, caCertificate: String) throws -> HTTPResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
        process.arguments = [
            "--silent", "--show-error", "--connect-timeout", "10", "--max-time", "30",
            "--cacert", caCertificate, "--cert", certificate, "--key", privateKey,
            "--header", "Content-Type: application/json", "--request", "POST", "--data-binary", "@-",
            "--write-out", "\n%{http_code}", url,
        ]
        let input = Pipe(), output = Pipe(), error = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = error
        do { try process.run() } catch { throw AgentError.transport("network_or_tls_failure") }
        input.fileHandleForWriting.write(body)
        try? input.fileHandleForWriting.close()
        let response = output.fileHandleForReading.readDataToEndOfFile()
        _ = error.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard let newline = response.lastIndex(of: 0x0A), newline < response.endIndex else {
            throw AgentError.transport("network_or_tls_failure")
        }
        let statusData = response[response.index(after: newline)...]
        let responseBody = Data(response[..<newline])
        guard let status = Int(String(decoding: statusData, as: UTF8.self)), status > 0 else {
            throw AgentError.transport("network_or_tls_failure")
        }
        return HTTPResult(status: status, body: responseBody)
    }
}

public final class CollectorClient: @unchecked Sendable {
    private let configuration: AgentConfiguration
    private let curl: CurlExecuting
    private let decoder = JSONDecoder()
    private let encoder = contractEncoder()

    public init(configuration: AgentConfiguration, curl: CurlExecuting = ProcessCurl()) {
        self.configuration = configuration
        self.curl = curl
    }

    public func register(_ request: RegisterRequest) throws -> RegisterResult {
        try post(path: "/collector/agents/register", request: request, response: RegisterResult.self)
    }

    public func heartbeat(_ request: HeartbeatRequest) throws -> HeartbeatResult {
        try post(path: "/collector/agents/heartbeat", request: request, response: HeartbeatResult.self)
    }

    public func telemetry(body: Data) throws -> TelemetryResult {
        let result = try curl.post(
            url: endpoint("/collector/telemetry/batches"), body: body,
            certificate: configuration.certificatePath, privateKey: configuration.privateKeyPath,
            caCertificate: configuration.caCertificatePath
        )
        return try decode(result, as: TelemetryResult.self)
    }

    private func post<Request: Encodable, Response: Codable & Sendable>(path: String, request: Request, response: Response.Type) throws -> Response {
        let body = try encoder.encode(request)
        let result = try curl.post(
            url: endpoint(path), body: body,
            certificate: configuration.certificatePath, privateKey: configuration.privateKeyPath,
            caCertificate: configuration.caCertificatePath
        )
        return try decode(result, as: response)
    }

    private func decode<Response: Codable & Sendable>(_ result: HTTPResult, as response: Response.Type) throws -> Response {
        if (200..<300).contains(result.status) {
            return try decoder.decode(SuccessEnvelope<Response>.self, from: result.body).data
        }
        if let envelope = try? decoder.decode(ErrorEnvelope.self, from: result.body) {
            throw AgentError.collector(status: result.status, code: envelope.error.code, retryable: envelope.error.retryable)
        }
        throw AgentError.collector(status: result.status, code: "INVALID_ERROR_ENVELOPE", retryable: result.status == 503)
    }

    private func endpoint(_ path: String) -> String {
        configuration.collectorBaseUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path
    }
}

public func exponentialBackoff(attempt: Int, base: Int, cap: Int) -> Int {
    guard attempt > 0 else { return base }
    let multiplier = 1 << min(attempt - 1, 20)
    return min(cap, base * multiplier)
}
