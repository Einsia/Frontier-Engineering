#pragma once

#include <iostream>
#include <string>
#include <cstring>
#include <vector>
#include <sstream>

class StringUtil {
public:
	static std::string read_istream(const std::istream& data) {
		std::stringstream buffer;
		buffer << data.rdbuf();
		return buffer.str();
	}

	static void str_split(std::vector<std::string>& result, const std::string& input, const char delimiter);

	static void char_replace(std::string& str, char from, char to) {
		for (char& c : str) { if (c == from) c = to; }
	}

#ifdef _WIN32
	static std::string GbkToUtf8(const std::string& str);

	static std::string Utf8ToGbk(const std::string& str);
#endif

	template <typename... Args>
	static std::string format(const char* pformat, Args... args) {
		// 计算字符串长度
		int len_str = std::snprintf(nullptr, 0, pformat, args...);

		if (0 >= len_str) return std::string("");

		len_str++;
		char* pstr_out = nullptr;
		pstr_out = new(std::nothrow) char[len_str];
		// 申请失败
		if (NULL == pstr_out || nullptr == pstr_out)
			return std::string("");

		// 构造字符串
		std::snprintf(pstr_out, len_str, pformat, args...);

		// 保存构造结果
		std::string str(pstr_out);

		// 释放空间
		delete pstr_out;
		pstr_out = nullptr;

		return str;
	}
};