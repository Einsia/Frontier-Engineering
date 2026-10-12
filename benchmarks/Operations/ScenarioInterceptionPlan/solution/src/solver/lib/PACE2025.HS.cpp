#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#else
#include <unistd.h>
#include <csignal>
#endif

#include <iostream>

#include "solver/lib/instance.h"
#include "solver/lib/greedy_solver.h"
#include "solver/analysis/analyzer.h"
#include "solver/lib/ls_solver.h"
#include "solver/tools/NaiveThreadPool.h"


// 捕获全局终止信号
#ifdef _WIN32
BOOL WINAPI CtrlHandler(DWORD fdwCtrlType) {
	if (fdwCtrlType == CTRL_C_EVENT || fdwCtrlType == CTRL_CLOSE_EVENT) {
		PACE2025_HS::global_exit_signal_reached = true;
		return TRUE;
	}
	return FALSE;
}
#else
void signal_handler(int sig) {
	PACE2025_HS::global_exit_signal_reached = true;
}
#endif

namespace PACE2025_HS {
	Vec<Str> readInstanceNames(const std::string& instlist) {
		std::ifstream ifs(instlist);
		if (!ifs) { fatalif(1, "Open file %s failed!", instlist.c_str()); }

		std::vector<std::string> ret;
		std::string line;
		while (getline(ifs, line)) {
			if (!line.size() || line[0] == '#') continue;

			ret.emplace_back(line);
		}

		return ret;
	}

	static void collect_info() {
		std::ofstream inst_info("../docs/InstanceInfo.csv");
		inst_info << "Instance,ElementNum,SetNum,MaxElementD,MinElementD,AvgElementD,MaxSetD,MinSetD,AvgSetD,";
		inst_info << "S-ElementNum,S-SetNum,S-MaxElementD,S-MinElementD,S-AvgElementD,S-MaxSetD,S-MinSetD,S-AvgSetD,Time\n";

		Vec<Str> inst_names = readInstanceNames("./instancelist.txt");
		for (const std::string& inst_name : inst_names) {
			dbg(inst_name);

			goal::Log logger(Log::On, std::cout);
			OriginalSCInstance oins;
			oins.read_hs_instance(inst_name);
			SimplifiedSCInstance sins(oins, logger);

			goal::Timer timer;
			sins.reduction(60);
			double t = timer.elapsedSeconds();

			recode_instance_info(inst_info, oins, sins, t); 
		}

		inst_info.close();
	}

	static void local_batch_run() {
		Vec<Str> inst_names = readInstanceNames("./instancelist.txt");
		auto solve_one_instance = [&](OriginalSCInstance oins, const std::string& inst_name) {
			std::ofstream instance_log_file(inst_name + ".log.txt");
			goal::Log logger(Log::On, instance_log_file);

			goal::Stopwatch stpw;

			logger << "Instance Name: " << inst_name << std::endl;

			SimplifiedSCInstance sins(oins, logger);
			stpw.printTime("Instance Reading Completed", logger);
			sins.reduction(60);
			//sins.print_statistics();
			logger
				<< "Instance Info: "
				<< "\n\tComponent Number: " << sins.set_component_number_
				<< "\n\tGraph Density: " << sins.graph_density_
				<< std::endl;
			stpw.printTime("Instance Reduction Completed", logger);

			GreedyGenerator greedy_solver(sins);
			Vec<SetId> greedy_res = greedy_solver.greedy_by_iterated_pagerank(16, 60);

			stpw.printTime("Greedy by Iterated Pagerank Completed", logger);

			Vec<SetId> completed_greedy_res = sins.generate_complete_sol(greedy_res);
			logger << "Validity: " << oins.is_valid_solution(completed_greedy_res) << ", Set Size: " << completed_greedy_res.size() << std::endl;

			WVNS4SCP ls_solver(sins, greedy_res, /*113*//*998244353*/20261006);
			Vec<SetId> ls_res = ls_solver.solve(1000000000, 180);

			Vec<SetId> completed_ls_res = sins.generate_complete_sol(ls_res);
			logger << "Validity: " << oins.is_valid_solution(completed_ls_res) << ", Set Size: " << completed_ls_res.size() << std::endl;
		
			instance_log_file.close();

			return (int)completed_ls_res.size();
		};

		goal::NaiveThreadPool thread_pool(10);
		Vec<std::future<int>> handlers;
		handlers.reserve(inst_names.size());
		for (const std::string& inst_name : inst_names) {
			OriginalSCInstance oins;
			oins.read_hs_instance(inst_name);
			handlers.emplace_back(thread_pool.enqueue(
				solve_one_instance, oins, inst_name
			));
		}

		std::ofstream result_out_file("results.csv", std::ios_base::app);
		for (auto i = 0; i < handlers.size(); ++i) {
			result_out_file << inst_names[i] << "," << handlers[i].get() << std::endl;
		}
		result_out_file.close();
	}

	static void local_run() {
		Vec<Str> inst_names = readInstanceNames("./instancelist.txt");
		auto solve_one_instance = [&](OriginalSCInstance oins, const std::string& inst_name) {
			goal::Log logger(Log::On, std::cerr);

			goal::Stopwatch stpw;

			logger << "Instance Name: " << inst_name << std::endl;

			SimplifiedSCInstance sins(oins, logger);
			stpw.printTime("Instance Reading Completed", logger);
			sins.reduction(60);
			//sins.print_statistics();
			logger
				<< "Instance Info: "
				<< "\n\tComponent Number: " << sins.set_component_number_
				<< "\n\tGraph Density: " << sins.graph_density_
				<< std::endl;
			stpw.printTime("Instance Reduction Completed", logger);

			GreedyGenerator greedy_solver(sins);
			//Vec<SetId> greedy_res = greedy_solver.greedy_by_pagerank(60);
			Vec<SetId> greedy_res = greedy_solver.greedy_by_iterated_pagerank(16, 60);

			stpw.printTime("Greedy by Iterated Pagerank Completed", logger);

			Vec<SetId> completed_greedy_res = sins.generate_complete_sol(greedy_res);
			logger << "Validity: " << oins.is_valid_solution(completed_greedy_res) << ", Set Size: " << completed_greedy_res.size() << std::endl;

			WVNS4SCP ls_solver(sins, greedy_res, /*113*//*998244353*/20261006);
			Vec<SetId> ls_res = ls_solver.solve(1000000000, 180);

			Vec<SetId> completed_ls_res = sins.generate_complete_sol(ls_res);
			logger << "Validity: " << oins.is_valid_solution(completed_ls_res) << ", Set Size: " << completed_ls_res.size() << std::endl;

			return (int)completed_ls_res.size();
		};

		for (const std::string& inst_name : inst_names) {
			OriginalSCInstance oins;
			oins.read_hs_instance(inst_name);
			solve_one_instance(oins, inst_name);
		}
	}

	static void submit_run() {
		goal::Log logger(Log::Off, std::cout);
		OriginalSCInstance oins;
		oins.read_hs_instance(stdin);
		SimplifiedSCInstance sins(oins, logger);

		sins.reduction(60);
		//sins.try_to_initialize_hop2_neighbor(30);

		GreedyGenerator greedy_solver(sins);
		//Vec<SetId> greedy_res = greedy_solver.greedy_by_cover_count(60.0);
		Vec<SetId> greedy_res = greedy_solver.greedy_by_iterated_pagerank(16, 60.0);
		WVNS4SCP local_search_solver(sins, greedy_res, /*113*//*998244353*/20261006);
		Vec<SetId> ls_res = local_search_solver.solve(1000000000, 1000000);

		Vec<SetId> completed_res = sins.generate_complete_sol(ls_res);
		printf("%d\n", (int)completed_res.size());
		for (SetId s : completed_res) { printf("%d\n", s + 1); }
	}
}

int main() {
#ifdef _WIN32
	SetConsoleCtrlHandler(CtrlHandler, TRUE);
#else
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);
#endif

#ifdef _WIN32
	//PACE2025_HS::local_batch_run();
	PACE2025_HS::local_run();
#else
	PACE2025_HS::submit_run();
#endif // _WIN32
}
