#pragma once

#include "../lib/instance.h"
#include <filesystem>

namespace PACE2025_HS {
    static void recode_instance_info(
        std::ofstream& fp,
        const OriginalSCInstance& oins,
        const SimplifiedSCInstance& sins,
        double simplfy_time) {

        // 元素数目、元素最大/最小/平均大小
        // 集合数目、集合最大/最小/平均大小

        auto o_statistic_on_element = [&]() {
            std::map<ElementId, SetId> element_degree_count;
            printf("Element Infomation: \n");
            printf("\tElement Number: %d\n", oins.element_num_);
            SetId max_cover_n = 0, min_cover_n = oins.set_num_;
            Count avg_cover_n = 0;
            for (ElementId e = 0; e < oins.element_num_; ++e) {
                SetId cover_n = SetId(oins.elements_[e].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                element_degree_count[cover_n] += 1;
            }
            printf("\tElement Max Covered Number: %d\n", max_cover_n);
            printf("\tElement Min Covered Number: %d\n", min_cover_n);
            printf("\tElement Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / oins.element_num_);

            Str tmp_s1 = StringUtil::format("%.2f", 1.0 * avg_cover_n / oins.element_num_);

            fp << max_cover_n << "," << min_cover_n << "," << tmp_s1 << ",";
            };

        auto o_statistic_on_set = [&]() {
            std::map<SetId, ElementId> set_degree_count;
            printf("Set Infomation: \n");
            printf("\tSet Number: %d\n", oins.set_num_);
            SetId max_cover_n = 0, min_cover_n = oins.element_num_;
            Count avg_cover_n = 0;
            for (SetId s = 0; s < oins.set_num_; ++s) {
                ElementId cover_n = ElementId(oins.sets_[s].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                set_degree_count[cover_n] += 1;
            }
            printf("\tSet Max Covered Number: %d\n", max_cover_n);
            printf("\tSet Min Covered Number: %d\n", min_cover_n);
            printf("\tSet Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / oins.set_num_);

            Str tmp_s1 = StringUtil::format("%.2f", 1.0 * avg_cover_n / oins.set_num_);

            fp << max_cover_n << "," << min_cover_n << "," << tmp_s1 << ",";
            };


        auto s_statistic_on_element = [&]() {
            std::map<ElementId, SetId> element_degree_count;
            printf("Element Infomation: \n");
            printf("\tElement Number: %d\n", sins.element_num_);
            SetId max_cover_n = 0, min_cover_n = sins.set_num_;
            Count avg_cover_n = 0;
            for (ElementId e = 0; e < sins.element_num_; ++e) {
                SetId cover_n = SetId(sins.elements_[e].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                element_degree_count[cover_n] += 1;
            }
            printf("\tElement Max Covered Number: %d\n", max_cover_n);
            printf("\tElement Min Covered Number: %d\n", min_cover_n);
            printf("\tElement Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / sins.element_num_);

            Str tmp_s1 = StringUtil::format("%.2f", 1.0 * avg_cover_n / sins.element_num_);

            fp << max_cover_n << "," << min_cover_n << "," << tmp_s1 << ",";
            };

        auto s_statistic_on_set = [&]() {
            std::map<SetId, ElementId> set_degree_count;
            printf("Set Infomation: \n");
            printf("\tSet Number: %d\n", sins.set_num_);
            SetId max_cover_n = 0, min_cover_n = sins.element_num_;
            Count avg_cover_n = 0;
            for (SetId s = 0; s < sins.set_num_; ++s) {
                ElementId cover_n = ElementId(sins.sets_[s].size());
                if (max_cover_n < cover_n) { max_cover_n = cover_n; }
                if (min_cover_n > cover_n) { min_cover_n = cover_n; }
                avg_cover_n += cover_n;
                set_degree_count[cover_n] += 1;
            }
            printf("\tSet Max Covered Number: %d\n", max_cover_n);
            printf("\tSet Min Covered Number: %d\n", min_cover_n);
            printf("\tSet Avg Covered Number: %.2f\n", 1.0 * avg_cover_n / sins.set_num_);

            Str tmp_s1 = StringUtil::format("%.2f", 1.0 * avg_cover_n / sins.set_num_);

            fp << max_cover_n << "," << min_cover_n << "," << tmp_s1 << ",";
            };

        fp << oins.instname_ << "," << oins.element_num_ << "," << oins.set_num_ << ",";
        o_statistic_on_element(); o_statistic_on_set();
        fp << sins.element_num_ << "," << sins.set_num_ << ",";
        s_statistic_on_element(); s_statistic_on_set();
        fp << simplfy_time << "\n";
    }

}