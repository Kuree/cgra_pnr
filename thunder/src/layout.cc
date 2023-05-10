#include <sstream>
#include "layout.hh"

using std::vector;
using std::runtime_error;


Layer::Layer(char blk_type, uint32_t width,
             uint32_t height) : blk_type(blk_type),
                                layout_(height, ::vector<int>(width, 0)) {}

Layer::Layer(const Layer &layer) {
    auto height = layer.layout_.size();
    blk_type = layer.blk_type;
    layout_.reserve(height);
    for (auto const &row: layer.layout_) {
        auto vec = std::vector<int>(row.begin(), row.end());
        layout_.emplace_back(vec);
    }
}

std::vector<std::pair<uint32_t, uint32_t>>
Layer::produce_available_pos() const {
    ::vector<std::pair<uint32_t, uint32_t>> result;

    for (uint32_t y = 0; y < layout_.size(); y++) {
        for (uint32_t x = 0; x < layout_[y].size(); x++) {
            for (int z = 0; z < layout_[y][x]; z++) {
                result.emplace_back(std::make_pair(x, y));
            }
        }
    }
    return result;
}

int Layer::operator[](const std::pair<uint32_t, uint32_t> &pos) const {
    auto [x, y] = pos;
    return layout_[y][x];
}

std::pair<uint64_t, uint64_t> Layer::get_size() const {
    return {layout_[0].size(), layout_.size()};
}

Layout::Layout(const std::map<char, std::vector<std::vector<int>>> &layers) {
    for (auto &[blk_type, layer]: layers) {
        auto height = static_cast<uint32_t>(layer.size());
        auto width = static_cast<uint32_t>(layer[0].size());
        // add a layer one by one
        Layer l(blk_type, width, height);
        for (uint32_t y = 0; y < height; y++) {
            for (uint32_t x = 0; x < width; x++) {
                l.mark_available(x, y, layer[y][x]);
            }
        }
        add_layer(l);
    }
}

Layout::Layout(const std::vector<std::vector<char>> &layers) {
    auto height = static_cast<uint32_t>(layers.size());
    auto width = static_cast<uint32_t>(layers[0].size());
    // first pass to create the empty layers
    for (uint32_t y = 0; y < height; y++) {
        for (uint32_t x = 0; x < width; x++) {
            auto const blk_type = layers[y][x];
            if (layers_.find(blk_type) == layers_.end())
                add_layer(Layer(blk_type, width, height));
        }
    }
    // second pass to fill that layer in
    for (uint32_t y = 0; y < height; y++) {
        for (uint32_t x = 0; x < width; x++) {
            auto const blk_type = layers[y][x];
            auto &layer = layers_.at(blk_type);
            layer.mark_available(x, y, 1);
        }
    }
}

uint32_t Layout::DEFAULT_PRIORITY = 20;
void Layout::add_layer(const Layer &layer) {
    add_layer(layer, Layout::DEFAULT_PRIORITY, Layout::DEFAULT_PRIORITY);
}

void Layout::add_layer(const Layer &layer, uint32_t priority_major,
                       uint32_t priority_minor) {
    const char blk_type = layer.blk_type;
    if (layers_.find(blk_type) != layers_.end())
        throw ::runtime_error(std::string(1, blk_type) + " already exists");
    layers_.insert({blk_type, layer});

    // set width and height
    auto [width, height] = layer.get_size();
    if (width_ == 0) {
        width_ = width;
        height_ = height;
    } else {
        if (width_ != width || height_ != height)
            throw ::runtime_error("layer size doesn't match");
    }

    layers_priority_major_.insert({blk_type, priority_major});
    layers_priority_minor_.insert({blk_type, priority_minor});
}

bool Layout::is_legal(const std::string &blk_id, uint32_t x, uint32_t y) {
    const char blk_type = blk_id[0];
    auto const &layer = layers_.at(blk_type);
    return layer[{x, y}];
}

char Layout::get_blk_type(uint32_t x, uint32_t y) const {
    char blk = ' ';
    uint32_t priority_major = 0;
    uint32_t priority_minor = 0;
    for (auto const &[blk_type, layer]: layers_) {
        if (layer[{x, y}] &&
            layers_priority_major_.at(blk_type) >= priority_major &&
            layers_priority_minor_.at(blk_type) >= priority_minor &&
            blk_type != REGISTER) {
            blk = blk_type;
            priority_major = layers_priority_major_.at(blk_type);
            priority_minor = layers_priority_minor_.at(blk_type);
        }

    }
    return blk;
}

std::vector<char> Layout::get_blk_types(uint32_t x, uint32_t y) const {
    ::vector<char> results;
    uint32_t priority_major = 0;
    // first pass to find out the max priority
    for (const auto &[blk_type, layer]: layers_) {
        if (layer[{x, y}] &&
            layers_priority_major_.at(blk_type) > priority_major &&
            blk_type != REGISTER) {
            priority_major = layers_priority_major_.at(blk_type);
        }
    }
    // second pass to find all blk types has the same priority major
    for (const auto &[blk_type, layer]: layers_) {
        if (layer[{x, y}] &&
            layers_priority_major_.at(blk_type) >= priority_major) {
            results.emplace_back(blk_type);
        }
    }
    return results;
}

void Layout::set_priority_major(char blk_type, uint32_t priority) {
    if (layers_priority_major_.find(blk_type) == layers_priority_major_.end())
        throw std::runtime_error(std::string(1, blk_type) + " not found");
    layers_priority_major_[blk_type] = priority;
}

void Layout::set_priority_minor(char blk_type, uint32_t priority) {
    if (layers_priority_minor_.find(blk_type) == layers_priority_minor_.end())
        throw std::runtime_error(std::string(1, blk_type) + " not found");
    layers_priority_minor_[blk_type] = priority;
}

std::set<char> Layout::get_layer_types() const {
    std::set<char> result;
    for (auto const &iter: layers_)
        result.insert(iter.first);
    return result;
}

std::map<char, std::vector<std::pair<int, int>>>
Layout::produce_available_pos() const {
    std::map<char, std::vector<std::pair<int, int>>> result;
    for (uint32_t x = 0; x < width_; x++) {
        for (uint32_t y = 0; y < height_; y++) {
            auto blks = get_blk_types(x, y);
            for (auto const &blk : blks) {
                auto const &layer = layers_.at(blk);
                for (int z = 0; z < layer[{x, y}]; z++) {
                    result[blk].emplace_back(std::make_pair(x, y));
                }
            }
        }
    }
    return result;
}

std::tuple<uint32_t, uint32_t, uint32_t, uint32_t> Layout::get_layout_margin() {
    uint32_t margin_top = 0, margin_right = 0, margin_bottom = 0,
             margin_left = 0;

    uint64_t size = width_ > height_? height_ : width_;
    size /= 2;

    for (uint32_t i = 0; i < height_; i++) {
        // get margin top
        const auto blk_type = get_blk_type(size, i);
        if (get_priority_major(blk_type) > DEFAULT_PRIORITY / 2) {
            margin_top = i;
            break;
        }
    }
    for (int i = height_ - 1; i >= 0; i--) {
        // get margin bottom
        const auto blk_type = get_blk_type(size, i);
        if (get_priority_major(blk_type) > DEFAULT_PRIORITY / 2) {
            margin_bottom = height_ - i - 1;
            break;
        }
    }
    for (uint32_t i = 0; i < width_; i++) {
        // get margin left
        const auto blk_type = get_blk_type(i, size);
        if (get_priority_major(blk_type) > DEFAULT_PRIORITY / 2) {
            margin_left = i;
            break;
        }
    }
    for (int i = width_ - 1; i >= 0; i--) {
        // get margin bottom
        const auto blk_type = get_blk_type(i, size);
        if (get_priority_major(blk_type) > DEFAULT_PRIORITY / 2) {
            margin_right = width_ - i - 1;
            break;
        }
    }

    return std::make_tuple(margin_top, margin_right, margin_bottom,
            margin_left);
}

char Layout::get_clb_type() const {
    // the blk_type that has highest priority
    uint32_t major = 0;
    uint32_t minor = 0;
    char blk = ' ';
    for (uint32_t x = 0; x < width_; x++) {
        for (uint32_t y = 0; y < height_; y++) {
            auto blk_type = get_blk_type(x, y);
            auto blk_major = get_priority_major(blk_type);
            auto blk_minor = get_priority_minor(blk_type);

            if (blk_major >= major && blk_minor >= minor) {
                blk = blk_type;
                major = blk_major;
                minor = blk_minor;

            }
        }
    }
    return blk;
}

std::string Layout::layout_repr() {
    std::stringstream ss;
    for (uint32_t y = 0; y < height_; y++) {
        for (uint32_t x = 0; x < width_; x++) {
            ss << get_blk_type(x, y);
        }
        ss << std::endl;
    }
    return ss.str();
}

void Layout::add_layer_mask(const LayerMask &mask) {
    auto const blk_type = mask.blk_type;
    if (layer_masks_.find(blk_type) != layer_masks_.end())
        throw std::runtime_error(std::string(1, blk_type) + " already exists");
    layer_masks_.insert({blk_type, mask});
}