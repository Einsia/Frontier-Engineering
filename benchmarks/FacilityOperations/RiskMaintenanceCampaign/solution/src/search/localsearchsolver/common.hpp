#pragma once

#include "optimizationtools/info.hpp"
#include "optimizationtools/utils.hpp"

#include <cstdint>
#include <set>

namespace localsearchsolver
{

using Seed = int64_t;
using Counter = int64_t;

////////////////////////////////////////////////////////////////////////////////
////////////////////////////// Tuple operations ////////////////////////////////
////////////////////////////////////////////////////////////////////////////////

template<typename T, T...>
struct integer_sequence { };

template<std::size_t N, std::size_t... I>
struct gen_indices : gen_indices<(N - 1), (N - 1), I...> { };
template<std::size_t... I>
struct gen_indices<0, I...> : integer_sequence<std::size_t, I...> { };

// to_string(t) //

template<typename H>
std::stringstream& to_string_impl(std::stringstream& ss, H&& h)
{
    ss << std::forward<H>(h);
    return ss;
}

template<typename H, typename... T>
std::stringstream& to_string_impl(std::stringstream& ss, H&& h, T&&... t)
{
    to_string_impl(ss, std::forward<T>(t)...);
    ss << ", " << std::forward<H>(h);
    return ss;
}

template<typename... T, std::size_t... I>
std::stringstream to_string(
        const std::tuple<T...>& tup,
        integer_sequence<std::size_t, I...>)
{
    std::stringstream ss;
    int ctx[] = { (to_string_impl(ss, std::get<I>(tup)...), 0), 0 };
    (void)ctx;
    return ss;
}

template<typename... T>
std::string to_string(const std::tuple<T...>& tup)
{
    return to_string(tup, gen_indices<sizeof...(T)>{}).str();
}

// dominates(t1, t2) //

template<typename... T, std::size_t... I>
bool dominates(
        const std::tuple<T...>& t1,
        const std::tuple<T...>& t2,
        integer_sequence<std::size_t, I...>)
{
   using unused = bool[];

   bool b { true };

   (void)unused { b, (b = b && std::get<I>(t1) <= std::get<I>(t2))... };

   return b;
}

template <typename ... T>
bool dominates(
        const std::tuple<T...>& t1,
        const std::tuple<T...>& t2)
{
    return dominates(t1, t2, gen_indices<sizeof...(T)>{});
}

// sum_t //

template <typename ... Ts, std::size_t ... Is>
std::tuple<Ts...> sum_t(
        std::tuple<Ts...> const & t1,
        std::tuple<Ts...> const & t2,
        integer_sequence<std::size_t, Is...> const &)
{
     return { (std::get<Is>(t1) + std::get<Is>(t2))... };
}

template <typename ... Ts>
std::tuple<Ts...> operator+(
        std::tuple<Ts...> const & t1,
        std::tuple<Ts...> const & t2)
{
    return sum_t(t1, t2, gen_indices<sizeof...(Ts)>{});
}

// diff_t //

template <typename ... Ts, std::size_t ... Is>
std::tuple<Ts...> diff_t(
        std::tuple<Ts...> const & t1,
        std::tuple<Ts...> const & t2,
        integer_sequence<std::size_t, Is...> const &)
{
     return { (std::get<Is>(t1) - std::get<Is>(t2))... };
}

template <typename ... Ts>
std::tuple<Ts...> operator-(
        std::tuple<Ts...> const & t1,
        std::tuple<Ts...> const & t2)
{
    return diff_t(t1, t2, gen_indices<sizeof...(Ts)>{});
}

// worst and best //

template <typename> struct Helper;

template <typename... Ts>
struct Helper<std::tuple<Ts...>>
{
    static std::tuple<Ts...> max()
    {
        return { std::numeric_limits<Ts>::max()... };
    }

    static std::tuple<Ts...> min()
    {
        return { std::numeric_limits<Ts>::lowest()... };
    }
};

template <typename T>
T worst() { return Helper<T>::max(); }

template <typename T>
T best() { return Helper<T>::min(); }


////////////////////////////////////////////////////////////////////////////////
//////////////////////// print_local_scheme_global_cost ////////////////////////
////////////////////////////////////////////////////////////////////////////////

template<typename, typename T>
struct HasPrintGlobalCostMethod
{
    static_assert(
        std::integral_constant<T, false>::value,
        "Second template parameter needs to be of function type.");
};

template<typename C, typename Ret, typename... Args>
struct HasPrintGlobalCostMethod<C, Ret(Args...)>
{

private:

    template<typename T>
    static constexpr auto check(T*) -> typename std::is_same<decltype(std::declval<T>().global_cost_export(std::declval<Args>()...)), Ret>::type;

    template<typename>
    static constexpr std::false_type check(...);

    typedef decltype(check<C>(0)) type;

public:

    static constexpr bool value = type::value;

};

template<typename LocalScheme>
std::string print_local_scheme_global_cost(
        LocalScheme&,
        const typename LocalScheme::GlobalCost& global_cost,
        std::false_type)
{
    return to_string(global_cost);
}

template<typename LocalScheme>
std::string print_local_scheme_global_cost(
        LocalScheme& local_scheme,
        const typename LocalScheme::GlobalCost& global_cost,
        std::true_type)
{
    return local_scheme.global_cost_export(global_cost);
}

template<typename LocalScheme>
std::string print_local_scheme_global_cost(
        LocalScheme& local_scheme,
        const typename LocalScheme::GlobalCost& global_cost)
{
    return print_local_scheme_global_cost(
            local_scheme,
            global_cost,
            std::integral_constant<
                bool,
                HasPrintGlobalCostMethod<LocalScheme,
                std::string(const typename LocalScheme::GlobalCost&)>::value>());
}


////////////////////////////////////////////////////////////////////////////////
//////////////////////////////// Solution Pool /////////////////////////////////
////////////////////////////////////////////////////////////////////////////////

template <typename Scheme>
struct SolutionPoolComparator
{
    typedef typename Scheme::Solution Solution;

    SolutionPoolComparator(const Scheme& local_scheme):
        local_scheme(local_scheme) { }

    const Scheme& local_scheme;

    bool operator()(
            const Solution& solution_1,
            const Solution& solution_2) const {
        return local_scheme.global_cost(solution_1)
            < local_scheme.global_cost(solution_2);
    }
};

template <typename Scheme>
class SolutionPool
{
    typedef typename Scheme::Solution Solution;
    typedef typename Scheme::GlobalCost GlobalCost;

public:

    SolutionPool(const Scheme& local_scheme, Counter size_max):
        scheme_(local_scheme),
        size_max_(size_max),
        solution_pool_comparator_(local_scheme),
        solutions_(solution_pool_comparator_),
        worst_(local_scheme.empty_solution()),
        best_(local_scheme.empty_solution()) { }

    virtual ~SolutionPool() { }

    const std::multiset<Solution, SolutionPoolComparator<Scheme>>& solutions() const { return solutions_; };
    const Solution& best() { return best_; }
    const Solution& worst() { return worst_; }
    Counter size() const { return solutions_.size(); }

    int add(
            const Solution& solution,
            const std::stringstream& ss,
            optimizationtools::Info& info)
    {
        info.output->mutex_solutions.lock();
        // If the solution is worse than the worst solution of the pool, stop.
        if ((Counter)solutions_.size() >= size_max_) {
            if (scheme_.global_cost(solution)
                    > scheme_.global_cost(*std::prev(solutions_.end()))) {
                info.output->mutex_solutions.unlock();
                return 0;
            }
        }
        //for (const auto& solution_tmp: solutions_)
        //    if (solution == solution_tmp)
        //        return 0;
        // If new best solution, display.
        bool new_best = (solutions_.size() == 0)
            || (scheme_.global_cost(solution) < scheme_.global_cost(*solutions_.begin()));
        // Add new solution to solution pool.
        solutions_.insert(solution);
        if (new_best) {
            info.output->number_of_solutions++;
            double t = info.elapsed_time();
            std::string sol_str = "Solution" + std::to_string(info.output->number_of_solutions);
            PUT(info, sol_str, "Value", print_local_scheme_global_cost(scheme_, scheme_.global_cost(solution)));
            PUT(info, sol_str, "Time", t);
            PUT(info, sol_str, "Comment", ss.str());
            if (!info.output->only_write_at_the_end) {
                info.write_json_output();
                scheme_.write(*solutions_.begin(), info.output->certificate_path);
            }
        }
        // If the pool size is now above its maximum allowed size, remove worst
        // solutions from it.
        if ((Counter)solutions_.size() > size_max_)
            solutions_.erase(std::prev(solutions_.end()));
        best_ = *solutions_.begin();
        worst_ = *std::prev(solutions_.end());
        info.output->mutex_solutions.unlock();
        return (new_best)? 2: 1;
    }

    void display_init(optimizationtools::Info& info)
    {
        VER(info,
                std::setw(10) << "Time"
                << std::setw(40) << "Value"
                << std::setw(40) << "Comment" << std::endl
                << std::setw(10) << "----"
                << std::setw(40) << "-----"
                << std::setw(40) << "-------" << std::endl);
    }

    void display(const std::stringstream& ss, optimizationtools::Info& info)
    {
        double t = info.elapsed_time();
        std::streamsize precision = std::cout.precision();
        VER(info,
                std::setw(10) << std::fixed << std::setprecision(3) << t << std::defaultfloat << std::setprecision(precision)
                << std::setw(40) << to_string(scheme_.global_cost(best()))
                << std::setw(40) << ss.str()
                << std::endl);
    }

    void display_end(optimizationtools::Info& info)
    {
        double t = info.elapsed_time();
        VER(info, std::endl
                << "Final statistics" << std::endl
                << "----------------" << std::endl
                << "Value:                      " << to_string(scheme_.global_cost(best())) << std::endl
                << "Time:                       " << t << std::endl);

        std::string sol_str = "Solution";
        PUT(info, sol_str, "Time", t);
        PUT(info, sol_str, "Value", print_local_scheme_global_cost(scheme_, scheme_.global_cost(*solutions_.begin())));
        info.write_json_output();
        scheme_.write(best_, info.output->certificate_path);
    }

private:

    const Scheme& scheme_;
    Counter size_max_;
    SolutionPoolComparator<Scheme> solution_pool_comparator_;
    std::multiset<Solution, SolutionPoolComparator<Scheme>> solutions_;
    Solution worst_;
    Solution best_;

};


////////////////////////////////////////////////////////////////////////////////
////////////////////////////// global_cost_cutoff //////////////////////////////
////////////////////////////////////////////////////////////////////////////////

template<typename, typename T>
struct HasGlobalCostCutoffMethod
{
    static_assert(
        std::integral_constant<T, false>::value,
        "Second template parameter needs to be of function type.");
};

template<typename C, typename Ret, typename... Args>
struct HasGlobalCostCutoffMethod<C, Ret(Args...)>
{

private:

    template<typename T>
    static constexpr auto check(T*) -> typename std::is_same<decltype(std::declval<T>().global_cost_cutoff(std::declval<Args>()...)), Ret>::type;

    template<typename>
    static constexpr std::false_type check(...);

    typedef decltype(check<C>(0)) type;

public:

    static constexpr bool value = type::value;

};

template<typename LocalScheme>
typename LocalScheme::GlobalCost global_cost_cutoff(
        const LocalScheme&,
        double,
        std::false_type)
{
    return best<typename LocalScheme::GlobalCost>();
}

template<typename LocalScheme>
typename LocalScheme::GlobalCost global_cost_cutoff(
        const LocalScheme& local_scheme,
        double cutoff,
        std::true_type)
{
    return local_scheme.global_cost_cutoff(cutoff);
}

template<typename LocalScheme>
typename LocalScheme::GlobalCost global_cost_cutoff(
        const LocalScheme& local_scheme,
        double cutoff)
{
    typedef typename LocalScheme::GlobalCost GlobalCost;

    return global_cost_cutoff(
            local_scheme,
            cutoff,
            std::integral_constant<
                bool,
                HasGlobalCostCutoffMethod<LocalScheme,
                GlobalCost(double)>::value>());
}


////////////////////////////////////////////////////////////////////////////////
//////////////////////// print_local_scheme_parameters /////////////////////////
////////////////////////////////////////////////////////////////////////////////

template<typename, typename T>
struct HasPrintParametersMethod
{
    static_assert(
        std::integral_constant<T, false>::value,
        "Second template parameter needs to be of function type.");
};

template<typename C, typename Ret, typename... Args>
struct HasPrintParametersMethod<C, Ret(Args...)>
{

private:

    template<typename T>
    static constexpr auto check(T*) -> typename std::is_same<decltype(std::declval<T>().print_parameters(std::declval<Args>()...)), Ret>::type;

    template<typename>
    static constexpr std::false_type check(...);

    typedef decltype(check<C>(0)) type;

public:

    static constexpr bool value = type::value;

};

template<typename LocalScheme>
void print_local_scheme_parameters(
        LocalScheme&,
        optimizationtools::Info&,
        std::false_type)
{
}

template<typename LocalScheme>
void print_local_scheme_parameters(
        LocalScheme& local_scheme,
        optimizationtools::Info& info,
        std::true_type)
{
    VER(info, std::endl
            << "Local scheme parameters" << std::endl
            << "-----------------------" << std::endl);
    local_scheme.print_parameters(info);
}

template<typename LocalScheme>
void print_local_scheme_parameters(
        LocalScheme& local_scheme,
        optimizationtools::Info& info)
{
    print_local_scheme_parameters(
            local_scheme,
            info,
            std::integral_constant<
                bool,
                HasPrintParametersMethod<LocalScheme,
                void(optimizationtools::Info&)>::value>());
}


////////////////////////////////////////////////////////////////////////////////
//////////////////////// print_local_scheme_statistics /////////////////////////
////////////////////////////////////////////////////////////////////////////////

template<typename, typename T>
struct HasPrintStatisticsMethod
{
    static_assert(
        std::integral_constant<T, false>::value,
        "Second template parameter needs to be of function type.");
};

template<typename C, typename Ret, typename... Args>
struct HasPrintStatisticsMethod<C, Ret(Args...)>
{

private:

    template<typename T>
    static constexpr auto check(T*) -> typename std::is_same<decltype(std::declval<T>().print_statistics(std::declval<Args>()...)), Ret>::type;

    template<typename>
    static constexpr std::false_type check(...);

    typedef decltype(check<C>(0)) type;

public:

    static constexpr bool value = type::value;

};

template<typename LocalScheme>
void print_local_scheme_statistics(
        LocalScheme&,
        optimizationtools::Info&,
        std::false_type)
{
}

template<typename LocalScheme>
void print_local_scheme_statistics(
        LocalScheme& local_scheme,
        optimizationtools::Info& info,
        std::true_type)
{
    VER(info, std::endl
            << "Local scheme statistics" << std::endl
            << "-----------------------" << std::endl);
    local_scheme.print_statistics(info);
}

template<typename LocalScheme>
void print_local_scheme_statistics(
        LocalScheme& local_scheme,
        optimizationtools::Info& info)
{
    print_local_scheme_statistics(
            local_scheme,
            info,
            std::integral_constant<
                bool,
                HasPrintStatisticsMethod<LocalScheme,
                void(optimizationtools::Info&)>::value>());
}

}

