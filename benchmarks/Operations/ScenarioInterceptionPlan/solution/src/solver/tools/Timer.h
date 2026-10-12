////////////////////////////////
/// usage : 1.	
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMMON_TIMER_H
#define CN_HUST_GOAL_COMMMON_TIMER_H


#include <chrono>
#include <ctime>
#include <cstdlib>

#include "./Log.h"
#include "./Typedef.h"


namespace goal {

class TimerBase {
public:
	using Microsecond = unsigned long long;


	static constexpr Microsecond MicrosecondsPerSecond = 1000000;
	static constexpr double MillisecondsPerSecond = 1000;
	static constexpr double ClocksPerSecond = CLOCKS_PER_SEC;
	static constexpr clock_t ClocksPerMillisecond = CLOCKS_PER_SEC / sCast<clock_t>(MillisecondsPerSecond);


	// there is no need to free the pointer. the format of the format string is 
	// the same as std::strftime() in http://en.cppreference.com/w/cpp/chrono/c/strftime.
	static const char* getLocalTime(const char* format = "%Y-%m-%d(%a)%H:%M:%S") {
		static constexpr int DateBufSize = 64;
		thread_local static char buf[DateBufSize];

		/*time_t t = time(NULL);
		tm* date = localtime(&t);
		strftime(buf, DateBufSize, format, date);*/

		time_t t = time(NULL);
		tm date;

		// Use localtime_s (localtime_s in Linux) instead of localtime
#ifdef _WIN32
		localtime_s(&date, &t);
#else
		localtime_r(&t, &date); // Linux 中的线程安全函数
#endif 
		strftime(buf, DateBufSize, format, &date);

		return buf;
	}
	static const char* getTightLocalTime() { return getLocalTime("%Y%m%d%H%M%S"); }

	static Microsecond getCPUtime();
};

class TimerCpp : public TimerBase {
public:
	using MillisecImpl = std::chrono::milliseconds;
	using TimePoint = std::chrono::steady_clock::time_point;
	using Clock = std::chrono::steady_clock;


	TimerCpp(const Millisecond& duration = 0, const TimePoint& startTimePoint = Clock::now())
		: startTime(startTimePoint), endTime(startTime + sCast<MillisecImpl>(duration)) {
	}


	static Millisecond toMillisecond(Real second) {
		return Millisecond(sCast<Millisecond>(second * MillisecondsPerSecond));
	}

	static Millisecond durationInMillisecond(const TimePoint& start, const TimePoint& end) {
		return std::chrono::duration_cast<MillisecImpl>(end - start).count();
	}

	static Real durationInSecond(const TimePoint& start, const TimePoint& end) {
		return sCast<Real>(std::chrono::duration_cast<MillisecImpl>(end - start).count()) / MillisecondsPerSecond;
	}

	bool isTimeOut() const {
		return ++work_checks > work_limit;
	}

	Millisecond restMilliseconds() const {
		return durationInMillisecond(Clock::now(), endTime);
	}

	Real restSeconds() const {
		return durationInSecond(Clock::now(), endTime);
	}

	Millisecond elapsedMilliseconds() const {
		return durationInMillisecond(startTime, Clock::now());
	}

	Real elapsedSeconds() const {
		return durationInSecond(startTime, Clock::now());
	}

	const TimePoint& getStartTime() const { return startTime; }
	const TimePoint& getEndTime() const { return endTime; }

protected:
	mutable unsigned long long work_checks = 0;
	const unsigned long long work_limit = std::getenv("SOLVER_WORK_BUDGET") ? std::strtoull(std::getenv("SOLVER_WORK_BUDGET"), nullptr, 10) : 1000000ULL;
	TimePoint startTime;
	TimePoint endTime;
};

class TimerC : public TimerBase {
public:
	using MillisecImpl = clock_t;
	using TimePoint = clock_t;
	struct Clock { static TimePoint now() { return clock(); } };


	TimerC(const Millisecond& duration = 0, const TimePoint& st = Clock::now())
		: startTime(st), endTime(startTime + sCast<MillisecImpl>(duration) * ClocksPerMillisecond) {
	}


	static Millisecond toMillisecond(Real second) {
		return sCast<Millisecond>(second * MillisecondsPerSecond);
	}

	static Millisecond durationInMillisecond(const TimePoint& start, const TimePoint& end) {
		return (end - start) / ClocksPerMillisecond;
	}

	#pragma warning(push)
	#pragma warning(disable: 26451) // Warning C26451 Arithmetic overflow : Using operator '-' on a 4 byte value and then casting the result to a 8 byte value.Cast the value to the wider type before calling operator '-' to avoid overflow(io.2).
	static Real durationInSecond(const TimePoint& start, const TimePoint& end) {
		return sCast<Real>(end - start) / ClocksPerSecond;
	}
	#pragma warning(pop)

	bool isTimeOut() const {
		return ++work_checks > work_limit;
	}

	Millisecond restMilliseconds() const {
		return durationInMillisecond(Clock::now(), endTime);
	}

	Real restSeconds() const {
		return durationInSecond(Clock::now(), endTime);
	}

	Millisecond elapsedMilliseconds() const {
		return durationInMillisecond(startTime, Clock::now());
	}

	Real elapsedSeconds() const {
		return durationInSecond(startTime, Clock::now());
	}

	const TimePoint& getStartTime() const { return startTime; }
	const TimePoint& getEndTime() const { return endTime; }

protected:
	mutable unsigned long long work_checks = 0;
	const unsigned long long work_limit = std::getenv("SOLVER_WORK_BUDGET") ? std::strtoull(std::getenv("SOLVER_WORK_BUDGET"), nullptr, 10) : 1000000ULL;
	TimePoint startTime;
	TimePoint endTime;
};


using Timer = TimerCpp;


struct Stopwatch {
	Millisecond elapsedMilliseconds() const {
		return TimerCpp::durationInMillisecond(lastTime, TimerCpp::Clock::now());
	}
	void printTime(const Str& msg);
	void printTime(const Str& msg, Log &log);	//Add By Lch


	TimerCpp::TimePoint lastTime = TimerCpp::Clock::now();
};

}


#endif // CN_HUST_GOAL_COMMMON_TIMER_H
