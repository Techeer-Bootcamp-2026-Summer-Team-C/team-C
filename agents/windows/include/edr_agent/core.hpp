#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace edr {

using JsonValue = std::variant<std::string, std::int64_t, bool, std::vector<std::string>>;

struct Event {
    std::string event_id;
    std::string event_type;
    std::string occurred_at;
    std::map<std::string, JsonValue> payload;
};

struct BufferedRow {
    std::int64_t row_id{};
    std::string event_id;
    std::optional<std::string> batch_id;
    std::string event_json;
    int retry_count{};
};

struct Rejection {
    std::string event_id;
    std::string code;
    bool retryable{};
};

struct BufferMetrics {
    int pending{};
    int failed{};
    int retry_count{};
};

struct Batch {
    std::string batch_id;
    std::string body;
    std::vector<BufferedRow> rows;
};

std::string utc_now();
std::string uuid_string();
std::string json_escape(const std::string& value);
std::string encode_event(const Event& event);
std::string sanitize_url(const std::string& value);
int exponential_backoff(int attempt, int base_seconds, int cap_seconds);

class EventBuffer {
  public:
    EventBuffer(const std::filesystem::path& path, int max_events);
    ~EventBuffer();
    EventBuffer(const EventBuffer&) = delete;
    EventBuffer& operator=(const EventBuffer&) = delete;

    void enqueue(const Event& event, std::optional<std::int64_t> endpoint_id = std::nullopt);
    std::vector<BufferedRow> pending(int limit = 100, const std::string& now = utc_now()) const;
    void assign_batch(const std::string& batch_id, const std::vector<BufferedRow>& rows);
    void apply_result(const std::vector<std::string>& accepted, const std::vector<Rejection>& rejected, int base, int cap);
    void transport_failure(const std::vector<BufferedRow>& rows, const std::string& code, int base, int cap);
    void retry_now();
    void set_endpoint_id(std::int64_t endpoint_id);
    BufferMetrics metrics() const;

  private:
    struct Impl;
    Impl* impl_;
};

std::optional<Batch> make_batch(
    const std::string& agent_id,
    const std::vector<BufferedRow>& rows,
    std::size_t max_events = 100,
    std::size_t max_bytes = 5 * 1024 * 1024
);

constexpr int kFlushIntervalSeconds = 5;
constexpr std::size_t kMaxBatchEvents = 100;
constexpr std::size_t kMaxBatchBytes = 5 * 1024 * 1024;

}  // namespace edr
