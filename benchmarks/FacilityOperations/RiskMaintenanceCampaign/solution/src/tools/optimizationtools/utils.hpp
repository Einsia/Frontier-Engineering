#pragma once

#include <algorithm>
#include <random>
#include <sstream>

namespace optimizationtools
{

template <typename T>
std::vector<T> bob_floyd(T sample_size, T upper_bound, std::mt19937_64& generator);

inline std::vector<std::string> split(std::string line, char c = ',');

inline void hash_combine(std::size_t& seed, const size_t v);

/******************************************************************************/

template <typename T>
std::vector<T> bob_floyd(T sample_size, T upper_bound, std::mt19937_64& generator)
{
    std::vector<T> samples;
    for (T d = upper_bound - sample_size; d < upper_bound; d++) {
        T t = std::uniform_int_distribution<T>(0, d)(generator);
        if (std::find(samples.begin(), samples.end(), t) == samples.end()) {
            samples.push_back(t);
        } else {
            samples.push_back(d);
        }
    }
    return samples;
}

static inline void ltrim(std::string &s) {
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](int ch) {
        return !std::isspace(ch);
    }));
}

static inline void rtrim(std::string &s) {
    s.erase(std::find_if(s.rbegin(), s.rend(), [](int ch) {
        return !std::isspace(ch);
    }).base(), s.end());
}

std::vector<std::string> split(std::string line, char c)
{
    std::vector<std::string> v;
    std::string line_without_extra_whitespaces;
    unique_copy(line.begin(), line.end(),
            std::back_insert_iterator<std::string>(line_without_extra_whitespaces),
            [](char a, char b){ return isspace(a) && isspace(b);});
    rtrim(line_without_extra_whitespaces);
    ltrim(line_without_extra_whitespaces);
    std::stringstream ss(line_without_extra_whitespaces);
    std::string tmp;
    while (getline(ss, tmp, c)) {
        rtrim(tmp);
        ltrim(tmp);
        v.push_back(tmp);
    }
    return v;
}

void hash_combine(std::size_t& seed, const size_t v)
{
    seed ^= v + 0x9e3779b9 + (seed << 6) + (seed >> 2);
}

}

