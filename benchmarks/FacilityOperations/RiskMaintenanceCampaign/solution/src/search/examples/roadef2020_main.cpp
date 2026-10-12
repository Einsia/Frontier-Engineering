#include <cstdlib>
#include "examples/roadef2020.hpp"
#include "localsearchsolver/read_args.hpp"

#include <boost/program_options.hpp>

using namespace localsearchsolver;
using namespace localsearchsolver::roadef2020;

int main(int argc, char *argv[])
{
    namespace po = boost::program_options;

    // Parse program options

    std::string instance_path = "";
    std::string format = "";
    std::string output_path = "";
    std::string i_path = "";
    std::string c_path = "";
    std::string certificate_path = "";
    std::string team_id = "S19";
    Counter number_of_threads_1 = 1;
    Counter number_of_threads_2 = 1;
    Counter initial_solution_id = 0;
    int seed = 0;
    double time_limit = std::numeric_limits<double>::infinity();

    po::options_description desc("Allowed options");
    desc.add_options()
        ("help,h", "produce help message")
        ("name", "Team ID")
        (",p", po::value<std::string>(&instance_path), "set input file (required)")
        (",o", po::value<std::string>(&certificate_path), "set certificate file")
        (",t", po::value<double>(&time_limit), "time limit in seconds")
        (",w", po::value<Counter>(&initial_solution_id), "set initial solution id")
        (",x", po::value<Counter>(&number_of_threads_1), "set thread number 1")
        (",y", po::value<Counter>(&number_of_threads_2), "set thread number 2")
        (",s", po::value<int>(&seed), "set seed")
        (",i", po::value<std::string>(&i_path), "")
        (",c", po::value<std::string>(&c_path), "")
        (",e", "Only write output and certificate files at the end")
        ("verbose", "set verbosity")
        ;
    po::variables_map vm;
    boost::program_options::store(
            boost::program_options::command_line_parser(argc, argv)
            .options(desc)
            .style(
                boost::program_options::command_line_style::unix_style |
                boost::program_options::command_line_style::allow_long_disguise)
            .run(),
            vm);
    if (vm.count("name")) {
        std::cout << team_id << std::endl;;
        return 1;
    }
    if (vm.count("help")) {
        std::cout << desc << std::endl;;
        return 1;
    }
    try {
        po::notify(vm);
    } catch (const po::required_option& e) {
        std::cout << desc << std::endl;;
        return 1;
    }

    // If option -i has been used, then consider that it is not the challenge
    // configuration.
    if (!i_path.empty()) {
        // Get the instance from option -i.
        instance_path = i_path;
        // Get the json output form option -o.
        output_path = certificate_path;
        // Get the solution file from option -c.
        certificate_path = c_path;
    }

    // Run algorithm

    optimizationtools::Info info = optimizationtools::Info()
        .set_json_output_path(output_path)
        .set_verbose(true)
        .set_time_limit(std::numeric_limits<double>::infinity())
        .set_certificate_path(certificate_path)
        .set_only_write_at_the_end(false)
        ;

    std::mt19937_64 generator(0);

    // Read instance.
    Instance instance(instance_path, format);
    VER(info, instance << std::endl);

    // Create LocalScheme.
    LocalScheme::Parameters parameters_local_scheme;
    LocalScheme local_scheme(instance, parameters_local_scheme);

    // Run A*.
    BestFirstLocalSearchOptionalParameters<LocalScheme> parameters_best_first_local_search;
    parameters_best_first_local_search.info.set_verbose(true);
    // Fixed node budget, no wall-clock search limit.
    parameters_best_first_local_search.maximum_number_of_nodes = std::getenv("SOLVER_NODES") ? std::atoll(std::getenv("SOLVER_NODES")) : 100;
    parameters_best_first_local_search.seed = 0;
    parameters_best_first_local_search.number_of_threads_1 = 1;
    parameters_best_first_local_search.number_of_threads_2 = 1;
    parameters_best_first_local_search.initial_solution_ids = std::vector<Counter>(
            number_of_threads_2, initial_solution_id);
    parameters_best_first_local_search.new_solution_callback
        = [&local_scheme, &info](
                const LocalScheme::Solution& solution)
        {
            std::cout << "                " << local_scheme.real_cost(solution) << std::endl;

            if (local_scheme.feasible(solution)) {
                info.output->number_of_solutions++;
                double t = info.elapsed_time();
                std::string sol_str = "Solution" + std::to_string(info.output->number_of_solutions);
                PUT(info, sol_str, "Value", local_scheme.real_cost(solution));
                PUT(info, sol_str, "Time", t);
                if (!info.output->only_write_at_the_end) {
                    info.write_json_output();
                    local_scheme.write(solution, info.output->certificate_path);
                }
            }
        };
    auto output = best_first_local_search(local_scheme, parameters_best_first_local_search);

    const LocalScheme::Solution& solution = output.solution_pool.best();
    double t = info.elapsed_time();
    std::string sol_str = "Solution";
    PUT(info, sol_str, "Time", t);
    PUT(info, sol_str, "Value", local_scheme.real_cost(solution));
    info.write_json_output();
    local_scheme.write(solution, info.output->certificate_path);

    return 0;
}

