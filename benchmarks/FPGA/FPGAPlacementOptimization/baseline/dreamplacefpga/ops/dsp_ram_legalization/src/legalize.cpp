/**
 * @file   dsp_ram_legalization.cpp
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 * @brief  Legalize DSP/RAM instances at the end of Global Placement.
 */
#include <omp.h>
#include <chrono>
#include <limits>
#include <sstream>

#include <pybind11/pybind11.h>
#include <pybind11/stl_bind.h>
#include <pybind11/numpy.h>
#include "utility/src/utils.h"
#include "utility/src/torch.h"
// Lemon for min cost flow
#include "lemon/list_graph.h"
#include "lemon/network_simplex.h"
#include "lemon/cost_scaling.h"
// local dependency
#include "dsp_ram_legalization/src/legalize_auction.h"

DREAMPLACE_BEGIN_NAMESPACE

#define INVALID -1
#define AUCTION_MAX_EPS 5.0 // Larger values mean solution is more approximate
#define AUCTION_MIN_EPS 1.0
#define AUCTION_FACTOR  0.1
#define AUCTION_MAX_ITERS 9999

//Min-cost flow to legalize DSPs/RAMs
void legalize(
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& locX,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& locY,
    int const num_nodes, int const num_sites,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& sites,
    pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& precond,
    double const &lg_max_dist_init, double const &lg_max_dist_incr,
    double const &lg_flow_cost_scale, pybind11::list &movVal, pybind11::list &out)
{
    typedef lemon::ListDigraph graphType;
    graphType graph; 
    graphType::ArcMap<double> capLo(graph);
    graphType::ArcMap<double> capHi(graph);
    graphType::ArcMap<double> cost(graph);
    std::vector<graphType::Node> lNodes, rNodes;
    std::vector<graphType::Arc> lArcs, rArcs, mArcs;
    std::vector<std::pair<int, int>> mArcPairs;

    //Source and target Nodes
    graphType::Node s = graph.addNode(), t = graph.addNode();

    //Add left nodes (blocks) and arcs between source node and left nodes
    for (int i = 0; i < num_nodes; ++i)
    {
        lNodes.emplace_back(graph.addNode());
        lArcs.emplace_back(graph.addArc(s, lNodes.back()));
        cost[lArcs.back()] = 0.0;
        capLo[lArcs.back()] = 0.0;
        capHi[lArcs.back()] = 1.0;
    }

    //Add right nodes (sites) and arc between right nodes and target node
    for (int j=0; j < num_sites; ++j)
    {
        rNodes.emplace_back(graph.addNode());
        rArcs.emplace_back(graph.addArc(rNodes.back(), t));
        cost[rArcs.back()] = 0.0;
        capLo[rArcs.back()] = 0.0;
        capHi[rArcs.back()] = 1.0;
    }

    //To improve efficiency, we do not run matching for complete bipartite graph but incrementally add arcs when needed
    double distMin = 0.0;
    double distMax = lg_max_dist_init;

    while (true)
    {
        //Generate arcs between left (blocks) and right (sites) nodes, pruning based on distance
        for (int blk = 0; blk < num_nodes; ++blk)
        {
            for (int st = 0; st < num_sites; ++st)
            {
                double dist = std::abs(locX.at(blk) - sites.at(st*2)) + std::abs(locY.at(blk) - sites.at(st*2+1));
                if (dist >= distMin && dist < distMax)
                {
                    mArcs.emplace_back(graph.addArc(lNodes[blk], rNodes[st]));
                    mArcPairs.emplace_back(blk, st);
                    double mArcCost = dist * precond.at(blk) * lg_flow_cost_scale;
                    cost[mArcs.back()] = mArcCost;
                    capLo[mArcs.back()] = 0.0;
                    capHi[mArcs.back()] = 1.0;
                }
            }
        }

        //Run min-cost flow
        lemon::NetworkSimplex<graphType, double> mcf(graph);
        mcf.stSupply(s, t, num_nodes);
        mcf.lowerMap(capLo).upperMap(capHi).costMap(cost);
        mcf.run();

        //A feasible solution must have flow size equal to the no of blocks
        //If not, we need to increase the max distance constraint
        double flowSize = 0.0;
        for (const auto &arc : rArcs)
        {
            flowSize += mcf.flow(arc);
        }
        if (flowSize != num_nodes)
        {
            //Increase searching range
            distMin = distMax;
            distMax += lg_max_dist_incr;
            continue;
        }
        ////DBG
        //std::cout << "INFO: Search range min: 0 and max: " << distMax
        //          << " for " << num_nodes << " instances and " << num_sites
        //          << " sites with " << mArcs.size() << " arcs" <<std::endl;
        //std::cout << "INFO: Legalized " << flowSize << " instances out of " << num_nodes << std::endl;
        ////DBG

        double maxMov = 0;
        double avgMov = 0;
        //If the execution hits here, we found a feasible solution
        for (int i = 0; i < mArcs.size(); ++i)
        {
            if (mcf.flow(mArcs[i]))
            {
                const auto &p = mArcPairs[i];
                double mov = std::abs(locX.at(p.first) - sites.at(p.second*2)) + std::abs(locY.at(p.first) - sites.at(p.second*2+1));
                avgMov += mov;
                maxMov = std::max(maxMov, mov);
                out[p.first] = sites.at(p.second*2);
                out[num_nodes+p.first] = sites.at(p.second*2+1);
            }
        }
        if (num_nodes)
        {
            avgMov /= num_nodes;
        }
        movVal[0] = maxMov;
        movVal[1] = avgMov;
        return;
    }
}

//Legalize using Auction Algorithm
template <typename T>
int auctionAlgorithmLauncher(
    const T* locX,
    const T* locY,
    const T* sites,
    const T* precond,
    const int num_nodes,
    const int num_sites,
    T* cost,
    T* displacements,
    int* outLoc)
{
    //Populate cost array
    for (int blk = 0; blk < num_nodes; ++blk)
    {
        for (int st = 0; st < num_sites; ++st)
        {
            T dist = std::abs(locX[blk] - sites[st*2]) + std::abs(locY[blk] - sites[st*2+1]);
            T mArcCost = dist * precond[blk];
            unsigned index = blk*num_sites+ st;
            cost[index] = mArcCost;
        }
    }

    std::vector<T> m_matrix; 
    std::vector<int> m_item2person; 
    std::vector<T> m_bids;
    std::vector<T> m_prices;
    std::vector<int> m_sbids;

    unsigned nn = num_sites*num_sites;

    m_matrix.resize(nn); 
    m_item2person.resize(num_sites); 
    m_bids.resize(nn); 
    m_prices.resize(num_sites);
    m_sbids.resize(num_sites); 

    std::copy(cost, cost+nn, m_matrix.data()); 

    int ret = run_auction<T>(
            num_nodes,
            num_sites,
            m_matrix.data(),
            outLoc,
            AUCTION_MAX_EPS,
            AUCTION_MIN_EPS,
            AUCTION_FACTOR, 
            AUCTION_MAX_ITERS, 
            m_item2person.data(), 
            m_bids.data(), 
            m_prices.data(), 
            m_sbids.data()
            );

    ////Collect node displacements
    for (int idx = 0; idx < num_nodes; ++idx)
    {
        int sId = outLoc[idx];
        if (sId != INVALID)
        {
            displacements[idx] = std::abs(locX[idx] - sites[sId*2]) + std::abs(locY[idx] - sites[sId*2+1]);
        }
    }

    return ret;
}


void legalize_auction(
        at::Tensor posX, at::Tensor posY, at::Tensor sites,
        at::Tensor precond, int num_nodes, int num_sites,
        at::Tensor cost, at::Tensor displacements,
        at::Tensor locations)
{
    CHECK_FLAT_CPU(posX);
    CHECK_CONTIGUOUS(posX);

    CHECK_FLAT_CPU(posY);
    CHECK_CONTIGUOUS(posY);

    CHECK_FLAT_CPU(sites);
    CHECK_EVEN(sites);
    CHECK_CONTIGUOUS(sites);

    CHECK_FLAT_CPU(precond);
    CHECK_CONTIGUOUS(precond);

    CHECK_FLAT_CPU(cost);
    CHECK_CONTIGUOUS(cost);

    ////DBG
    //CPUTimer::hr_clock_rep timer_start, timer_stop;
    //timer_start = CPUTimer::getGlobaltime();
    ////DBG

    DREAMPLACE_DISPATCH_FLOATING_TYPES(posX, "auctionAlgorithmLauncher", [&] {
            auctionAlgorithmLauncher<scalar_t>(
                    DREAMPLACE_TENSOR_DATA_PTR(posX, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(posY, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(sites, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(precond, scalar_t),
                    num_nodes, num_sites,
                    DREAMPLACE_TENSOR_DATA_PTR(cost, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(displacements, scalar_t),
                    DREAMPLACE_TENSOR_DATA_PTR(locations, int));
            });

    ////DBG
    //timer_stop = CPUTimer::getGlobaltime();
    //dreamplacePrint(kINFO, "Legalize using Auction Algorithm takes %g ms\n",
    //        (timer_stop - timer_start) * CPUTimer::getTimerPeriod());
    ////DBG
}

DREAMPLACE_END_NAMESPACE

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
    m.def("legalize", &DREAMPLACE_NAMESPACE::legalize, "Legalize DSP & RAM instances using Min-Cost Flow");
    m.def("legalize_auction", &DREAMPLACE_NAMESPACE::legalize_auction, "Legalize using Auction Algorithm");
}
