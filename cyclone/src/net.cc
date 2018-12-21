#include <stdint.h>
#include <string>
#include "net.hh"

Net::Net(const std::string &name,
         std::vector<std::pair<std::pair<uint32_t,
                                         uint32_t>,
                               std::pair<std::string, std::string>>> net)
                               : name(name) {
    for (const auto &pin : net) {
        pins_.emplace_back(Pin(pin.first.first, pin.first.second,
                               pin.second.first, pin.second.second));
        pins_.back().id = static_cast<uint32_t>(pins_.size() - 1);
    }
}

void Net::add_pin(const Pin &pin) {
    pins_.emplace_back(pin);
    pins_.back().id = static_cast<uint32_t>(pins_.size() - 1);
}

Pin::Pin(uint32_t x, uint32_t y, const std::string &name,
         const std::string &port)
    : x(x), y(y), name(name), port(port) { }