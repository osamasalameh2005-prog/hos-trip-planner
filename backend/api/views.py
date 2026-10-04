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

    scored_results = []

    for result in results:
        address = result.get("address", {})
        result_type = result.get("type", "").lower()

        if result_type in rejected_types:
            continue

        score = 0

        if result_type in {
            "city",
            "town",
            "village",
            "municipality",
        }:
            score += 100

        if "city" in address:
            score += 40

        if "town" in address:
            score += 35

        if "village" in address:
            score += 30

        if "country" in address:
            score += 10

        display_name = result.get(
            "display_name",
            "",
        ).lower()

        query_parts = [
            part.strip().lower()
            for part in location.split(",")
            if part.strip()
        ]

        for part in query_parts:
            if part in display_name:
                score += 10

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
    day,
    start,
    end,
    status,
    location="",
):
    if end <= start:
        return

    logs.append(
        {
            "day": day,
            "start_hour": round(start, 2),
            "end_hour": round(end, 2),
            "status": status,
            "location": location,
        }
    )


def add_rest_period(
    logs,
    day,
    start,
    duration,
    reason,
):
    end = min(
        start + duration,
        24.0,
    )

    add_log(
        logs,
        day,
        start,
        end,
        "Sleeper Berth",
        reason,
    )

    return end


def build_hos_plan(
    total_driving_hours,
    total_distance_miles,
    cycle_used,
):
    cycle_remaining = max(
        0.0,
        CYCLE_LIMIT - cycle_used,
    )

    remaining_driving = max(
        0.0,
        total_driving_hours,
    )

    current_day = 1
    day_elapsed = 0.0
    day_driving = 0.0
    day_since_break = 0.0

    total_trip_hours = 0.0
    total_break_hours = 0.0

    logs = []

    fuel_distance = 0.0

    if total_driving_hours > 0:
        trip_distance_ratio = (
            total_distance_miles
            / total_driving_hours
        )
    else:
        trip_distance_ratio = 0.0

    while remaining_driving > 0.001:

        if cycle_remaining <= 0.001:
            restart_remaining = RESTART_DURATION

            while restart_remaining > 0:
                available_today = 24.0 - day_elapsed

                if available_today <= 0:
                    current_day += 1
                    day_elapsed = 0.0
                    day_driving = 0.0
                    day_since_break = 0.0
                    continue

                restart_today = min(
                    restart_remaining,
                    available_today,
                )

                add_log(
                    logs,
                    current_day,
                    day_elapsed,
                    day_elapsed + restart_today,
                    "Sleeper Berth",
                    "34-hour restart",
                )

                day_elapsed += restart_today
                total_trip_hours += restart_today
                restart_remaining -= restart_today

                if restart_remaining > 0:
                    current_day += 1
                    day_elapsed = 0.0
                    day_driving = 0.0
                    day_since_break = 0.0

            cycle_remaining = CYCLE_LIMIT
            continue

        if (
            day_elapsed >= DAILY_DUTY_WINDOW
            or day_driving >= DAILY_DRIVING_LIMIT
        ):
            start = day_elapsed

            if start < 24.0:
                rest_available = min(
                    RESET_DURATION,
                    24.0 - start,
                )

                add_log(
                    logs,
                    current_day,
                    start,
                    start + rest_available,
                    "Sleeper Berth",
                    "10-hour daily reset",
                )

                total_trip_hours += rest_available

            current_day += 1
            day_elapsed = 0.0
            day_driving = 0.0
            day_since_break = 0.0

            continue

        if day_since_break >= DRIVING_BREAK_LIMIT:
            if (
                day_elapsed + BREAK_DURATION
                <= DAILY_DUTY_WINDOW
            ):
                add_log(
                    logs,
                    current_day,
                    day_elapsed,
                    day_elapsed + BREAK_DURATION,
                    "Off Duty",
                    "30-minute break",
                )

                day_elapsed += BREAK_DURATION
                total_break_hours += BREAK_DURATION
                total_trip_hours += BREAK_DURATION
                day_since_break = 0.0

                continue

            current_day += 1
            day_elapsed = 0.0
            day_driving = 0.0
            day_since_break = 0.0
            continue

        daily_drive_remaining = (
            DAILY_DRIVING_LIMIT - day_driving
        )

        daily_window_remaining = (
            DAILY_DUTY_WINDOW - day_elapsed
        )

        break_remaining = (
            DRIVING_BREAK_LIMIT - day_since_break
        )

        available_driving = min(
            remaining_driving,
            daily_drive_remaining,
            daily_window_remaining,
            cycle_remaining,
            break_remaining,
        )

        if available_driving <= 0.001:
            current_day += 1
            day_elapsed = 0.0
            day_driving = 0.0
            day_since_break = 0.0
            continue

        drive_start = day_elapsed
        drive_end = (
            day_elapsed + available_driving
        )

        add_log(
            logs,
            current_day,
            drive_start,
            drive_end,
            "Driving",
        )

        day_elapsed = drive_end
        day_driving += available_driving
        day_since_break += available_driving

        cycle_remaining -= available_driving
        remaining_driving -= available_driving

        distance_driven = (
            available_driving
            * trip_distance_ratio
        )

        fuel_distance += distance_driven
        total_trip_hours += available_driving

        if (
            fuel_distance >= FUEL_DISTANCE
            and remaining_driving > 0.001
        ):
            if (
                day_elapsed + FUEL_DURATION
                <= DAILY_DUTY_WINDOW
            ):
                add_log(
                    logs,
                    current_day,
                    day_elapsed,
                    day_elapsed + FUEL_DURATION,
                    "On Duty (Not Driving)",
                    "Fuel stop",
                )

                day_elapsed += FUEL_DURATION
                total_trip_hours += FUEL_DURATION
                fuel_distance = 0.0

    if day_elapsed + PICKUP_DURATION <= 24.0:
        add_log(
            logs,
            current_day,
            day_elapsed,
            day_elapsed + PICKUP_DURATION,
            "On Duty (Not Driving)",
            "Pickup",
        )

        day_elapsed += PICKUP_DURATION
        total_trip_hours += PICKUP_DURATION

    if day_elapsed + DROPOFF_DURATION <= 24.0:
        add_log(
            logs,
            current_day,
            day_elapsed,
            day_elapsed + DROPOFF_DURATION,
            "On Duty (Not Driving)",
            "Dropoff",
        )

        day_elapsed += DROPOFF_DURATION
        total_trip_hours += DROPOFF_DURATION

    max_day = max(
        [
            item["day"]
            for item in logs
        ],
        default=1,
    )

    days = []

    for day_number in range(
        1,
        max_day + 1,
    ):
        day_logs = [
            item
            for item in logs
            if item["day"] == day_number
        ]

        days.append(
            {
                "day": day_number,
                "logs": day_logs,
            }
        )

    return {
        "total_trip_hours": round(
            total_trip_hours,
            2,
        ),
        "number_of_days": max_day,
        "total_break_hours": round(
            total_break_hours,
            2,
        ),
        "days": days,
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
        if request.content_type == "application/json":
            data = json.loads(
                request.body.decode("utf-8")
            )
        else:
            data = request.POST

        current_location = str(
            data.get(
                "current_location",
                "",
            )
        ).strip()

        pickup_location = str(
            data.get(
                "pickup_location",
                "",
            )
        ).strip()

        dropoff_location = str(
            data.get(
                "dropoff_location",
                "",
            )
        ).strip()

        cycle_value = data.get(
            "current_cycle_used"
        )

        if not current_location:
            return JsonResponse(
                {
                    "error": (
                        "Current location is required."
                    )
                },
                status=400,
            )

        if not pickup_location:
            return JsonResponse(
                {
                    "error": (
                        "Pickup location is required."
                    )
                },
                status=400,
            )

        if not dropoff_location:
            return JsonResponse(
                {
                    "error": (
                        "Dropoff location is required."
                    )
                },
                status=400,
            )

        if cycle_value is None:
            return JsonResponse(
                {
                    "error": (
                        "Current cycle used is required."
                    )
                },
                status=400,
            )

        cycle_used = float(cycle_value)

        if cycle_used < 0 or cycle_used > 70:
            return JsonResponse(
                {
                    "error": (
                        "Current cycle used must "
                        "be between 0 and 70 hours."
                    )
                },
                status=400,
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

        total_distance = (
            current_to_pickup["distance_miles"]
            + pickup_to_dropoff["distance_miles"]
        )

        total_driving_hours = (
            current_to_pickup["driving_hours"]
            + pickup_to_dropoff["driving_hours"]
        )

        hos_plan = build_hos_plan(
            total_driving_hours,
            total_distance,
            cycle_used,
        )

        trip = Trip.objects.create(
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            current_cycle_used=cycle_used,
        )

        return JsonResponse(
            {
                "id": trip.id,
                "current_cycle_used": cycle_used,
                "remaining_cycle_hours": round(
                    max(
                        0,
                        CYCLE_LIMIT - cycle_used,
                    ),
                    2,
                ),
                "current_to_pickup": current_to_pickup,
                "pickup_to_dropoff": pickup_to_dropoff,
                "total_distance_miles": round(
                    total_distance,
                    2,
                ),
                "total_driving_hours": round(
                    total_driving_hours,
                    2,
                ),
                "pickup_hours": PICKUP_DURATION,
                "dropoff_hours": DROPOFF_DURATION,
                "fuel_interval_miles": FUEL_DISTANCE,
                "hos_plan": hos_plan,
            }
        )

    except ValueError as error:
        return JsonResponse(
            {
                "error": str(error)
            },
            status=400,
        )

    except requests.RequestException:
        return JsonResponse(
            {
                "error": (
                    "A map or routing service "
                    "is temporarily unavailable."
                )
            },
            status=502,
        )

    except Exception as error:
        return JsonResponse(
            {
                "error": str(error)
            },
            status=500,
        )