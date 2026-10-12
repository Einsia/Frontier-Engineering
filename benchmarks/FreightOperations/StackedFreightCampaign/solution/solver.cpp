// ROADEF/EURO 2022 truck loading - independent feasibility-oriented constructive solver.
// Deterministic: no randomness, no wall-clock dependence.
#include <bits/stdc++.h>
using namespace std;
typedef long long ll;

// ---------------------------------------------------------------- CSV utils
static string trim(const string& s) {
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n' || s[a] == '"')) a++;
    while (b > a && (s[b-1] == ' ' || s[b-1] == '\t' || s[b-1] == '\r' || s[b-1] == '\n' || s[b-1] == '"')) b--;
    return s.substr(a, b - a);
}
static vector<string> splitLine(const string& line) {
    vector<string> out; string cur;
    for (char ch : line) { if (ch == ';') { out.push_back(trim(cur)); cur.clear(); } else cur.push_back(ch); }
    out.push_back(trim(cur));
    return out;
}
struct Table {
    vector<string> hdr; vector<vector<string>> rows; map<string,int> col;
    int c(const string& name) const {
        auto it = col.find(name);
        if (it == col.end()) { fprintf(stderr, "Missing column: %s\n", name.c_str()); exit(2); }
        return it->second;
    }
};
static Table readTable(const string& path) {
    ifstream f(path, ios::binary);
    if (!f) { fprintf(stderr, "Cannot open %s\n", path.c_str()); exit(2); }
    Table t; string line; bool first = true;
    while (getline(f, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) {
            if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF) line = line.substr(3);
            t.hdr = splitLine(line);
            for (int i = 0; i < (int)t.hdr.size(); i++) t.col[t.hdr[i]] = i;
            first = false; continue;
        }
        if (trim(line).empty()) continue;
        vector<string> v = splitLine(line);
        v.resize(t.hdr.size());
        t.rows.push_back(v);
    }
    return t;
}
static double toD(string s) { for (char& ch : s) if (ch == ',') ch = '.'; if (s.empty()) return 0.0; return strtod(s.c_str(), nullptr); }
static ll toI(const string& s) { if (s.empty()) return 0; return llround(toD(s)); }
static ll toTime(const string& s) { return strtoll(s.c_str(), nullptr, 10); }
static string lower(string s) { for (char& ch : s) ch = (char)tolower((unsigned char)ch); return s; }

// ---------------------------------------------------------------- data
struct Item {
    string ident, supplier, sdock, plant, pdock, product, package, stackcode;
    int qty = 0, L = 0, W = 0, H = 0, NH = 0, ISM = 1000000, forced = 0; // forced: 0 none, 1 lengthwise, 2 widthwise
    ll wg = 0, IDE = 0, IDL = 0; // weight in grams
};
struct Truck {
    string id, plant; ll TDA = 0;
    int L = 0, W = 0, H = 0; ll maxWg = 0; double TEM = 0; int multi = 0; double cost = 0;
    double EMmm = 0, EMmr = 0, CM = 0, CJfm = 0, CJfc = 0, CJfh = 0, EM = 0, EJhr = 0, EJcr = 0, EJeh = 0;
    map<string,int> supOrd;          // supplier -> loading order
    map<string,int> sdockOrd;        // supplier|sdock -> order
    map<string,int> pdockOrd;        // plant dock -> order
    map<string,ll> tmm;              // supplier|product|pdock -> max weight above bottom (grams)
};
static vector<Item> items;
static vector<Truck> trucks; // sorted by (TDA, id)

// ---------------------------------------------------------------- per-truck context
struct GroupInfo { int L = 0, W = 0, forced = 0; array<int,3> key{}; ll densLimit = 0; int dx = 0, dy = 0; bool ok = false; string stackcode; };
struct Ctx {
    const Truck* T = nullptr;
    int n = 0;
    vector<int> row;         // item row per candidate
    vector<ll> tmm;          // grams (max weight above when this candidate is bottom)
    vector<int> grp;
    vector<int> H, NH, ISM; vector<ll> wg;
    vector<GroupInfo> groups;
};
struct SB { int grp = 0; vector<int> u; ll sumW = 0; int sumHm = 0; int minISM = INT_MAX; };
struct PStack { int sb = 0; int xo = 0, yo = 0, dx = 0, dy = 0; };
struct Layout { vector<SB> stacks; vector<PStack> pos; int length = 0; double emm = 0, emr = 0; };

static inline bool bottomOK(const Ctx& C, int b, ll W, int Hm) {
    if (Hm + C.NH[b] > C.T->H) return false;
    ll above = W - C.wg[b];
    if (above == 0) return true;
    return above <= C.tmm[b] - 1;
}
static bool canAdd(const Ctx& C, const SB& s, int c) {
    const GroupInfo& g = C.groups[s.grp];
    int n = (int)s.u.size() + 1;
    int mi = min(s.minISM, C.ISM[c]);
    if (n > mi) return false;
    ll W = s.sumW + C.wg[c];
    if (W > g.densLimit) return false;
    int Hm = s.sumHm + (C.H[c] - C.NH[c]);
    if (bottomOK(C, c, W, Hm)) return true;
    int last = -1;
    for (int b : s.u) { if (b == last) continue; last = b; if (bottomOK(C, b, W, Hm)) return true; }
    return false;
}
static void addTo(const Ctx& C, SB& s, int c) {
    s.u.push_back(c); s.sumW += C.wg[c]; s.sumHm += C.H[c] - C.NH[c]; s.minISM = min(s.minISM, C.ISM[c]);
}
// returns order bottom->top
static vector<int> finalizeOrder(const Ctx& C, const SB& s) {
    int best = -1; ll bestSlack = LLONG_MIN;
    for (int idx = 0; idx < (int)s.u.size(); idx++) {
        int b = s.u[idx];
        if (!bottomOK(C, b, s.sumW, s.sumHm)) continue;
        ll slack = C.tmm[b] - (s.sumW - C.wg[b]);
        if (best < 0 || slack > bestSlack) { best = idx; bestSlack = slack; }
    }
    if (best < 0) { fprintf(stderr, "internal error: no valid bottom\n"); exit(3); }
    vector<int> rest;
    for (int idx = 0; idx < (int)s.u.size(); idx++) if (idx != best) rest.push_back(s.u[idx]);
    stable_sort(rest.begin(), rest.end(), [&](int a, int b) {
        if (C.wg[a] != C.wg[b]) return C.wg[a] > C.wg[b];
        if (C.H[a] != C.H[b]) return C.H[a] > C.H[b];
        return a < b; });
    vector<int> ord; ord.push_back(s.u[best]); ord.insert(ord.end(), rest.begin(), rest.end());
    return ord;
}

static bool buildStacks(const Ctx& C, const vector<int>& cnt, vector<SB>& stacks) {
    int G = (int)C.groups.size();
    vector<vector<int>> ug(G);
    for (int i = 0; i < C.n; i++) for (int k = 0; k < cnt[i]; k++) ug[C.grp[i]].push_back(i);
    for (int g = 0; g < G; g++) {
        auto& v = ug[g]; if (v.empty()) continue;
        if (!C.groups[g].ok) return false;
        stable_sort(v.begin(), v.end(), [&](int a, int b) {
            if (C.H[a] != C.H[b]) return C.H[a] > C.H[b];
            if (C.wg[a] != C.wg[b]) return C.wg[a] > C.wg[b];
            return a < b; });
        size_t first = stacks.size();
        for (int c : v) {
            bool placed = false;
            for (size_t j = first; j < stacks.size(); j++) {
                if (canAdd(C, stacks[j], c)) { addTo(C, stacks[j], c); placed = true; break; }
            }
            if (!placed) {
                SB s; s.grp = g;
                if (!canAdd(C, s, c)) return false;
                addTo(C, s, c); stacks.push_back(s);
            }
        }
    }
    return true;
}

// ---------------------------------------------------------------- placement
struct Col { int dx = 0; vector<int> st; ll w = 0; int usedY = 0; int ord = 0; };

// P3 (adjacency) check, strict & safe version: positive y-overlap with a stack s2 of the previous column
// AND (s2.yo in [y, y+d] or s2.ye in [y, y+d]) (literal rule formula).
static inline bool p3ok(int y, int d, const vector<pair<int,int>>& prev) {
    int a = y, b = y + d;
    for (auto& p : prev) {
        if (p.first < b && p.second > a && (p.first >= a || p.second <= b)) return true;
    }
    return false;
}
static bool dfsPlace(int j, int cur, const vector<int>& perm, const vector<int>& dys, const vector<int>& suf,
                     const vector<pair<int,int>>& prev, int TW, vector<int>& ys) {
    int k = (int)perm.size();
    if (j == k) return true;
    int d = dys[perm[j]];
    int maxY = TW - suf[j + 1] - d;
    if (maxY < cur) return false;
    vector<int> cs; cs.reserve(2 + 2 * prev.size());
    cs.push_back(cur); cs.push_back(maxY);
    for (auto& p : prev) { cs.push_back(p.first); cs.push_back(p.second - d); }
    sort(cs.begin(), cs.end()); cs.erase(unique(cs.begin(), cs.end()), cs.end());
    for (int y : cs) {
        if (y < cur || y > maxY) continue;
        if (!p3ok(y, d, prev)) continue;
        ys[perm[j]] = y;
        if (dfsPlace(j + 1, y + d, perm, dys, suf, prev, TW, ys)) return true;
    }
    return false;
}
static bool placeColumn(const vector<int>& dys, const vector<pair<int,int>>& prev, int TW, vector<int>& ys) {
    int k = (int)dys.size();
    ys.assign(k, 0);
    int sum = 0; for (int d : dys) sum += d;
    if (sum > TW) return false;
    // "spread" placement: single stack centered; otherwise first at 0, last flush with the far wall
    if (k == 1) ys[0] = (TW - dys[0]) / 2;
    else {
        int G = TW - sum, y = 0, base = G / (k - 1);
        for (int i = 0; i < k; i++) {
            ys[i] = y; y += dys[i];
            if (i < k - 1) y += (i == k - 2) ? (G - base * (k - 2)) : base;
        }
    }
    bool ok = true;
    if (!prev.empty()) for (int i = 0; i < k && ok; i++) if (!p3ok(ys[i], dys[i], prev)) ok = false;
    if (ok) return true;
    if (k > 6) return false;
    vector<int> perm(k); iota(perm.begin(), perm.end(), 0);
    vector<int> suf(k + 1, 0);
    do {
        suf[k] = 0;
        for (int j = k - 1; j >= 0; j--) suf[j] = suf[j + 1] + dys[perm[j]];
        if (dfsPlace(0, 0, perm, dys, suf, prev, TW, ys)) return true;
    } while (next_permutation(perm.begin(), perm.end()));
    return false;
}

// weight / axle computation for a subset of placed stacks
static void axle(const Truck& T, const vector<SB>& stacks, const vector<PStack>& pos, const vector<char>& use,
                 double& tm, double& emm, double& emr) {
    double sw = 0, sm = 0;
    for (size_t i = 0; i < pos.size(); i++) {
        if (!use[i]) continue;
        double w = stacks[pos[i].sb].sumW / 1000.0;
        sm += w; sw += (pos[i].xo + pos[i].dx / 2.0) * w;
    }
    tm = sm;
    if (sm <= 0) { emm = 0; emr = 0; return; }
    double eje = sw / sm;
    double ejr = T.EJeh + T.EJhr - eje;
    double emh = (sm * ejr + T.EM * T.EJcr) / T.EJhr;
    emr = sm + T.EM - emh;
    emm = (T.CM * T.CJfc + emh * T.CJfh) / T.CJfm;
}
static bool checkWeights(const Ctx& C, const vector<SB>& stacks, const vector<PStack>& pos, double& emmAll, double& emrAll) {
    const Truck& T = *C.T;
    // supplier pickup prefixes (by supplier loading order)
    set<int> orders;
    vector<int> so(pos.size());
    for (size_t i = 0; i < pos.size(); i++) { so[i] = C.groups[stacks[pos[i].sb].grp].key[0]; orders.insert(so[i]); }
    for (int o : orders) {
        vector<char> use(pos.size());
        for (size_t i = 0; i < pos.size(); i++) use[i] = so[i] <= o;
        double tm, emm, emr;
        axle(T, stacks, pos, use, tm, emm, emr);
        if (tm <= 0) continue;
        if (emm > T.EMmm - 1.0 || emr > T.EMmr - 1.0) return false;
    }
    vector<char> all(pos.size(), 1);
    double tm;
    axle(T, stacks, pos, all, tm, emmAll, emrAll);
    return true;
}

static bool placeSeq(vector<Col> seq, const vector<int>& dy, const vector<SB>& stacks, const Truck& T,
                     vector<PStack>& pos, int& length) {
    vector<pair<int,int>> prev; int x = 0;
    pos.clear();
    for (size_t i = 0; i < seq.size(); i++) {
        vector<int> st = seq[i].st;
        int cdx = seq[i].dx;
        stable_sort(st.begin(), st.end(), [&](int a, int b) { if (dy[a] != dy[b]) return dy[a] > dy[b]; return a < b; });
        vector<int> ys;
        while (true) {
            vector<int> dys; for (int s : st) dys.push_back(dy[s]);
            if (placeColumn(dys, prev, T.W, ys)) break;
            if (st.size() <= 1) return false; // should not happen
            int s = st.back(); st.pop_back();
            Col nc; nc.dx = cdx; nc.st = {s}; nc.w = stacks[s].sumW; nc.usedY = dy[s]; nc.ord = seq[i].ord;
            seq.insert(seq.begin() + i + 1, nc);
        }
        if (x + cdx > T.L) return false;
        prev.clear();
        for (size_t j = 0; j < st.size(); j++) {
            PStack p; p.sb = st[j]; p.xo = x; p.yo = ys[j]; p.dx = cdx; p.dy = dy[st[j]];
            pos.push_back(p); prev.push_back({p.yo, p.yo + p.dy});
        }
        x += cdx;
    }
    length = x;
    return true;
}

static bool layoutStacks(const Ctx& C, vector<SB>& stacks, Layout& out) {
    const Truck& T = *C.T;
    int S = (int)stacks.size();
    vector<int> dx(S), dy(S);
    map<array<int,3>, vector<int>> byKey;
    for (int s = 0; s < S; s++) { auto& g = C.groups[stacks[s].grp]; dx[s] = g.dx; dy[s] = g.dy; byKey[g.key].push_back(s); }
    vector<vector<Col>> colsByKey;
    int ordc = 0;
    ll areaLen = 0;
    for (auto& kv : byKey) {
        map<int, vector<int>, greater<int>> byDx;
        for (int s : kv.second) byDx[dx[s]].push_back(s);
        vector<Col> cols;
        for (auto& dv : byDx) {
            vector<int> v = dv.second;
            stable_sort(v.begin(), v.end(), [&](int a, int b) {
                if (dy[a] != dy[b]) return dy[a] > dy[b];
                if (stacks[a].sumW != stacks[b].sumW) return stacks[a].sumW > stacks[b].sumW;
                return a < b; });
            size_t first = cols.size();
            for (int s : v) {
                bool placed = false;
                for (size_t j = first; j < cols.size(); j++) if (cols[j].usedY + dy[s] <= T.W) {
                    cols[j].st.push_back(s); cols[j].usedY += dy[s]; cols[j].w += stacks[s].sumW; placed = true; break; }
                if (!placed) { Col c; c.dx = dv.first; c.st = {s}; c.usedY = dy[s]; c.w = stacks[s].sumW; c.ord = ordc++; cols.push_back(c); areaLen += c.dx; }
            }
        }
        colsByKey.push_back(cols);
    }
    if (areaLen > T.L) return false; // columns alone exceed truck length (splits only add length)
    for (int strat = 0; strat < 3; strat++) {
        vector<Col> seq;
        for (auto& cols : colsByKey) {
            vector<Col> cc = cols;
            if (strat == 0) stable_sort(cc.begin(), cc.end(), [&](const Col& a, const Col& b) {
                __int128 l = (__int128)a.w * b.dx, r = (__int128)b.w * a.dx;
                if (l != r) return l < r;
                if (a.usedY != b.usedY) return a.usedY > b.usedY;
                return a.ord < b.ord; });
            else if (strat == 2) stable_sort(cc.begin(), cc.end(), [&](const Col& a, const Col& b) {
                __int128 l = (__int128)a.w * b.dx, r = (__int128)b.w * a.dx;
                if (l != r) return l > r;
                if (a.usedY != b.usedY) return a.usedY > b.usedY;
                return a.ord < b.ord; });
            seq.insert(seq.end(), cc.begin(), cc.end());
        }
        vector<PStack> pos; int length = 0;
        if (!placeSeq(seq, dy, stacks, T, pos, length)) continue;
        double emm, emr;
        if (!checkWeights(C, stacks, pos, emm, emr)) continue;
        out.stacks = stacks; out.pos = pos; out.length = length; out.emm = emm; out.emr = emr;
        return true;
    }
    return false;
}

static bool feasible(const Ctx& C, const vector<int>& cnt, Layout& out) {
    ll tot = 0;
    for (int i = 0; i < C.n; i++) tot += (ll)cnt[i] * C.wg[i];
    if (tot > C.T->maxWg - 1) return false;
    vector<SB> stacks;
    if (!buildStacks(C, cnt, stacks)) return false;
    return layoutStacks(C, stacks, out);
}

// choose orientation (dx, dy) for a footprint
static bool chooseOrient(const Truck& T, int L, int W, int forced, int& dx, int& dy) {
    vector<pair<int,int>> opts;
    if (forced != 2 && W <= T.W && L <= T.L) opts.push_back({L, W});
    if (forced != 1 && L <= T.W && W <= T.L) opts.push_back({W, L});
    if (opts.empty()) return false;
    int bi = 0;
    for (int i = 1; i < (int)opts.size(); i++) {
        ll n0 = T.W / opts[bi].second, n1 = T.W / opts[i].second;
        // per-stack length = dx / n ; smaller better
        if ((ll)opts[i].first * n0 < (ll)opts[bi].first * n1) bi = i;
    }
    dx = opts[bi].first; dy = opts[bi].second;
    return true;
}

static Ctx makeCtx(const Truck& T, const vector<int>& candRows) {
    Ctx C; C.T = &T; C.n = (int)candRows.size();
    C.row = candRows;
    C.tmm.resize(C.n); C.grp.resize(C.n); C.H.resize(C.n); C.NH.resize(C.n); C.ISM.resize(C.n); C.wg.resize(C.n);
    map<string,int> gid;
    for (int i = 0; i < C.n; i++) {
        const Item& it = items[candRows[i]];
        C.H[i] = it.H; C.NH[i] = it.NH; C.ISM[i] = it.ISM; C.wg[i] = it.wg;
        auto tt = T.tmm.find(it.supplier + "|" + it.product + "|" + it.pdock);
        C.tmm[i] = (tt == T.tmm.end()) ? 0 : tt->second;
        string gk = it.supplier + "|" + it.sdock + "|" + it.pdock + "|" + it.stackcode + "|" + to_string(it.L) + "|" + to_string(it.W) + "|" + to_string(it.forced);
        auto f = gid.find(gk);
        if (f == gid.end()) {
            GroupInfo g; g.L = it.L; g.W = it.W; g.forced = it.forced; g.stackcode = it.stackcode;
            auto so = T.supOrd.find(it.supplier);
            g.key[0] = so == T.supOrd.end() ? 0 : so->second;
            auto sd = T.sdockOrd.find(it.supplier + "|" + it.sdock);
            g.key[1] = (it.sdock.empty() || sd == T.sdockOrd.end()) ? 0 : sd->second;
            auto pd = T.pdockOrd.find(it.pdock);
            g.key[2] = pd == T.pdockOrd.end() ? 0 : pd->second;
            long double lim = (long double)T.TEM * it.L * it.W / 1000.0L; // grams
            g.densLimit = (ll)floorl(lim - 1e-9L) - 1;
            g.ok = chooseOrient(T, it.L, it.W, it.forced, g.dx, g.dy);
            int id = (int)C.groups.size();
            C.groups.push_back(g); gid[gk] = id; C.grp[i] = id;
        } else C.grp[i] = f->second;
    }
    return C;
}

// ---------------------------------------------------------------- main
static string fmtGrams(ll g) { char buf[64]; snprintf(buf, sizeof buf, "%lld.%03lld", g / 1000, g % 1000); return buf; }
static string fmtVol(ll mm3) { // mm^3 -> m^3 exact decimal
    char buf[64]; snprintf(buf, sizeof buf, "%lld.%09lld", mm3 / 1000000000LL, mm3 % 1000000000LL); return buf; }
static string stackCode(int k) { // 0->A, 25->Z, 26->AA ...
    string s; k++;
    while (k > 0) { int r = (k - 1) % 26; s.insert(s.begin(), (char)('A' + r)); k = (k - 1) / 26; }
    return s;
}

struct Used { int tIdx; string id; Layout lay; vector<int> candRows; };

int main(int argc, char** argv) {
    string inDir = argc > 1 ? argv[1] : "/app/data/campaign";
    string outDir = argc > 2 ? argv[2] : "/app/results";
    Table ti = readTable(inDir + "/input_items.csv");
    Table tt = readTable(inDir + "/input_trucks.csv");

    for (auto& r : ti.rows) {
        Item it;
        it.ident = r[ti.c("Item ident")];
        it.supplier = r[ti.c("Supplier code")];
        it.sdock = r[ti.c("Supplier dock")];
        it.plant = r[ti.c("Plant code")];
        it.pdock = r[ti.c("Plant dock")];
        it.product = r[ti.c("Product code")];
        it.package = r[ti.c("Package code")];
        it.qty = (int)toI(r[ti.c("Number of items")]);
        it.L = (int)toI(r[ti.c("Length")]);
        it.W = (int)toI(r[ti.c("Width")]);
        it.H = (int)toI(r[ti.c("Height")]);
        it.wg = llround(toD(r[ti.c("Weight")]) * 1000.0);
        it.NH = (int)toI(r[ti.c("Nesting height")]);
        it.stackcode = r[ti.c("Stackability code")];
        string fo = lower(r[ti.c("Forced orientation")]);
        it.forced = (fo == "lengthwise") ? 1 : (fo == "widthwise") ? 2 : 0;
        it.IDE = toTime(r[ti.c("Earliest arrival time")]);
        it.IDL = toTime(r[ti.c("Latest arrival time")]);
        string ism = r[ti.c("Max stackability")];
        it.ISM = ism.empty() ? 1000000 : (int)toI(ism);
        if (it.ISM <= 0) it.ISM = 1000000;
        items.push_back(it);
    }
    {
        map<string,int> tIndex; vector<Truck> tv;
        for (auto& r : tt.rows) {
            string id = r[tt.c("Id truck")];
            auto f = tIndex.find(id);
            int idx;
            if (f == tIndex.end()) {
                Truck t; t.id = id;
                t.plant = r[tt.c("Plant code")];
                t.TDA = toTime(r[tt.c("Arrival time")]);
                t.L = (int)toI(r[tt.c("Length")]); t.W = (int)toI(r[tt.c("Width")]); t.H = (int)toI(r[tt.c("Height")]);
                t.maxWg = llround(toD(r[tt.c("Max weight")]) * 1000.0);
                string md = lower(r[tt.c("Stack with multiple docks")]);
                t.multi = (md == "1" || md == "yes" || md == "true") ? 1 : 0;
                t.TEM = toD(r[tt.c("Max density")]);
                t.cost = toD(r[tt.c("Cost")]);
                t.EMmm = toD(r[tt.c("EMmm")]); t.EMmr = toD(r[tt.c("EMmr")]);
                t.CM = toD(r[tt.c("CM")]); t.CJfm = toD(r[tt.c("CJfm")]); t.CJfc = toD(r[tt.c("CJfc")]); t.CJfh = toD(r[tt.c("CJfh")]);
                t.EM = toD(r[tt.c("EM")]); t.EJhr = toD(r[tt.c("EJhr")]); t.EJcr = toD(r[tt.c("EJcr")]); t.EJeh = toD(r[tt.c("EJeh")]);
                idx = (int)tv.size(); tv.push_back(t); tIndex[id] = idx;
            } else idx = f->second;
            Truck& t = tv[idx];
            string sup = r[tt.c("Supplier code")], sd = r[tt.c("Supplier dock")], pd = r[tt.c("Plant dock")], pr = r[tt.c("Product code")];
            t.supOrd[sup] = (int)toI(r[tt.c("Supplier loading order")]);
            if (!sd.empty()) t.sdockOrd[sup + "|" + sd] = (int)toI(r[tt.c("Supplier dock loading order")]);
            t.pdockOrd[pd] = (int)toI(r[tt.c("Plant dock loading order")]);
            t.tmm[sup + "|" + pr + "|" + pd] = llround(toD(r[tt.c("Max weight on the bottom item in stacks")]) * 1000.0);
        }
        sort(tv.begin(), tv.end(), [](const Truck& a, const Truck& b) { if (a.TDA != b.TDA) return a.TDA < b.TDA; return a.id < b.id; });
        trucks = tv;
    }
    int NT = (int)trucks.size(), NI = (int)items.size();
    // compatibility
    map<string, vector<int>> spIndex; // supplier|product|pdock -> trucks (sorted)
    for (int t = 0; t < NT; t++) for (auto& kv : trucks[t].tmm) spIndex[kv.first].push_back(t);
    vector<vector<int>> compat(NI);
    vector<vector<int>> truckCands(NT);
    vector<int> lastIdx(NI, -1), remQ(NI);
    for (int i = 0; i < NI; i++) {
        const Item& it = items[i];
        remQ[i] = it.qty;
        auto f = spIndex.find(it.supplier + "|" + it.product + "|" + it.pdock);
        if (f != spIndex.end()) for (int t : f->second) {
            const Truck& T = trucks[t];
            if (T.plant != it.plant) continue;
            if (!(it.IDE <= T.TDA && T.TDA <= it.IDL)) continue;
            compat[i].push_back(t);
        }
        if (compat[i].empty()) { fprintf(stderr, "Item %s has no compatible truck\n", it.ident.c_str()); return 4; }
        lastIdx[i] = compat[i].back();
        for (int t : compat[i]) truckCands[t].push_back(i);
    }

    vector<Used> used;
    long long nExtra = 0, nPlanned = 0;
    for (int t = 0; t < NT; t++) {
        const Truck& T = trucks[t];
        int extraNo = 0;
        for (int copy = 0;; copy++) {
            vector<int> cand;
            for (int i : truckCands[t]) if (remQ[i] > 0) cand.push_back(i);
            if (cand.empty()) break;
            bool hasMust = false;
            for (int i : cand) if (lastIdx[i] == t) { hasMust = true; break; }
            if (copy > 0 && !hasMust) break;
            stable_sort(cand.begin(), cand.end(), [&](int a, int b) {
                if (lastIdx[a] != lastIdx[b]) return lastIdx[a] < lastIdx[b];
                if (items[a].IDL != items[b].IDL) return items[a].IDL < items[b].IDL;
                if (items[a].stackcode != items[b].stackcode) return items[a].stackcode < items[b].stackcode;
                return a < b; });
            Ctx C = makeCtx(T, cand);
            vector<int> cnt(C.n, 0);
            Layout best; best.length = 0;
            ll curW = 0;
            for (int pass = 0; pass < 2; pass++) {
                for (int i = 0; i < C.n; i++) {
                    int avail = remQ[C.row[i]] - cnt[i];
                    if (avail <= 0) continue;
                    ll room = (T.maxWg - 1) - curW;
                    if (room < C.wg[i]) continue;
                    if ((ll)avail * C.wg[i] > room) avail = (int)(room / C.wg[i]);
                    if (avail <= 0) continue;
                    Layout lay;
                    cnt[i] += avail;
                    if (feasible(C, cnt, lay)) { best = lay; curW += (ll)avail * C.wg[i]; continue; }
                    cnt[i] -= avail;
                    int lo = 0, hi = avail;
                    while (hi - lo > 1) {
                        int mid = (lo + hi) / 2;
                        cnt[i] += mid;
                        Layout l2;
                        if (feasible(C, cnt, l2)) { lo = mid; best = l2; } else hi = mid;
                        cnt[i] -= mid;
                    }
                    cnt[i] += lo; curW += (ll)lo * C.wg[i];
                }
            }
            int tot = 0, must = 0;
            for (int i = 0; i < C.n; i++) { tot += cnt[i]; if (lastIdx[C.row[i]] == t) must += cnt[i]; }
            if (tot == 0) {
                if (hasMust) { fprintf(stderr, "Cannot load must-go items for truck %s\n", T.id.c_str()); return 5; }
                break;
            }
            if (copy > 0 && must == 0) { fprintf(stderr, "Extra truck without progress %s\n", T.id.c_str()); return 6; }
            // verify final
            Layout fin;
            if (!feasible(C, cnt, fin)) { fprintf(stderr, "internal: final infeasible\n"); return 7; }
            for (int i = 0; i < C.n; i++) remQ[C.row[i]] -= cnt[i];
            Used u; u.tIdx = t; u.lay = fin; u.candRows = C.row;
            if (copy == 0) { u.id = T.id; nPlanned++; }
            else { extraNo++; u.id = "Q" + T.id.substr(1) + "_" + to_string(extraNo); nExtra++; }
            used.push_back(u);
        }
        for (int i : truckCands[t]) if (lastIdx[i] == t && remQ[i] > 0) { fprintf(stderr, "unassigned must-go remains\n"); return 8; }
    }
    for (int i = 0; i < NI; i++) if (remQ[i] != 0) { fprintf(stderr, "Item %s remaining %d\n", items[i].ident.c_str(), remQ[i]); return 9; }

    // ---------------------------------------------------------------- output
    FILE* fi = fopen((outDir + "/output_items.csv").c_str(), "wb");
    FILE* fs = fopen((outDir + "/output_stacks.csv").c_str(), "wb");
    FILE* ft = fopen((outDir + "/output_trucks.csv").c_str(), "wb");
    if (!fi || !fs || !ft) { fprintf(stderr, "cannot open outputs\n"); return 10; }
    fprintf(fi, "Item ident;Id truck;Id stack;Item code;X origin;Y origin;Z origin;X extremity;Y extremity;Z extremity\n");
    fprintf(fs, "Id truck;Id stack;Stack code;X origin;Y origin;Z origin;X extremity;Y extremity;Z extremity\n");
    fprintf(ft, "Id truck;Loaded length;Weight of loaded items;Volume of loaded items;EMm;EMr\n");
    double totalCost = 0;
    for (auto& u : used) {
        const Truck& T = trucks[u.tIdx];
        Ctx C = makeCtx(T, u.candRows);
        const Layout& L = u.lay;
        // order stacks by (xo, yo)
        vector<int> order(L.pos.size()); iota(order.begin(), order.end(), 0);
        stable_sort(order.begin(), order.end(), [&](int a, int b) {
            if (L.pos[a].xo != L.pos[b].xo) return L.pos[a].xo < L.pos[b].xo;
            return L.pos[a].yo < L.pos[b].yo; });
        ll wsum = 0, vsum = 0; int maxX = 0;
        int k = 0;
        for (int pi : order) {
            const PStack& p = L.pos[pi];
            const SB& s = L.stacks[p.sb];
            vector<int> ord = finalizeOrder(C, s);
            string sid = u.id + "_" + to_string(k + 1);
            string scode = stackCode(k);
            // z convention (as validated by the official checker): contiguous chain.
            // bottom item occupies [0, H]; each upper item occupies [prev_ze, prev_ze + H - NH]
            // so that the top equals the stack height sum(H) - sum_{non-bottom}(NH).
            int ze = 0;
            for (size_t lv = 0; lv < ord.size(); lv++) {
                const Item& it = items[C.row[ord[lv]]];
                int zo = (lv == 0) ? 0 : ze;
                ze = zo + ((lv == 0) ? it.H : it.H - it.NH);
                fprintf(fi, "%s;%s;%s;%s%d;%d;%d;%d;%d;%d;%d\n", it.ident.c_str(), u.id.c_str(), sid.c_str(), scode.c_str(), (int)lv + 1,
                        p.xo, p.yo, zo, p.xo + p.dx, p.yo + p.dy, ze);
                wsum += it.wg;
            }
            if (ze > T.H) { fprintf(stderr, "internal: stack too high\n"); return 11; }
            vsum += (ll)p.dx * p.dy * ze; // loaded volume = total stack volume
            fprintf(fs, "%s;%s;%s;%d;%d;%d;%d;%d;%d\n", u.id.c_str(), sid.c_str(), scode.c_str(), p.xo, p.yo, 0, p.xo + p.dx, p.yo + p.dy, ze);
            maxX = max(maxX, p.xo + p.dx);
            k++;
        }
        fprintf(ft, "%s;%d;%s;%s;%.6f;%.6f\n", u.id.c_str(), maxX, fmtGrams(wsum).c_str(), fmtVol(vsum).c_str(), L.emm, L.emr);
        totalCost += (u.id[0] == 'Q') ? T.cost * 1.2 : T.cost;
    }
    fclose(fi); fclose(fs); fclose(ft);
    fprintf(stderr, "trucks used: planned=%lld extra=%lld total=%zu\n", nPlanned, nExtra, used.size());
    return 0;
}
