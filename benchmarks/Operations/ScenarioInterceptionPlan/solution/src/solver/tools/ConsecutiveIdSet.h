////////////////////////////////
/// usage : 1.	bidirection index for fixed size of numbers.
///             for each number i, there should be (i == item[index[i]]).
/// 
/// note  : 1.  "capacity" indicate the max or total valid item number which is different from std container,
///             while "itemNum" and "size" indicate the current inserted items.
///         2.  index is count from 0, while item is between [min, max].
///         3.  it will not consider index out of range error.
////////////////////////////////

#ifndef CN_HUST_GOAL_COMMON_CONSECUTIVE_ID_SET_H
#define CN_HUST_GOAL_COMMON_CONSECUTIVE_ID_SET_H


#include <algorithm>

#include "./Typedef.h"
#include "./Exception.h"
#include "./Math.h"
#include "./Random.h"

namespace goal {

class ConsecutiveIdList {
public:
    using ID = int;


    ConsecutiveIdList(ID count) : ids(generate(count)), upperBound(count) {}
    ConsecutiveIdList(const Vec<ID> &idList) : ids(idList), upperBound(sCast<ID>(idList.size())) {}


    static Vec<ID> generate(ID count) {
        Vec<ID> l(count);
        for (ID i = 0; i < count; ++i) { l[i] = i; }
        return l;
    }

    bool get(ID &i) {
        if (ids[i] < upperBound) {
            i = ids[i];
            return true;
        }
        remove(i);
        return false;
    }

    static void remove(Vec<ID> &l, ID i) {
        l[i] = l.back();
        l.pop_back();
    }
    void remove(ID i) { remove(ids, i); }
    void remove_safe(ID i) {
        if (i < size()) { remove(i); }
    }

    void drop(ID newSize) { // TODO[szx][8]: make sure `newSize < upperBound`.
        upperBound = newSize;
        if (newSize < size()) { ids.resize(newSize); }
    }

    ID size() const { return sCast<ID>(ids.size()); }

    bool empty() const { return ids.empty(); }


protected:
    Vec<ID> ids;
    ID upperBound;
};

template<typename Item = long long>
class ConsecutiveIdSet {
    static constexpr bool SafetyCheck = false;
public:
    using Index = ID; // EXT[szx][4]: make sure no integer overflow! make it a template parameter?
    //using Item = Index;


    static constexpr Index InvalidIndex = -1;


    ConsecutiveIdSet(Index capacity, Item minValue = 0)
        : lowerBound(minValue), upperBound(minValue + capacity), itemNum(0),
        items(capacity), index(capacity, InvalidIndex) {
    }


    // if the item is in range [min, max], return true.
    bool isItemValid(Item e) const { return math::inRange(e, lowerBound, upperBound); }
    // if the index is in range [0, itemNum), return true.
    bool isIndexValid(Index i) const { return math::inRange(i, Index(0), itemNum); }
    // if the item has been inserted, return true.
    bool isItemExist(Item e) const {
        if (SafetyCheck && !isItemValid(e)) { throw IndexOutOfRangeException(); }
		return (index[e - lowerBound] != InvalidIndex);
	}

    // return item at the index of i.
    Item itemAt(Index i) const {
        if (SafetyCheck && !isIndexValid(i)) { throw IndexOutOfRangeException(); }
        return items[i];
    }
    // return index of item e.
    Index indexOf(Item e) const {
        if (SafetyCheck && !isItemValid(e)) { throw ItemNotExistException(); }
        return index[e - lowerBound];
    }
    // return the last item.
    Item back() const { return itemAt(size() - 1); }

    // insert item e and update index.
    void insert(Item e) {
        if (SafetyCheck && isItemExist(e)) { throw DuplicateItemException(); }
        items[itemNum] = e;
        index[e - lowerBound] = itemNum++;
    }
    bool tryInsert(Item e) {
        if (isItemExist(e)) { return false; }
        insert(e);
        return true;
    }
    // remove item and update index.
    // never call erase during forward traversing, but it is usually ok for backward traversing.
    void eraseItem(Item e) {
        if (SafetyCheck && !isItemExist(e)) { throw ItemNotExistException(); }
        Index i = indexOf(e);
        index[items[--itemNum] - lowerBound] = i;
        items[i] = items[itemNum];
        index[e - lowerBound] = InvalidIndex;
    }
    // remove index and update item.
    // never call erase during forward traversing, but it is usually ok for backward traversing.
    void eraseIndex(Index i) {
        if (SafetyCheck && !isIndexValid(i)) { throw IndexOutOfRangeException(); }
        Item e = itemAt(i);
        index[items[--itemNum] - lowerBound] = i;
        items[i] = items[itemNum];
        index[e - lowerBound] = InvalidIndex;
    }
    // remove the last item.
    Item pop() {
        Item e = itemAt(--itemNum);
        index[e - lowerBound] = InvalidIndex;
        return e;
    }

    // return number of inserted items.
    Index size() const { return itemNum; }

    bool empty() const { return size() <= 0; }

    // keep the capacity but invalidate all items and reset the size.
    void clear(bool sparseData = false) {
        if (sparseData) {
            for (Index i = 0; i < itemNum; ++i) { index[items[i] - lowerBound] = InvalidIndex; }
        } else {
            std::fill(index.begin(), index.end(), InvalidIndex);
        }
        itemNum = 0;
    }

    //const Arr<Item>& getItems() const { return items; } // TODO[szx][0]: handle the invalid items in [itemNum, upperBound).
    const Vec<Index>& getIndices() const { return index; }
	const Vec<Item> getItems() const { return Vec<Item>(items.begin(), items.begin() + itemNum); }		//add by luocanhui

	Item randomPick(Random &rand) { return items[rand.pick(0, int(itemNum))]; }	//add by luocanhui

protected:
    Item lowerBound; // min value of items.
    Item upperBound; // max value of items.

    Index itemNum; // current number of items.
    Vec<Item> items; // items value, itemNum valid items in it.
    Vec<Index> index; // items index in item.
};

}


#endif // CN_HUST_GOAL_COMMON_CONSECUTIVE_ID_SET_H