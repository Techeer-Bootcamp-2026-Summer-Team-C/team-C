#pragma once

#include "edr_agent/core.hpp"

#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace edr {

class PacketParser {
  public:
    std::vector<Event> parse_ethernet(std::span<const std::uint8_t> packet);
    [[nodiscard]] int parse_error_count() const { return parse_errors_; }

  private:
    int parse_errors_{};
    std::vector<Event> parse_udp(std::span<const std::uint8_t> packet, std::size_t offset);
    std::vector<Event> parse_tcp(std::span<const std::uint8_t> packet, std::size_t offset);
};

}  // namespace edr
