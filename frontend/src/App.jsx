import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const API_URL = "/api/trips/";

const defaultCenter = [31.9539, 35.9106];

const markerIcon = new L.Icon({
  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const statusColors = {
  Driving: "#2563eb",
  "On Duty (Not Driving)": "#f59e0b",
  "Off Duty": "#22c55e",
  "Sleeper Berth": "#7c3aed",
};

function MapUpdater({ points }) {
  const map = useMap();

  useEffect(() => {
    if (points.length === 0) return;

    if (points.length === 1) {
      map.setView(points[0], 8);
      return;
    }

    const bounds = L.latLngBounds(points);

    map.fitBounds(bounds, {
      padding: [30, 30],
    });
  }, [map, points]);

  return null;
}

function ELDGraph({ logs }) {
  const graphHeight = 180;
  const leftPadding = 150;
  const rightPadding = 20;
  const topPadding = 25;
  const bottomPadding = 25;

  const graphWidth = 1000;
  const chartWidth =
    graphWidth - leftPadding - rightPadding;

  const rowHeight = 32;

  const statuses = [
    "Off Duty",
    "Sleeper Berth",
    "Driving",
    "On Duty (Not Driving)",
  ];

  const getY = (status) => {
    const index = statuses.indexOf(status);

    return (
      topPadding +
      index * rowHeight +
      rowHeight / 2
    );
  };

  const getX = (hour) => {
    return (
      leftPadding +
      (hour / 24) * chartWidth
    );
  };

  return (
    <div
      style={{
        width: "100%",
        overflowX: "auto",
        border: "1px solid #ddd",
        borderRadius: "8px",
        background: "#fff",
      }}
    >
      <svg
        viewBox={`0 0 ${graphWidth} ${graphHeight}`}
        style={{
          width: "100%",
          minWidth: "700px",
          display: "block",
        }}
      >
        {statuses.map((status) => {
          const y = getY(status);

          return (
            <g key={status}>
              <line
                x1={leftPadding}
                y1={y}
                x2={graphWidth - rightPadding}
                y2={y}
                stroke="#ddd"
                strokeWidth="1"
              />

              <text
                x={leftPadding - 10}
                y={y + 5}
                textAnchor="end"
                fontSize="13"
                fill="#333"
              >
                {status}
              </text>
            </g>
          );
        })}

        {Array.from(
          { length: 25 },
          (_, hour) => (
            <g key={hour}>
              <line
                x1={getX(hour)}
                y1={topPadding - 5}
                x2={getX(hour)}
                y2={
                  graphHeight -
                  bottomPadding
                }
                stroke="#eee"
                strokeWidth="1"
              />

              <text
                x={getX(hour)}
                y={graphHeight - 7}
                textAnchor="middle"
                fontSize="11"
                fill="#555"
              >
                {hour}
              </text>
            </g>
          )
        )}

        {logs.map((log, index) => {
          const startX = getX(
            Number(log.start_hour)
          );

          const endX = getX(
            Number(log.end_hour)
          );

          const y = getY(log.status);

          return (
            <g key={index}>
              <line
                x1={startX}
                y1={y}
                x2={endX}
                y2={y}
                stroke={
                  statusColors[log.status] ||
                  "#333"
                }
                strokeWidth="14"
                strokeLinecap="round"
              />

              <circle
                cx={startX}
                cy={y}
                r="4"
                fill={
                  statusColors[log.status] ||
                  "#333"
                }
              />

              <circle
                cx={endX}
                cy={y}
                r="4"
                fill={
                  statusColors[log.status] ||
                  "#333"
                }
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function App() {
  const [currentLocation, setCurrentLocation] =
    useState("");

  const [pickupLocation, setPickupLocation] =
    useState("");

  const [dropoffLocation, setDropoffLocation] =
    useState("");

  const [cycleUsed, setCycleUsed] =
    useState("");

  const [result, setResult] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    const cycleNumber = Number(cycleUsed);

    if (!currentLocation.trim()) {
      alert("Enter current location.");
      return;
    }

    if (!pickupLocation.trim()) {
      alert("Enter pickup location.");
      return;
    }

    if (!dropoffLocation.trim()) {
      alert("Enter dropoff location.");
      return;
    }

    if (cycleUsed === "") {
      alert(
        "Enter current cycle used hours."
      );
      return;
    }

    if (
      cycleNumber < 0 ||
      cycleNumber > 70
    ) {
      alert(
        "Cycle used must be between 0 and 70 hours."
      );
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          current_location:
            currentLocation,
          pickup_location:
            pickupLocation,
          dropoff_location:
            dropoffLocation,
          current_cycle_used:
            cycleNumber,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        alert(
          data.error ||
            "Something went wrong."
        );
        return;
      }

      setResult(data);

      alert(
        "Trip created successfully!"
      );
    } catch (error) {
      console.error(error);

      alert(
        "Unable to connect to the server."
      );
    } finally {
      setLoading(false);
    }
  };

  const currentPoint =
    result?.current_to_pickup?.geometry ||
    null;

  const pickupPoint =
    result?.pickup_to_dropoff?.geometry ||
    null;

  const routePoints = [];

  if (currentPoint?.coordinates) {
    currentPoint.coordinates.forEach(
      ([longitude, latitude]) => {
        routePoints.push([
          latitude,
          longitude,
        ]);
      }
    );
  }

  if (pickupPoint?.coordinates) {
    pickupPoint.coordinates.forEach(
      ([longitude, latitude]) => {
        routePoints.push([
          latitude,
          longitude,
        ]);
      }
    );
  }

  const uniqueRoutePoints =
    routePoints.filter(
      (point, index, array) => {
        if (index === 0) return true;

        const previous =
          array[index - 1];

        return (
          point[0] !== previous[0] ||
          point[1] !== previous[1]
        );
      }
    );

  return (
    <div
      style={{
        maxWidth: "1100px",
        margin: "0 auto",
        padding: "30px",
        fontFamily:
          "Arial, sans-serif",
      }}
    >
      <h1>HOS Trip Planner</h1>

      <form
        onSubmit={handleSubmit}
        style={{
          display: "grid",
          gap: "12px",
          maxWidth: "600px",
          marginBottom: "30px",
        }}
      >
        <input
          type="text"
          placeholder="Current Location"
          value={currentLocation}
          onChange={(e) =>
            setCurrentLocation(
              e.target.value
            )
          }
          style={{
            padding: "12px",
            fontSize: "16px",
          }}
        />

        <input
          type="text"
          placeholder="Pickup Location"
          value={pickupLocation}
          onChange={(e) =>
            setPickupLocation(
              e.target.value
            )
          }
          style={{
            padding: "12px",
            fontSize: "16px",
          }}
        />

        <input
          type="text"
          placeholder="Dropoff Location"
          value={dropoffLocation}
          onChange={(e) =>
            setDropoffLocation(
              e.target.value
            )
          }
          style={{
            padding: "12px",
            fontSize: "16px",
          }}
        />

        <input
          type="number"
          min="0"
          max="70"
          step="0.1"
          placeholder="Current Cycle Used"
          value={cycleUsed}
          onChange={(e) =>
            setCycleUsed(
              e.target.value
            )
          }
          style={{
            padding: "12px",
            fontSize: "16px",
          }}
        />

        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "12px",
            fontSize: "16px",
            cursor: loading
              ? "not-allowed"
              : "pointer",
          }}
        >
          {loading
            ? "Planning..."
            : "Plan Trip"}
        </button>
      </form>

      {result && (
        <div>
          <h2>Trip Result</h2>

          <div
            style={{
              display: "grid",
              gap: "8px",
              marginBottom: "25px",
            }}
          >
            <p>
              <strong>
                Current Cycle Used:
              </strong>{" "}
              {result.current_cycle_used}{" "}
              hours
            </p>

            <p>
              <strong>
                Remaining Cycle Hours:
              </strong>{" "}
              {
                result.remaining_cycle_hours
              }{" "}
              hours
            </p>

            <p>
              <strong>
                Current to Pickup:
              </strong>{" "}
              {result.current_to_pickup
                ? `${result.current_to_pickup.distance_miles} miles, ${result.current_to_pickup.driving_hours} hours`
                : "Route not found"}
            </p>

            <p>
              <strong>
                Pickup to Dropoff:
              </strong>{" "}
              {result.pickup_to_dropoff
                ? `${result.pickup_to_dropoff.distance_miles} miles, ${result.pickup_to_dropoff.driving_hours} hours`
                : "Route not found"}
            </p>

            <p>
              <strong>
                Total Distance:
              </strong>{" "}
              {
                result.total_distance_miles
              }{" "}
              miles
            </p>

            <p>
              <strong>
                Total Driving Hours:
              </strong>{" "}
              {
                result.total_driving_hours
              }{" "}
              hours
            </p>

            <p>
              <strong>
                Pickup Time:
              </strong>{" "}
              {result.pickup_hours} hour
            </p>

            <p>
              <strong>
                Dropoff Time:
              </strong>{" "}
              {result.dropoff_hours} hour
            </p>

            {result.hos_plan && (
              <>
                <p>
                  <strong>
                    Total Trip Hours:
                  </strong>{" "}
                  {
                    result.hos_plan
                      .total_trip_hours
                  }{" "}
                  hours
                </p>

                <p>
                  <strong>
                    Trip Days:
                  </strong>{" "}
                  {
                    result.hos_plan
                      .number_of_days
                  }
                </p>

                <p>
                  <strong>
                    Total Break Hours:
                  </strong>{" "}
                  {
                    result.hos_plan
                      .total_break_hours
                  }{" "}
                  hours
                </p>
              </>
            )}
          </div>

          {uniqueRoutePoints.length > 0 && (
            <div
              style={{
                marginBottom: "30px",
              }}
            >
              <h2>Route Map</h2>

              <MapContainer
                center={defaultCenter}
                zoom={7}
                style={{
                  height: "500px",
                  width: "100%",
                  borderRadius: "8px",
                }}
              >
                <TileLayer
                  attribution='&copy; OpenStreetMap contributors &copy; CARTO'
                  url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                />

                <MapUpdater
                  points={
                    uniqueRoutePoints
                  }
                />

                <Marker
                  position={
                    uniqueRoutePoints[0]
                  }
                  icon={markerIcon}
                >
                  <Popup>
                    Current Location
                  </Popup>
                </Marker>

                {uniqueRoutePoints.length >
                  1 && (
                  <Marker
                    position={
                      uniqueRoutePoints[
                        Math.floor(
                          uniqueRoutePoints.length /
                            2
                        )
                      ]
                    }
                    icon={markerIcon}
                  >
                    <Popup>
                      Pickup Location
                    </Popup>
                  </Marker>
                )}

                {uniqueRoutePoints.length >
                  1 && (
                  <Marker
                    position={
                      uniqueRoutePoints[
                        uniqueRoutePoints.length -
                          1
                      ]
                    }
                    icon={markerIcon}
                  >
                    <Popup>
                      Dropoff Location
                    </Popup>
                  </Marker>
                )}

                {uniqueRoutePoints.length >
                  1 && (
                  <Polyline
                    positions={
                      uniqueRoutePoints
                    }
                  />
                )}
              </MapContainer>
            </div>
          )}

          {result.hos_plan?.days && (
            <div>
              <h2>
                ELD Daily Logs
              </h2>

              {result.hos_plan.days.map(
                (day) => (
                  <div
                    key={day.day}
                    style={{
                      border:
                        "1px solid #ccc",
                      borderRadius: "8px",
                      padding: "15px",
                      marginBottom:
                        "20px",
                    }}
                  >
                    <h3>
                      Day {day.day}
                    </h3>

                    <ELDGraph
                      logs={day.logs}
                    />

                    <div
                      style={{
                        marginTop:
                          "15px",
                      }}
                    >
                      {day.logs.length ===
                      0 ? (
                        <p>
                          No activity
                          recorded.
                        </p>
                      ) : (
                        day.logs.map(
                          (
                            log,
                            index
                          ) => (
                            <div
                              key={`${day.day}-${index}`}
                              style={{
                                display:
                                  "grid",
                                gridTemplateColumns:
                                  "90px 90px 1fr 1fr",
                                gap: "10px",
                                padding:
                                  "8px 0",
                                borderBottom:
                                  "1px solid #eee",
                              }}
                            >
                              <span>
                                {
                                  log.start_hour
                                }
                                h
                              </span>

                              <span>
                                {
                                  log.end_hour
                                }
                                h
                              </span>

                              <strong>
                                {
                                  log.status
                                }
                              </strong>

                              <span>
                                {log.location ||
                                  "-"}
                              </span>
                            </div>
                          )
                        )
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;