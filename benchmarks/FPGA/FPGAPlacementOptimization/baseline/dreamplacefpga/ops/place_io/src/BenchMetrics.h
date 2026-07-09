/*************************************************************************
    > File Name: BenchMetrics.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_BENCHMETRICS_H
#define DREAMPLACE_BENCHMETRICS_H

#include <string>
#include <vector>
#include "Box.h"

DREAMPLACE_BEGIN_NAMESPACE

/// ================================================
/// a simple class storing metrics for benchmarks 
/// which is to help report benchmark statistics 
/// ================================================

struct BenchMetrics
{
    /// metrics from PlaceDB
    std::string designName; 
    std::size_t numMacro;
    std::size_t numNodes; 
    std::size_t numMovable;
    std::size_t numFixed;
    //std::size_t numIOPin;
    std::size_t numNets;
    std::size_t numPins;
    unsigned siteWidth;
    unsigned rowHeight;
    Box<int> dieArea;
    std::size_t numIgnoredNet; 
    std::size_t numDuplicateNet; 

    bool initPlaceDBFlag; ///< a flag indicates whether it is initialized, must set to true after initialization, from PlaceDB
    //bool initAlgoDBFlag;

    BenchMetrics();

    void print() const;
};

DREAMPLACE_END_NAMESPACE

#endif
