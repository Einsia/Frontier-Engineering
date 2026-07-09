/*************************************************************************
    > File Name: BenchMetrics.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "BenchMetrics.h"
#include "utility/src/Msg.h"

DREAMPLACE_BEGIN_NAMESPACE

BenchMetrics::BenchMetrics()
{
    initPlaceDBFlag = false; 
    //initAlgoDBFlag = false; 
}

void BenchMetrics::print() const
{
    if (initPlaceDBFlag)
    {
        dreamplacePrint(kINFO, "design name = %s\n", designName.c_str());
        dreamplacePrint(kINFO, "number of macros = %lu\n", numMacro);
        dreamplacePrint(kINFO, "number of nodes = %lu (movable %lu, fixed %lu)\n", numNodes, numMovable, numFixed);
        dreamplacePrint(kINFO, "number of nets = %lu\n", numNets);
        dreamplacePrint(kINFO, "number of pin connections = %lu\n", numPins);
        dreamplacePrint(kINFO, "site dimensions = (%d, %d)\n", siteWidth, rowHeight);
        dreamplacePrint(kINFO, "die dimensions = (%d, %d, %d, %d)\n", dieArea.xl(), dieArea.yl(), dieArea.xh(), dieArea.yh());
        if (numIgnoredNet)
            dreamplacePrint(kWARN, "# ingored nets = %lu (nets belong to the same cells)\n", numIgnoredNet);
        if (numDuplicateNet)
            dreamplacePrint(kWARN, "# duplicate nets = %lu\n", numDuplicateNet);
    }
}

DREAMPLACE_END_NAMESPACE
