#ifndef CYCLONE_NET_HH
#define CYCLONE_NET_HH

#include <vector>
#include "graph.hh"


struct Pin {
public:
    uint32_t x = 0;
    uint32_t y = 0;
    std::string name;
    std::string port;
    std::shared_ptr<Node> node = nullptr;
    uint32_t id = 0;
    Pin() = default;
    Pin(uint32_t x, uint32_t y, const std::string &name,
        const std::string &port);
};

struct Net {
public:
    int id = -1;
    std::string name;
    bool fixed = false;
    Net() = default;
    explicit Net(const std::string &name,
                 std::vector<std::pair<std::pair<uint32_t, uint32_t>,
                                       std::pair<std::string,
                                                 std::string>>> net);

    std::vector<Pin>::iterator begin() { return pins_.begin(); }
    std::vector<Pin>::iterator end() { return pins_.end(); }

    void add_pin(const Pin &pin);
    inline uint64_t size() const { return pins_.size(); }
    inline Pin& operator[](const uint64_t &index) { return pins_[index]; }
    inline const Pin& operator[](const uint64_t &index) const
    { return pins_[index]; }
private:
    std::vector<Pin> pins_;
};


#endif //CYCLONE_NET_HH
