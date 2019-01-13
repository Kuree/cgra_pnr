#ifndef THUNDER_LAYOUT_HH
#define THUNDER_LAYOUT_HH
#include <vector>
#include <unordered_map>
#include <map>
#include <iostream>

class Layer {
public:
    char blk_type;
    uint32_t id = 0;

    Layer(char blk_type, uint32_t width, uint32_t height);
    bool operator[](const std::pair<uint32_t, uint32_t> &pos) const;
    std::vector<bool> operator[](uint32_t row) const
    { return std::vector<bool>(layout_[row].begin(), layout_[row].end()); }
    std::pair<uint64_t, uint64_t> get_size() const;

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
    Layout(const std::map<char, std::vector<std::vector<bool>>> &layers);

    void add_layer(const Layer & layer);
    bool is_legal(const std::string &blk_id, uint32_t x, uint32_t y);
    const Layer& get_layer(char blk_type) const { return layers_.at(blk_type); }
    char get_blk_type (uint32_t x, uint32_t y) const;

    uint64_t width() const { return width_; }
    uint64_t height() const { return height_; }

private:
    // NOTE:
    // for now we don't support capacity for the same blk type
    std::unordered_map<char, Layer> layers_;
    uint64_t width_ = 0;
    uint64_t height_ = 0;
};


#endif //THUNDER_LAYOUT_HH
