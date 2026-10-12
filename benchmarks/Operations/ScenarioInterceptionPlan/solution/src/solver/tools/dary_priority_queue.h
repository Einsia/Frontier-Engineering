#pragma once
#include <vector>
#include <functional>
#include <algorithm>
#include <cstdint>
#include <queue> // for std::priority_queue compatibility
#include "minmax_and_dary_heap.hpp" // 包含原始堆操作

#include <vector>
#include <functional>
#include <cstdint>
#include <utility> // for std::move
#include <algorithm> // for std::swap
#include "minmax_and_dary_heap.hpp"

namespace goal {
    // Min-Max 堆适配器（优化版）
    template<typename T, typename Compare = std::less<T>>
    class minmax_priority_queue {
    public:
        using container_type = std::vector<T>;
        using value_compare = Compare;
        using value_type = T;
        using size_type = typename container_type::size_type;
        using reference = T&;
        using const_reference = const T&;

        minmax_priority_queue() = default;

        explicit minmax_priority_queue(const Compare& comp)
            : comp(comp) {}

        template<typename InputIt>
        minmax_priority_queue(InputIt first, InputIt last, const Compare& comp = Compare())
            : comp(comp), c(first, last), heap_size(c.size()) {
            make_minmax_heap(c.begin(), c.begin() + heap_size, comp);
        }

        bool empty() const { return heap_size == 0; }
        size_type size() const { return heap_size; }

        const_reference top_min() const {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            return c.front();
        }

        const_reference top_max() const {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            if (heap_size == 1) return c.front();
            if (heap_size == 2) return comp(c[0], c[1]) ? c[1] : c[0];
            return comp(c[1], c[2]) ? c[2] : c[1];
        }

        void push(const T& value) {
            if (heap_size < c.size()) {
                c[heap_size] = value;
            }
            else {
                c.push_back(value);
            }
            heap_size++;
            push_minmax_heap(c.begin(), c.begin() + heap_size, comp);
        }

        void push(T&& value) {
            if (heap_size < c.size()) {
                c[heap_size] = std::move(value);
            }
            else {
                c.push_back(std::move(value));
            }
            heap_size++;
            push_minmax_heap(c.begin(), c.begin() + heap_size, comp);
        }

        template<typename... Args>
        void emplace(Args&&... args) {
            if (heap_size < c.size()) {
                c[heap_size] = T(std::forward<Args>(args)...);
            }
            else {
                c.emplace_back(std::forward<Args>(args)...);
            }
            heap_size++;
            push_minmax_heap(c.begin(), c.begin() + heap_size, comp);
        }

        void pop_min() {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            pop_minmax_heap_min(c.begin(), c.begin() + heap_size, comp);
            heap_size--;
        }

        void pop_max() {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            pop_minmax_heap_max(c.begin(), c.begin() + heap_size, comp);
            heap_size--;
        }

        void swap(minmax_priority_queue& other) noexcept {
            c.swap(other.c);
            std::swap(heap_size, other.heap_size);
            std::swap(comp, other.comp);
        }

        // 可选：实际缩减容器大小
        void shrink_to_fit() {
            if (heap_size < c.size() / 2) {
                c.resize(heap_size);
                c.shrink_to_fit();
            }
        }

    private:
        container_type c;
        size_type heap_size = 0;
        value_compare comp;
    };

    // D-ary 堆适配器（优化版）
    template<int D, typename T, typename Compare = std::less<T>>
    class dary_priority_queue {
    public:
        using container_type = std::vector<T>;
        using value_compare = Compare;
        using value_type = T;
        using size_type = typename container_type::size_type;
        using reference = T&;
        using const_reference = const T&;

        dary_priority_queue() = default;

        explicit dary_priority_queue(const Compare& comp)
            : comp(comp) {}

        template<typename InputIt>
        dary_priority_queue(InputIt first, InputIt last, const Compare& comp = Compare())
            : comp(comp), c(first, last), heap_size(c.size()) {
            make_dary_heap<D>(c.begin(), c.begin() + heap_size, comp);
        }

        bool empty() const { return heap_size == 0; }
        size_type size() const { return heap_size; }

        const_reference top() const {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            return c.front();
        }

        void push(const T& value) {
            if (heap_size < c.size()) {
                c[heap_size] = value;
            }
            else {
                c.push_back(value);
            }
            heap_size++;
            push_dary_heap<D>(c.begin(), c.begin() + heap_size, comp);
        }

        void push(T&& value) {
            if (heap_size < c.size()) {
                c[heap_size] = std::move(value);
            }
            else {
                c.push_back(std::move(value));
            }
            heap_size++;
            push_dary_heap<D>(c.begin(), c.begin() + heap_size, comp);
        }

        template<typename... Args>
        void emplace(Args&&... args) {
            if (heap_size < c.size()) {
                c[heap_size] = T(std::forward<Args>(args)...);
            }
            else {
                c.emplace_back(std::forward<Args>(args)...);
            }
            heap_size++;
            push_dary_heap<D>(c.begin(), c.begin() + heap_size, comp);
        }

        void pop() {
            if (heap_size == 0) throw std::out_of_range("Heap is empty");
            pop_dary_heap<D>(c.begin(), c.begin() + heap_size, comp);
            heap_size--;
        }

        void swap(dary_priority_queue& other) noexcept {
            c.swap(other.c);
            std::swap(heap_size, other.heap_size);
            std::swap(comp, other.comp);
        }

        // 可选：实际缩减容器大小
        void shrink_to_fit() {
            if (heap_size < c.size() / 2) {
                c.resize(heap_size);
                c.shrink_to_fit();
            }
        }

    private:
        container_type c;
        size_type heap_size = 0;
        value_compare comp;
    };

    // 非成员交换函数
    template<typename T, typename Compare>
    void swap(minmax_priority_queue<T, Compare>& a,
        minmax_priority_queue<T, Compare>& b) noexcept {
        a.swap(b);
    }

    template<int D, typename T, typename Compare>
    void swap(dary_priority_queue<D, T, Compare>& a,
        dary_priority_queue<D, T, Compare>& b) noexcept {
        a.swap(b);
    }
}