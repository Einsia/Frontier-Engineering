/*************************************************************************
    > File Name: BookshelfWriter.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_BOOKSHELFWRITER_H
#define DREAMPLACE_BOOKSHELFWRITER_H

#include <cstdio>
#include <vector>
#include "PlaceWriter.h"

DREAMPLACE_BEGIN_NAMESPACE

class BookShelfWriter : public PlaceSolWriter
{
    public:
        typedef PlaceSolWriter base_type;
        typedef PlaceDB::index_type index_type;

        BookShelfWriter(PlaceDB const& db) : base_type(db) {}
        BookShelfWriter(BookShelfWriter const& rhs) : base_type(rhs) {}

        /// write .plx file  
        /// \param outFile is plx file name
        /// \param first, last should contain components to write 
        bool write(std::string const& outFile, 
                float const* x = NULL, float const* y = NULL,
                PlaceDB::index_type const* z = NULL) const;
        /// write all files in book shelf format 
        /// \param outFile is aux file name 
        /// \param first, last should contain components to write 
        bool writeAll(std::string const& outFile,
                float const* x = NULL, float const* y = NULL,
                PlaceDB::index_type const* z = NULL) const;

    protected:
        bool writePlx(std::string const& outFileNoSuffix, 
                float const* x = NULL, float const* y = NULL,
                PlaceDB::index_type const* z = NULL) const;
        void writeHeader(FILE* os, std::string const& fileType) const;
        FILE* openFile(std::string const& outFileNoSuffix, std::string const& fileType) const;
        void closeFile(FILE* os) const;
};

DREAMPLACE_END_NAMESPACE

#endif
