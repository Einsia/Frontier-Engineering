/*************************************************************************
    > File Name: LibCell.h
    > Author: Yibo Lin (DREAMPlace), Rachel Selina Rajarathnam (DREAMPlaceFPGA)
    > Updated: Mar 2021
 ************************************************************************/

#ifndef DREAMPLACE_MACRO_H
#define DREAMPLACE_MACRO_H

#include <string>
#include <vector>
#include <map>

DREAMPLACE_BEGIN_NAMESPACE

//class Macro : public Box<Object::coordinate_type>, public Object
class LibCell : public Object
{
    public:
        typedef Object base_type;
        typedef coordinate_traits<coordinate_type>::index_type index_type;
        typedef std::map<std::string, index_type> string2index_map_type;

        /// default constructor 
        LibCell();
        explicit LibCell(const std::string &name) : m_name(name) {}
        /// copy constructor
        LibCell(LibCell const& rhs);
        /// assignment
        LibCell& operator=(LibCell const& rhs);

        string2index_map_type const& libCellPinName2Type() const {return m_mPinName2Type;}
        string2index_map_type& libCellPinName2Type() {return m_mPinName2Type;}

        int pinType(std::string const& s) const 
        {
            string2index_map_type::const_iterator found = m_mPinName2Type.find(s);
            //return (found != m_mPinName2Type.end())? found->second : std::numeric_limits<index_type>::max();
            return (found != m_mPinName2Type.end())? found->second : -1;
        }

    void addInputPin(std::string& s)
    {
        m_inputPins.push_back(s); 
        m_mPinName2Type.insert(std::make_pair(s, 1));
    }
    void addOutputPin(std::string& s)
    {
        m_outputPins.push_back(s); 
        m_mPinName2Type.insert(std::make_pair(s, 0));
    }
    void addClkPin(std::string& s)
    {
        m_clkPins.push_back(s); 
        m_mPinName2Type.insert(std::make_pair(s, 2));
    }
    void addCtrlPin(std::string& s)
    {
        m_ctrlPins.push_back(s); 
        m_mPinName2Type.insert(std::make_pair(s, 3));
    }
    //When LUT and adder are combined together as single cell - need to differentiate the signals
    void addInputAddPin(std::string& s)
    {
        m_inputPins.push_back(s); 
        if (s == "cin0" || s.find("cin") != std::string::npos)
        {
            m_mPinName2Type.insert(std::make_pair(s, 31));
        } else if (s == "sharein0" || s.find("sharein") != std::string::npos)
        {
            m_mPinName2Type.insert(std::make_pair(s, 41));
        } else
        {
            m_mPinName2Type.insert(std::make_pair(s, 21));
        }
    }
    void addOutputAddPin(std::string& s)
    {
        m_outputPins.push_back(s); 
        if (s == "cout0" || s.find("cout") != std::string::npos)
        {
            m_mPinName2Type.insert(std::make_pair(s, 30));
        } else if (s == "shareout0" || s.find("shareout") != std::string::npos)
        {
            m_mPinName2Type.insert(std::make_pair(s, 40));
        } else
        {
            m_mPinName2Type.insert(std::make_pair(s, 20));
        }
    }

    // Getters
    const std::string &                 name() const                            { return m_name; }
    index_type                          id() const                              { return m_id; }

    const std::vector<std::string> &    inputPinArray() const                   { return m_inputPins; }
    std::vector<std::string> &         inputPinArray()                         { return m_inputPins; }
    const std::string&                  inputPin(index_type i) const            { return m_inputPins.at(i); }
    index_type                          numInputPins() const                    { return m_inputPins.size(); }

    const std::vector<std::string> &    outputPinArray() const                  { return m_outputPins; }
    std::vector<std::string> &         outputPinArray()                        { return m_outputPins; }
    const std::string&                  outputPin(index_type i) const           { return m_outputPins.at(i); }
    index_type                          numOutputPins() const                   { return m_outputPins.size(); }

    const std::vector<std::string> &    clkPinArray() const                     { return m_clkPins; }
    std::vector<std::string> &         clkPinArray()                           { return m_clkPins; }
    const std::string&                  clkPin(index_type i) const              { return m_clkPins.at(i); }
    index_type                          numClkPins() const                      { return m_clkPins.size(); }

    const std::vector<std::string> &    ctrlPinArray() const                    { return m_ctrlPins; }
    std::vector<std::string> &         ctrlPinArray()                          { return m_ctrlPins; }
    const std::string&                  ctrlPin(index_type i) const             { return m_ctrlPins.at(i); }
    index_type                          numCtrlPins() const                     { return m_ctrlPins.size(); }

    // Setters
    void                                setId(index_type id)                          { m_id = id; }


    protected:
        void copy(LibCell const& rhs);

        std::string m_name; ///< LibCell name 
        index_type m_id;

        std::vector<std::string> m_inputPins; ///< standard cell pins 
        std::vector<std::string> m_outputPins; ///< standard cell pins 
        std::vector<std::string> m_clkPins; ///< standard cell pins 
        std::vector<std::string> m_ctrlPins; ///< standard cell pins 
        string2index_map_type m_mPinName2Type; ///< map names of standard cell pins to type 
};

inline LibCell::LibCell() 
    : LibCell::base_type()
    , m_name("")
    , m_id(std::numeric_limits<index_type>::max())
    , m_inputPins()
    , m_outputPins()
    , m_clkPins()
    , m_ctrlPins()
    , m_mPinName2Type()
{
}
inline LibCell::LibCell(LibCell const& rhs)
    : LibCell::base_type(rhs)
{
    copy(rhs);
}
inline LibCell& LibCell::operator=(LibCell const& rhs)
{
    if (this != &rhs)
    {
        this->base_type::operator=(rhs);
        copy(rhs);
    }
    return *this;
}
inline void LibCell::copy(LibCell const& rhs)
{
    m_name = rhs.m_name;
    m_id = rhs.m_id;
    m_inputPins = rhs.m_inputPins;
    m_outputPins = rhs.m_outputPins;
    m_clkPins = rhs.m_clkPins;
    m_ctrlPins = rhs.m_ctrlPins;
    m_mPinName2Type = rhs.m_mPinName2Type;
}

DREAMPLACE_END_NAMESPACE

#endif
