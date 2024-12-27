import csv
import json
import pathlib
from glob import glob

import clingo
import clorm
import os
import haversine
import yaml


from run_scheduler.domain import RouteDistanceK, Ascent, Exchange, RoutePairDistanceK, Descent, Route, \
    ExchangePairDistanceK


def load_exchanges(exchange_filename: pathlib.Path):
    exchanges = {}
    with open(exchange_filename, 'r') as f:
        exchange_data = json.load(f)["features"]
        for exchange in exchange_data:
            props = exchange["properties"]
            exchanges[props["id"]] = {"name": props["name"], "id": props["id"], "coordinates": exchange["geometry"]["coordinates"], "reachability": props["reachability"]}
    return exchanges


def load_routes_from_dir(dir_path: pathlib.Path):
    routes = []

    for route_filename in dir_path.glob("*.geojson"):
        try:
            # Load the route and metadata
            with open(route_filename) as f:
                route_data = json.load(f)
            props = route_data["properties"]
            title = props["name"]
            route = {
                'title': title,
                'id': props["id"],
                'distance_mi': float(props["distance_mi"]),
                'ascent_m': int(props["ascent_m"]),
                'descent_m': int(props["descent_m"] if props["descent_m"] else -1),
                'start_exchange': props["start"],
                'end_exchange': props["end"],
                'coordinates': route_data["geometry"]["coordinates"],
                'attributes': {
                    #"type": props["type"],
                    "surface": props["surface"],
                    "deprecated": "deprecated" in props,
                }
            }
            routes.append(route)
        except Exception as e:
            print(f"Error loading route {route_filename}: {e}")
    return routes


def load_routes_from_table(yaml_path: pathlib.Path):
    routes = []

    with open(yaml_path) as f:
        route_data = yaml.load(f, Loader=yaml.FullLoader)
    for route in route_data:
        title = route["name"]
        route = {
            'title': title,
            'id': route["id"],
            'distance_mi': float(route["distance_mi"]),
            'ascent_ft': int(route["ascent_m"]),
            'descent_ft': int(route["descent_m"] if route["descent_m"] else -1),
            'start_exchange': route["start"],
            'end_exchange': route["end"],
            'attributes': {
                #"type": route["type"],
                "surface": route["surface"],
                "deprecated": "deprecated" in route,
                "neighborhoods": route["neighborhoods"],
                "coarse_neighborhoods": route["coarse_neighborhoods"],
                "dates_run": route["dates_run"],
            }
        }
        routes.append(route)
    return routes


def flip_lat_long(lat_long_ele_point):
    return lat_long_ele_point[1], lat_long_ele_point[0], lat_long_ele_point[2]


def routes_to_facts(routes, exchanges, distance_precision, duration_precision):
    facts = []
    Distance = RouteDistanceK(distance_precision)
    exchange_coords = {exchange_id: (exchanges[exchange_id]["coordinates"][1], exchanges[exchange_id]["coordinates"][0]) for exchange_id in exchanges}
    all_dates = set()
    for route in routes:
        if route["attributes"]["deprecated"]:
            continue
        start_id = exchanges[route["start_exchange"]]["id"]
        end_id = exchanges[route["end_exchange"]]["id"]
        facts.append(Route(route_id=route["id"], name=route["title"], start_exchange=start_id, end_exchange=end_id))
        facts.append(Distance(route_id=route["id"], dist=route["distance_mi"]))
        if route["ascent_ft"] != -1:
            facts.append(Ascent(route_id=route["id"], ascent=round(route["ascent_ft"])))
        if route["descent_ft"] != -1:
            facts.append(Descent(route_id=route["id"], descent=round(route["descent_ft"])))
        for attribute_name in route["attributes"]:
            if not route["attributes"][attribute_name]:
                continue
            # Any special aspects of the leg which you may want to reason about can be shoved into attributes
            attribute_type = clorm.simple_predicate(attribute_name, 2)
            if type(route["attributes"][attribute_name]) == str:
                facts.append(
                    attribute_type(clingo.String(route["id"]), clingo.String(route["attributes"][attribute_name])))
            elif type(route["attributes"][attribute_name]) == int:
                facts.append(
                    attribute_type(clingo.String(route["id"]), clingo.Number(route["attributes"][attribute_name])))
            elif attribute_name == "neighborhoods":
                attribute_type = clorm.simple_predicate("neighborhood", 2)
                for neighborhood in route["attributes"][attribute_name]:
                    facts.append(attribute_type(clingo.String(route["id"]), clingo.String(neighborhood)))
            elif attribute_name == "coarse_neighborhoods":
                attribute_type = clorm.simple_predicate("coarseNeighborhood", 2)
                for neighborhood in route["attributes"][attribute_name]:
                    facts.append(attribute_type(clingo.String(route["id"]), clingo.String(neighborhood)))

    for route in routes:
        if "dates_run" in route["attributes"]:
            all_dates.update(route["attributes"]["dates_run"])
    # Higher indices -> more recently run
    sorted_dates = list(sorted(all_dates))
    for route in routes:
        if "dates_run" in route["attributes"] and len(route["attributes"]["dates_run"]) > 0:
            last_run_index = sorted_dates.index(route["attributes"]["dates_run"][-1])
            facts.append(clorm.simple_predicate("lastRun", 2)(clingo.String(route["id"]), clingo.Number(last_run_index)))
        else:
            facts.append(clorm.simple_predicate("lastRun", 2)(clingo.String(route["id"]), clingo.Number(-1)))


    for exchange_id, attr in exchanges.items():
        facts.append(Exchange(exchange_id=exchange_id, name=attr["id"]))
        for attribute_name in attr:
            if not attr[attribute_name]:
                continue
            attribute_type = clorm.simple_predicate(attribute_name, 2)
            if type(attr[attribute_name]) == str:
                facts.append(attribute_type(clingo.String(exchange_id), clingo.String(attr[attribute_name])))
            elif type(attr[attribute_name]) == int:
                facts.append(attribute_type(clingo.String(exchange_id), clingo.Number(attr[attribute_name])))

    # Compute geographic mean of each route by averaging the lat/long of each point
    means = {}
    for route in routes:
        lat_sum = 0
        long_sum = 0
        for coord in route["coordinates"]:
            lat_sum += coord[1]
            long_sum += coord[0]
        means[route["id"]] = ((lat_sum / len(route["coordinates"]), long_sum / len(route["coordinates"])))

    PairDistance = RoutePairDistanceK(distance_precision)
    pairwise_distances = []
    for id1, coord1 in means.items():
        for id2, coord2 in means.items():
            if id1 != id2:
                pairwise_distances.append(
                    (id1, id2, haversine.haversine(coord1[:2], coord2[:2], unit=haversine.Unit.MILES)))
                facts.append(PairDistance(route_a=id1, route_b=id2, dist=pairwise_distances[-1][2]))
                facts.append(PairDistance(route_a=id2, route_b=id1, dist=pairwise_distances[-1][2]))
            else:
                facts.append(PairDistance(route_a=id1, route_b=id2, dist=0))
                facts.append(PairDistance(route_a=id2, route_b=id1, dist=0))

    ExchangeDistance = ExchangePairDistanceK(distance_precision)
    pairwise_distances = []
    for id1, coord1 in exchange_coords.items():
        for id2, coord2 in exchange_coords.items():
            if id1 != id2:
                pairwise_distances.append((id1, id2, haversine.haversine(coord1[:2], coord2[:2], unit=haversine.Unit.MILES)))
                facts.append(ExchangeDistance(exchange_a=id1, exchange_b=id2, dist=pairwise_distances[-1][2]))
                facts.append(ExchangeDistance(exchange_a=id2, exchange_b=id1, dist=pairwise_distances[-1][2]))
            else:
                facts.append(ExchangeDistance(exchange_a=id1, exchange_b=id2, dist=0))
                facts.append(ExchangeDistance(exchange_a=id2, exchange_b=id1, dist=0))
    return facts
