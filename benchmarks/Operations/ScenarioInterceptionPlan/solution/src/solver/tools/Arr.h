////////////////////////////////
/// usage : 1.	fixed size 1D and 2D array following RAII idiom.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_ARR_H
#define CN_HUST_GOAL_COMMON_ARR_H


#include <algorithm>
#include <array>
#include <initializer_list>
#include <type_traits>
#include <cstring>

#include "./Flag.h"
#include "./Typedef.h"
#include "./Exception.h"
#include "./Math.h"


namespace goal {

enum ArrResetOption { AllBits0 = 0, AllBits1 = -1, SafeMaxInt = 0x3F };

template<typename T, typename IndexType = int>
class Array {
	static constexpr bool SafetyCheck = false;
public:
	using Index = IndexType;
	// it is always valid before copy assignment due to no reallocation.
	using Iterator = T*;
	using ConstIterator = T const*;

	explicit Array() : arr(nullptr), len(0) {}
	explicit Array(Index length) { allocate(length); }
	explicit Array(Index length, T* data) : arr(data), len(length) {}
	explicit Array(Index length, const T& defaultValue) : Array(length) {
		std::fill(arr, arr + length, defaultValue);
	}
	Array(std::initializer_list<T> l) : Array(sCast<Index>(l.size())) {
		std::copy(l.begin(), l.end(), arr);
	}

	Array(const Array& a) : Array(a.len) {
		if (this != &a) { copyData(a.arr); }
	}
	Array(Array&& a) : Array(a.len, a.arr) { a.arr = nullptr; }

	Array& operator=(const Array& a) {
		if (this != &a) {
			if (len != a.len) {
				clear();
				init(a.len);
			}
			copyData(a.arr);
		}
		return *this;
	}
	Array& operator=(Array&& a) {
		if (this != &a) {
			delete[] arr;
			arr = a.arr;
			len = a.len;
			a.arr = nullptr;
		}
		return *this;
	}

	~Array() { clear(); }

	// allocate memory if it has not been init before.
	bool init(Index length) {
		if (arr == nullptr) { // avoid re-init and memory leak.
			allocate(length);
			return true;
		}
		return false;
	}

	// remove all items.
	void clear() {
		delete[] arr;
		arr = nullptr;
	}

	// set all data to val. any value other than 0 or -1 is undefined behavior.
	void reset(ArrResetOption val = ArrResetOption::AllBits0) { std::memset(arr, val, sizeof(T) * len); }

	T& operator[](Index i) {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	const T& operator[](Index i) const {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}

	T& at(Index i) {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	const T& at(Index i) const {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}

	Iterator begin() { return arr; }
	Iterator end() { return (arr + len); }
	ConstIterator begin() const { return arr; }
	ConstIterator end() const { return (arr + len); }
	T& front() { return at(0); }
	T& back() { return at(len - 1); }
	const T& front() const { return at(0); }
	const T& back() const { return at(len - 1); }

	Index size() const { return len; }
	bool empty() const { return (len == 0); }

protected:
	// must not be called except init.
	void allocate(Index length) {
		// TODO[szx][2]: length > (1 << 32)?
		arr = new T[sCast<size_t>(length)];
		len = length;
	}

	void copyData(T* data) {
		// OPT[szx][8]: memcpy?
		//(std::is_trivially_copyable<T>::value)
		//    ? std::copy(data, data + len, arr)
		//    : memcpy(arr, data, len * sizeof(T));
		std::copy(data, data + len, arr);
	}


	T* arr;
	Index len;
};

template<typename T, typename IndexType = int>
class Array2D {
	static constexpr bool SafetyCheck = false;
public:
	using Index = IndexType;
	// it is always valid before copy assignment due to no reallocation.
	using Iterator = T*;
	using ConstIterator = T const*;

	explicit Array2D() : arr(nullptr), len1(0), len2(0), len(0) {}
	explicit Array2D(Index length1, Index length2) { allocate(length1, length2); }
	explicit Array2D(Index length1, Index length2, T* data)
		: arr(data), len1(length1), len2(length2), len(length1 * length2) {
	}
	explicit Array2D(Index length1, Index length2, const T& defaultValue) : Array2D(length1, length2) {
		std::fill(arr, arr + len, defaultValue);
	}

	Array2D(const Array2D& a) : Array2D(a.len1, a.len2) {
		if (this != &a) { copyData(a.arr); }
	}
	Array2D(Array2D&& a) : Array2D(a.len1, a.len2, a.arr) { a.arr = nullptr; }

	Array2D& operator=(const Array2D& a) {
		if (this != &a) {
			if (len != a.len) {
				clear();
				init(a.len1, a.len2);
			} else {
				len1 = a.len1;
				len2 = a.len2;
			}
			copyData(a.arr);
		}
		return *this;
	}
	Array2D& operator=(Array2D&& a) {
		if (this != &a) {
			delete[] arr;
			arr = a.arr;
			len1 = a.len1;
			len2 = a.len2;
			len = a.len;
			a.arr = nullptr;
		}
		return *this;
	}

	~Array2D() { clear(); }

	// allocate memory if it has not been init before.
	bool init(Index length1, Index length2) {
		if (arr == nullptr) { // avoid re-init and memory leak.
			allocate(length1, length2);
			return true;
		}
		return false;
	}

	// remove all items.
	void clear() {
		delete[] arr;
		arr = nullptr;
	}

	// set all data to val. any value other than 0 or -1 is undefined behavior.
	void reset(ArrResetOption val = ArrResetOption::AllBits0) { std::memset(arr, val, sizeof(T) * len); }

	Index getFlatIndex(Index i1, Index i2) const { return (i1 * len2 + i2); }

	T* operator[](Index i1) {
		if (SafetyCheck && !math::inRange(i1, Index(0), len1)) { throw IndexOutOfRangeException(); }
		return (arr + i1 * len2);
	}
	const T* operator[](Index i1) const {
		if (SafetyCheck && !math::inRange(i1, Index(0), len1)) { throw IndexOutOfRangeException(); }
		return (arr + i1 * len2);
	}

	T& at(Index i) {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	const T& at(Index i) const {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	T& at(Index i1, Index i2) {
		if (SafetyCheck && !(math::inRange(i1, Index(0), len1) && math::inRange(i2, Index(0), len2))) { throw IndexOutOfRangeException(); }
		return arr[getFlatIndex(i1, i2)];
	}
	const T& at(Index i1, Index i2) const {
		if (SafetyCheck && !(math::inRange(i1, Index(0), len1) && math::inRange(i2, Index(0), len2))) { throw IndexOutOfRangeException(); }
		return arr[getFlatIndex(i1, i2)];
	}

	Iterator begin() { return arr; }
	Iterator begin(Index i1) { return arr + (i1 * len2); }
	ConstIterator begin() const { return arr; }
	ConstIterator begin(Index i1) const { return arr + (i1 * len2); }

	Iterator end() { return (arr + len); }
	Iterator end(Index i1) { return arr + (i1 * len2) + len2; }
	ConstIterator end() const { return (arr + len); }
	ConstIterator end(Index i1) const { return arr + (i1 * len2) + len2; }

	T& front() { return at(0); }
	T& front(Index i1) { return at(i1, 0); }
	const T& front() const { return at(0); }
	const T& front(Index i1) const { return at(i1, 0); }

	T& back() { return at(len - 1); }
	T& back(Index i1) { return at(i1, len - 1); }
	const T& back() const { return at(len - 1); }
	const T& back(Index i1) const { return at(i1, len - 1); }

	Index size1() const { return len1; }
	Index size2() const { return len2; }
	Index size() const { return len; }
	bool empty() const { return (len == 0); }

protected:
	// must not be called except init.
	void allocate(Index length1, Index length2) {
		len1 = length1;
		len2 = length2;
		len = length1 * length2;
		arr = new T[sCast<size_t>(len)];
	}

	void copyData(T* data) {
		// TODO[szx][1]: what if data is shorter than arr?
		// OPT[szx][8]: use memcpy() if all callers are POD type.
		std::copy(data, data + len, arr);
	}


	T* arr;
	Index len1;
	Index len2;
	Index len;
};

template<typename T, int Dim, typename IndexType = int>
class ArrayMD {
	static constexpr bool SafetyCheck = false;
public:
	static constexpr int Dim1 = Dim - 1;

	using Index = IndexType;
	using Indices = std::array<Index, Dim>;
	using LenProducts = std::array<Index, Dim1>;
	// it is always valid before copy assignment due to no reallocation.
	using Iterator = T*;
	using ConstIterator = T const*;

	explicit ArrayMD() : arr(nullptr), lens({ 0 }), lenProds({ 0 }), len(0) {}
	explicit ArrayMD(const Indices& lengths) { allocate(lengths); }
	explicit ArrayMD(const Indices& lengths, T* data) : arr(data), lens(lengths), len(calcProduct(lengths)) { calcSizes(); }
	explicit ArrayMD(const Indices& lengths, const T& defaultValue) : ArrayMD(lengths) {
		std::fill(arr, arr + len, defaultValue);
	}

	ArrayMD(const ArrayMD& a) : ArrayMD(a.lens) {
		if (this != &a) { copyData(a.arr); }
	}
	ArrayMD(ArrayMD&& a) : ArrayMD(a.lens, a.arr) { a.arr = nullptr; }

	ArrayMD& operator=(const ArrayMD& a) {
		if (this != &a) {
			if (len != a.len) {
				clear();
				init(a.lens);
			} else {
				lens = a.lens;
				lenProds = a.lenProds;
			}
			copyData(a.arr);
		}
		return *this;
	}
	ArrayMD& operator=(ArrayMD&& a) {
		if (this != &a) {
			delete[] arr;
			arr = a.arr;
			lens = a.lens;
			lenProds = a.lenProds;
			len = a.len;
			a.arr = nullptr;
		}
		return *this;
	}

	~ArrayMD() { clear(); }

	// allocate memory if it has not been init before.
	bool init(const Indices& lengths) {
		if (arr == nullptr) { // avoid re-init and memory leak.
			allocate(lengths);
			return true;
		}
		return false;
	}

	// remove all items.
	void clear() {
		delete[] arr;
		arr = nullptr;
	}

	// set all data to val. any value other than 0 or -1 is undefined behavior.
	void reset(ArrResetOption val = ArrResetOption::AllBits0) { std::memset(arr, val, sizeof(T) * len); }

	Index getFlatIndex(const Indices& i) const {
		Index j = i[Dim1];
		for (Index k = 0; k < Dim1; ++k) { j += (i[k] * lenProds[k]); }
		return j;
	}

	T& at(Index i) {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	const T& at(Index i) const {
		if (SafetyCheck && !math::inRange(i, Index(0), len)) { throw IndexOutOfRangeException(); }
		return arr[i];
	}
	T& at(const Indices& i) {
		if (SafetyCheck) { for (Index k = 0; k < Dim1; ++k) { if (!math::inRange(i[k], Index(0), lens[k])) { throw IndexOutOfRangeException(); } } }
		return arr[getFlatIndex(i)];
	}
	const T& at(const Indices& i) const {
		if (SafetyCheck) { for (Index k = 0; k < Dim1; ++k) { if (!math::inRange(i[k], Index(0), lens[k])) { throw IndexOutOfRangeException(); } } }
		return arr[getFlatIndex(i)];
	}

	T& operator[](Index i) { return at(i); }
	const T& operator[](Index i) const { return at(i); }
	T& operator[](const Indices& i) { return at(i); }
	const T& operator[](const Indices& i) const { return at(i); }

	Iterator begin() { return arr; }
	ConstIterator begin() const { return arr; }

	Iterator end() { return (arr + len); }
	ConstIterator end() const { return (arr + len); }

	T& front() { return at(0); }
	const T& front() const { return at(0); }

	T& back() { return at(len - 1); }
	const T& back() const { return at(len - 1); }

	const Indices& sizes() const { return lens; }
	Index size() const { return len; }
	bool empty() const { return (len == 0); }

protected:
	static Index calcProduct(const Indices& lengths) {
		Index prod = 1;
		for (auto l = lengths.begin(); l != lengths.end(); ++l) { prod *= *l; }
		return prod;
	}

	void calcSizes() {
		Index s = lens[Dim1];
		for (Index k = Dim1 - 1; ;) {
			lenProds[k] = s;
			if (k <= 0) { break; }
			s *= lens[k--];
		}
	}

	// must not be called except init.
	void allocate(const Indices& lengths) {
		lens = lengths;
		calcSizes();
		len = calcProduct(lengths);
		arr = new T[sCast<size_t>(len)];
	}

	void copyData(T* data) {
		// TODO[szx][1]: what if data is shorter than arr?
		// OPT[szx][8]: use memcpy() if all callers are POD type.
		std::copy(data, data + len, arr);
	}


	T* arr;
	Indices lens; // `arr[{ i, j, k }] == arr[i][j][k] == *(arr + ((i * lens[0]) + j) * lens[1] + k)`.
	LenProducts lenProds; // `arr[{ i, j, k }] == arr[i][j][k] == *(arr + (i * lenProds[0]) + (j * lenProds[1]) + k)`.
	Index len;
};


template<typename T, typename IndexType = ID>
using List = Array<T, IndexType>;

template<typename T, typename IndexType = ID>
using Mat = Array2D<T, IndexType>;


namespace demo {

struct ArrayMdDemo {
	static void demo0() {
		ArrayMD<int, 3> arr({ 3, 4, 5 });
		int n = 0;
		for (auto i = arr.begin(); i != arr.end(); ++i) { *i = n++; }

		int a[3][4][5] = { 0 };
		for (int i = 0; i < 3; ++i) {
			for (int j = 0; j < 4; ++j) {
				for (int k = 0; k < 5; ++k) {
					a[i][j][k] = arr[{ i, j, k }];
				}
			}
		}
	}

	static void demo1() {
		using Arr2D = ArrayMD<double, 2>;
		Arr2D arr({ 6, 7 }, 1);
		Arr2D arr2(arr);

		arr2.at({ 1, 2 }) = 3;

		typename Arr2D::Indices i = { 0, 0 };
		for (; i[0] < 3; ++i[0]) {
			for (; i[1] < 4; ++i[1]) {
				++arr[i];
			}
		}
		arr = arr2;
	}
};

}

}


#endif // CN_HUST_GOAL_COMMON_ARR_H
