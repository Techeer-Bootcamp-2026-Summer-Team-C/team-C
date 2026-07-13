import Foundation
import SQLite3

private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

public struct BufferedEvent: Sendable {
    public let rowId: Int64
    public let endpointId: Int64?
    public let batchId: String?
    public let event: TelemetryEvent
    public let retryCount: Int
}

public struct BufferMetrics: Equatable, Sendable {
    public let pending: Int
    public let failed: Int
    public let retryCount: Int
}

public final class EventBuffer: @unchecked Sendable {
    private var database: OpaquePointer?
    private let lock = NSLock()
    private let encoder = contractEncoder()
    public let maxEvents: Int

    public init(path: String, maxEvents: Int) throws {
        self.maxEvents = maxEvents
        let url = URL(fileURLWithPath: path)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        guard sqlite3_open_v2(path, &database, SQLITE_OPEN_CREATE | SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK else {
            throw AgentError.invalidConfiguration("unable to open SQLite event buffer")
        }
        try execute("PRAGMA journal_mode=WAL")
        try execute("PRAGMA synchronous=FULL")
        try execute("""
        CREATE TABLE IF NOT EXISTS local_event_buffer (
            local_event_buffer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER NULL,
            event_id TEXT NOT NULL UNIQUE,
            batch_id TEXT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'FAILED')),
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            next_retry_at TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        try execute("CREATE INDEX IF NOT EXISTS idx_local_event_buffer_pending ON local_event_buffer(status, next_retry_at, local_event_buffer_id)")
    }

    deinit { sqlite3_close(database) }

    public func enqueue(_ event: TelemetryEvent, endpointId: Int64? = nil) throws {
        lock.lock(); defer { lock.unlock() }
        guard try scalarInt("SELECT COUNT(*) FROM local_event_buffer") < maxEvents else { throw AgentError.queueFull }
        let encoded = String(decoding: try encoder.encode(event), as: UTF8.self)
        let now = utcNow()
        let statement = try prepare("""
        INSERT OR IGNORE INTO local_event_buffer
        (endpoint_id, event_id, batch_id, event_type, payload_json, collected_at, status, retry_count, last_error, next_retry_at, created_at, updated_at)
        VALUES (?, ?, NULL, ?, ?, ?, 'PENDING', 0, NULL, NULL, ?, ?)
        """)
        defer { sqlite3_finalize(statement) }
        if let endpointId { sqlite3_bind_int64(statement, 1, endpointId) } else { sqlite3_bind_null(statement, 1) }
        bindText(statement, 2, event.eventId)
        bindText(statement, 3, event.eventType)
        bindText(statement, 4, encoded)
        bindText(statement, 5, event.occurredAt)
        bindText(statement, 6, now)
        bindText(statement, 7, now)
        try stepDone(statement)
    }

    public func pending(limit: Int = 100, now: String = utcNow()) throws -> [BufferedEvent] {
        lock.lock(); defer { lock.unlock() }
        let statement = try prepare("""
        SELECT local_event_buffer_id, endpoint_id, batch_id, payload_json, retry_count
        FROM local_event_buffer
        WHERE status = 'PENDING' AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY local_event_buffer_id LIMIT ?
        """)
        defer { sqlite3_finalize(statement) }
        bindText(statement, 1, now)
        sqlite3_bind_int(statement, 2, Int32(limit))
        var rows: [BufferedEvent] = []
        while sqlite3_step(statement) == SQLITE_ROW {
            let rowId = sqlite3_column_int64(statement, 0)
            let endpointId = sqlite3_column_type(statement, 1) == SQLITE_NULL ? nil : sqlite3_column_int64(statement, 1)
            let batchId = sqlite3_column_type(statement, 2) == SQLITE_NULL ? nil : String(cString: sqlite3_column_text(statement, 2))
            guard let pointer = sqlite3_column_text(statement, 3) else { continue }
            let event = try JSONDecoder().decode(TelemetryEvent.self, from: Data(String(cString: pointer).utf8))
            rows.append(BufferedEvent(rowId: rowId, endpointId: endpointId, batchId: batchId, event: event, retryCount: Int(sqlite3_column_int(statement, 4))))
        }
        return rows
    }

    public func assign(batchId: String, rowIds: [Int64]) throws {
        try updateRows(rowIds, sql: "UPDATE local_event_buffer SET batch_id = ?, updated_at = ? WHERE local_event_buffer_id = ?") { statement, rowId in
            bindText(statement, 1, batchId)
            bindText(statement, 2, utcNow())
            sqlite3_bind_int64(statement, 3, rowId)
        }
    }

    public func apply(result: TelemetryResult, backoffSeconds: (Int) -> Int) throws {
        lock.lock(); defer { lock.unlock() }
        try execute("BEGIN IMMEDIATE")
        do {
            for eventId in result.acceptedEventIds {
                let statement = try prepare("DELETE FROM local_event_buffer WHERE event_id = ?")
                bindText(statement, 1, eventId)
                try stepDone(statement)
                sqlite3_finalize(statement)
            }
            for rejection in result.rejectedEvents {
                let retryCount = try retryCountFor(eventId: rejection.eventId) + 1
                let statement = try prepare("""
                UPDATE local_event_buffer SET status = ?, retry_count = ?, last_error = ?, next_retry_at = ?, updated_at = ?
                WHERE event_id = ?
                """)
                bindText(statement, 1, rejection.retryable ? "PENDING" : "FAILED")
                sqlite3_bind_int(statement, 2, Int32(retryCount))
                bindText(statement, 3, rejection.code)
                if rejection.retryable {
                    bindText(statement, 4, utcNow(Date().addingTimeInterval(TimeInterval(backoffSeconds(retryCount)))))
                } else {
                    sqlite3_bind_null(statement, 4)
                }
                bindText(statement, 5, utcNow())
                bindText(statement, 6, rejection.eventId)
                try stepDone(statement)
                sqlite3_finalize(statement)
            }
            try execute("COMMIT")
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    public func markTransportFailure(rowIds: [Int64], error code: String, backoffSeconds: (Int) -> Int) throws {
        lock.lock(); defer { lock.unlock() }
        try execute("BEGIN IMMEDIATE")
        do {
            for rowId in rowIds {
                let current = try retryCountFor(rowId: rowId) + 1
                let statement = try prepare("""
                UPDATE local_event_buffer SET status = 'PENDING', retry_count = ?, last_error = ?, next_retry_at = ?, updated_at = ?
                WHERE local_event_buffer_id = ?
                """)
                sqlite3_bind_int(statement, 1, Int32(current))
                bindText(statement, 2, code)
                bindText(statement, 3, utcNow(Date().addingTimeInterval(TimeInterval(backoffSeconds(current)))))
                bindText(statement, 4, utcNow())
                sqlite3_bind_int64(statement, 5, rowId)
                try stepDone(statement)
                sqlite3_finalize(statement)
            }
            try execute("COMMIT")
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    public func makeRetryableNow() throws {
        try execute("UPDATE local_event_buffer SET next_retry_at = NULL WHERE status = 'PENDING'")
    }

    public func setEndpointId(_ endpointId: Int64) throws {
        lock.lock(); defer { lock.unlock() }
        let statement = try prepare("UPDATE local_event_buffer SET endpoint_id = ?, updated_at = ? WHERE endpoint_id IS NULL")
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_int64(statement, 1, endpointId)
        bindText(statement, 2, utcNow())
        try stepDone(statement)
    }

    public func metrics() throws -> BufferMetrics {
        lock.lock(); defer { lock.unlock() }
        return BufferMetrics(
            pending: try scalarInt("SELECT COUNT(*) FROM local_event_buffer WHERE status = 'PENDING'"),
            failed: try scalarInt("SELECT COUNT(*) FROM local_event_buffer WHERE status = 'FAILED'"),
            retryCount: try scalarInt("SELECT COALESCE(SUM(retry_count), 0) FROM local_event_buffer")
        )
    }

    private func updateRows(_ rowIds: [Int64], sql: String, binder: (OpaquePointer, Int64) -> Void) throws {
        lock.lock(); defer { lock.unlock() }
        try execute("BEGIN IMMEDIATE")
        do {
            for rowId in rowIds {
                let statement = try prepare(sql)
                binder(statement, rowId)
                try stepDone(statement)
                sqlite3_finalize(statement)
            }
            try execute("COMMIT")
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    private func retryCountFor(eventId: String) throws -> Int {
        let statement = try prepare("SELECT retry_count FROM local_event_buffer WHERE event_id = ?")
        defer { sqlite3_finalize(statement) }
        bindText(statement, 1, eventId)
        return sqlite3_step(statement) == SQLITE_ROW ? Int(sqlite3_column_int(statement, 0)) : 0
    }

    private func retryCountFor(rowId: Int64) throws -> Int {
        let statement = try prepare("SELECT retry_count FROM local_event_buffer WHERE local_event_buffer_id = ?")
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_int64(statement, 1, rowId)
        return sqlite3_step(statement) == SQLITE_ROW ? Int(sqlite3_column_int(statement, 0)) : 0
    }

    private func scalarInt(_ sql: String) throws -> Int {
        let statement = try prepare(sql)
        defer { sqlite3_finalize(statement) }
        guard sqlite3_step(statement) == SQLITE_ROW else { return 0 }
        return Int(sqlite3_column_int64(statement, 0))
    }

    private func execute(_ sql: String) throws {
        var error: UnsafeMutablePointer<CChar>?
        guard sqlite3_exec(database, sql, nil, nil, &error) == SQLITE_OK else {
            let message = error.map { String(cString: $0) } ?? "SQLite execution failed"
            sqlite3_free(error)
            throw AgentError.transport(message)
        }
    }

    private func prepare(_ sql: String) throws -> OpaquePointer {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw AgentError.transport("SQLite statement preparation failed")
        }
        return statement
    }

    private func bindText(_ statement: OpaquePointer, _ index: Int32, _ value: String) {
        sqlite3_bind_text(statement, index, value, -1, sqliteTransient)
    }

    private func stepDone(_ statement: OpaquePointer) throws {
        guard sqlite3_step(statement) == SQLITE_DONE else { throw AgentError.transport("SQLite write failed") }
    }
}

public struct BatchSelection: Sendable {
    public let batch: TelemetryBatch
    public let rows: [BufferedEvent]
    public let body: Data
}

public enum MicroBatcher {
    public static let maxEvents = 100
    public static let maxBodyBytes = 5 * 1024 * 1024
    public static let flushIntervalSeconds: TimeInterval = 5

    public static func select(agentId: String, rows: [BufferedEvent], maxEvents: Int = maxEvents, maxBodyBytes: Int = maxBodyBytes) throws -> BatchSelection? {
        guard !rows.isEmpty else { return nil }
        let existingBatchId = rows.first?.batchId
        let eligibleRows = rows.filter { row in
            if let existingBatchId { return row.batchId == existingBatchId }
            return row.batchId == nil
        }
        let batchId = existingBatchId ?? UUID().uuidString.lowercased()
        var selected: [BufferedEvent] = []
        var body = Data()
        var seen = Set<String>()
        for row in eligibleRows.prefix(maxEvents) where seen.insert(row.event.eventId).inserted {
            let candidate = selected + [row]
            let candidateBatch = TelemetryBatch(batchId: batchId, agentId: agentId, events: candidate.map(\.event))
            let encoded = try contractEncoder().encode(candidateBatch)
            if encoded.count > maxBodyBytes {
                if selected.isEmpty { throw AgentError.eventTooLarge }
                break
            }
            selected = candidate
            body = encoded
        }
        let batch = TelemetryBatch(batchId: batchId, agentId: agentId, events: selected.map(\.event))
        return BatchSelection(batch: batch, rows: selected, body: body)
    }
}
