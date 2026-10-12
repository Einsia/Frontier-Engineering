////////////////////////////////
/// usage : 1.	utility for SVG graph generation.
/// 
/// note  : 1.	
////////////////////////////////

#ifndef CN_HUST_GOAL_SYSTEM_SVG_DRAWER_H
#define CN_HUST_GOAL_SYSTEM_SVG_DRAWER_H


#include <algorithm>
#include <string>
#include <random>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <vector>
#include <array>


namespace WorkSpace {

struct RandColor {
	static constexpr auto ColorCodeChar = "0123456789ABCDEF";
	static constexpr int ColorCodeBase = 16;
	static constexpr int ColorCodeLen = 6;

	void next() {
		for (int i = 1; i <= ColorCodeLen; ++i) {
			int c = r() % ColorCodeBase;
			bcolor[i] = ColorCodeChar[c];
			tcolor[i] = ColorCodeChar[(c > (ColorCodeBase / 2)) ? 0 : (ColorCodeBase - 1)]; // (c + ColorCodeBase / 2) % ColorCodeBase
			//scolor[i] = tcolor[i];
		}
	}

	char bcolor[ColorCodeLen + 2] = { '#' }; // background color.
	char tcolor[ColorCodeLen + 2] = { '#' }; // text color.
	//char scolor[ColorCodeLen + 2] = { '#' }; // stroke color.
	char* scolor = tcolor; // stroke color.
	std::mt19937 r = std::mt19937(std::random_device()());
};

template<typename Coord = double>
struct SvgDrawer {
	using Buf = std::ostringstream;

	std::string toStr(Coord viewBoxMinX, Coord viewBoxMinY, Coord viewBoxWidth, Coord viewBoxHeight,
		std::string graphWidth = "100%", std::string graphHeight = "100%", // "1080px"
		std::string style = "<style>rect { fill:grey; stroke:black; stroke-width: 1px; opacity: 0.8; } line { stroke:black; stroke-width: 1px; } path { stroke: black; fill:transparent; }</style>") const {
		std::ostringstream out;
		out << "<!DOCTYPE html>\n"
			<< "<html>\n"
			<< "\t<head>\n"
			<< "\t\t<meta charset='utf-8'>\n"
			<< "\t\t<title>Visualization</title>\n"
			<< "\t\t" << style << "\n"
			<< "\t\t<style> #mdbg { position: fixed; font-size: 1vh; border-style: none; bottom: 1vh; left: 1vh; } </style>"
			<< "\t\t<script src='0dbg.js'></script>"
			<< "\t</head>\n"
			<< "\t<body>\n" // style='text-align:center;'
			<< "\t\t<div id='mdbg'></div>"
			<< "\t\t<svg id='v' width='" << graphWidth << "' height='" << graphHeight << "' viewBox='" << viewBoxMinX << " " << viewBoxMinY << " " << viewBoxWidth << " " << viewBoxHeight << "'>\n";
		out << oss.str();
		out << "\t\t</svg>\n"
			<< "\t</body>\n"
			<< "</html>\n";
		return out.str();
	}


	static void pathBegin(std::ostringstream& oss, const std::string& tag = "") {
		oss << "<path " << tag << ((tag.empty()) ? "" : " ") << "d='";
	}
	void pathBegin(const std::string& tag = "") { pathBegin(oss, tag); }
	static void pathEnd(std::ostringstream& oss, bool closed = false) {
		if (closed) { oss << " z"; }
		oss << "' />\n";
	}
	void pathEnd(bool closed = false) { pathEnd(closed); }
	static void pathLine(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, bool inPos = false) {
		if (!inPos) { oss << "M" << x1 << " " << y1 << " "; }
		if (x1 == x2) {
			oss << "v" << (y2 - y1);
		}
		else if (y1 == y2) {
			oss << "h" << (x2 - x1);
		}
		else {
			oss << "L" << x2 << " " << y2; // OPT[szx][9]: merge parallel segments.
		}
		oss << "\n";
	}
	void pathLine(Coord x1, Coord y1, Coord x2, Coord y2, bool inPos = false) { pathLine(oss, x1, y1, x2, y2, inPos); }
	static void pathArc(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, Coord rx, Coord ry, bool longArc, bool clockwise, double rotation, bool inPos = false) {
		if (!inPos) { oss << "M" << x1 << " " << y1 << " "; }
		oss << "A" << rx << " " << ry // OPT[szx][8]: avoid move to the current position.
			<< " " << rotation << " " << longArc << " " << clockwise << " " << x2 << " " << y2 << "\n";
	}
	void pathArc(Coord x1, Coord y1, Coord x2, Coord y2, Coord rx, Coord ry, bool longArc, bool clockwise, double rotation, bool inPos = false) {
		pathArc(oss, x1, y1, x2, y2, rx, ry, longArc, clockwise, rotation, inPos);
	}
	static void pathRect(std::ostringstream& oss, Coord x, Coord y, Coord w, Coord h) {
		oss << "M" << x << " " << y << " h" << w << " v" << h << " h" << -w << " Z\n"; // OPT[szx][8]: avoid move to the current position.
	}
	void pathRect(Coord x, Coord y, Coord w, Coord h) { pathRect(oss, x, y, w, h); }

	void line(Coord x1, Coord y1, Coord x2, Coord y2, const std::string& tag = "") {
		oss << "<line " << tag << ((tag.empty()) ? "" : " ") << "x1='" << x1 << "' y1='" << y1 << "' x2='" << x2 << "' y2='" << y2 << "' />\n";
	}
	static void line(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, Coord width, const std::string& tag = "") {
		oss << "<line " << tag << ((tag.empty()) ? "" : " ") << "x1='" << x1 << "' y1='" << y1 << "' x2='" << x2 << "' y2='" << y2 << "' style='stroke-width:" << width << ";' />\n";
	}
	static void line(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, const std::string& tag = "") {
		oss << "<line " << tag << ((tag.empty()) ? "" : " ") << "x1='" << x1 << "' y1='" << y1 << "' x2='" << x2 << "' y2='" << y2 << "' />\n";
	}
	void line(Coord x1, Coord y1, Coord x2, Coord y2, Coord width, const std::string& tag = "") {
		line(oss, x1, y1, x2, y2, width, tag);
	}
	void line(Coord x1, Coord y1, Coord x2, Coord y2, Coord width, std::string scolor, std::string style) { // "stroke-dasharray:12 4".
		oss << "<line x1='" << x1 << "' y1='" << y1 << "' x2='" << x2 << "' y2='" << y2 << "' style='stroke:" << scolor << "; stroke-width:" << width << "; " << style << "' />\n";
	}

	static void arc(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, Coord rx, Coord ry, bool longArc, bool clockwise, double rotation, Coord width, const std::string& tag = "") {
		oss << "<path " << tag << ((tag.empty()) ? "" : " ") << "d='M" << x1 << " " << y1 << " A" << rx << " " << ry
			<< " " << rotation << " " << longArc << " " << clockwise << " " << x2 << " " << y2
			<< "' style='stroke-width:" << width << ";' />\n";
	}
	static void arc(std::ostringstream& oss, Coord x1, Coord y1, Coord x2, Coord y2, Coord rx, Coord ry, bool longArc, bool clockwise, double rotation, const std::string& tag = "") {
		oss << "<path " << tag << ((tag.empty()) ? "" : " ") << "d='M" << x1 << " " << y1 << " A" << rx << " " << ry
			<< " " << rotation << " " << longArc << " " << clockwise << " " << x2 << " " << y2 << "' />\n";
	}
	void arc(Coord x1, Coord y1, Coord x2, Coord y2, Coord rx, Coord ry, bool longArc, bool clockwise, double rotation, Coord width, const std::string& tag = "") {
		arc(oss, x1, y1, x2, y2, rx, ry, longArc, clockwise, rotation, width, tag);
	}


	static void rect(std::ostringstream& oss, Coord x, Coord y, Coord w, Coord h, const std::string& tag = "") {
		oss << "<rect " << tag << ((tag.empty()) ? "" : " ") << "x='" << x << "' y='" << y << "' width='" << w << "' height='" << h << "' />\n";
	}
	void rect(Coord x, Coord y, Coord w, Coord h, const std::string& tag = "") {
		rect(oss, x, y, w, h, tag);
	}
	static void rect(std::ostringstream& oss, Coord x, Coord y, Coord w, Coord h, Coord r, const std::string& tag = "") {
		oss << "<rect " << tag << ((tag.empty()) ? "" : " ") << "x='" << x << "' y='" << y << "' width='" << w << "' height='" << h << "' rx='" << r << "' />\n";
	}
	void rect(Coord x, Coord y, Coord w, Coord h, Coord r, const std::string& tag = "") {
		rect(oss, x, y, w, h, r, tag);
	}
	void rect(Coord x, Coord y, Coord w, Coord h, const std::string& bcolor, const std::string& scolor, Coord width) {
		oss << "<rect x='" << x << "' y='" << y << "' width='" << w << "' height='" << h << "' style='fill:" << bcolor << "; stroke:" << scolor << "; stroke-width:"<< width << "' />\n";
	}
	void rect(Coord x, Coord y, Coord w, Coord h, const std::string& bcolor, const std::string& scolor) {
		oss << "<rect x='" << x << "' y='" << y << "' width='" << w << "' height='" << h << "' style='fill:" << bcolor << "; stroke:" << scolor << "; stroke-width:1' />\n";
	}
	void translucencyRect(Coord x, Coord y, Coord w, Coord h, const std::string& bcolor, const std::string& scolor, Coord opacity) {
		oss << "<rect x='" << x << "' y='" << y << "' width='" << w << "' height='" << h << "' style='fill:" << bcolor << "; fill-opacity:"<< opacity <<"; stroke:" << scolor << "; stroke-width:1' />\n";
	}
	void rect(Coord x, Coord y, Coord w, Coord h, const std::string& bcolor, const std::string& scolor, const std::string& tcolor, const std::string& label) {
		rect(x, y, w, h, bcolor, scolor);
		oss << "<text x='" << x + w / 3 << "' y='" << y + h / 3 << "' text-anchor='middle' alignment-baseline='middle' style='fill:" << tcolor << ";font-size:320px'>" << label << "</text>\n";
	}
	void rectRC(Coord x, Coord y, Coord w, Coord h) {
		rc.next();
		rect(x, y, w, h, rc.bcolor, rc.scolor);
	}
	void rectRC(Coord x, Coord y, Coord w, Coord h, const std::string& label) {
		rc.next();
		rect(x, y, w, h, rc.bcolor, rc.scolor, rc.tcolor, label);
	}

	static void circle(std::ostringstream& oss, Coord x, Coord y, Coord r, const std::string& tag = "") {
		oss << "<circle " << tag << ((tag.empty()) ? "" : " ") << "cx='" << x << "' cy='" << y << "' r='" << r << "' />\n";
	}
	void circle(Coord x, Coord y, Coord r, const std::string& tag = "") {
		circle(oss, x, y, r, tag);
	}
	void circle(Coord x, Coord y, Coord r, const std::string& bcolor, const std::string& scolor) {
		oss << "<circle cx='" << x << "' cy='" << y << "' r='" << r << "' style='fill:" << bcolor << "; stroke:" << scolor << "; stroke-width:1' />\n";
	}
	void circle(Coord x, Coord y, Coord r, const std::string& bcolor, const std::string& scolor, Coord& width) {
		oss << "<circle cx='" << x << "' cy='" << y << "' r='" << r << "' style='fill:" << bcolor << "; stroke:" << scolor << "; stroke-width:" << width << "' />\n";;
	}

	static void cross(std::ostringstream& oss, Coord x, Coord y, Coord rx, Coord ry, const std::string& tag = "") {
		oss << "<path " << tag << ((tag.empty()) ? "" : " ") << "d='M" << (x - rx) << " " << y << " h" << (2 * rx)
			<< " M" << x << " " << (y - ry) << " v" << (2 * ry) << "' />\n";
	}
	void cross(Coord x, Coord y, Coord rx, Coord ry, const std::string& tag = "") {
		cross(oss, x, y, rx, ry, tag);
	}


	void polygon(const std::vector<std::array<Coord, 2>>& coords, const std::string& tag = "", bool closed = false) {
		pathBegin(tag);
		auto s = coords.begin();
		oss << "M" << (*s)[0] << " " << (*s)[1];
		for (auto d = coords.begin() + 1; d != coords.end(); s = d, ++d) {
			pathLine((*s)[0], (*s)[1], (*s)[1], (*d)[1]); // OPT[szx][9]: merge parallel segments.
		}
		pathEnd(closed);
	}

	std::ostringstream oss;
	RandColor rc;
};

template<typename Coord = double>
struct CanvasDrawer {
	std::string toStr(Coord viewBoxMinX, Coord viewBoxMinY, Coord viewBoxWidth, Coord viewBoxHeight,
		Coord graphWidth = 100, Coord graphHeight = 100, std::string widthUnit = "%", std::string heightUnit = "%",
		std::string style = "") const {
		std::ostringstream out;
		out << "<!DOCTYPE html>\n"
			<< "<html>\n"
			<< "\t<head>\n"
			<< "\t\t<meta charset='utf-8'>\n"
			<< "\t\t<title>Visualization</title>\n"
			<< "\t\t<script type='application/javascript'>\n"
			<< "\t\t\tfunction draw() {\n"
			<< "\t\t\t\tvar canvas = document.getElementById('szx');\n"
			<< "\t\t\t\tif (!canvas.getContext) { return; }\n"
			<< "\t\t\t\tvar ctx = canvas.getContext('2d');\n"
			<< "\t\t\t\tctx.beginPath();\n"
			<< "\t\t\t\tfunction l(x1, y1, x2, y2) { ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }\n"
			<< "\t\t\t\tfunction r(x, y, w, h) { ctx.rect(x, y, w, h) }\n"
			<< "\t\t\t\tfunction fr(x, y, w, h) { ctx.fillRect(x, y, w, h) }\n";
		//<< "\t\t\t\tctx.fillStyle = 'white';"
		//<< "\t\t\t\tctx.strokeStyle = 'black';"
		//<< "\t\t\t\tctx.lineWidth = 1;";
		out << oss.str();
		out << "\t\t\t\tctx.stroke();\n"
			<< "\t\t\t}\n"
			<< "\t\t</script>\n"
			<< "\t</head>\n"
			<< "\t<body onload='draw();'>\n" // style='text-align:center;'
			<< "\t\t<canvas id='szx' width='" << (graphWidth * scale) << widthUnit << "' height='" << (graphHeight * scale) << heightUnit << "'></canvas>\n"
			<< "\t</body>\n"
			<< "</html>\n";
		return out.str();
	}

	void rect(Coord x, Coord y, Coord w, Coord h) {
		oss << "r(" << (x * scale) << "," << (y * scale) << "," << (w * scale) << "," << (h * scale) << ");\n";
	}
	void line(Coord x1, Coord y1, Coord x2, Coord y2) {
		oss << "l(" << (x1 * scale) << "," << (y1 * scale) << "," << (x2 * scale) << "," << (y2 * scale) << ");\n";
	}

	std::ostringstream oss;
	Coord scale = 2;
};

}


#endif // CN_HUST_GOAL_SYSTEM_SVG_DRAWER_H