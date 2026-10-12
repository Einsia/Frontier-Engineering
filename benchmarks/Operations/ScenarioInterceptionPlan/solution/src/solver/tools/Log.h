////////////////////////////////
/// usage : 1.	compile-time switchable log printer.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_LOG_H
#define CN_HUST_GOAL_COMMON_LOG_H


#include <iostream>

#include "./Flag.h"


namespace goal {

// it is recommended to define the log switches as follows.
// the users may also add the developers' names as prefixes for better collaboration experience.
// ```cpp
// struct LogSwitch {
//     enum Level {
//         Fatal = Log::State::On,
//         Error = Log::State::On,
//         Warning = Log::State::On,
//         Debug, // = Off.
//         Info, // = Off.
//     };
// 
//     // TODO[szx][0]: turn off all logs before the release.
//     enum Stage {
//         Main = Level::Info,
//         Cli = Level::Info,
//         Framework = Level::Debug,
//         Input = Level::Debug,
//         Output = Level::Debug,
//         Config = Level::Debug,
//         Preprocess = Level::Warning,
//         Postprocess = Level::Warning,
//         Model = Level::Error,
//         TabuSearch = Level::Error,
//         Checker = Level::Fatal,
//     };
// };
// ```
class Log {
public:
    using Manipulator = std::ostream& (*)(std::ostream&);


    enum Level {
        On,
        Off, // the default state if not specified.

        Fatal = On, // the program will crash.
        Error = On, // logic errors that can affect effectiveness.
        Warning = On, // logic errors that can affect efficiency.
        #if SZX_DEBUG
        Debug = On,
        Info = On,
        #else
        Debug, // = Off.
        Info, // = Off.
        #endif // SZX_DEBUG
    };

    static bool isTurnedOn(int level) { return (level == On); }
    static bool isTurnedOff(int level) { return !isTurnedOn(level); }


    Log(int logLevel, std::ostream &logFile) : level(logLevel), os(&logFile) {}
    Log(int logLevel) : Log(logLevel, std::cerr) {}
	Log() :Log(Off) {}

    template<typename T>
    Log& operator<<(const T &obj) {
        if (isTurnedOn(level)) { *os << obj; }
        return *this;
    }
    Log& operator<<(Manipulator manip) {
        if (isTurnedOn(level)) { *os << manip; }
        return *this;
    }

 //   template<typename T>
	//void reprint(const T& obj) {
	//	std::string s(std::to_string(obj));
	//	os << s;
	//	std::fill(s.begin(), s.end(), '\b');
	//	os << s;
	//}

protected:
    static int init() { // already called in `Implementation.cpp`, executed before `main()`.
        std::cin.tie(nullptr);
        std::ios::sync_with_stdio(false);
        return 0;
    }


    int level;
    std::ostream* os;
};

}


#endif // CN_HUST_GOAL_COMMON_LOG_H
