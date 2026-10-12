////////////////////////////////
/// usage : 1.	csv file reader.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_SYSTEM_CSV_READER_H
#define CN_HUST_GOAL_SYSTEM_CSV_READER_H


#include <utility>

#include "./Typedef.h"
#include "./File.h"


namespace goal {
namespace file {

class CsvReader {
public:
    using Row = Vec<char*>;
    using Table = Vec<Row>;


    static constexpr char CommaChar = ',';


    const Table& scan(const Str &path) {
        charBuf = std::move(readAllText(path));
        charBuf.back() = '\n'; // add a sentinel so that end of file check is only necessary in onNewLine().
        end = charBuf.data() + charBuf.size();

        #if CN_HUST_GOAL_SYSTEM_CSV_READER_RECURSIVE_VERSION
        onNewLine(charBuf.data());
        #else
        onNewLine_opt(&charBuf[0]);
        #endif // CN_HUST_GOAL_SYSTEM_CSV_READER_RECURSIVE_VERSION

        return rows;
    }

protected:
    static bool IsNewLineChar[];
    static bool IsSpaceChar[];
    static bool IsEndCellChar[];

    static int init() { // already called in `Implementation.cpp`, executed before `main()`.
        IsNewLineChar['\r'] = 1;
        IsNewLineChar['\n'] = 1;
        IsSpaceChar[' '] = 1;
        IsSpaceChar['\t'] = 1;
        IsEndCellChar[CommaChar] = 1;
        IsEndCellChar['\r'] = 1;
        IsEndCellChar['\n'] = 1;
        return 0;
    }


    #if CN_HUST_GOAL_SYSTEM_CSV_READER_RECURSIVE_VERSION
    void onNewLine(char *s) {
        while ((s != end) && IsNewLineChar[*s]) { ++s; } // remove empty lines.
        if (s == end) { return; }

        rows.push_back(Row());

        onSpace(s);
    }

    void onSpace(char *s) {
        while (IsSpaceChar[*s]) { ++s; } // trim spaces.

        onValue(s);
    }

    void onValue(char *s) {
        rows.back().push_back(s);

        char c = *s;
        if (!IsEndCellChar[c]) {
            while (!IsEndCellChar[*(++s)]) {}
            c = *s;

            char *space = s;
            while (IsSpaceChar[*(space - 1)]) { --space; }
            *space = 0; // trim spaces and remove comma or line ending.
        } else { // empty cell.
            *s = 0;
        }

        ++s;
        IsNewLineChar[c] ? onNewLine(s) : onSpace(s);
    }
    #else // in case there is no Tail-Call Optimization which leads to stack overflow.
    void onNewLine_opt(char *s) {
Label_OnNewLine:
        while ((s != end) && IsNewLineChar[*s]) { ++s; } // remove empty lines.
        if (s == end) { return; }

        rows.push_back(Row());

Label_OnSpace:
        while (IsSpaceChar[*s]) { ++s; } // trim spaces.

//Label_OnValue:
        rows.back().push_back(s);

        char c = *s;
        if (!IsEndCellChar[c]) {
            while (!IsEndCellChar[*(++s)]) {}
            c = *s;

            char *space = s;
            while (IsSpaceChar[*(space - 1)]) { --space; }
            *space = 0; // trim spaces and remove comma or line ending.
        } else { // empty cell.
            *s = 0;
        }

        ++s;
        if (IsNewLineChar[c]) {
            goto Label_OnNewLine;
        } else {
            goto Label_OnSpace;
        }
    }
    #endif // CN_HUST_GOAL_SYSTEM_CSV_READER_RECURSIVE_VERSION

    // TODO[szx][2]: handle quote (comma may not end cells).
    // EXT[szx][5]: make trim space configurable.

    const char *end;

    Str charBuf;
    Table rows;
};

}
}


#endif // CN_HUST_GOAL_SYSTEM_CSV_READER_H
