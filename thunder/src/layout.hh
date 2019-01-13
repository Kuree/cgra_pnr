#ifndef THUNDER_LAYOUT_HH
#define THUNDER_LAYOUT_HH
#include <vector>
#include <unordered_map>
#include <iostream>

class Layer {
public:
    char blk_type;
    uint32_t id = 0;

    Layer(char blk_type, uint32_t width, uint32_t height);
    bool operator[](const std::pair<uint32_t, uint32_t> &pos) const;

private:
    std::vector<std::vector<bool>> layout_;
public:
    inline void mark_available(uint32_t x,
                               uint32_t y) { layout_[y][x] = true; }
    inline void mark_unavailable(uint32_t x,
                                 uint32_t y) { layout_[y][x] = false; }
};

class Layout {
public:
    // layout consists of each layers, where you can only place one single
    // cell on the layer
    Layout() = default;
    void add_layer(const Layer & layer);
    bool is_legal(const std::string &blk_id, uint32_t x, uint32_t y);

private:
    // NOTE:
    // for now we don't support capacity for the same blk type
    std::unordered_map<char, Layer> layers_;
};


#endif //THUNDER_LAYOUT_HH
