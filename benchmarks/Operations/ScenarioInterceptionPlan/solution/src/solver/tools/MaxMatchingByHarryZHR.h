////////////////////////////////
/// usage : 1.	
/// 
/// note  : 1.	
////////////////////////////////

#ifndef SMART_SZX_GOAL_MAX_MATCHING_BY_HARRYZHR_H
#define SMART_SZX_GOAL_MAX_MATCHING_BY_HARRYZHR_H


#include <algorithm>
#include <queue>

#include "Arr.h"


namespace szx {

template<typename T, typename IndexType = int>
class LoopQueue {
public:
	LoopQueue() {}
	LoopQueue(IndexType size) : len(size), head(0), tail(0), q(size) {}

	void clear() { head = tail = 0; }
	const T& front() const { return q[head]; }
	void push(const T& item) { q[tail] = item; increaseIndex(tail); }
	void pop() { increaseIndex(head); }
	bool empty() const { return (head == tail); }

protected:
	IndexType& increaseIndex(IndexType& index) const {
		if ((++index) >= len) { index = 0; }
		return index;
	}


	IndexType len;
	IndexType head;
	IndexType tail;
	Arr<T, IndexType> q;
};


struct MaxMatchingByHarryZHR {
	using ID = int;
	using Cost = long long;


	MaxMatchingByHarryZHR(const Arr2D<Cost>& costMat)
		: cost(costMat), n(costMat.size1()), q(n), lx(n, -1), ly(n, -1),
		slack(n), prx(n, -1), pry(n, -1), pre(n, -1), visx(n), visy(n) {
	}


    const Arr<ID>& solve() { // maximize the total cost.
		if (cost.size1() != cost.size2()) { return prx; }

		KM();
        return prx;
    }


protected:
    static constexpr Cost INF = 10000000000000000ll;


    Arr2D<Cost> cost; // cost matrix.

	ID n; // n workers and n jobs.
	Arr<Cost> lx;
	Arr<Cost> ly;
	Arr<Cost> slack;
	Arr<ID> prx;
	Arr<ID> pry;
	Arr<ID> pre;
	Arr<bool> visx;
	Arr<bool> visy;

	//std::queue<ID> q;
	//void qClear() { while (!q.empty()) { q.pop(); } }

	LoopQueue<ID, ID> q;
	void qClear() { q.clear(); }

	bool check(ID x) {
		visy[x] = true;
		if (pry[x] >= 0) { q.push(pry[x]); return false; }
		while (x >= 0) {
			pry[x] = pre[x];
			std::swap(x, prx[pre[x]]);
		}
		return true;
	}

	void clear() {
		visx.reset(Arr<bool>::ResetOption::AllBits0);
		visy.reset(Arr<bool>::ResetOption::AllBits0);
		qClear();
		slack.reset(Arr<Cost>::ResetOption::SafeMaxInt);
	}

	bool bfs() {
		while (!q.empty()) {
			ID u = q.front();
			q.pop();
			if (visx[u]) { continue; }
			visx[u] = true;
			for (ID i = 0; i < n; ++i) {
				if (cost[u][i] <= -INF) { continue; }
				if (visy[i]) { continue; }
				if (lx[u] + ly[i] - cost[u][i] < slack[i]) {
					slack[i] = lx[u] + ly[i] - cost[u][i];
					pre[i] = u;
					if (!slack[i] && check(i)) { return true; }
				}
			}
		}
		Cost delta = INF;
		for (ID i = 0; i < n; ++i) { if (!visy[i]) { delta = std::min(delta, slack[i]); } }
		for (ID i = 0; i < n; ++i) {
			if (visx[i]) { lx[i] -= delta; }
			if (visy[i]) { ly[i] += delta; } else { slack[i] -= delta; }
		}
		for (ID i = 0; i < n; ++i) {
			if (!visy[i] && !slack[i] && check(i)) { return true; }
		}
		return false;
	}

	void KM() {
		for (ID i = 0; i < n; ++i) {
			ly[i] = -INF;
			for (ID j = 0; j < n; ++j) { ly[i] = std::max(ly[i], cost[j][i]); }
			lx[i] = 0;
		}
		for (ID i = 0; i < n; ++i) {
			clear();
			q.push(i);
			while (!bfs()) {}
		}
	}
};

}


#endif // SMART_SZX_GOAL_MAX_MATCHING_BY_HARRYZHR_H
