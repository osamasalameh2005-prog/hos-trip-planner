import json
import requests

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Trip


CYCLE_LIMIT = 70.0
DAILY_DRIVING_LIMIT = 11.0
DAILY_DUTY_WINDOW = 14.0
DRIVING_BREAK_LIMIT = 8.0
BREAK_DURATION = 0.5
RESET_DURATION = 10.0
RESTART_DURATION = 34.0
PICKUP_DURATION = 1.0
DROPOFF_DURATION = 1.0
FUEL_DISTANCE = 1000.0
FUEL_DURATION = 0.5


def geocode_location(location):
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": location,
        "format": "json",
        "limit": 20,
        "addressdetails": 1,
        "namedetails": 1,
    }

    headers = {
        "User-Agent": "HOS-Trip-Planner/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError(
            f"Location not found: {location}"
        )

    rejected_types = {
        "river",
        "road",
        "street",
        "boundary",
        "administrative",
        "forest",
        "lake",
        "park",
        "water",
        "island",
    }

    query = location.strip().lower()

    query_parts = [
        part.strip().lower()
        for part in location.split(",")
        if part.strip()
    ]

    scored_results = []

    for result in results:
        address = result.get("address", {})
        result_type = result.get("type", "").lower()

        display_name = result.get(
            "display_name",
            "",
        ).lower()

        if result_type in rejected_types:
            continue

        score = 0

        if result_type == "city":
            score += 120
        elif result_type == "town":
            score += 110
        elif result_type == "municipality":
            score += 105
        elif result_type == "village":
            score += 100

        if address.get("country"):
            score += 20

        place_names = [
            address.get("city", ""),
            address.get("town", ""),
            address.get("village", ""),
            address.get("municipality", ""),
        ]

        for name in place_names:
            if name and name.strip().lower() == query:
                score += 100

        for part in query_parts:
            if part in display_name:
                score += 20

        for name in place_names:
            if name and query == name.strip().lower():
                score += 80

        scored_results.append(
            (score, result)
        )

    if not scored_results:
        raise ValueError(
            f"Could not find a suitable location: {location}"
        )

    scored_results.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_result = scored_results[0][1]

    return {
        "latitude": float(best_result["lat"]),
        "longitude": float(best_result["lon"]),
        "display_name": best_result.get(
            "display_name",
            location,
        ),
    }


def route_between(start, end):
    url = (
        "https://router.project-osrm.org/"
        "route/v1/driving/"
        f"{start['longitude']},{start['latitude']};"
        f"{end['longitude']},{end['latitude']}"
    )

    params = {
        "overview": "full",
        "steps": "true",
        "geometries": "geojson",
    }

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("code") != "Ok":
        raise ValueError(
            "Routing service could not calculate the route."
        )

    route = data["routes"][0]

    distance_miles = route["distance"] / 1609.344
    driving_hours = route["duration"] / 3600

    steps = []

    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            name = step.get("name", "").strip()

            if name:
                steps.append(name)

    return {
        "distance_miles": round(
            distance_miles,
            2,
        ),
        "driving_hours": round(
            driving_hours,
            2,
        ),
        "steps": steps,
        "geometry": route.get(
            "geometry",
            {},
        ),
    }


def add_log(
    logs,
    status,
    start,
    end,
    duration,
    location="",
):
    logs.append(
        {
            "status": status,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(duration, 2),
            "location": location,
        }
    )


def add_rest_period(
    logs,
    current_time,
    remaining_driving,
    remaining_duty,
):
    rest_duration = 0.5

    add_log(
        logs,
        "Break",
        current_time,
        current_time + rest_duration,
        rest_duration,
    )

    return (
        current_time + rest_duration,
        remaining_driving,
        remaining_duty,
    )


def build_hos_plan(
    current_cycle_used,
    first_drive_hours,
    second_drive_hours,
):
    logs = []

    cycle_remaining = (
        CYCLE_LIMIT - current_cycle_used
    )

    total_driving = (
        first_drive_hours + second_drive_hours
    )

    current_time = 0.0
    duty_time = 0.0
    driving_time = 0.0
    cycle_used = current_cycle_used

    def add_driving(hours, description):
        nonlocal current_time
        nonlocal duty_time
        nonlocal driving_time
        nonlocal cycle_used

        remaining = hours

        while remaining > 0:
            available_drive = min(
                DAILY_DRIVING_LIMIT - driving_time,
                DRIVING_BREAK_LIMIT - (
                    driving_time % DRIVING_BREAK_LIMIT
                    if driving_time > 0
                    else 0
                ),
                CYCLE_LIMIT - cycle_used,
                remaining,
            )

            if available_drive <= 0:
                if driving_time >= DAILY_DRIVING_LIMIT:
                    add_log(
                        logs,
                        "Daily Reset",
                        current_time,
                        current_time + RESET_DURATION,
                        RESET_DURATION,
                    )

                    current_time += RESET_DURATION
                    duty_time = 0.0
                    driving_time = 0.0

                    continue

                if cycle_used >= CYCLE_LIMIT:
                    add_log(
                        logs,
                        "Cycle Reset",
                        current_time,
                        current_time + RESTART_DURATION,
                        RESTART_DURATION,
                    )

                    current_time += RESTART_DURATION
                    cycle_used = 0.0

                    continue

                add_log(
                    logs,
                    "Break",
                    current_time,
                    current_time + BREAK_DURATION,
                    BREAK_DURATION,
                )

                current_time += BREAK_DURATION
                continue

            if (
                duty_time + available_drive
                > DAILY_DUTY_WINDOW
            ):
                add_log(
                    logs,
                    "Daily Reset",
                    current_time,
                    current_time + RESET_DURATION,
                    RESET_DURATION,
                )

                current_time += RESET_DURATION
                duty_time = 0.0
                driving_time = 0.0

                continue

            add_log(
                logs,
                "Driving",
                current_time,
                current_time + available_drive,
                available_drive,
                description,
            )

            current_time += available_drive
            duty_time += available_drive
            driving_time += available_drive
            cycle_used += available_drive
            remaining -= available_drive

            if (
                remaining > 0
                and driving_time >= DRIVING_BREAK_LIMIT
            ):
                add_log(
                    logs,
                    "Break",
                    current_time,
                    current_time + BREAK_DURATION,
                    BREAK_DURATION,
                )

                current_time += BREAK_DURATION
                duty_time += BREAK_DURATION

                driving_time = 0.0

    add_driving(
        first_drive_hours,
        "Current Location → Pickup",
    )

    add_log(
        logs,
        "Pickup",
        current_time,
        current_time + PICKUP_DURATION,
        PICKUP_DURATION,
    )

    current_time += PICKUP_DURATION
    duty_time += PICKUP_DURATION

    add_driving(
        second_drive_hours,
        "Pickup → Dropoff",
    )

    add_log(
        logs,
        "Dropoff",
        current_time,
        current_time + DROPOFF_DURATION,
        DROPOFF_DURATION,
    )

    current_time += DROPOFF_DURATION
    duty_time += DROPOFF_DURATION

    fuel_stops = int(
        total_driving // FUEL_DISTANCE
    )

    if fuel_stops > 0:
        for _ in range(fuel_stops):
            add_log(
                logs,
                "Fuel",
                current_time,
                current_time + FUEL_DURATION,
                FUEL_DURATION,
            )

            current_time += FUEL_DURATION
            duty_time += FUEL_DURATION

    return {
        "logs": logs,
        "total_time_hours": round(
            current_time,
            2,
        ),
        "cycle_remaining_hours": round(
            max(0, CYCLE_LIMIT - cycle_used),
            2,
        ),
    }


@csrf_exempt
def create_trip(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "error": "Only POST requests are allowed."
            },
            status=405,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )

        current_location = data.get(
            "current_location",
            "",
        ).strip()

        pickup_location = data.get(
            "pickup_location",
            "",
        ).strip()

        dropoff_location = data.get(
            "dropoff_location",
            "",
        ).strip()

        current_cycle_used = float(
            data.get(
                "current_cycle_used",
                0,
            )
        )

        if not current_location:
            raise ValueError(
                "Current location is required."
            )

        if not pickup_location:
            raise ValueError(
                "Pickup location is required."
            )

        if not dropoff_location:
            raise ValueError(
                "Dropoff location is required."
            )

        if (
            current_cycle_used < 0
            or current_cycle_used > CYCLE_LIMIT
        ):
            raise ValueError(
                "Current cycle used must be between 0 and 70 hours."
            )

        current = geocode_location(
            current_location
        )

        pickup = geocode_location(
            pickup_location
        )

        dropoff = geocode_location(
            dropoff_location
        )

        current_to_pickup = route_between(
            current,
            pickup,
        )

        pickup_to_dropoff = route_between(
            pickup,
            dropoff,
        )

        total_distance_miles = round(
            current_to_pickup["distance_miles"]
            + pickup_to_dropoff["distance_miles"],
            2,
        )

        total_driving_hours = round(
            current_to_pickup["driving_hours"]
            + pickup_to_dropoff["driving_hours"],
            2,
        )

        hos_plan = build_hos_plan(
            current_cycle_used,
            current_to_pickup["driving_hours"],
            pickup_to_dropoff["driving_hours"],
        )

        trip = Trip.objects.create(
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            current_cycle_used=current_cycle_used,
            total_distance_miles=total_distance_miles,
            total_driving_hours=total_driving_hours,
        )

        return JsonResponse(
            {
                "id": trip.id,

                "locations": {
                    "current": current,
                    "pickup": pickup,
                    "dropoff": dropoff,
                },

                "current_cycle_used": current_cycle_used,

                "remaining_cycle_hours": round(
                    CYCLE_LIMIT
                    - current_cycle_used,
                    2,
                ),

                "current_to_pickup": current_to_pickup,

                "pickup_to_dropoff": pickup_to_dropoff,

                "total_distance_miles": total_distance_miles,

                "total_driving_hours": total_driving_hours,

                "pickup_hours": PICKUP_DURATION,

                "dropoff_hours": DROPOFF_DURATION,

                "fuel_interval_miles": FUEL_DISTANCE,

                "hos_plan": hos_plan,
            }
        )

    except ValueError as exc:
        return JsonResponse(
            {
                "error": str(exc)
            },
            status=400,
        )

    except requests.RequestException as exc:
        return JsonResponse(
            {
                "error": (
                    "Location or routing service error: "
                    f"{str(exc)}"
                )
            },
            status=502,
        )

    except Exception as exc:
        return JsonResponse(
            {
                "error": str(exc)
            },
            status=500,
        )