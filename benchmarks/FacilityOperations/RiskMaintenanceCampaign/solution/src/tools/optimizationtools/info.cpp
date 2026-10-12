#include "optimizationtools/info.hpp"

#include <chrono>
#include <signal.h>

using namespace optimizationtools;

volatile sig_atomic_t sigint_flag = 0;

void sigint_handler(int)
{
    sigint_flag = 1; // set flag
}

Info::Info()
{
    logger = std::shared_ptr<Logger>(new Logger());
    output = std::shared_ptr<Output>(new Output());
    start = std::chrono::high_resolution_clock::now();
}

Info::Info(const Info& info, bool keep_output, std::string keep_logger)
{
    if (keep_logger == "") {
        logger = std::shared_ptr<Logger>(info.logger);
    } else {
        // Insert 'keep_logger' string before the extension.
        std::string log_file = info.logger->log_path;
        if (log_file != "") {
            for (int i=log_file.length()-1; i>=0; --i) {
                if (log_file[i] == '.') {
                    log_file.insert(i, "_" + keep_logger);
                    break;
                }
            }
        }
        logger = std::shared_ptr<Logger>(new Logger());
        set_log_path(log_file);
    }
    output = (!keep_output)? std::shared_ptr<Output>(new Output()):
        std::shared_ptr<Output>(info.output);
    start = info.start;
    time_limit = info.time_limit;
}

Info& Info::set_log_path(std::string log_path)
{
    logger->log_path = log_path;
    if (log_path == "")
        return *this;
    if (logger->log_file.is_open())
        logger->log_file.close();
    logger->log_file.open(log_path);
    return *this;
}

Info& Info::set_sigint_handler()
{
    signal(SIGINT, sigint_handler);
    return *this;
}

double Info::elapsed_time() const
{
    std::chrono::high_resolution_clock::time_point end
        = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> time_span
        = std::chrono::duration_cast<std::chrono::duration<double>>(end - start);
    return time_span.count();
}

bool Info::terminated_by_sigint() const
{
    return sigint_flag;
}

void Info::write_json_output(std::string json_output_path) const
{
    if (json_output_path == "")
        return;
    output->mutex_json.lock();
    std::ofstream file(json_output_path);
    if (!file.good())
        throw std::runtime_error(
                "Unable to open file \"" + json_output_path + "\".");
    file << std::setw(4) << output->j << std::endl;
    output->mutex_json.unlock();
}

