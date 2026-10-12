////////////////////////////////
/// usage : 1.	a simple wrapper for a random number generator.
///         2.	an online algorithm for sampling targetNum items from a data stream.
///         3.	for the case of single selection, call Sampling1::isPicked() on each element to randomly select equiprobability.
///             this class is usefull when you can not find out how many elements are there before enumerating them all,
///             you will not need to hold all possible selections and use (rand() % N) to select one by using this class.
/// 
/// note  : 1.	https://en.wikipedia.org/wiki/Reservoir_sampling
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_RANDOM_H
#define CN_HUST_GOAL_COMMON_RANDOM_H


#include <functional>
#include <random>
#include <ctime>

#include "./Typedef.h"

namespace goal {

class Random {
public:
    using Generator = std::mt19937;
    using ResultType = Generator::result_type;


    Random(int seed) : rgen(seed) {}
    Random() : rgen(generateSeed()) {}

    void setSeed() { rgen.seed(); }
    void setSeed(int seed) { rgen.seed(seed); }


    static int generateSeed() {
        return 20261006;
    }

	int producibleSeed() {				                //add by luocanhui
		return sCast<int>(rgen());
	}
    
    Generator& random_engine() { return rgen; }         //add by luocanhui

    ResultType operator()() { return rgen(); }

    // pick with probability of (numerator / denominator).
    bool isPicked(int numerator, int denominator) {
        return sCast<int>(rgen() % denominator) < numerator;
    }

    // pick from [min, max).
    template<typename T = int>
    T pick(T min, T max) {
        return sCast<T>(rgen() % sCast<ResultType>(max - min)) + min;
    }
    // pick from [0, max).
    template<typename T = int>
    T pick(T max) {
        return sCast<T>(rgen() % sCast<ResultType>(max));
    }

	template<typename T = double>
	T pickReal(T lb, T ub) { return std::uniform_real_distribution<T>(lb, ub)(rgen); }

    Generator rgen;
};


class Sampling1 { // pick single item.
public:
    enum StartCount { NoPresetItem = 0, WithPresetItem = 1 };

    using TieBreaker = std::function<bool(void)>;

    Sampling1(Random &randomNumberGenerator, int startCount = StartCount::WithPresetItem)
        : rgen(randomNumberGenerator) {
        reset(startCount);
    }

    // start a new selection on another N elements.
    // sometimes the first element is pre-selected with the possibility of 1, 
    // so you can pass 1 in this condition to leave out a isPicked() call.
    void reset(int startCount = StartCount::WithPresetItem) { pickCount = startCount; }

    // call this for each of the N elements (N times in total) to judge 
    // whether each of them is selected. 
    // only the last returned "true" means that element is selected finally.
    bool isPicked() { return ((rgen() % (++pickCount)) == 0); }

    // if (newItem != minItem), return as their strict order. else select one
    // as the minimal in the sequence of isMinimal() calls randomly.
    template<typename T>
    bool isMinimal(const T &minItem, const T &newItem, TieBreaker breakTie) {
        if (minItem < newItem) {
            return false;
        } else if (newItem == minItem) {
            return breakTie();
        } else {
            reset();
            return true;
        }
    }
    template<typename T>
    bool isMinimal(const T &minItem, const T &newItem) {
        return isMinimal(minItem, newItem, [this]() { return isPicked(); });
    }
    template<typename T>
    bool isMaximal(const T &maxItem, const T &newItem) { return isMinimal(newItem, maxItem); }

protected:
    Random &rgen;
    int pickCount; // number of elements that have been considered.
};

// count | 1 2 3 4 ...  k   k+1   k+2   k+3  ...  n
// ------|------------------------------------------
// index | 0 1 2 3 ... k-1   k    k+1   k+2  ... n-1
// prob. | 1 1 1 1 ...  1  k/k+1 k/k+2 k/k+3 ... k/n
class Sampling {
public:
    Sampling(Random &randomNumberGenerator, int targetNumber)
        : rgen(randomNumberGenerator), targetNum(targetNumber), pickCount(0) {
    }

    // return 0 for not picked.
    // return an integer i \in [1, targetNum] if it is the i_th item in the picked set.
    int isPicked() {
        if ((++pickCount) <= targetNum) {
            return pickCount;
        } else {
            int i = rgen.pick(pickCount) + 1;
            return (i <= targetNum) ? i : 0;
        }
    }

    // return -1 for no need to replace any item.
    // return an integer i \in [0, targetNum) as the index to be replaced in the picked set.
    int replaceIndex() {
        if (pickCount < targetNum) {
            return pickCount++;
        } else {
            int i = rgen.pick(++pickCount);
            return (i < targetNum) ? i : -1;
        }
    }

    void reset() {
        pickCount = 0;
    }

protected:
    Random &rgen;
    int targetNum;
    int pickCount;
};

}


#endif // CN_HUST_GOAL_COMMON_RANDOM_H
