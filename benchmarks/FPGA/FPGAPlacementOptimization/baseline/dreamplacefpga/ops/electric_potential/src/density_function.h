/**
 * @file   density_function.h
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 */

#ifndef DREAMPLACE_ELECTRIC_POTENTIAL_DENSITY_FUNCTION_H
#define DREAMPLACE_ELECTRIC_POTENTIAL_DENSITY_FUNCTION_H

DREAMPLACE_BEGIN_NAMESPACE

//Added by Rachel
// return non-negative value
#define DEFINE_FPGA_DENSITY_FUNCTION(type) \
    T fpga_density_function(T xh, T xl, int k, T bin_size) \
    { \
        T bin_k = k * bin_size; \
        T bin_kp1 = bin_k + bin_size; \
        return DREAMPLACE_STD_NAMESPACE::max(T(0.0), DREAMPLACE_STD_NAMESPACE::min(xh, bin_kp1) - DREAMPLACE_STD_NAMESPACE::max(xl, bin_k)); \
    } 

DREAMPLACE_END_NAMESPACE

#endif
