/**
 * @file   legalize_auction.h
 * @author Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Jul 2023
 */
#ifndef _DREAMPLACE_LEGALIZE_AUCTION_H
#define _DREAMPLACE_LEGALIZE_AUCTION_H

#include <iostream>
#include <cstring>
#include <cassert>

DREAMPLACE_BEGIN_NAMESPACE

#define INVALID -1
#define BIG_POSITIVE 9999999

/// Auction Algorithm
template <typename T>
int run_auction(
    int num_nodes,
    int num_sites,
    T* data_ptr,      // data, num_sites*num_sites in row-major  
    int*   person2item_ptr, // results
    float auction_max_eps,
    float auction_min_eps,
    float auction_factor, 
    int auction_max_iters, 
    int* item2person_ptr=nullptr, 
    T* bids_ptr=nullptr, 
    T* prices_ptr=nullptr, 
    int* sbids_ptr=nullptr
)
{
    // Declare variables
    bool allocate_flag = false; 
    if (!item2person_ptr)
    {
        item2person_ptr = (int*)malloc(num_sites * sizeof(int));
        bids_ptr = (T*)malloc(num_sites * num_sites * sizeof(T));
        prices_ptr = (T*)malloc(num_sites * sizeof(T));
        sbids_ptr = (int*)malloc(num_sites * sizeof(int));
        allocate_flag = true; 
    }

    T *data = data_ptr;
    int *person2item = person2item_ptr;
    int *item2person = item2person_ptr;
    T *prices = prices_ptr;
    int *sbids = sbids_ptr;
    T *bids = bids_ptr;
    int num_assigned = 0; 

    for(int i = 0; i < num_sites; i++) {
        prices[i] = 0.0;
        person2item[i] = INVALID;
    }

    float auction_eps = auction_max_eps;
    int counter = 0;
    while(auction_eps >= auction_min_eps && counter < auction_max_iters) {
        for(int i = 0; i < num_sites; i++) {
            person2item[i] = INVALID;
            item2person[i] = INVALID;
        }
        num_assigned = 0;

        while(num_assigned < num_nodes && counter < auction_max_iters){
            counter += 1;

            std::memset(bids, BIG_POSITIVE, num_sites * num_sites * sizeof(T));
            std::memset(sbids, 0, num_sites * sizeof(int));

            for(int i = 0; i < num_nodes; i++) {
                if(person2item[i] == INVALID) {
                    T top1_val = BIG_POSITIVE; 
                    T top2_val = BIG_POSITIVE; 
                    int top1_col = BIG_POSITIVE; 
                    T tmp_val = BIG_POSITIVE;

                    for (int col = 0; col < num_sites; col++)
                    {
                        tmp_val = data[i * num_sites+ col]; 
                        if (tmp_val < 0)
                        {
                            continue;
                        }
                        tmp_val = tmp_val + prices[col];
                        if (tmp_val < top1_val)
                        {
                            top2_val = top1_val;
                            top1_col = col;
                            top1_val = tmp_val;
                        }
                        else if (tmp_val <= top2_val)
                        {
                            top2_val = tmp_val;
                        }
                    }
                    if (top2_val == BIG_POSITIVE)
                    {
                        top2_val = top1_val;
                    }
                    T bid = top1_val + auction_eps;
                    bids[i*num_sites + top1_col] = bid;
                    sbids[top1_col] = 1; 
                }
            }

            for(int j = 0; j < num_sites; j++) {
                if(sbids[j] != 0) {
                    T low_bid  = BIG_POSITIVE;
                    int low_bidder = INVALID;

                    T tmp_bid = BIG_POSITIVE;
                    for(int i = 0; i < num_nodes; i++){
                        tmp_bid = bids[i*num_sites + j]; 
                        if(tmp_bid < low_bid){
                            low_bid    = tmp_bid;
                            low_bidder = i;
                        }
                    }

                    int current_person = item2person[j];
                    if(current_person >= 0){
                        person2item[current_person] = INVALID; 
                    } else {
                        num_assigned++;
                    }

                    prices[j]                += low_bid;
                    person2item[low_bidder] = j;
                    item2person[j]           = low_bidder;
                }
            }
        }

        auction_eps *= auction_factor;
    } 

    ////DBG
    ////Print results
    //int score = 0;
    //for (int i = 0; i < num_nodes; i++) {
    //    std::cout << i << " " << person2item[i] << std::endl;
    //    score += data[i * num_sites + person2item[i]];
    //}
    //std::cout << "score=" <<score << std::endl;   
    ////DBG

    if (allocate_flag)
    {
        free(item2person_ptr); 
        free(bids_ptr);
        free(prices_ptr);  
        free(sbids_ptr); 
    }

    return (num_assigned >= num_nodes);
}

DREAMPLACE_END_NAMESPACE

#endif
