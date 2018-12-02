#include <stdint.h>
#include <string>
#include "net.hh"

Net::Net(std::vector<std::pair<std::pair<uint32_t,
                                         uint32_t>, std::string>> net) {
    for (const auto &pin : net) {
        pins_.emplace_back(Pin(pin.first.first, pin.first.second, pin.second));
    }
}

Pin::Pin(uint32_t x, uint32_t y, const std::string &port)
    : x(x), y(y), port(port) { }