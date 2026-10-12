#pragma once

#include <vector>
#include <cstdint>
#include <cassert>
#include <random>
#include <algorithm>

namespace optimizationtools
{

/*

Removing elements while iterating:

for (auto it = set.begin(); it != set.end();) {
    bool remove = true;
    // ...
    if (remove) {
        solution.remove(*it);
    } else {
        it++;
    }
}

*/

class IndexedSet
{

public:

    typedef int64_t Index;
    typedef int64_t Position;

    inline IndexedSet(Index number_of_elements);
    inline virtual ~IndexedSet() { }

    inline bool empty() const { return number_of_elements_ == 0; }
    inline Position size() const { return number_of_elements_; }
    inline bool contains(Index index) const { return (positions_[index] < number_of_elements_); }
    inline Position position(Index index) const { return positions_[index]; }

    inline std::vector<Index>::const_iterator begin() const { return elements_.begin(); }
    inline std::vector<Index>::const_iterator end() const { return elements_.begin() + number_of_elements_; }
    inline std::vector<Index>::const_iterator out_begin() const { return elements_.begin() + number_of_elements_; }
    inline std::vector<Index>::const_iterator out_end() const { return elements_.end(); }

    inline bool add(Index index);
    inline bool remove(Index index);
    inline void clear() { number_of_elements_ = 0; }
    inline void fill() { number_of_elements_ = elements_.size(); }
    inline void shuffle(std::mt19937_64& generator);
    inline void shuffle_in(std::mt19937_64& generator);
    inline void shuffle_out(std::mt19937_64& generator);

    inline bool check() const;

private:

    std::vector<Index> elements_;
    std::vector<Position> positions_;
    Position number_of_elements_ = 0;

};

/******************************************************************************/

inline IndexedSet::IndexedSet(Index number_of_elements):
    elements_(number_of_elements),
    positions_(number_of_elements)
{
    for (Index index = 0; index < number_of_elements; ++index) {
        elements_[index] = index;
        positions_[index] = index;
    }
}

inline bool IndexedSet::add(Index index)
{
    Position position = positions_[index];
    if (position < number_of_elements_)
        return false;
    elements_[position] = elements_[number_of_elements_];
    elements_[number_of_elements_] = index;
    positions_[elements_[position]] = position;
    positions_[elements_[number_of_elements_]] = number_of_elements_;
    number_of_elements_++;
    return true;
}

inline bool IndexedSet::remove(Index index)
{
    Position position = positions_[index];
    if (position >= number_of_elements_)
        return false;
    elements_[position] = elements_[number_of_elements_ - 1];
    elements_[number_of_elements_ - 1] = index;
    positions_[elements_[position]] = position;
    positions_[elements_[number_of_elements_ - 1]] = number_of_elements_ - 1;
    number_of_elements_--;
    return true;
}

inline void IndexedSet::shuffle_in(std::mt19937_64& generator)
{
    std::shuffle(elements_.begin(), elements_.begin() + number_of_elements_, generator);
    for (Position position = 0; position < number_of_elements_; ++position)
        positions_[elements_[position]] = position;
}

inline void IndexedSet::shuffle_out(std::mt19937_64& generator)
{
    std::shuffle(elements_.begin() + number_of_elements_, elements_.end(), generator);
    for (Position position = number_of_elements_; position < (Position)elements_.size(); ++position)
        positions_[elements_[position]] = position;
}

inline void IndexedSet::shuffle(std::mt19937_64& generator)
{
    std::shuffle(elements_.begin(), elements_.begin() + number_of_elements_, generator);
    std::shuffle(elements_.begin() + number_of_elements_, elements_.end(), generator);
    for (Position position = 0; position < (Position)elements_.size(); ++position)
        positions_[elements_[position]] = position;
}

}

