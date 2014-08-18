#!/usr/bin/env python
# TradeDangerous :: Scripts :: Populate star database
# TradeDangerous Copyright (C) Oliver 'kfsone' Smith 2014 <oliver@kfs.org>:
#   You are free to use, redistribute, or even print and eat a copy of this
#   software so long as you include this copyright notice. I guarantee that
#   there is at least one bug neither of us knew about.
#
# Import data from http://forums.frontier.co.uk/showthread.php?t=34824
# and ensure existing data is correct.

from tradedb import *

from collections import namedtuple
import math

class Star(object):
    def __init__(self, name, x, y, z, links):
        self.name, self.x, self.y, self.z, self.links = name, x, y, z, links
        self.tdID = None
        self.tdStar = None
    def __repr__(self):
        return "Star(%s,%f,%f,%f,%s)\n" % (self.name, self.x, self.y, self.z, str(self.links))

# List of star system coordinates provided by wtbw
stars = [
  Star("26 Draconis",-39.000000,24.906250,-0.656250, {}),
  Star("Acihaut",-18.500000,25.281250,-4.000000, {}),
  Star("Aganippe",-11.562500,43.812500,11.625000, {}),
  Star("Asellus Primus",-23.937500,40.875000,-1.343750, {}),
  Star("Aulin",-19.687500,32.687500,4.750000, {}),
  Star("Aulis",-16.468750,44.187500,-11.437500, {}),
  Star("BD+47 2112",-14.781250,33.468750,-0.406250, {}),
  Star("BD+55 1519",-16.937500,44.718750,-16.593750, {}),
  Star("Bolg",-7.906250,34.718750,2.125000, {}),
  Star("Chi Herculis",-30.750000,39.718750,12.781250, {}),
  Star("CM Draco",-35.687500,30.937500,2.156250, {}),
  Star("Dahan",-19.750000,41.781250,-3.187500, {}),
  Star("DN Draconis",-27.093750,21.625000,0.781250, {}),
  Star("DP Draconis",-17.500000,25.968750,-11.375000, {}),
  Star("Eranin",-22.843750,36.531250,-1.187500, {}),
  Star("G 239-25",-22.687500,25.812500,-6.687500, {}),
  Star("GD 319",-19.375000,43.625000,-12.750000, {}),
  Star("h Draconis",-39.843750,29.562500,-3.906250, {}),
  Star("Hermitage",-28.750000,25.000000,10.437500, {}),
  Star("i Bootis",-22.375000,34.843750,4.000000, {}),
  Star("Ithaca",-8.093750,44.937500,-9.281250, {}),
  Star("Keries",-18.906250,27.218750,12.593750, {}),
  Star("Lalande 29917",-26.531250,22.156250,-4.562500, {}),
  Star("LFT 1361",-38.781250,24.718750,-0.500000, {}),
  Star("LFT 880",-22.812500,31.406250,-18.343750, {}),
  Star("LFT 992",-7.562500,42.593750,0.687500, {}),
  Star("LHS 2819",-30.500000,38.562500,-13.437500, {}),
  Star("LHS 2884",-22.000000,48.406250,1.781250, {}),
  Star("LHS 2887",-7.343750,26.781250,5.718750, {}),
  Star("LHS 3006",-21.968750,29.093750,-1.718750, {}),
  Star("LHS 3262",-24.125000,18.843750,4.906250, {}),
  Star("LHS 417",-18.312500,18.187500,4.906250, {}),
  Star("LHS 5287",-36.406250,48.187500,-0.781250, {}),
  Star("LHS 6309",-33.562500,33.125000,13.468750, {}),
  Star("LP 271-25",-10.468750,31.843750,7.312500, {}),
  Star("LP 275-68",-23.343750,25.062500,15.187500, {}),
  Star("LP 64-194",-21.656250,32.218750,-16.218750, {}),
  Star("LP 98-132",-26.781250,37.031250,-4.593750, {}),
  Star("Magec",-32.875000,36.156250,15.500000, {}),
  Star("Meliae",-17.312500,49.531250,-1.687500, {}),
  Star("Morgor",-15.250000,39.531250,-2.250000, {}),
  Star("Nang Ta-khian",-18.218750,26.562500,-6.343750, {}),
  Star("Naraka",-34.093750,26.218750,-5.531250, {}),
  Star("Opala",-25.500000,35.250000,9.281250, {}),
  Star("Ovid",-28.062500,35.156250,14.812500, {}),
  Star("Pi-fang",-34.656250,22.843750,-4.593750, {}),
  Star("Rakapila",-14.906250,33.625000,9.125000, {}),
  Star("Ross 1015",-6.093750,29.468750,3.031250, {}),
  Star("Ross 1051",-37.218750,44.500000,-5.062500, {}),
  Star("Ross 1057",-32.312500,26.187500,-12.437500, {}),
  Star("Styx",-24.312500,37.750000,6.031250, {}),
  Star("Surya",-38.468750,39.250000,5.406250, {}),
  Star("Tilian",-21.531250,22.312500,10.125000, {}),
  Star("WISE 1647+5632",-21.593750,17.718750,1.750000, {}),
  Star("Wyrd",-11.625000,31.531250,-3.937500, {}),
]

# list of Star objects by their name
starsByName = { star.name: star for star in stars }

# Build up the links table
print("Calculating distance matrix")
for lhsIdx in range(0, len(stars) - 1):
    lhs = stars[lhsIdx]
    lhsX, lhsY, lhsZ = lhs.x, lhs.y, lhs.z
    for rhsIdx in range(lhsIdx + 1, len(stars)):
        rhs = stars[rhsIdx]
        xDelta, yDelta, zDelta = (rhs.x - lhsX), (rhs.y - lhsY), (rhs.z - lhsZ)
        xd2, yd2, zd2 = (xDelta * xDelta), (yDelta * yDelta), (zDelta * zDelta)
        # Truncate to 2 decimal places but round up, thus 0.841 becomes 0.842
        distance = math.ceil(math.sqrt(xd2 + yd2 + zd2) * 100) / 100
        lhs.links[rhs] = distance
        rhs.links[lhs] = distance

print("Opening database")
tdb = TradeDB(r'.\TradeDangerous.accdb')

# Import correct star names.
# Original TD star names were kinda lazy before I added partial matching.
# Check the existing database for a likely target for this star.
print("Importing names")
for star in stars:
    starName = star.name
    if starName.find('\'') != -1:
        raise ValueError("Apostrophe in star name not handled")

    norm = tdb.normalized_str(starName)
    tdStation = None
    for curStnID, station in tdb.stations.items():
        tdStarName = station.system.system
        tdNorm = tdb.normalized_str(tdStarName)
        if norm.find(tdNorm) == 0:
            if tdStation:
                raise ValueError("%s could be %s or %s" % (star.name, tdStation.system.system, tdStarName))
            tdStation = station
    if not tdStation:
        print("* TD is missing %s" % star.name)
        continue
    star.tdID = tdStation.ID
    star.tdStar = tdStation.system
    tdStarName = tdStation.system.system
    if starName != tdStarName:
        print("%s changing to %s" % (tdStarName, starName))
        tdb.query("UPDATE Stations SET `system` = '%s' WHERE Stations.ID = %d" % (starName, tdStation.ID)).commit()

# Now process all the links.
print("Importing distance matrix")
for star in stars:
    srcID = star.tdID
    if not srcID:
        continue
    for dest, dist in star.links.items():
        dstID = dest.tdID
        if not dstID:
            continue
        if not dest.tdStar in star.tdStar.links:
            print("%s had no link to %s" % (star.name, dest.name))
            tdb.query("INSERT INTO Links (`from`, `to`, `distLy`) VALUES (%d, %d, %.2f)" % (srcID, dstID, dist)).commit()
        else:
            tdDist = star.tdStar.links[dest.tdStar]
            if tdDist != dist:
                print("%s -> %s is wrong: %.2f vs %.2f" % (star.name, dest.name, tdDist, dist))
                tdb.query("UPDATE Links SET `distLy` = %.2f WHERE `from` = %d AND `to` = %d" % (dist, srcID, dstID)).commit()
        