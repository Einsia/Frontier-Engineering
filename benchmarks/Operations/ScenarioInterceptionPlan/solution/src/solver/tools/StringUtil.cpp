#include "StringUtil.h"

#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#include <Psapi.h>
#else
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/times.h>
#endif // _OS_MS_WINDOWS

void StringUtil::str_split(std::vector<std::string>& result, const std::string& input, const char delimiter) {
	result.clear();
	size_t len = input.length();
	std::string curr_str = "";
	for (size_t i = 0; i < len; ++i) {
		if (input[i] == delimiter) {
			result.emplace_back(curr_str);
			curr_str = "";
		}
		else {
			curr_str.push_back(input[i]);
		}
	}
	result.emplace_back(curr_str);
}

#ifdef _WIN32

//https://developer.aliyun.com/article/1294133
std::string StringUtil::GbkToUtf8(const std::string& str) {
	int len = MultiByteToWideChar(CP_ACP, 0, str.c_str(), -1, NULL, 0);
	wchar_t* wstr = new wchar_t[len + 1ull];
	memset(wstr, 0, len + 1ull);
	MultiByteToWideChar(CP_ACP, 0, str.c_str(), -1, wstr, len);
	len = WideCharToMultiByte(CP_UTF8, 0, wstr, -1, NULL, 0, NULL, NULL);
	char* cstr = new char[len + 1ull];
	memset(cstr, 0, len + 1ull);
	WideCharToMultiByte(CP_UTF8, 0, wstr, -1, cstr, len, NULL, NULL);
	std::string res(cstr);

	if (wstr) delete[] wstr;
	if (cstr) delete[] cstr;

	return res;
}

//https://developer.aliyun.com/article/1294133
std::string StringUtil::Utf8ToGbk(const std::string& str) {
	// calculate length
	int len = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, NULL, 0);
	wchar_t* wsGbk = new wchar_t[len + 1ull];
	// set to '\0'
	memset(wsGbk, 0, len + 1ull);
	MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, wsGbk, len);
	len = WideCharToMultiByte(CP_ACP, 0, wsGbk, -1, NULL, 0, NULL, NULL);
	char* csGbk = new char[len + 1ull];
	memset(csGbk, 0, len + 1ull);
	WideCharToMultiByte(CP_ACP, 0, wsGbk, -1, csGbk, len, NULL, NULL);
	std::string res(csGbk);

	if (wsGbk) delete[] wsGbk;
	if (csGbk) delete[] csGbk;

	return res;
}

#endif
