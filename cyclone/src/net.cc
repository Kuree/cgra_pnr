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
    }
}

Pin::Pin(uint32_t x, uint32_t y, const std::string &name,
         const std::string &port)
    : x(x), y(y), name(name), port(port) { }