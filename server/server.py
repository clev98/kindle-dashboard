from flask import Flask, render_template
from flask_cors import CORS
from google.transit import gtfs_realtime_pb2
from dataclasses import dataclass
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import json
import os
import csv

server = Flask(__name__)
# "security"
CORS(server)


@dataclass
class WmataTrainTimes:
    destination: str
    line: str
    minutes: int


class WmataTrainTimesFactory:
    @classmethod
    def make_WmataTrainTimes(cls, api_data, outlook=4) -> []:
        try:
            trains = api_data["Trains"]
        except TypeError:
            return []

        reports = []

        if len(trains) < outlook:
            outlook = len(trains)

        for i in range(0, outlook):
            reports.append(
                WmataTrainTimes(
                    trains[i]["Destination"],
                    trains[i]["Line"],
                    (
                        trains[i]["Min"]
                        if trains[i]["Min"] != "BRD" and trains[i]["Min"] != "ARR"
                        else 0
                    ),
                )
            )

        return reports


@dataclass
class Incident:
    description: str
    affected: str


class IncidentFactory:
    @classmethod
    def make_WmataIncidents(cls, api_data, filter=["SV", "RD"]) -> []:
        try:
            incidents = api_data["Incidents"]
        except TypeError:
            return []

        reports = []

        for alert in incidents:
            for line in filter:
                if line in alert["LinesAffected"]:
                    reports.append(
                        Incident(
                            alert["Description"],
                            alert["LinesAffected"],
                        )
                    )
                    break

        return reports

    @classmethod
    def make_FcBusAlerts(cls, api_data) -> []:
        reports = []

        for route in api_data.keys():
            for alert in api_data[route]:
                reports.append(Incident(alert["description"], route))

        return reports


@dataclass
class FcBusTimes:
    minutes: str
    bus_id: str
    destination: str


class FcBusTimesFactory:
    @classmethod
    def make_FcBusTimes(cls, api_data) -> []:
        reports = []
        current_time = datetime.now()

        for key in api_data.keys():
            arrival_time = datetime.strptime(api_data[key]["stop_time"], "%H:%M:%S")

            stop_time = (arrival_time - current_time).seconds // 60

            # Filter out anything not coming in the next hour
            if stop_time > 60:
                continue

            # Forced to use a little bit of guilty knowledge here, as the
            # buses I care about don't run on the weekend and fairfax doesn't
            # publish good scheduling in their API
            if current_time.strftime("%A").lower() in ["saturday", "sunday"]:
                continue

            reports.append(
                FcBusTimes(
                    stop_time, api_data[key]["route_id"], api_data[key]["destination"]
                )
            )

        return reports


@dataclass
class DayWeather:
    name: str
    current: float
    high: float
    low: float
    precipitation: float


class DayWeatherFactory:
    @classmethod
    def make_DayWeathers(cls, api_data, outlook=2) -> []:
        periods = api_data["properties"]["periods"]
        report = []

        for i in range(outlook):
            current_time = datetime.now() + timedelta(days=i)
            current_day = []

            for period in periods:
                time = datetime.fromisoformat(period["startTime"])

                if time.day == current_time.day:
                    current_day.append(period)

            high = max(period["temperature"] for period in current_day)
            low = min(period["temperature"] for period in current_day)

            for period in current_day:
                time = datetime.fromisoformat(period["startTime"])

                if time.hour == current_time.hour:
                    current = period["temperature"]
                    precipitation = period["probabilityOfPrecipitation"]["value"]
                    break
            else:
                current = -1
                precipitation = -1

            report.append(
                DayWeather(
                    current_time.strftime("%A"),
                    current,
                    high,
                    low,
                    precipitation,
                )
            )

        return report


@server.route("/dashboard/")
def render_dashboard():
    metro_incidents = IncidentFactory.make_WmataIncidents(get_transit_incidents())
    bus_incidents = IncidentFactory.make_FcBusAlerts(get_bus_alerts())
    train_times = WmataTrainTimesFactory.make_WmataTrainTimes(get_transit_times())
    bus_times = FcBusTimesFactory.make_FcBusTimes(get_bus_times())
    weather_report = DayWeatherFactory.make_DayWeathers(get_weather())

    return render_template(
        "index.html",
        weather_periods=weather_report,
        alerts=metro_incidents + bus_incidents,
        metro_times=train_times,
        bus_times=bus_times,
        # TODO: Kindle claims to be in my timezone, but for whatever reason is 4 hours behind anyway
        update_time=(datetime.now() - timedelta(hours=4)).strftime("%I:%M %p"),
    )


def get_transit_incidents():
    if not set(["WMATA_API_KEY"]).issubset(os.environ):
        return None

    WMATA_API_KEY = os.getenv("WMATA_API_KEY")

    r = requests.get(
        "https://api.wmata.com/Incidents.svc/json/Incidents",
        headers={
            "Cache-Control": "max-age=1800000",
            "api_key": WMATA_API_KEY,
        },
    )

    if r.status_code != 200:
        return None

    return json.loads(r.text)


def get_transit_times():
    if not set(["STATION_CODE", "WMATA_API_KEY"]).issubset(os.environ):
        return None

    STATION_CODE = os.getenv("STATION_CODE")
    WMATA_API_KEY = os.getenv("WMATA_API_KEY")

    r = requests.get(
        f"https://api.wmata.com/StationPrediction.svc/json/GetPrediction/{STATION_CODE}",
        headers={
            "Cache-Control": "no-cache",
            "api_key": WMATA_API_KEY,
        },
    )

    if r.status_code != 200:
        return None

    return json.loads(r.text)


def get_bus_alerts():
    if not set(["FC_BUS_1", "FC_BUS_1"]).issubset(os.environ):
        return None

    FC_BUS_1 = os.getenv("FC_BUS_1")
    FC_BUS_2 = os.getenv("FC_BUS_2")
    reports = {}

    r = requests.get("https://www.fairfaxcounty.gov/gtfsrt/alerts")

    if r.status_code != 200:
        return None

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)

    for entity in feed.entity:
        if entity.alert.informed_entity[0].route_id not in [FC_BUS_1, FC_BUS_2]:
            continue

        if entity.alert.informed_entity[0].route_id not in reports.keys():
            reports[entity.alert.informed_entity[0].route_id] = []

        reports[entity.alert.informed_entity[0].route_id].append(
            {
                "description": entity.alert.description_text.translation[0].text,
            }
        )

    return reports


def get_bus_times():
    if not set(["FC_STOP_TIMES", "FC_STOP_1", "FC_STOP_2"]).issubset(os.environ):
        return None

    FC_STOP_TIMES = os.getenv("FC_STOP_TIMES")
    FC_STOP_1 = os.getenv("FC_STOP_1")
    FC_STOP_2 = os.getenv("FC_STOP_2")
    TRIP_ID = 0
    STOP_TIME = 1
    STOP_ID = 3
    STOP_SEQ = 4
    FRIENDLY_NAME = 5
    times = {}

    # Get the static stop times from our local list
    with open(FC_STOP_TIMES, "r") as fd:
        reader = csv.reader(fd)

        for row in reader:
            if row[STOP_ID] != FC_STOP_1 and row[STOP_ID] != FC_STOP_2:
                continue

            times[row[TRIP_ID]] = {
                "stop_time": row[STOP_TIME],
                "route_id": row[FRIENDLY_NAME][:3],
                "destination": row[FRIENDLY_NAME][4:],
                "stop_seq": row[STOP_SEQ],
            }

    # Get the updated times from the GTFS endpoint
    r = requests.get("https://www.fairfaxcounty.gov/gtfsrt/trips")

    if r.status_code != 200:
        return None

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)

    for entity in feed.entity:
        if entity.trip_update.trip.trip_id in times.keys():
            stop_updates = entity.trip_update.stop_time_update

            for stop in stop_updates:
                if (
                    stop.stop_sequence
                    == times[entity.trip_update.trip.trip_id]["stop_seq"]
                ):
                    times[entity.trip_update.trip.trip_id]["stop_time"] = (
                        datetime.fromtimestamp(stop.arrival.time).strftime("%H:%M:%S")
                    )

    return times


def get_weather():
    if not set(["OFS", "GRID_X", "GRID_Y"]).issubset(os.environ):
        return None

    OFS = os.getenv("OFS")
    GRID_X = os.getenv("GRID_X")
    GRID_Y = os.getenv("GRID_Y")

    r = requests.get(
        f"https://api.weather.gov/gridpoints/{OFS}/{GRID_X},{GRID_Y}/forecast/hourly",
        headers={
            "Cache-Control": "max-age=3600000",
        },
    )

    if r.status_code != 200:
        return None

    return json.loads(r.text)


if __name__ == "__main__":
    load_dotenv()
    server.run("0.0.0.0", 8080, debug=False)
