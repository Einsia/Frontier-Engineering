#Load the synthesized netlist
open_checkpoint ../design.dcp

#Place design using the bookshelf
place_design -placement ../placement.pl

#Route design
route_design

#Routing Report
report_route_status
