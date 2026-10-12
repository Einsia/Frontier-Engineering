#pragma once

#include <iostream>
#include <fstream>
#include <sstream>
#include <mutex>
#include <iomanip>
#include <memory>

#include <nlohmann/json.hpp>

#define VER(info, message) \
    if (info.output->verbose) { \
        info.output->mutex_cout.lock(); \
        std::cout << message; \
        info.output->mutex_cout.unlock(); \
    }

#define PUT(info, category, key, value) \
    info.output->mutex_json.lock(); \
    info.output->j[category][key] = value; \
    info.output->mutex_json.unlock();

#ifdef NDEBUG

#define DBG(x)
#define LOG(info, message) {  }
#define LOG_FOLD_START(info, message) {  }
#define LOG_FOLD_END(info, message) {  }
#define LOG_FOLD(info, message) {  }
#define LOG_ON(info) {  }
#define LOG_OFF(info) {  }

#else

#define DBG(x) x
#define LOG(info, message) \
    { \
        if (info.logger->on && info.logger->level <= info.logger->maximum_log_level) { \
            if (info.logger->log_file.is_open()) \
                info.logger->log_file << message; \
            if (info.logger->log2stderr) \
                std::cerr << message; \
        } \
    }
#define LOG_FOLD_START(info, message) \
    { \
        info.logger->level++; \
        LOG(info, "{{{ " << message); \
    }
#define LOG_FOLD_END(info, message) \
    { \
        LOG(info, message << " }}}" << std::endl); \
        info.logger->level--; \
    }
#define LOG_FOLD(info, message) \
    { \
        info.logger->level++; \
        LOG(info, "{{{ " << message << " }}}" << std::endl); \
        info.logger->level--; \
    }
#define LOG_ON(info)  { info.logger->on = true; }
#define LOG_OFF(info) { info.logger->on = false; }

#endif

#define TOL 0.000001

namespace optimizationtools
{

/**
 * Structure passed as argument of optimization algorithms which simplifies
 * several aspects of the implementation.
 *
 * It is designed such that the user can use a default value:
 *     algorithm(Instance instance, Info info = Info());
 *
 * Thus, this works:
 *     algorithm(instance);
 * as well as:
 *     Info info = Info().set_time_limit(60);
 *     algorithm(instance, info);
 *
 * Verbosity features:
 * - Enable verbosity:
 *     info.set_verbose(true);
 * - Write something on the standard output (thread safe):
 *     VER(info, "Print " << message);
 *
 * Certificate path features:
 * - Set the path of the certificate file:
 *     info.set_certificate_path("certificate_path");
 *
 * JSON output features:
 * - Set the path of the JSON output file:
 *     info.set_json_output_path("json_output_path");
 * - Write something in the JSON output file (thread safe):
 *     PUT(info, "category", "key", value);
 *
 * Logging features:
 * - When compiling with NODEBUG, loggin is disabled and no line related to the
 *   logging is kept in the final executable.
 * - Set the path of the log file:
 *     info.set_log_path("log_path");
 * - Also write the log to the standard error output:
 *     info.set_log2stderr(true);
 * - Disable/enable logging (enabled by default):
 *     LOG_OFF(info);
 *     LOG_ON(info);
 * - Write some logging information:
 *     LOG(info, "I want to log " << message << std::endl);
 * - Start a new fold:
 *     LOG_FOLD_START(info, "new fold" << std::endl);
 * - End the current fold:
 *     LOG_FOLD_END(info, "new fold");
 *
 * Time limit features:
 * - Set the time limit (in seconds) of the algorithm:
 *     info.set_time_limit(60);
 * - Check if the time limit has been reached:
 *     info.check_time();
 * - Get the elapsed time:
 *     info.elapsed_time();
 * - Get the remaining time:
 *     info.remaining_time();
 * - Reset the starting time:
 *     info.reset_time();
 *
 * SIGINT handler:
 * - Enable SIGINT handler:
 *     info.set_sigint_handler()
 * - Check if the program has received SIGINT signal:
 *     info.terminated_by_sigint()
 * - Check SIGINT and time limit:
 *     info.needs_to_end()
 *
 * Example of function to update an incumbent solution:

void update_solution(
        Solution& incumbent_solution,
        const Solution& new_solution,
        optimizationtools::Info& info)
{
    info.output->mutex_solutions.lock();

    if (incumbent_solution is worse than new_solution) {
        incumbent_solution = new_solution;

        info.output->number_of_solutions++;
        double t = round(info.elapsed_time() * 10000) / 10000;
        VER(info,
                "Time: " << t
                << "; New solution with value: " << incumbent_solution.value()
                << std::endl);
        std::string sol_str = "Solution" + std::to_string(info.output->number_of_solutions);
        PUT(info, sol_str, "Value", incumbent_solution.value());
        PUT(info, sol_str, "Time", t);
        if (!info.output->only_write_at_the_end) {
            info.write_json_output();
            solution.write(info.output->certificate_path);
        }
    }

    info.output->mutex_solutions.unlock();
}

 */
struct Info
{

public:

    /**
     * Logger structure.
     */
    struct Logger
    {
        /** Enable logging. */
        bool on = true;
        /** Enable writing logs to standard error output. */
        bool log2stderr = false;
        /** Log file. */
        std::ofstream log_file;
        /** Path to the log file. */
        std::string log_path;
        /** Current level of the logs. */
        int level = 0;
        /** Maximum level of the logs. */
        int maximum_log_level = 999;
    };

    /**
     * Output structure.
     *
     * It stores everything related to the certificate file and the the JSON output
     * file.
     */
    struct Output
    {
        /** JSON output file. */
        nlohmann::json j;
        /** Only write outputs at the end of the algorithm. */
        bool only_write_at_the_end = true;
        /** Path to the JSON output file. */
        std::string json_output_path  = "";
        /** Path to the certificate file. */
        std::string certificate_path = "";
        /** Mutex to access the JSON output. */
        std::mutex mutex_json;
        /** Mutex to access the standard output. */
        std::mutex mutex_cout;
        /** Mutex to manipulate solutions. */
        std::mutex mutex_solutions;
        /** Verbosity. */
        bool verbose = false;
        /** Counter for the number of solutions. */
        int number_of_solutions = 0;
        /** Counter for the number of bounds. */
        int number_of_bounds = 0;
    };


    /*
     * Constructors and destructors.
     */

    /** Constructor. */
    Info();

    /**
     * Copy an existing Info structure.
     *
     * This is meant to be used in parallel algorithms.
     *
     * Keep the Output structure iff 'keep_output == true'.
     *
     * Keep the Logging structure iff 'keep_logger == ""'.  Otherwise, create a
     * new Logger structure with 'logger_string' append to the log path (before
     * the extension).
     *
     * Note that Info(info, false, "newthread") keeps the time limit.
     */
    Info(const Info& info, bool keep_output, std::string keep_logger);


    /*
     * Set options.
     */

    /** Enable verbosity. */
    Info& set_verbose(bool verbose) { output->verbose = verbose; return *this; }

    /** Set JSON output path. */
    Info& set_json_output_path(std::string outputfile) { output->json_output_path = outputfile; return *this; }

    /** Set certificate path. */
    Info& set_certificate_path(std::string certfile) { output->certificate_path = certfile; return *this; }

    /** Only write the output files at the end of the algorithm. */
    Info& set_only_write_at_the_end(bool b) { output->only_write_at_the_end = b; return *this; }

    /** Enable logs to standard error output. */
    Info& set_log2stderr(bool log2stderr) { logger->log2stderr = log2stderr; return *this; }

    /** Set a maximum level for the logs. */
    Info& set_maximum_log_level(int maximum_log_level) { logger->maximum_log_level = maximum_log_level; return *this; }

    /** Set the time limit of the algorithm. */
    Info& set_time_limit(double t) { time_limit = t; return *this; }

    /** Set the path of the log file. */
    Info& set_log_path(std::string log_path);

    /** Set SIGINT handler. */
    Info& set_sigint_handler();

    /*
     * Time.
     */

    /** Get the elapsed time since the start of the algorithm. */
    double elapsed_time() const;

    /** Get the remaining time before reaching the time limit. */
    double remaining_time() const { return std::max(0.0, time_limit - elapsed_time()); }

    /** Return 'true' iff the time limit has not been reached yet. */
    bool check_time() const { return elapsed_time() <= time_limit; }

    /** Reset the starting time of the algorithm. */
    void reset_time() { start = std::chrono::high_resolution_clock::now(); }

    /** Return 'true' iff the program has received the SIGINT signal. */
    bool terminated_by_sigint() const;

    /** Return 'true' iff the algorithm needs to end. */
    bool needs_to_end() const { return !check_time() || terminated_by_sigint(); }

    /*
     * JSON output.
     */

    /** Write the JSON output file. */
    void write_json_output(std::string json_output_path) const;

    /** Write the JSON output file. */
    void write_json_output() const { write_json_output(output->json_output_path); }


    /*
     * Attributes
     */

    /** Pointer to the logger. */
    std::shared_ptr<Logger> logger = NULL;

    /** Pointer to the output structure. */
    std::shared_ptr<Output> output = NULL;

    /** Start time of the algorithm. */
    std::chrono::high_resolution_clock::time_point start;

    /** Time limit of the algorithm. */
    double time_limit = std::numeric_limits<double>::infinity();

};

}

