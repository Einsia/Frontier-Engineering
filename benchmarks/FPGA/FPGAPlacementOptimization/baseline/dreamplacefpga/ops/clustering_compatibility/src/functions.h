/**
 * @file   functions.h
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Oct 2020
 */

#ifndef DREAMPLACE_CLUSTERING_COMPATIBILITY_FUNCTIONS_H
#define DREAMPLACE_CLUSTERING_COMPATIBILITY_FUNCTIONS_H

DREAMPLACE_BEGIN_NAMESPACE

#define DEFINE_GAUSSIAN_AUC_FUNCTION(type) \
    T gaussian_auc_function(T mu, T sigma, T xLo, T xHi, T invSqrt) \
    { \
        T a = invSqrt / sigma; \
        T hiVal = DREAMPLACE_STD_NAMESPACE::erfc((mu - xHi) * a); \
        T loVal = DREAMPLACE_STD_NAMESPACE::erfc((mu - xLo) * a); \
        return T(0.5) * (hiVal - loVal); \
    } 

#define DEFINE_SMOOTH_CEIL_FUNCTION(type) \
    T smooth_ceil_function(T val, T threshold) \
    { \
        T r = DREAMPLACE_STD_NAMESPACE::fmod(val, T(1.0)); \
        T interm = DREAMPLACE_STD_NAMESPACE::min(r/threshold, T(1.0)); \
        return val - r + interm; \
    }

//LUT
// Reuse version
//// Note the following mergings are feasible
//// LUT1 and {LUT1, LUT2, LUT3, LUT4}
//// LUT2 and {LUT2, LUT3}
//
//// Compute white space area in the window
//RealType totalDem = std::accumulate(dem.begin(), dem.end(), 0.0);
//RealType space = std::max(winArea - totalDem, 0.0);
//RealType totalArea = totalDem + space;
//
//area[0] = (dem[0] + dem[1] + dem[2] + dem[3] + 2.0 * (dem[4] + dem[5] + space)) / totalArea;
//area[1] = (dem[0] + dem[1] + dem[2] + 2.0 * (dem[3] + dem[4] + dem[5] + space)) / totalArea;
//area[2] = (dem[0] + dem[1] + 2.0 * (dem[2] + dem[3] + dem[4] + dem[5] + space)) / totalArea;
//area[3] = (dem[0] + 2.0 * (dem[1] + dem[2] + dem[3] + dem[4] + dem[5] + space)) / totalArea;
//area[4] = 2.0;
//area[5] = 2.0;

//Hard-coded version for Ultrascale
#define DEFINE_LUT_COMPUTE_AREAS_FUNCTION(type) \
    void lut_compute_areas_function(const T winArea, T* area, const int idx, const int lBins) \
    { \
        T totalDem = T(0.0); \
        for (int x = 0; x < lBins; ++x) \
        { \
            totalDem += area[idx + x]; \
        } \
        T space = DREAMPLACE_STD_NAMESPACE::max(winArea - totalDem, T(0.0)); \
        T totalArea = totalDem + space; \
        space += space; \
        \
        T sum23 = area[idx+2] + area[idx+3]; \
        T sum45 = area[idx+4] + area[idx+5]; \
        T sum3 = area[idx+3]; \
        T sum0 = area[idx]; \
        area[idx] = (totalDem + sum45 + space) / totalArea; \
        area[idx+1] = (totalDem + sum3 + sum45 + space) / totalArea; \
        area[idx+2] = (totalDem + sum23 + sum45 + space) / totalArea; \
        area[idx+3] = (T(2.0) * totalDem - sum0 + space) / totalArea; \
        area[idx+4] = T(2.0); \
        area[idx+5] = area[idx+4]; \
    }

//Generic version based on lut_fracture
#define DEFINE_LUT_COMPUTE_AREAS_FUNCTION_GENERIC(type) \
    void lut_compute_areas_function_generic(const int* lut_fracture, const T winArea, T* area, const int idx, const int lBins) \
    { \
        T totalDem = T(0.0); \
        T dem[16]; \
        for (int x = 0; x < lBins; ++x) \
        { \
            totalDem += area[idx + x]; \
            dem[x] = area[idx + x]; \
        } \
        T space = DREAMPLACE_STD_NAMESPACE::max(winArea - totalDem, T(0.0)); \
        T totalArea = totalDem + space; \
        space += space; \
        \
        for (int lt = 0; lt < lBins; ++lt) \
        {\
            char fracture(0);\
            T val = T(0.0);\
            for (int lf = 0; lf < lBins; ++lf)\
            {\
                int lfId = lt*lBins + lf;\
                if (lut_fracture[lfId] == 1)\
                {\
                    val += dem[lf];\
                    fracture = 1;\
                } else\
                {\
                    val += T(2.0)*dem[lf]; \
                }\
            }\
            if (fracture == 1)\
            {\
                area[idx+lt] = (val + space)/totalArea;\
            } else\
            {\
                area[idx+lt] = T(2.0);\
            }\
        }\
    }

//Flop

#define DEFINE_FLOP_AGGREGATE_DEMAND_FUNCTION(type) \
    void flop_aggregate_demand_function(const T* demMap, unsigned int dIdx, T* resMap, int rIdx, const int ckSize, const int ceSize) \
    { \
        for (int ck = 0; ck < ckSize; ++ck) \
        { \
            for (int ce = 0; ce < ceSize; ++ce) \
            { \
                int cIdx = ck*ceSize + ce; \
                resMap[rIdx+cIdx] += demMap[dIdx+cIdx]; \
            } \
        } \
    }


DREAMPLACE_END_NAMESPACE

#endif
