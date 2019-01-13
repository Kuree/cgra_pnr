#ifndef THUNDER_LAYOUT_HH
#define THUNDER_LAYOUT_HH
#include <vector>
#include <unordered_map>
#include <map>
#include <set>
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
    // Note on major and minor
    // major priority determines whether the blk_type1 overrides blk_type2,
    // if blk_type1 has higher major priority
    // minor priority determines the primary blk_type at (x, y). this is very
    // useful when registers lays on top of PE layer. 1-bit PE blocks lays on
    // top of 16-bit PE block layers. Here since 16-bit PE block is the
    // primary one, it will have highest minor priority.

    Layout() = default;
    Layout(const std::map<char, std::vector<std::vector<bool>>> &layers);
    Layout(const std::vector<std::vector<char>> &layers);

    void add_layer(const Layer &layer);
    void add_layer(const Layer &layer, uint32_t priority_major,
                   uint32_t priority_minor);
    bool is_legal(const std::string &blk_id, uint32_t x, uint32_t y);
    const Layer& get_layer(char blk_type) const { return layers_.at(blk_type); }
    char get_blk_type(uint32_t x, uint32_t y) const;
    std::vector<char> get_blk_types(uint32_t x, uint32_t y) const;

    uint64_t width() const { return width_; }
    uint64_t height() const { return height_; }

    static uint32_t DEFAULT_PRIORITY;

    uint32_t get_priority_major(char blk_type)
    { return layers_priority_major_.at(blk_type); }
    uint32_t get_priority_minor(char blk_type)
    { return layers_priority_minor_.at(blk_type); }
    std::set<char> get_layer_types();

private:
    // NOTE:
    // for now we don't support capacity for the same blk type
    std::unordered_map<char, Layer> layers_;
    std::unordered_map<char, uint32_t> layers_priority_major_;
    std::unordered_map<char, uint32_t> layers_priority_minor_;
    uint64_t width_ = 0;
    uint64_t height_ = 0;
};


#endif //THUNDER_LAYOUT_HH
