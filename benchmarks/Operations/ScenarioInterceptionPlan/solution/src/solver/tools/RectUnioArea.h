#pragma once

#include <iostream>

#include "./Typedef.h"

#include<cstdio>
#include<algorithm>

namespace goal {
	struct RectUnionArea {
		const static int maxn = 2e5 + 5;
		static int v[maxn];

		struct L {
			int x, y1, y2, state;
			L() {}
			L(int _x, int _y1, int _y2, int _s) : x(_x), y1(_y1), y2(_y2), state(_s) {}
			bool operator<(const L &oth) const { return x < oth.x; }
		} ;

		static L line[maxn];

		struct node {   //Ïß¶ÎÊ÷
			int l, r, cover;
			long long len;
		} ;

		static node sgt[maxn << 3];

		static inline int ls(int k) { return k << 1; }

		static inline int rs(int k) { return k << 1 | 1; }

		static inline void push_up(int k) {
			if (sgt[k].cover)sgt[k].len = sgt[k].r - sgt[k].l;
			else sgt[k].len = sgt[ls(k)].len + sgt[rs(k)].len;
		}

		static void build(int l, int r, int k = 1) {
			sgt[k].l = v[l];
			sgt[k].r = v[r];
			sgt[k].len = sgt[k].cover = 0;
			if (r - l <= 1)return;
			int m = (l + r) >> 1;
			build(l, m, ls(k));
			build(m, r, rs(k));
		}

		static void modify(int x, int y, int z, int k = 1) {
			int l = sgt[k].l, r = sgt[k].r;
			if (x <= l && r <= y) {
				sgt[k].cover += z;
				push_up(k);
				return;
			}
			if (x < sgt[ls(k)].r) modify(x, y, z, ls(k));
			if (y > sgt[rs(k)].l) modify(x, y, z, rs(k));
			push_up(k);
		}

		static long long unionArea(const std::vector<Arr<long long, 4>> &rects) {
			int n = int(rects.size()); if (!n) return 0ll;
			for (int i = 1; i <= n; i++) {
				int a = rects[i - 1][0], b = rects[i - 1][1],
					c = rects[i - 1][2], d = rects[i - 1][3];

				v[i] = b, v[n + i] = d;
				line[i] = { a, b, d, 1 }, line[n + i] = { c, b, d, -1 };
			}
			n <<= 1;
			std::sort(v + 1, v + n + 1);
			std::sort(line + 1, line + n + 1);
			build(1, n);
			long long ans = 0;
			for (int i = 1; i <= n; ++i) {
				ans += sgt[1].len * (line[i].x - line[i - 1].x);
				modify(line[i].y1, line[i].y2, line[i].state);
			}
			
			return ans;
		}
	};
	
	int RectUnionArea::v[maxn];
	RectUnionArea::L RectUnionArea::line[maxn];
	RectUnionArea::node RectUnionArea::sgt[maxn << 3];
}