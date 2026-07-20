#include "edr_agent/core.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>

#include <sqlite3.h>

namespace edr {
namespace {

struct Statement {
    sqlite3_stmt* value{};
    ~Statement() { sqlite3_finalize(value); }
};

std::string utc_at(const std::chrono::system_clock::time_point point) {
    const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(point.time_since_epoch()) % 1000;
    const std::time_t value = std::chrono::system_clock::to_time_t(point);
    std::tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &value);
#else
    gmtime_r(&value, &utc);
#endif
    std::ostringstream result;
    result << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setw(3) << std::setfill('0')
           << milliseconds.count() << 'Z';
    return result.str();
}

void bind_text(sqlite3_stmt* statement, int index, const std::string& value) {
    if (sqlite3_bind_text(statement, index, value.c_str(), -1, SQLITE_TRANSIENT) != SQLITE_OK) {
        throw std::runtime_error("SQLite bind failed");
    }
}

std::string json_value(const JsonValue& value) {
    if (const auto* string = std::get_if<std::string>(&value)) return '"' + json_escape(*string) + '"';
    if (const auto* integer = std::get_if<std::int64_t>(&value)) return std::to_string(*integer);
    if (const auto* boolean = std::get_if<bool>(&value)) return *boolean ? "true" : "false";
    const auto& strings = std::get<std::vector<std::string>>(value);
    std::string result = "[";
    for (std::size_t index = 0; index < strings.size(); ++index) {
        if (index) result += ',';
        result += '"' + json_escape(strings[index]) + '"';
    }
    return result + ']';
}

}  // namespace

struct EventBuffer::Impl {
    sqlite3* database{};
    int max_events{};
    mutable std::mutex mutex;

    Statement prepare(const char* sql) const {
        Statement statement;
        if (sqlite3_prepare_v2(database, sql, -1, &statement.value, nullptr) != SQLITE_OK) {
            throw std::runtime_error("SQLite prepare failed");
        }
        return statement;
    }

    void execute(const char* sql) const {
        char* error = nullptr;
        if (sqlite3_exec(database, sql, nullptr, nullptr, &error) != SQLITE_OK) {
            sqlite3_free(error);
            throw std::runtime_error("SQLite execute failed");
        }
    }

    int scalar(const char* sql) const {
        auto statement = prepare(sql);
        return sqlite3_step(statement.value) == SQLITE_ROW ? sqlite3_column_int(statement.value, 0) : 0;
    }
};

std::string utc_now() { return utc_at(std::chrono::system_clock::now()); }

std::string uuid_string() {
    std::array<unsigned char, 16> bytes{};
    std::random_device source;
    for (auto& byte : bytes) byte = static_cast<unsigned char>(source());
    bytes[6] = static_cast<unsigned char>((bytes[6] & 0x0f) | 0x40);
    bytes[8] = static_cast<unsigned char>((bytes[8] & 0x3f) | 0x80);
    std::ostringstream result;
    result << std::hex << std::setfill('0');
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        if (index == 4 || index == 6 || index == 8 || index == 10) result << '-';
        result << std::setw(2) << static_cast<int>(bytes[index]);
    }
    return result.str();
}

std::string json_escape(const std::string& value) {
    std::string output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': output += "\\\""; break;
            case '\\': output += "\\\\"; break;
            case '\b': output += "\\b"; break;
            case '\f': output += "\\f"; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default:
                if (character < 0x20) {
                    std::ostringstream escaped;
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(character);
                    output += escaped.str();
                } else output.push_back(static_cast<char>(character));
        }
    }
    return output;
}

std::string encode_event(const Event& event) {
    std::string result = "{\"eventId\":\"" + json_escape(event.event_id) + "\",\"eventType\":\"" +
                         json_escape(event.event_type) + "\",\"occurredAt\":\"" + json_escape(event.occurred_at) +
                         "\",\"payload\":{";
    bool first = true;
    for (const auto& [key, value] : event.payload) {
        if (!first) result += ',';
        first = false;
        result += '"' + json_escape(key) + "\":" + json_value(value);
    }
    return result + "}}";
}

std::string sanitize_url(const std::string& value) {
    const auto query = value.find('?');
    const auto fragment = value.find('#');
    return value.substr(0, std::min(query == std::string::npos ? value.size() : query,
                                    fragment == std::string::npos ? value.size() : fragment));
}

int exponential_backoff(int attempt, int base_seconds, int cap_seconds) {
    const int shift = std::clamp(attempt - 1, 0, 20);
    return std::min(cap_seconds, base_seconds * (1 << shift));
}

EventBuffer::EventBuffer(const std::filesystem::path& path, int max_events) : impl_(new Impl) {
    impl_->max_events = max_events;
    std::filesystem::create_directories(path.parent_path());
    if (sqlite3_open_v2(path.string().c_str(), &impl_->database, SQLITE_OPEN_CREATE | SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX, nullptr) != SQLITE_OK) {
        throw std::runtime_error("unable to open SQLite event buffer");
    }
    impl_->execute("PRAGMA journal_mode=WAL");
    impl_->execute("PRAGMA synchronous=FULL");
    impl_->execute(
        "CREATE TABLE IF NOT EXISTS local_event_buffer ("
        "local_event_buffer_id INTEGER PRIMARY KEY AUTOINCREMENT,endpoint_id INTEGER NULL,event_id TEXT NOT NULL UNIQUE,"
        "batch_id TEXT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,collected_at TEXT NOT NULL,"
        "status TEXT NOT NULL CHECK(status IN ('PENDING','FAILED')),retry_count INTEGER NOT NULL DEFAULT 0,"
        "last_error TEXT NULL,next_retry_at TEXT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"
    );
    impl_->execute("CREATE INDEX IF NOT EXISTS idx_local_event_buffer_pending ON local_event_buffer(status,next_retry_at,local_event_buffer_id)");
}

EventBuffer::~EventBuffer() {
    sqlite3_close(impl_->database);
    delete impl_;
}

void EventBuffer::enqueue(const Event& event, std::optional<std::int64_t> endpoint_id) {
    std::scoped_lock lock(impl_->mutex);
    if (impl_->scalar("SELECT COUNT(*) FROM local_event_buffer") >= impl_->max_events) throw std::overflow_error("event buffer full");
    auto statement = impl_->prepare(
        "INSERT OR IGNORE INTO local_event_buffer(endpoint_id,event_id,batch_id,event_type,payload_json,collected_at,status,retry_count,last_error,next_retry_at,created_at,updated_at) "
        "VALUES(?,?,NULL,?,?,?,'PENDING',0,NULL,NULL,?,?)"
    );
    if (endpoint_id) sqlite3_bind_int64(statement.value, 1, *endpoint_id); else sqlite3_bind_null(statement.value, 1);
    bind_text(statement.value, 2, event.event_id);
    bind_text(statement.value, 3, event.event_type);
    bind_text(statement.value, 4, encode_event(event));
    bind_text(statement.value, 5, event.occurred_at);
    const auto now = utc_now();
    bind_text(statement.value, 6, now); bind_text(statement.value, 7, now);
    if (sqlite3_step(statement.value) != SQLITE_DONE) throw std::runtime_error("SQLite enqueue failed");
}

std::vector<BufferedRow> EventBuffer::pending(int limit, const std::string& now) const {
    std::scoped_lock lock(impl_->mutex);
    auto statement = impl_->prepare(
        "SELECT local_event_buffer_id,event_id,batch_id,payload_json,retry_count FROM local_event_buffer "
        "WHERE status='PENDING' AND (next_retry_at IS NULL OR next_retry_at<=?) ORDER BY local_event_buffer_id LIMIT ?"
    );
    bind_text(statement.value, 1, now); sqlite3_bind_int(statement.value, 2, limit);
    std::vector<BufferedRow> rows;
    while (sqlite3_step(statement.value) == SQLITE_ROW) {
        const auto batch_id = sqlite3_column_type(statement.value, 2) == SQLITE_NULL
                                  ? std::nullopt
                                  : std::optional<std::string>(reinterpret_cast<const char*>(sqlite3_column_text(statement.value, 2)));
        rows.push_back({sqlite3_column_int64(statement.value, 0),
                        reinterpret_cast<const char*>(sqlite3_column_text(statement.value, 1)),
                        batch_id,
                        reinterpret_cast<const char*>(sqlite3_column_text(statement.value, 3)),
                        sqlite3_column_int(statement.value, 4)});
    }
    return rows;
}

void EventBuffer::assign_batch(const std::string& batch_id, const std::vector<BufferedRow>& rows) {
    std::scoped_lock lock(impl_->mutex);
    impl_->execute("BEGIN IMMEDIATE");
    try {
        for (const auto& row : rows) {
            auto statement = impl_->prepare("UPDATE local_event_buffer SET batch_id=?,updated_at=? WHERE local_event_buffer_id=?");
            bind_text(statement.value, 1, batch_id); bind_text(statement.value, 2, utc_now()); sqlite3_bind_int64(statement.value, 3, row.row_id);
            if (sqlite3_step(statement.value) != SQLITE_DONE) throw std::runtime_error("SQLite batch assignment failed");
        }
        impl_->execute("COMMIT");
    } catch (...) { impl_->execute("ROLLBACK"); throw; }
}

void EventBuffer::apply_result(const std::vector<std::string>& accepted, const std::vector<Rejection>& rejected, int base, int cap) {
    std::scoped_lock lock(impl_->mutex);
    impl_->execute("BEGIN IMMEDIATE");
    try {
        for (const auto& id : accepted) {
            auto statement = impl_->prepare("DELETE FROM local_event_buffer WHERE event_id=?");
            bind_text(statement.value, 1, id); sqlite3_step(statement.value);
        }
        for (const auto& item : rejected) {
            auto lookup = impl_->prepare("SELECT retry_count FROM local_event_buffer WHERE event_id=?");
            bind_text(lookup.value, 1, item.event_id);
            const int retry = sqlite3_step(lookup.value) == SQLITE_ROW ? sqlite3_column_int(lookup.value, 0) + 1 : 1;
            auto statement = impl_->prepare("UPDATE local_event_buffer SET status=?,retry_count=?,last_error=?,next_retry_at=?,updated_at=? WHERE event_id=?");
            bind_text(statement.value, 1, item.retryable ? "PENDING" : "FAILED");
            sqlite3_bind_int(statement.value, 2, retry); bind_text(statement.value, 3, item.code);
            if (item.retryable) bind_text(statement.value, 4, utc_at(std::chrono::system_clock::now() + std::chrono::seconds(exponential_backoff(retry, base, cap))));
            else sqlite3_bind_null(statement.value, 4);
            bind_text(statement.value, 5, utc_now()); bind_text(statement.value, 6, item.event_id); sqlite3_step(statement.value);
        }
        impl_->execute("COMMIT");
    } catch (...) { impl_->execute("ROLLBACK"); throw; }
}

void EventBuffer::transport_failure(const std::vector<BufferedRow>& rows, const std::string& code, int base, int cap) {
    std::vector<Rejection> rejected;
    for (const auto& row : rows) rejected.push_back({row.event_id, code, true});
    apply_result({}, rejected, base, cap);
}

void EventBuffer::retry_now() {
    std::scoped_lock lock(impl_->mutex);
    impl_->execute("UPDATE local_event_buffer SET next_retry_at=NULL WHERE status='PENDING'");
}

void EventBuffer::set_endpoint_id(std::int64_t endpoint_id) {
    std::scoped_lock lock(impl_->mutex);
    auto statement = impl_->prepare("UPDATE local_event_buffer SET endpoint_id=?,updated_at=? WHERE endpoint_id IS NULL");
    sqlite3_bind_int64(statement.value, 1, endpoint_id); bind_text(statement.value, 2, utc_now()); sqlite3_step(statement.value);
}

BufferMetrics EventBuffer::metrics() const {
    std::scoped_lock lock(impl_->mutex);
    return {impl_->scalar("SELECT COUNT(*) FROM local_event_buffer WHERE status='PENDING'"),
            impl_->scalar("SELECT COUNT(*) FROM local_event_buffer WHERE status='FAILED'"),
            impl_->scalar("SELECT COALESCE(SUM(retry_count),0) FROM local_event_buffer")};
}

std::optional<Batch> make_batch(const std::string& agent_id, const std::vector<BufferedRow>& rows, std::size_t max_events, std::size_t max_bytes) {
    if (rows.empty()) return std::nullopt;
    const auto existing_batch_id = rows.front().batch_id;
    Batch result{existing_batch_id.value_or(uuid_string()), {}, {}};
    const std::string prefix = "{\"schemaVersion\":1,\"batchId\":\"" + result.batch_id + "\",\"agentId\":\"" +
                               json_escape(agent_id) + "\",\"sentAt\":\"" + utc_now() + "\",\"events\":[";
    constexpr std::string_view suffix = "]}";
    std::string events;
    std::set<std::string> seen;
    for (const auto& row : rows) {
        if ((existing_batch_id && row.batch_id != existing_batch_id) || (!existing_batch_id && row.batch_id)) continue;
        if (result.rows.size() >= max_events || !seen.insert(row.event_id).second) continue;
        const auto separator_size = events.empty() ? 0U : 1U;
        const auto candidate_size = prefix.size() + events.size() + separator_size + row.event_json.size() + suffix.size();
        if (candidate_size > max_bytes) {
            if (result.rows.empty()) throw std::length_error("single event exceeds 5MiB batch limit");
            break;
        }
        if (!events.empty()) events += ',';
        events += row.event_json;
        result.rows.push_back(row);
    }
    if (!result.rows.empty()) result.body = prefix + events + std::string(suffix);
    return result;
}

}  // namespace edr
