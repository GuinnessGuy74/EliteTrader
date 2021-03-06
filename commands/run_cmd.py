from commands.commandenv import ResultRow
from commands.exceptions import *
from commands.parsing import MutuallyExclusiveGroup, ParseArgument
from itertools import chain
from formatting import RowFormat, ColumnFormat
from tradedb import TradeDB, System, Station, describeAge
from tradecalc import TradeCalc, Route, NoHopsError

import math

######################################################################
# Parser config

help = 'Calculate best trade run.'
name = 'run'
epilog = None
usesTradeData = True

arguments = [
    ParseArgument('--capacity',
            help='Maximum capacity of cargo hold.',
            metavar='N',
            type=int,
        ),
    ParseArgument('--credits',
            help='Starting credits.',
            metavar='CR',
            type=int,
        ),
]

switches = [
    ParseArgument('--from', '-f',
            help='Starting system/station.',
            dest='starting',
            metavar='STATION',
        ),
    MutuallyExclusiveGroup(
        ParseArgument('--to', '-t',
                help='Final system/station.',
                dest='ending',
                metavar='PLACE',
                default=None,
        ),
        ParseArgument('--towards', '-T',
                help=(
                    'Choose a route that continually reduces the '
                    'distance towards this system.'
                ),
                dest='goalSystem',
                metavar='SYSTEM',
                default=None,
        ),
    ),
    ParseArgument('--via',
            help='Require specified systems/stations to be en-route.',
            action='append',
            metavar='PLACE[,PLACE,...]',
        ),
    ParseArgument('--avoid',
            help='Exclude an item, system or station from trading. '
                    'Partial matches allowed, '
                    'e.g. "dom.App" or "domap" matches "Dom. Appliances".',
            action='append',
        ),
    ParseArgument('--hops',
            help='Number of hops (station-to-station) to run.',
            default=2,
            type=int,
            metavar='N',
        ),
    ParseArgument('--jumps-per',
        help='Maximum number of jumps (system-to-system) per hop.',
        default=2,
        dest='maxJumpsPer',
        metavar='N',
        type=int,
    ),
    ParseArgument('--direct',
        help="Assume destinations are reachable without worrying "
             "about jumps.",
        action='store_true',
    ),
    ParseArgument('--ly-per',
            help='Maximum light years per jump.',
            dest='maxLyPer',
            metavar='N.NN',
            type=float,
        ),
    ParseArgument('--empty-ly',
            help='Maximum light years ship can jump when empty.',
            dest='emptyLyPer',
            metavar='N.NN',
            type=float,
            default=None,
        ),
    ParseArgument('--start-jumps', '-s',
            help='Consider stations within this many jumps of the origin '
                 '(requires --from).',
            dest='startJumps',
            default=0,
            type=int,
        ),
    ParseArgument('--end-jumps', '-e',
            help='Consider stations within this many jumps of the destination '
                 '(requires --to).',
            dest='endJumps',
            default=0,
            type=int,
        ),
    ParseArgument('--limit',
            help='Maximum units of any one cargo item to buy (0: unlimited).',
            metavar='N',
            type=int,
        ),
    ParseArgument('--age', '--max-days-old', '-MD',
            help='Maximum age (in days) of trade data to use.',
            metavar='DAYS',
            type=float,
            dest='maxAge',
        ),
    ParseArgument('--pad-size', '-p',
            help='Limit the padsize to this ship size (S,M,L or ? for unknown).',
            metavar='PADSIZES',
            dest='padSize',
        ),
    ParseArgument('--black-market', '-bm',
            help='Require stations with a black market.',
            action='store_true',
            dest='blackMarket',
        ),
    ParseArgument('--ls-penalty', '--lsp',
            help="Penalty per 1kls stations are from their stars.",
            default=0.6,
            type=float,
            dest='lsPenalty'
        ),
    ParseArgument('--ls-max',
            help='Only consider stations upto this many ls from their star.',
            metavar='LS',
            dest='maxLs',
            type=int,
            default=0,
        ),
    ParseArgument('--gain-per-ton', '--gpt',
            help='Specify the minimum gain per ton of cargo',
            dest='minGainPerTon',
            type=int,
            default=1
        ),
    ParseArgument('--max-gain-per-ton', '--mgpt',
            help='Specify the maximum gain per ton of cargo',
            dest='maxGainPerTon',
            type=int,
            default=10000
        ),
    ParseArgument('--unique',
            help='Only visit each station once.',
            action='store_true',
            default=False,
        ),
    ParseArgument('--margin',
            help='Reduce gains made on each hop to provide a margin of error '
                    'for market fluctuations (e.g: 0.25 reduces gains by 1/4). '
                    '0<: N<: 0.25.',
            default=0.00,
            metavar='N.NN',
            type=float,
        ),
    ParseArgument('--insurance',
            help='Reserve at least this many credits to cover insurance.',
            default=0,
            metavar='CR',
            type=int,
        ),
    ParseArgument('--routes',
            help='Maximum number of routes to show. DEFAULT: 1',
            default=1,
            metavar='N',
            type=int,
        ),
    ParseArgument('--max-routes',
            help='At the end of each hop, limit the number of routes '
                    'that continue to the next round to the top N '
                    'highest scoring',
            default=0,
            metavar='N',
            type=int,
            dest='maxRoutes',
        ),
    ParseArgument('--checklist',
            help='Provide a checklist flow for the route.',
            action='store_true',
            default=False,
        ),
    ParseArgument('--x52-pro',
            help='Enable experimental X52 Pro MFD output.',
            action='store_true',
            default=False,
            dest='x52pro',
        ),
    ParseArgument('--prune-score',
            help='From the 3rd hop on, only consider routes which have ' \
                'at least this percentage of the current best route''s score.',
            dest='pruneScores',
            type=float,
            default=0,
        ),
    ParseArgument('--prune-hops',
            help='Changes which hop --prune-score takes effect from.',
            default=3,
            type=int,
            dest='pruneHops',
        ),
    ParseArgument('--progress', '-P',
            help='Show hop progress',
            default=False,
            action='store_true',
        ),
]

######################################################################
# Helpers

class Checklist(object):
    """
        Class for encapsulating display of a route as a series of
        steps to be 'checked off' as the user passes through them.
    """

    def __init__(self, tdb, cmdenv):
        self.tdb = tdb
        self.cmdenv = cmdenv
        self.mfd = cmdenv.mfd


    def doStep(self, action, detail=None, extra=None):
        self.stepNo += 1
        try:
            self.mfd.display(
                "#{} {}".format(self.stepNo, action),
                detail or "",
                extra or ""
            )
        except AttributeError:
            pass
        input(
            "   {:<3}: {}: "
            .format(
                self.stepNo,
                " ".join(item for item in [action, detail, extra] if item)
            )
        )


    def note(self, str, addBreak=True):
        print("(i) {} (i){}".format(str, "\n" if addBreak else ""))


    def run(self, route, cr):
        tdb, mfd = self.tdb, self.mfd
        stations, hops, jumps = route.route, route.hops, route.jumps
        lastHopIdx = len(stations) - 1
        gainCr = 0
        self.stepNo = 0

        heading = "(i) BEGINNING CHECKLIST FOR {} (i)".format(route.str())
        print(heading, "\n", '-' * len(heading), "\n\n", sep='')

        cmdenv = self.cmdenv
        if cmdenv.detail:
            print(route.summary())
            print()

        for idx in range(lastHopIdx):
            hopNo = idx + 1
            cur, nxt, hop = stations[idx], stations[idx + 1], hops[idx]
            sortedTradeOptions = sorted(
                hop[0],
                key=lambda tradeOption: \
                    tradeOption[1] * tradeOption[0].gainCr, reverse=True
            )

            # Tell them what they need to buy.
            if cmdenv.detail:
                self.note("HOP {} of {}".format(hopNo, lastHopIdx))

            self.note("Buy at {}".format(cur.name()))
            for (trade, qty) in sortedTradeOptions:
                self.doStep(
                        'Buy {:n} x'.format(qty),
                        trade.name(),
                        '@ {}cr / {} old'.format(
                            trade.costCr,
                            describeAge(trade.srcAge),
                ))
            if cmdenv.detail:
                self.doStep('Refuel')
            print()

            # If there is a next hop, describe how to get there.
            self.note(
                "Fly {}"
                .format(
                    " -> ".join(jump.name() for jump in jumps[idx])
                )
            )
            if idx < len(hops) and jumps[idx]:
                for jump in jumps[idx][1:]:
                    self.doStep('Jump to', jump.name())
            if cmdenv.detail:
                self.doStep('Dock at', nxt.str())
            print()

            self.note("Sell at {}".format(nxt.name()))
            for (trade, qty) in sortedTradeOptions:
                self.doStep(
                        'Sell {:n} x'.format(qty),
                        trade.name(),
                        '@ {:n}cr / {} old'.format(
                            trade.costCr + trade.gainCr,
                            describeAge(trade.dstAge),
                ))
            print()

            gainCr += hop[1]
            if cmdenv.detail and gainCr > 0:
                self.note("GAINED: {:n}cr, CREDITS: {:n}cr".format(
                            gainCr, cr + gainCr))

            if hopNo < lastHopIdx:
                print("\n--------------------------------------\n")

        if mfd:
            mfd.display('FINISHED',
                        "+{:n}cr".format(gainCr),
                        "={:n}cr".format(cr + gainCr))
            mfd.attention(3)
            from time import sleep
            sleep(1.5)


def expandForJumps(tdb, cmdenv, calc, origin, jumps, srcName):
    """
    Find all the stations you could reach if you made a given
    number of jumps away from the origin list.
    """

    assert jumps

    maxLyPer = cmdenv.emptyLyPer or cmdenv.maxLyPer
    avoidPlaces = cmdenv.avoidPlaces
    cmdenv.DEBUG0(
            "expanding {} reach from {} by {} jumps at {}ly per jump",
                srcName,
                origin.name(),
                jumps,
                maxLyPer,
    )

    if srcName == "--to":
        tradingList = calc.stationsSelling
    elif srcName == "--from":
        tradingList = calc.stationsBuying
    else:
        raise Exception("Unknown src")

    stations = set()
    origins, avoid = set([origin]), set(place for place in avoidPlaces)

    for jump in range(jumps):
        if not origins:
            break
        cmdenv.DEBUG1(
            "Ring {}: {}",
            jump,
            [sys.dbname for sys in origins]
        )
        thisJump, origins = origins, set()
        for sys in thisJump:
            avoid.add(sys)
            for stn in sys.stations or []:
                if stn.ID not in tradingList:
                    cmdenv.DEBUG2(
                        "X {}/{} not in trading list",
                        stn.system.dbname, stn.dbname,
                    )
                    continue
                if not checkStationSuitability(cmdenv, calc, stn):
                    cmdenv.DEBUG2(
                        "X {}/{} was not suitable",
                        stn.system.dbname, stn.dbname,
                    )
                    continue
                cmdenv.DEBUG2(
                    "- {}/{} meets requirements",
                    stn.system.dbname, stn.dbname,
                )
                stations.add(stn)
            for dest, dist in tdb.genSystemsInRange(sys, maxLyPer):
                if dest not in avoid:
                    origins.add(dest)

    cmdenv.DEBUG0(
            "Expanded {} stations: {}",
            srcName,
            [stn.name() for stn in stations]
    )

    stations = list(stations)
    stations.sort(key=lambda stn: stn.ID)

    return stations


def checkForEmptyStationList(category, focusPlace, stationList, jumps):
    if stationList:
        return
    if jumps:
        raise NoDataError(
                "Local database has no price data for any "
                "stations within {} jumps of {} ({})".format(
                    jumps,
                    focusPlace.name(),
                    category,
        ))
    if isinstance(focusPlace, System):
        raise NoDataError(
                "Local database either has no price data for "
                "stations in {} ({}) or could not find any that "
                "met your requirements (e.g. pad-size). "
                "Check \"trade.py local -vv --ly 0 {}\"".format(
                    focusPlace.name(),
                    category,
                    focusPlace.name(),
        ))
    raise NoDataError(
            "Local database has no price data for {} ({})".format(
                focusPlace.name(),
                category,
    ))


def checkAnchorNotInVia(hops, anchorName, place, viaSet):
    """
    Ensure that '--to' or '--from' is not in the via set.
    """

    if hops != 2:
        return
    if isinstance(place, Station) and place in viaSet:
        raise CommandLineError(
            "{} used in {} and --via with only 2 hops".format(
                place.name(),
                anchorName,
        ))


def checkStationSuitability(cmdenv, calc, station, src=None):
    cmdenv.DEBUG2(
        "checking {} (ls={}, bm={}, pad={}, mkt={}, shp={}) "
        "for {} suitability",
        station.name(),
        station.lsFromStar,
        station.blackMarket,
        station.maxPadSize,
        station.market,
        station.shipyard,
        src or "any",
    )

    if station in cmdenv.avoidPlaces and src != "--from":
        if src:
            raise CommandLineError(
                "{} station {} is marked to avoid"
                .format(src, station.name())
            )
        return False
    if station.system in cmdenv.avoidPlaces and src != "--from":
        if src:
            raise CommandLineError(
                "{} station {} is in system listed in --avoid"
                .format(src, station.name())
            )
        return False
    if station.market == 'N':
        if src:
            raise CommandLineError(
                "{} station {} is flagged as having no market".format(
                    src, station.name()
                )
            )
        return False
    if not station.itemCount:
        if src:
            raise NoDataError(
                "No price data in local database "
                "for {} station: {}".format(
                    src, station.name(),
            ))
        return False
    if src != "--to" and station.ID not in calc.stationsSelling:
        if src:
            raise NoDataError(
                "No buying prices at {}."
                .format(station.name())
            )
        return False
    if src != "--from" and station.ID not in calc.stationsBuying:
        if src:
            raise NoDataError(
                "No selling prices at {}."
                .format(station.name())
            )
        return False
    mps = cmdenv.padSize
    if mps and not station.checkPadSize(mps):
        if src:
            raise CommandLineError(
                "{} station {} does not meet pad-size requirement.\n"
                "You specified: {}, Current data for station: {} ({})\n"
                "You can use \"trade.py station\" to correct this.".format(
                    src, station.name(),
                    mps, station.maxPadSize,
                    TradeDB.padSizesExt[station.maxPadSize],
            ))
        return False
    bm = cmdenv.blackMarket
    if bm and station.blackMarket != 'Y':
        if src and src != "--from":
            raise CommandLineError(
                "{} station {} does not meet black-market "
                "requirement.".format(
                    src, station.name(),
            ))
        return False
    mls = cmdenv.maxLs
    if mls and (station.lsFromStar <= 0 or station.lsFromStar > mls):
        if src and src != "--from":
            raise CommandLineError(
                "{} station {} does not meet max-ls "
                "requirement.".format(
                    src, station.name(),
            ))
        return False
    maxAge = cmdenv.maxAge
    if maxAge and station.dataAge > maxAge:
        if src and src != "--from":
            raise CommandLineError(
                "{} station {} does not meet --age "
                "requirement.".format(
                    src, station.name(),
            ))
        return False
    return True


def filterStationSet(src, cmdenv, calc, stnList):
    if not stnList:
        return stnList
    cmdenv.DEBUG0(
        "filtering {} station list: {}",
        src,
        ",".join(station.name() for station in stnList),
        )
    filtered = [
        place for place in stnList
        if isinstance(place, System) or \
            checkStationSuitability(cmdenv, calc, place, src)
    ]
    if not stnList:
        raise CommandLineError(
                "No {} station met your criteria.".format(
                    src
        ))
    return stnList


def checkOrigins(tdb, cmdenv, calc):
    if cmdenv.origPlace:
        if cmdenv.startJumps and cmdenv.startJumps > 0:
            cmdenv.origins = expandForJumps(
                    tdb, cmdenv, calc,
                    cmdenv.origPlace.system,
                    cmdenv.startJumps,
                    "--from"
            )
        elif isinstance(cmdenv.origPlace, System):
            cmdenv.DEBUG0("origPlace: System: {}", cmdenv.origPlace.name())
            if not cmdenv.origPlace.stations:
                raise CommandLineError(
                        "No stations at --from system, {}"
                            .format(cmdenv.origPlace.name())
                        )
            cmdenv.origins = [
                station
                for station in cmdenv.origPlace.stations
                if checkStationSuitability(cmdenv, calc, station)
            ]
        else:
            cmdenv.DEBUG0("origPlace: Station: {}", cmdenv.origPlace.name())
            checkStationSuitability(cmdenv, calc, cmdenv.origPlace, '--from')
            cmdenv.origins = [ cmdenv.origPlace ]
            cmdenv.startStation = cmdenv.origPlace
        checkForEmptyStationList(
                "--from", cmdenv.origPlace,
                cmdenv.origins, cmdenv.startJumps
        )
    else:
        cmdenv.DEBUG0("using all suitable origins")
        cmdenv.origins = [
            station
            for station in tdb.stationByID.values()
            if checkStationSuitability(cmdenv, calc, station)
        ]
        if cmdenv.startJumps:
            raise CommandLineError("--start-jumps (-s) only works with --from")

    if isinstance(cmdenv.origPlace, System) and not cmdenv.startJumps:
        cmdenv.origins = filterStationSet(
            '--from', cmdenv, calc, cmdenv.origins
        )

    cmdenv.origSystems = list(set(
        stn.system for stn in cmdenv.origins
    ))


def checkDestinations(tdb, cmdenv, calc):
    cmdenv.destinations = None
    if cmdenv.destPlace:
        if cmdenv.endJumps and cmdenv.endJumps > 0:
            cmdenv.destinations = expandForJumps(
                    tdb, cmdenv, calc,
                    cmdenv.destPlace.system,
                    cmdenv.endJumps,
                    "--to"
            )
        elif isinstance(cmdenv.destPlace, Station):
            cmdenv.DEBUG0("destPlace: Station: {}", cmdenv.destPlace.name())
            checkStationSuitability(cmdenv, calc, cmdenv.destPlace, '--to')
            cmdenv.destinations = [ cmdenv.destPlace ]
        else:
            cmdenv.DEBUG0("destPlace: System: {}", cmdenv.destPlace.name())
            cmdenv.destinations = [
                station
                for station in cmdenv.destPlace.stations
                if checkStationSuitability(cmdenv, calc, station)
            ]
        checkForEmptyStationList(
                "--to", cmdenv.destPlace,
                cmdenv.destinations, cmdenv.endJumps
        )
    else:
        cmdenv.DEBUG0("Using all available destinations")
        if cmdenv.endJumps:
            raise CommandLineError("--end-jumps (-e) only works with --to")
        if cmdenv.goalSystem:
            if not cmdenv.origPlace:
                raise CommandLineError("--towards requires --from")
            dest = tdb.lookupPlace(cmdenv.goalSystem)
            cmdenv.goalSystem = dest.system

        if cmdenv.origPlace and cmdenv.maxJumpsPer == 0:
            stationSrc = chain.from_iterable(
                system.stations for system in cmdenv.origSystems
            )
        else:
            stationSrc = tdb.stationByID.values()

        cmdenv.destinations = [
            station
            for station in stationSrc
            if checkStationSuitability(cmdenv, calc, station)
        ]

    if isinstance(cmdenv.destPlace, System) and not cmdenv.endJumps:
        cmdenv.destinations = filterStationSet(
            '--to', cmdenv, calc, cmdenv.destinations
        )

    cmdenv.destSystems = list(set(
        stn.system for stn in cmdenv.destinations
    ))

def validateRunArguments(tdb, cmdenv, calc):
    """
        Process arguments to the 'run' option.
    """

    if cmdenv.credits < 0:
        raise CommandLineError("Invalid (negative) value for initial credits")
    # I'm going to allow 0 credits as a future way of saying "just fly"

    if cmdenv.routes < 1:
        raise CommandLineError(
            "Maximum routes has to be 1 or higher."
        )
    if cmdenv.routes > 1 and cmdenv.checklist:
        raise CommandLineError(
            "Checklist can only be applied to a single route."
        )

    if cmdenv.hops < 1:
        raise CommandLineError("Minimum of 1 hop required")
    if cmdenv.hops > 32:
        raise CommandLineError("Too many hops without more optimization")

    if cmdenv.maxJumpsPer < 0:
        raise CommandLineError("Negative jumps: you're already there?")
    if cmdenv.direct:
        cmdenv.hops = 1

    if cmdenv.capacity is None:
        raise CommandLineError("Missing '--capacity'")
    if cmdenv.maxLyPer is None and not cmdenv.direct:
        raise CommandLineError("Missing '--ly-per'")
    if cmdenv.capacity < 0:
        raise CommandLineError("Invalid (negative) cargo capacity")
    if cmdenv.capacity > 1200:
        raise CommandLineError(
            "Capacity > 1200 not supported (you specified {})"
            .format( cmdenv.capacity)
        )

    if cmdenv.limit and cmdenv.limit > cmdenv.capacity:
        raise CommandLineError("'limit' must be <= capacity")
    if cmdenv.limit and cmdenv.limit < 0:
        raise CommandLineError("'limit' can't be negative, silly")
    cmdenv.maxUnits = cmdenv.limit if cmdenv.limit else cmdenv.capacity

    if cmdenv.insurance:
        arbitraryInsuranceBuffer = 42
        if cmdenv.insurance >= (cmdenv.credits + arbitraryInsuranceBuffer):
            raise CommandLineError("Insurance leaves no margin for trade")

    checkOrigins(tdb, cmdenv, calc)
    checkDestinations(tdb, cmdenv, calc)

    # If they're going --from and --to single systems, and they have
    # specified zero jumps then it's futile to try anything.
    if cmdenv.maxJumpsPer == 0 and not cmdenv.direct:
        if len(cmdenv.origSystems) == 1 and len(cmdenv.destSystems) == 1:
            if cmdenv.origSystems[0] != cmdenv.destSystems[0]:
                raise CommandLineError(
                    "Could not find any connections that didn't require at "
                    "least one jump and --jumps 0 specified."
                )

    origins, destns = cmdenv.origins or [], cmdenv.destinations or []

    if cmdenv.hops == 1 and len(origins) == 1 and len(destns) == 1:
        if origins == destns:
            raise CommandLineError("Same to/from; more than one hop required.")

    avoidSet = set(cmdenv.avoidPlaces or [])
    viaSet = cmdenv.viaSet = set(cmdenv.viaPlaces)
    cmdenv.DEBUG0("Via: {}", viaSet)
    cmdenv.viaSet = filterStationSet('--via', cmdenv, calc, cmdenv.viaSet)
    checkAnchorNotInVia(cmdenv.hops, "--from", cmdenv.origPlace, viaSet)
    checkAnchorNotInVia(cmdenv.hops, "--to", cmdenv.destPlace, viaSet)

    viaSystems = set()
    for place in viaSet:
        if place in avoidSet or place.system in avoidSet:
            raise CommandLineError(
                '"--via {}" conflicts with --avoid'
                .format(place.name())
            )
        if isinstance(place, Station):
            viaSystems.add(place.system)
        else:
            viaSystems.add(place)

    if cmdenv.maxJumpsPer == 0 and viaSet and not cmdenv.direct:
        for via in viaSet:
            if via.system not in cmdenv.origSystems:
                raise CommandLineError(
                    "--via {} unreachable with --jumps 0"
                    .format(via.name())
                )
        cmdenv.origins = [
            origin for origin in cmdenv.origins
            if origin.system in viaSystems
        ]
        cmdenv.origSystems = [
            origin.system for origin in cmdenv.origins
        ]
        cmdenv.destinations = [
            dest for dest in cmdenv.destinations
            if destination.system in viaSystems
        ]
        cmdenv.destSystems = [
            dest.system for dest in cmdenv.destinations
        ]

    # How many of the hops do not have pre-determined stations. For example,
    # when the user uses "--from", they pre-determine the starting station.
    fixedRoutePoints = 0
    if cmdenv.origPlace:
        fixedRoutePoints += 1
    if cmdenv.destPlace:
        fixedRoutePoints += 1
    totalRoutePoints = cmdenv.hops + 1
    adhocRoutePoints = totalRoutePoints - fixedRoutePoints
    if len(viaSystems) > adhocRoutePoints:
        raise CommandLineError(
                "Route is not long enough for the list of '--via' "
                "destinations you gave. Reduce the vias or try again "
                "with '--hops {}' or greater.\n".format(
                    len(viaSet) + fixedRoutePoints - 1
                ))
    cmdenv.adhocHops = adhocRoutePoints - 1

    if cmdenv.unique and cmdenv.hops >= len(tdb.stationByID):
        raise CommandLineError(
            "Requested unique trip with more hops than there are stations..."
        )
    if cmdenv.unique:
        # if there's only one start and stop...
        if len(origins) == 1 and len(destns) == 1:
            if origins[0] == destns[0]:
                raise CommandLineError("Can't have same from/to with --unique")
        if viaSet:
            if len(origins) == 1 and origins[0] in viaSet:
                raise("Can't have --from station in --via list with --unique")
            if len(destns) == 1 and destns[0] in viaSet:
                raise("Can't have --to station in --via list with --unique")

    if cmdenv.mfd:
        cmdenv.mfd.display("Loading Trades")

    if cmdenv.pruneScores and cmdenv.pruneHops:
        if cmdenv.pruneScores > 100:
            raise CommandLineError("--prune-score value percentile exceed 100.")
        if cmdenv.pruneHops < 2:
            raise CommandLineError("--prune-hops must 2 or more.")
    else:
        cmdenv.pruneScores = cmdenv.pruneHops = 0

######################################################################


def filterByVia(routes, viaSet, viaStartPos):
    if not routes:
        return []

    matchedRoutes = []
    partialRoutes = {}
    maxMet = 0
    for route in routes:
        met = 0
        for hop in route.route[viaStartPos:]:
            if hop in viaSet or hop.system in viaSet:
                met += 1
        if met > 0:
            if met >= len(viaSet):
                matchedRoutes.append(route)
            else:
                if met > maxMet:
                    partialRoutes[met] = []
                if met >= maxMet:
                    maxMet = met
                    partialRoutes[met].append(route)

    if matchedRoutes:
        return matchedRoutes, None

    if not maxMet:
        raise NoDataError(
                "No routes were found which matched your 'via' selections."
        )

    return partialRoutes[maxMet], (
            "SORRY: No runs visited all of your via destinations. "
            "Listing runs that matched at least {}.".format(
                    maxMet
            )
    )

def checkReachability(tdb, cmdenv):
    if cmdenv.direct:
        return
    srcSys, dstSys = cmdenv.origSystems, cmdenv.destSystems
    if len(srcSys) == 1 and len(dstSys) == 1:
        srcSys, dstSys = srcSys[0], dstSys[0]
        if srcSys != dstSys:
            maxLyPer = cmdenv.maxLyPer
            avoiding = [
                avoid for avoid in cmdenv.avoidPlaces
                if isinstance(avoid, System)
            ]
            route = tdb.getRoute(
                srcSys, dstSys, maxLyPer, avoiding,
            )
            if not route:
                raise CommandLineError(
                    "No route between {} and {} with a {}ly/jump limit."
                    .format(
                        srcSys.name(), dstSys.name(),
                        maxLyPer,
                    )
                )

            # Were there just not enough hops?
            jumpLimit = cmdenv.maxJumpsPer * cmdenv.hops
            routeJumps = len(route) - 1
            if jumpLimit < routeJumps:
                hopsRequired = math.ceil(routeJumps / cmdenv.maxJumpsPer)
                jumpsRequired = math.ceil(routeJumps / cmdenv.hops)
                raise CommandLineError(
                    "Shortest route between {src} and {dst} at {jumply} "
                    "ly per jump requires at least {minjumps} jumps. "
                    "Your current settings (--hops {hops} --jumps {jumps}) "
                    "allows a maximum of {jumplimit}.\n"
                    "\n"
                    "You may need --hops={althops} or --jumps={altjumps}.\n"
                    "\n"
                    "See also:\n"
                    " --towards (aka -T),"
                    " --start-jumps (-s),"
                    " --end-jumps (-e),"
                    " --direct.\n"
                    .format(
                        src=srcSys.name(),
                        dst=dstSys.name(),
                        jumply=cmdenv.maxLyPer,
                        minjumps=routeJumps,
                        hops=cmdenv.hops,
                        jumps=cmdenv.maxJumpsPer,
                        jumplimit=jumpLimit,
                        althops=hopsRequired,
                        altjumps=jumpsRequired,
                    )
                )


def routeFailedRestrictions(
        tdb, cmdenv, restrictTo, maxLs, hopNo
        ):
    """
    Generate exception text indicating we couldn't complete a
    route given the restrictions supplied. If the user has
    specified detail, check if there is a route at all.
    """

    places = list(
        set(
            chain.from_iterable(
                [place] if isinstance(place, Station) else place.stations
                for place in restrictTo
            )
        )
    )
    places.sort(key=lambda stn: stn.dbname)

    dests = ", ".join(place.name() for place in places)

    return (
        "SORRY: Could not find any routes that delivered a profit to "
        "{} at hop #{}\n"
        "You may need to add more hops to your route or adjust your "
        "filters/restrictions.\n"
        .format(
            dests, hopNo + 1
        )
    )

######################################################################
# Perform query and populate result set

def run(results, cmdenv, tdb):
    cmdenv.DEBUG1("loading trades")

    if tdb.tradingCount == 0:
        raise NoDataError("Database does not contain any profitable trades.")

    # Instantiate the calculator object
    calc = TradeCalc(tdb, cmdenv)

    validateRunArguments(tdb, cmdenv, calc)

    origPlace, viaSet = cmdenv.origPlace, cmdenv.viaSet
    avoidPlaces = cmdenv.avoidPlaces
    stopStations = cmdenv.destinations
    goalSystem = cmdenv.goalSystem
    maxLs = cmdenv.maxLs

    # seed the route table with starting places
    startCr = cmdenv.credits - cmdenv.insurance
    routes = [
        Route(
            stations=[src],
            hops=[],
            jumps=[],
            startCr=startCr,
            gainCr=0,
            score=0
        )
        for src in cmdenv.origins
    ]

    numHops = cmdenv.hops
    lastHop = numHops - 1
    viaStartPos = 1 if origPlace else 0

    cmdenv.DEBUG1("numHops {}, vias {}, adhocHops {}",
                numHops, len(viaSet), cmdenv.adhocHops)

    results.summary = ResultRow()
    results.summary.exception = ""

    pruneMod = cmdenv.pruneScores / 100

    for hopNo in range(numHops):
        restrictTo = None
        if hopNo == lastHop and stopStations:
            restrictTo = set(stopStations)
            manualRestriction = bool(cmdenv.destPlace)
        elif len(viaSet) > cmdenv.adhocHops:
            restrictTo = viaSet
            manualRestriction = True

        if hopNo >= 1 and cmdenv.maxRoutes or pruneMod:
            routes.sort()
            if pruneMod and hopNo + 1 >= cmdenv.pruneHops and len(routes) > 10:
                crop = int(len(routes) * pruneMod)
                routes = routes[:-crop]
                cmdenv.NOTE("Pruned {} origins", crop)

            if cmdenv.maxRoutes and len(routes) > cmdenv.maxRoutes:
                routes = routes[:cmdenv.maxRoutes]

        if cmdenv.progress:
            print("* Hop {:3n}: {:.>10n} origins".format(hopNo+1, len(routes)))
        elif cmdenv.debug:
            cmdenv.DEBUG0("Hop {}...", hopNo+1)

        try:
            newRoutes = calc.getBestHops(routes, restrictTo=restrictTo)
        except NoHopsError:
            if hopNo == 0 and len(cmdenv.origSystems) == 1:
                raise NoDataError(
                    "Couldn't find any trading links within {} x {}ly jumps of {}."
                    .format(
                        cmdenv.maxJumpsPer,
                        cmdenv.maxLyPer,
                        cmdenv.origSystems[0].name(),
                    )
                )
            raise NoDataError(
                "No routes had reachable trading links at hop #{}".format(hopNo + 1)
            )

        if not newRoutes:
            checkReachability(tdb, cmdenv)
            if hopNo > 0:
                if restrictTo and manualRestriction:
                    results.summary.exception += routeFailedRestrictions(
                        tdb, cmdenv, restrictTo, maxLs, hopNo
                    )
                    break
                results.summary.exception += (
                    "SORRY: Could not find profitable destinations "
                    "beyond hop #{:n}\n"
                    .format(hopNo + 1)
                )
                break
            if hopNo == 0:
                if cmdenv.origPlace and len(routes) == 1:
                    errText = (
                        "No profitable buyers found for the goods at {}.\n"
                        "\n"
                        "You may want to try:\n"
                        "  {} local \"{}\" --ly {} -vv --stations --trading"
                        .format(
                            routes[0].lastStation.name(),
                            sys.argv[0], cmdenv.origPlace.system.name(),
                            cmdenv.maxJumpsPer * cmdenv.maxLyPer,
                        )
                    )
                    if isinstance(cmdenv.origPlace, Station):
                        errText += (
                            "\n"
                            "or:\n"
                            "  {} market \"{}\" --sell -vv"
                            .format(
                                sys.argv[0], cmdenv.origPlace.name(),
                            )
                        )
                    raise NoDataError(errText)

        routes = newRoutes
        if routes and goalSystem:
            # Promote the winning route to the top of the list
            # while leaving the remainder of the list intact
            routes.sort(
                key=lambda route:
                    0 if route.lastSystem is goalSystem else 1
            )
            if routes[0].lastSystem is goalSystem:
                cmdenv.NOTE("Goal system reached!")
                routes = routes[:1]
                break

    if not routes:
        raise NoDataError(
            "No profitable trades matched your critera, "
            "or price data along the route is missing."
        )

    if viaSet:
        routes, caution = filterByVia(routes, viaSet, viaStartPos)
        if caution:
            results.summary.exception += caution + "\n"

    routes.sort()
    results.data = routes

    return results


######################################################################
# Transform result set into output

def render(results, cmdenv, tdb):
    exception = results.summary.exception
    if exception:
        print('#' * 76)
        print("\a{}".format(exception), end="")
        print('#' * 76)
        print()

    routes = results.data

    for i in range(min(len(routes), cmdenv.routes)):
        print(routes[i].detail(cmdenv))

    # User wants to be guided through the route.
    if cmdenv.checklist:
        assert cmdenv.routes == 1
        cl = Checklist(tdb, cmdenv)
        cl.run(routes[0], cmdenv.credits)


