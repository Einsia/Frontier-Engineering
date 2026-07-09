/**
 * @file   demand_function.h
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA) 
 * @date   Nov 2020
 */

#ifndef DREAMPLACE_DEMANDMAP_DEMAND_FUNCTION_H
#define DREAMPLACE_DEMANDMAP_DEMAND_FUNCTION_H

DREAMPLACE_BEGIN_NAMESPACE

// return non-negative value
#define DEFINE_COMPUTE_DEMAND_FUNCTION(type) \
    T compute_demand_function(int k, T bin_size, T siteL, T siteW) \
    { \
        T bin_k = k * bin_size; \
        T bin_kp1 = bin_k + bin_size; \
        return DREAMPLACE_STD_NAMESPACE::max(T(0.0), DREAMPLACE_STD_NAMESPACE::min(siteL + siteW, bin_kp1) - DREAMPLACE_STD_NAMESPACE::max(siteL, bin_k)); \
    } 

DREAMPLACE_END_NAMESPACE

#endif
