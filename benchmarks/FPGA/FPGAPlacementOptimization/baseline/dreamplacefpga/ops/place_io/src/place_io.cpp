/**
 * @file   place_io.cpp
 * @author Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
 * @date   Mar 2021
 * @brief  Python binding 
 */

#include "PyPlaceDB.h"

DREAMPLACE_BEGIN_NAMESPACE

/// take numpy array 
template <typename T>
bool write(PlaceDB const& db, 
        std::string const& filename,
        pybind11::array_t<T, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
        pybind11::array_t<T, pybind11::array::c_style | pybind11::array::forcecast> const& y 
        )
{
    float* vx = NULL; 
    float* vy = NULL; 

    // assume all the movable nodes are in front of fixed nodes 
    // this is ensured by PlaceDB::sortNodeByPlaceStatus()
    PlaceDB::index_type lenx = x.size(); 
    if (lenx >= db.numMovable())
    {
        vx = new float [lenx];
        for (PlaceDB::index_type i = 0; i < lenx; ++i)
        {
            vx[i] = x.at(i); 
        }
    }
    PlaceDB::index_type leny = y.size(); 
    if (leny >= db.numMovable())
    {
        vy = new float [leny];
        for (PlaceDB::index_type i = 0; i < leny; ++i)
        {
            vy[i] = y.at(i); 
        }
    }

    //bool flag = db.write(filename, ff, vx, vy);
    bool flag = db.write(filename, vx, vy);

    if (vx)
    {
        delete [] vx; 
    }
    if (vy)
    {
        delete [] vy; 
    }

    return flag; 
}

/// take numpy array 
template <typename T>
void apply(PlaceDB& db, 
        pybind11::array_t<T, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
        pybind11::array_t<T, pybind11::array::c_style | pybind11::array::forcecast> const& y, 
        pybind11::array_t<PlaceDB::index_type, pybind11::array::c_style | pybind11::array::forcecast> const& z 
        )
{
    // assume all the movable nodes are in front of fixed nodes 
    if (db.numCCNodes() == 0)
    {
        for (int nIdx = 0; nIdx < db.numMovable()+db.numFixed(); ++nIdx)
        {
            float xx = x.at(nIdx); 
            float yy = y.at(nIdx); 
            PlaceDB::index_type zz = z.at(nIdx); 
            db.nodeXLocs().at(nIdx) = xx;
            db.nodeYLocs().at(nIdx) = yy;
            db.nodeZLocs().at(nIdx) = zz;
        }
    } else
    {
        for (int nIdx = 0; nIdx < db.numOrgMovable()+db.numFixed(); ++nIdx)
        {
            float xx = x.at(nIdx); 
            float yy = y.at(nIdx); 
            PlaceDB::index_type zz = z.at(nIdx); 
            db.orgNodeXLocs().at(nIdx) = xx;
            db.orgNodeYLocs().at(nIdx) = yy;
            db.orgNodeZLocs().at(nIdx) = zz;
        }
    }
}

PlaceDB place_io_forward(pybind11::str const& auxPath)
{

    DREAMPLACE_NAMESPACE::PlaceDB db; 

	bool flag; 

    // read bookshelf 
    flag = DREAMPLACE_NAMESPACE::readBookshelf(db, auxPath);
    dreamplaceAssertMsg(flag, "Failed to read input Bookshelf files");

    return db; 
}

DREAMPLACE_END_NAMESPACE

// create Python binding 

void bind_PlaceDB(pybind11::module&);
void bind_PyPlaceDB(pybind11::module&);

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {

    bind_PlaceDB(m); 
    bind_PyPlaceDB(m);

    m.def("write", [](DREAMPLACE_NAMESPACE::PlaceDB const& db, 
                std::string const& filename, 
                pybind11::array_t<float, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
                pybind11::array_t<float, pybind11::array::c_style | pybind11::array::forcecast> const& y) {return write(db, filename, x, y);}, 
            "Write Placement Solution (float)");
    m.def("write", [](DREAMPLACE_NAMESPACE::PlaceDB const& db, 
                std::string const& filename,
                pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
                pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& y) {return write(db, filename, x, y);}, 
            "Write Placement Solution (double)");
    m.def("apply", [](DREAMPLACE_NAMESPACE::PlaceDB& db, 
                pybind11::array_t<float, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
                pybind11::array_t<float, pybind11::array::c_style | pybind11::array::forcecast> const& y, 
                pybind11::array_t<DREAMPLACE_NAMESPACE::PlaceDB::index_type, pybind11::array::c_style | pybind11::array::forcecast> const& z) {apply(db, x, y, z);}, 
             "Apply Placement Solution (float)");
    m.def("apply", [](DREAMPLACE_NAMESPACE::PlaceDB& db, 
                pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& x, 
                pybind11::array_t<double, pybind11::array::c_style | pybind11::array::forcecast> const& y, 
                pybind11::array_t<DREAMPLACE_NAMESPACE::PlaceDB::index_type, pybind11::array::c_style | pybind11::array::forcecast> const& z) {apply(db, x, y, z);},
             "Apply Placement Solution (double)");
    m.def("pydb", [](DREAMPLACE_NAMESPACE::PlaceDB const& db){return DREAMPLACE_NAMESPACE::PyPlaceDB(db);}, "Convert PlaceDB to PyPlaceDB");
    m.def("forward", &DREAMPLACE_NAMESPACE::place_io_forward, "PlaceDB IO Read");
}


