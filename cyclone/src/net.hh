#ifndef CYCLONE_NET_HH
#define CYCLONE_NET_HH

#include <vector>

struct Pin;

struct Net {
public:
    int id = -1;
    std::vector<Pin> pins;
    Net() = default;
    explicit Net(std::vector<std::pair<std::pair<uint32_t, uint32_t>,
                                       std::string>> net);
};

struct Pin {
public:
    uint32_t x = 0;
    uint32_t y = 0;
    std::string port;
    Pin() = default;
    Pin(uint32_t x, uint32_t y, const std::string &port);
};

#endif //CYCLONE_NET_HH
