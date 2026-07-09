/*************************************************************************
    > File Name: BookshelfWriter.cpp
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Mail: yibolin@utexas.edu
    > Created Time: Mon 14 Mar 2016 09:22:46 PM CDT
    > Updated: Mar 2021
 ************************************************************************/

#include "BookshelfWriter.h"
#include "Iterators.h"
#include "PlaceDB.h"
#include <cstdio>
#include <limbo/string/String.h>

DREAMPLACE_BEGIN_NAMESPACE

bool BookShelfWriter::write(std::string const& outFile, 
                float const* x, float const* y,
                PlaceDB::index_type const* z) const
{
    std::string outFileNoSuffix = limbo::trim_file_suffix(outFile);
    return writePlx(outFileNoSuffix, x, y, z);
}
bool BookShelfWriter::writeAll(std::string const& outFile, 
                float const* x, float const* y,
                PlaceDB::index_type const* z) const
{
    std::string outFileNoSuffix = limbo::trim_file_suffix(outFile);
    std::string designName = "design";

    bool flag = writePlx(outFileNoSuffix, x, y, z);

    return true;
}

bool BookShelfWriter::writePlx(std::string const& outFileNoSuffix, 
                float const* x, float const* y,
                PlaceDB::index_type const* z) const 
{
    FILE* out = openFile(outFileNoSuffix, "pl");
    if (out == NULL)
        return false;

    writeHeader(out, "pl"); // use pl instead of plx to accommodate parser

    for (int mIdx = 0; mIdx < m_db.numMovable() + m_db.numFixed(); ++mIdx)
    {
        float xx = m_db.nodeX(mIdx); 
        float yy = m_db.nodeY(mIdx); 
        PlaceDB::index_type zz = m_db.nodeZ(mIdx); 
        fprintf(out, "%s %g %g %d", m_db.nodeName(mIdx).c_str(), xx, yy, zz);
        if (mIdx < m_db.numMovable())
        {
            fprintf(out, "\n"); 
        } else
        {
            fprintf(out, " /FIXED \n"); 
        }
    }

    closeFile(out);
    return true;
}

void BookShelfWriter::writeHeader(FILE* os, std::string const& fileType) const
{
    fprintf(os, "\n");
}
FILE* BookShelfWriter::openFile(std::string const& outFileNoSuffix, std::string const& fileType) const
{
    dreamplacePrint(kINFO, "writing placement to %s\n", (outFileNoSuffix+"."+fileType).c_str());

    FILE* out = fopen((outFileNoSuffix+"."+fileType).c_str(), "w");
    if (out == NULL)
        dreamplacePrint(kERROR, "unable to open %s for write\n", (outFileNoSuffix+"."+fileType).c_str());
    return out;
}
void BookShelfWriter::closeFile(FILE* os) const 
{
    fclose(os);
}

DREAMPLACE_END_NAMESPACE
