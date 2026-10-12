import os
import pickle
from datetime import date, datetime, time
from urllib.parse import quote

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium


# PAGE CONFIGURATION
st.set_page_config(
    page_title="TrafficAI | Route Intelligence",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# API KEY
def get_api_key():
    try:
        return st.secrets["TOMTOM_API_KEY"]
    except Exception:
        return os.getenv("TOMTOM_API_KEY", "")


# TOMTOM API HELPER
def get_json(url, params):
    response = requests.get(url, params=params, timeout=25)

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        detail = (
            data.get("errorText")
            or data.get("message")
            or "Check API access and request parameters."
        )
        raise RuntimeError(f"API error {response.status_code}: {detail}")

    return data


# LOCATION SEARCH
def search_locations(query, api_key):
    url = (
        "https://api.tomtom.com/search/2/search/"
        + quote(query, safe="")
        + ".json"
    )

    data = get_json(
        url,
        {
            "key": api_key,
            "countrySet": "IN",
            "limit": 5,
        },
    )

    candidates = []

    for result in data.get("results", []):
        position = result.get("position", {})
        address = result.get("address", {})
        poi = result.get("poi", {})

        if "lat" not in position or "lon" not in position:
            continue

        candidates.append(
            {
                "name": (
                    poi.get("name")
                    or address.get("freeformAddress")
                    or query
                ),
                "address": address.get("freeformAddress", query),
                "lat": float(position["lat"]),
                "lon": float(position["lon"]),
            }
        )

    if not candidates:
        raise ValueError(
            f"No location found for '{query}'. "
            "Try adding the area and city."
        )

    return candidates


# ROUTE CALCULATION
def calculate_route(
    origin,
    destination,
    departure,
    travel_mode="car",
):
    locations = (
        f"{origin['lat']},{origin['lon']}:"
        f"{destination['lat']},{destination['lon']}"
    )

    url = (
        "https://api.tomtom.com/routing/1/"
        f"calculateRoute/{locations}/json"
    )

    data = get_json(
        url,
        {
            "key": get_api_key(),
            "traffic": "true",
            "routeType": "fastest",
            "travelMode": travel_mode,
            "departAt": departure,
            "computeTravelTimeFor": "all",
            "sectionType": "travelMode",
        },
    )

    routes = data.get("routes", [])

    if not routes:
        raise ValueError(
            f"No {travel_mode} route was returned. "
            "Try another transport mode or location."
        )

    return routes[0]


# CHECK WHICH MODE TOMTOM ACTUALLY REPORTED
def get_effective_route_modes(route):
    modes = set()

    for section in route.get("sections", []):
        if str(section.get("sectionType", "")).upper() == "TRAVEL_MODE":
            mode = section.get("travelMode")

            if mode:
                modes.add(str(mode).lower())

    return sorted(modes)


# DISPLAY HELPERS
def format_duration(seconds):
    if seconds is None:
        return "Unavailable"

    minutes = max(0, round(seconds / 60))
    hours, remainder = divmod(minutes, 60)

    if hours:
        return f"{hours} hr {remainder} min"

    return f"{remainder} min"


def traffic_status(delay, free_flow_time):
    if delay is None:
        return "Unavailable", "⚪"

    ratio = (
        max(0, delay) / free_flow_time
        if free_flow_time and free_flow_time > 0
        else 0
    )

    # Project-defined display bands, not official classifications.
    if delay >= 600 or ratio >= 0.20:
        return "HIGH", "🔴"

    if delay >= 180 or ratio >= 0.08:
        return "MEDIUM", "🟠"

    return "LOW", "🟢"


def show_hero(title, subtitle):
    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">TRAFFIC INTELLIGENCE PLATFORM</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ROUTE MAP
def show_route_map(
    origin,
    destination,
    route,
    map_key,
    transport_label,
    travel_mode,
):
    points = []

    for leg in route.get("legs", []):
        for point in leg.get("points", []):
            if "latitude" in point and "longitude" in point:
                points.append(
                    [
                        float(point["latitude"]),
                        float(point["longitude"]),
                    ]
                )

    center = [
        (origin["lat"] + destination["lat"]) / 2,
        (origin["lon"] + destination["lon"]) / 2,
    ]

    route_map = folium.Map(
        location=center,
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    folium.Marker(
        [origin["lat"], origin["lon"]],
        tooltip="Starting location",
        popup=origin["address"],
        icon=folium.Icon(
            color="green",
            icon="play",
            prefix="fa",
        ),
    ).add_to(route_map)

    folium.Marker(
        [destination["lat"], destination["lon"]],
        tooltip="Destination",
        popup=destination["address"],
        icon=folium.Icon(
            color="red",
            icon="flag",
            prefix="fa",
        ),
    ).add_to(route_map)

    if points:
        colors = {
            "car": "#0D9488",
            "motorcycle": "#F59E0B",
            "bus": "#2563EB",
        }

        folium.PolyLine(
            points,
            color=colors.get(travel_mode, "#0D9488"),
            weight=6,
            opacity=0.9,
            tooltip=f"Calculated {transport_label} road route",
        ).add_to(route_map)

        route_map.fit_bounds(points)

    else:
        route_map.fit_bounds(
            [
                [origin["lat"], origin["lon"]],
                [destination["lat"], destination["lon"]],
            ]
        )

    st_folium(
        route_map,
        height=430,
        use_container_width=True,
        returned_objects=[],
        key=map_key,
    )

    if not points:
        st.warning(
            "The API did not return route geometry. "
            "The map displays the endpoints only."
        )


# HISTORICAL DATA HELPERS
@st.cache_data
def load_historical_data():
    path = "data/Metro_Interstate_Traffic_Volume.csv.gz"

    if not os.path.exists(path):
        return None

    df = pd.read_csv(path, compression="gzip")
    df["date_time"] = pd.to_datetime(
        df["date_time"],
        errors="coerce",
    )
    df["traffic_volume"] = pd.to_numeric(
        df["traffic_volume"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["date_time", "traffic_volume"]
    ).copy()

    df["hour"] = df["date_time"].dt.hour
    df["day_of_week"] = df["date_time"].dt.dayofweek
    df["month"] = df["date_time"].dt.month

    return df


@st.cache_resource
def load_ml_model():
    with open("model/traffic_model.pkl", "rb") as file:
        return pickle.load(file)


# PROFESSIONAL DESIGN
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1450px;
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }

    [data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid #334155;
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #F8FAFC;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label {
        color: #CBD5E1;
    }

    .hero {
        background: linear-gradient(120deg, #102A43, #087E8B);
        padding: 30px;
        border-radius: 20px;
        color: white;
        margin-bottom: 24px;
    }

    .hero h1 {
        color: white;
        font-size: 36px;
        margin: 8px 0;
    }

    .hero p {
        color: #E0F2FE;
        font-size: 16px;
        margin-bottom: 0;
    }

    .eyebrow {
        color: #99F6E4;
        font-size: 12px;
        letter-spacing: 2px;
        font-weight: 700;
    }

    div[data-testid="stMetric"] {
        background-color: #172033;
        border: 1px solid #334155;
        padding: 18px;
        border-radius: 14px;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] p,
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {
        color: #FFFFFF;
    }

    div.stButton > button {
        border-radius: 10px;
        min-height: 45px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# INITIAL SESSION STATE
st.session_state.setdefault("route_history", [])
st.session_state.setdefault("route_result", None)


# SIDEBAR
with st.sidebar:
    st.markdown("## 🚦 TrafficAI")
    st.caption("ROUTE INTELLIGENCE")
    st.divider()

    page = st.radio(
        "WORKSPACE",
        [
            "Dashboard",
            "Route Planner",
            "Recent Routes",
            "Historical ML Demo",
            "About Project",
        ],
    )

    st.divider()
    st.caption("ROUTING SERVICE")
    st.write("TomTom Routing API")
    st.caption("MAP")
    st.write("OpenStreetMap")
    st.divider()
    st.caption("AI / Software Mini Project")


api_key = get_api_key()


# DASHBOARD
if page == "Dashboard":
    show_hero(
        "TrafficAI Dashboard",
        "Plan journeys and review route traffic estimates.",
    )

    st.info(
        "Enter a start location and destination in Route Planner "
        "to calculate a route for your selected transport mode."
    )

    history = st.session_state.route_history
    a, b, c = st.columns(3)

    a.metric("Route Checks", len(history))

    if history:
        latest = history[-1]

        b.metric(
            "Latest Route Distance",
            f"{latest['Distance (km)']:.1f} km",
        )
        c.metric(
            "Latest Travel Time",
            latest["Travel Time"],
        )

        st.divider()
        st.subheader("Latest Journey")
        st.write(f"**From:** {latest['Origin']}")
        st.write(f"**To:** {latest['Destination']}")
        st.write(f"**Transport:** {latest.get('Transport', 'Car')}")
        st.caption("Use Route Planner to calculate another journey.")

    else:
        b.metric("Routes Calculated", 0)
        c.metric("Traffic Status", "Not checked")
        st.subheader("Get Started")

        st.write(
            "1. Open Route Planner.\n"
            "2. Enter the starting point and destination.\n"
            "3. Select the correct search result for each place.\n"
            "4. Choose transport and departure time, then calculate the route."
        )

    st.caption(
        "Route results depend on the routing provider's data "
        "and the route selected."
    )


# ROUTE PLANNER
elif page == "Route Planner":
    show_hero(
        "Plan Your Journey",
        "Find locations and compare road-route estimates for car, bike, and bus.",
    )

    st.info(
        "TomTom calculates the selected road route. Bike uses motorcycle "
        "routing. Bus means a bus-vehicle road route, not public bus numbers, "
        "stops, or schedules. Availability depends on TomTom coverage."
    )

    if not api_key:
        st.error(
            "TomTom API key is missing. Check .streamlit/secrets.toml."
        )

    st.subheader("📍 Journey Details")

    with st.form("location_search_form"):
        col1, col2 = st.columns(2)

        with col1:
            origin_query = st.text_input(
                "Starting location",
                placeholder="e.g. Perambur, Chennai",
            )

        with col2:
            destination_query = st.text_input(
                "Destination",
                placeholder="e.g. V R Chennai Shopping Mall",
            )

        search_clicked = st.form_submit_button(
            "🔎 Search Locations",
            type="primary",
            use_container_width=True,
        )

    if search_clicked:
        for key in (
            "origin_candidates",
            "destination_candidates",
            "origin_choice",
            "destination_choice",
        ):
            st.session_state.pop(key, None)

        st.session_state.route_result = None

        if not origin_query.strip() or not destination_query.strip():
            st.error("Enter both a starting location and a destination.")

        elif not api_key:
            st.error(
                "API key is missing. Configure TomTom before searching."
            )

        else:
            try:
                with st.spinner("Searching locations..."):
                    origin_results = search_locations(
                        origin_query.strip(),
                        api_key,
                    )
                    destination_results = search_locations(
                        destination_query.strip(),
                        api_key,
                    )

                st.session_state.origin_candidates = origin_results
                st.session_state.destination_candidates = destination_results

                st.success(
                    "Locations found. Choose the correct place "
                    "for each result below."
                )

            except (
                requests.RequestException,
                RuntimeError,
                ValueError,
            ) as error:
                st.error(f"Location search failed: {error}")

    origin_results = st.session_state.get("origin_candidates")
    destination_results = st.session_state.get("destination_candidates")

    if origin_results and destination_results:
        st.divider()
        st.subheader("✅ Confirm Exact Locations")

        with st.form("route_calculation_form"):
            left, right = st.columns(2)

            with left:
                origin_choice = st.selectbox(
                    "Choose starting place",
                    options=list(range(len(origin_results))),
                    index=None,
                    placeholder="Select the correct starting place",
                    format_func=lambda i: (
                        f"{origin_results[i]['name']} — "
                        f"{origin_results[i]['address']}"
                    ),
                    key="origin_choice",
                )

            with right:
                destination_choice = st.selectbox(
                    "Choose destination place",
                    options=list(range(len(destination_results))),
                    index=None,
                    placeholder="Select the correct destination",
                    format_func=lambda i: (
                        f"{destination_results[i]['name']} — "
                        f"{destination_results[i]['address']}"
                    ),
                    key="destination_choice",
                )

            st.subheader("🚗 Choose Transport")

            transport_choice = st.radio(
                "How are you travelling?",
                ["🚗 Car", "🏍️ Bike", "🚌 Bus"],
                horizontal=True,
                key="transport_mode_choice",
            )

            transport_config = {
                "🚗 Car": {"mode": "car", "label": "Car"},
                "🏍️ Bike": {
                    "mode": "motorcycle",
                    "label": "Bike",
                },
                "🚌 Bus": {"mode": "bus", "label": "Bus"},
            }

            st.subheader("🕒 Departure")

            departure_mode = st.radio(
                "When do you want to leave?",
                ["Leave now", "Schedule for later"],
                horizontal=True,
            )

            if departure_mode == "Schedule for later":
                travel_date = st.date_input(
                    "Departure date",
                    value=date.today(),
                    min_value=date.today(),
                )

                departure_time = st.time_input(
                    "Departure time",
                    value=time(18, 0),
                    step=900,
                )

            calculate_clicked = st.form_submit_button(
                "🚦 Calculate Route",
                type="primary",
                use_container_width=True,
            )

        if calculate_clicked:
            if origin_choice is None or destination_choice is None:
                st.error(
                    "Select one starting place and one destination."
                )

            else:
                origin = origin_results[origin_choice]
                destination = destination_results[destination_choice]

                if (
                    origin["lat"] == destination["lat"]
                    and origin["lon"] == destination["lon"]
                ):
                    st.error(
                        "Starting point and destination are the same. "
                        "Please choose two different places."
                    )

                else:
                    if departure_mode == "Leave now":
                        departure = "now"
                        departure_label = "Leave now"

                    else:
                        planned = datetime.combine(
                            travel_date,
                            departure_time,
                        )

                        if planned <= datetime.now():
                            st.error(
                                "The selected departure time has passed. "
                                "Choose a future date/time, or select Leave now."
                            )
                            departure = None
                            departure_label = None

                        else:
                            departure = planned.isoformat(
                                timespec="seconds"
                            )
                            departure_label = planned.strftime(
                                "%d %b %Y, %I:%M %p"
                            )

                    if departure:
                        st.session_state.route_result = None

                        selected = transport_config[transport_choice]
                        travel_mode = selected["mode"]
                        transport_label = selected["label"]

                        try:
                            with st.spinner(
                                f"Calculating {transport_label.lower()} "
                                "route and travel estimates..."
                            ):
                                route = calculate_route(
                                    origin,
                                    destination,
                                    departure,
                                    travel_mode,
                                )

                            st.session_state.route_result = {
                                "origin": origin,
                                "destination": destination,
                                "route": route,
                                "departure_label": departure_label,
                                "transport_label": transport_label,
                                "travel_mode": travel_mode,
                            }

                            summary = route.get("summary", {})
                            delay = summary.get("trafficDelayInSeconds")
                            distance_km = (
                                summary.get("lengthInMeters", 0) / 1000
                            )
                            travel_seconds = summary.get(
                                "travelTimeInSeconds"
                            )

                            st.session_state.route_history.append(
                                {
                                    "Origin": origin["address"],
                                    "Destination": destination["address"],
                                    "Transport": transport_label,
                                    "Distance (km)": round(distance_km, 2),
                                    "Travel Time": format_duration(
                                        travel_seconds
                                    ),
                                    "Departure": departure_label,
                                    "Reported Delay": (
                                        format_duration(delay)
                                        if delay is not None
                                        else "Unavailable"
                                    ),
                                }
                            )

                            st.success("Route calculated successfully.")

                        except (
                            requests.RequestException,
                            RuntimeError,
                            ValueError,
                        ) as error:
                            st.error(
                                f"Route calculation failed: {error}"
                            )

    # DISPLAY ROUTE RESULTS
    result = st.session_state.get("route_result")

    if result:
        st.divider()
        st.subheader(
            f"📊 {result['transport_label']} Route Results"
        )

        origin = result["origin"]
        destination = result["destination"]
        route = result["route"]
        summary = route.get("summary", {})

        effective_modes = get_effective_route_modes(route)
        requested_mode = result["travel_mode"]

        readable_modes = {
            "car": "Car",
            "motorcycle": "Motorcycle/Bike",
            "bus": "Bus vehicle",
            "other": "Other / unsupported section",
        }

        if not effective_modes:
            st.warning(
                "TomTom did not return travel-mode confirmation for this "
                "route. Treat these values as provider estimates, not a "
                "verified mode-specific comparison."
            )

        elif (
            "other" in effective_modes
            or requested_mode not in effective_modes
        ):
            reported = ", ".join(
                readable_modes.get(mode, mode)
                for mode in effective_modes
            )
            st.warning(
                f"TomTom could not confirm {result['transport_label']} "
                f"routing for every section. Reported modes: {reported}. "
                "Distance and time may not be fully specific to the selected mode."
            )

        else:
            reported = ", ".join(
                readable_modes.get(mode, mode)
                for mode in effective_modes
            )
            st.caption(
                f"Route mode reported by TomTom: {reported}."
            )

        distance_km = summary.get("lengthInMeters", 0) / 1000
        travel_seconds = summary.get("travelTimeInSeconds")
        delay = summary.get("trafficDelayInSeconds")
        free_flow = summary.get("noTrafficTravelTimeInSeconds")
        historic_time = summary.get(
            "historicTrafficTravelTimeInSeconds"
        )
        live_time = summary.get(
            "liveTrafficIncidentsTravelTimeInSeconds"
        )

        level, icon = traffic_status(delay, free_flow)

        a, b, c, d = st.columns(4)

        a.metric("Route Distance", f"{distance_km:.1f} km")
        b.metric(
            "Estimated Travel Time",
            format_duration(travel_seconds),
        )
        c.metric(
            "Reported Delay",
            (
                format_duration(delay)
                if delay is not None
                else "Unavailable"
            ),
        )
        d.metric("Delay Classification", f"{icon} {level}")

        st.caption(f"Departure: {result['departure_label']}")
        st.write(f"**From:** {origin['address']}")
        st.write(f"**To:** {destination['address']}")

        if result["travel_mode"] == "bus":
            st.info(
                "Bus mode shows a road route calculated for a bus vehicle. "
                "It does not provide public bus numbers, stops, or schedules."
            )

        elif result["travel_mode"] == "motorcycle":
            st.caption(
                "Bike mode uses TomTom motorcycle routing. It does not "
                "model riding through traffic gaps; route and time are estimates."
            )

        with st.expander("View detailed travel-time estimates"):
            details1, details2, details3 = st.columns(3)

            details1.metric(
                "Without Traffic",
                format_duration(free_flow),
            )
            details2.metric(
                "Historical Traffic",
                format_duration(historic_time),
            )
            details3.metric(
                "Live Traffic Estimate",
                format_duration(live_time),
            )

            st.caption(
                "These values are returned by TomTom when available "
                "and can vary by route and data coverage."
            )

        if level == "HIGH":
            st.warning(
                "The API-reported delay falls in this project's "
                "high-delay band. Consider allowing extra travel time."
            )

        elif level == "MEDIUM":
            st.info(
                "The API-reported delay falls in this project's "
                "medium-delay band."
            )

        elif level == "LOW":
            st.success(
                "The API-reported delay falls in this project's "
                "low-delay band."
            )

        else:
            st.info(
                "The API did not provide enough delay information "
                "to classify the route."
            )

        st.caption(
            "LOW/MEDIUM/HIGH are project-defined display bands, "
            "not official traffic authority classifications."
        )

        st.divider()
        st.subheader("🗺️ Route Map")

        show_route_map(
            origin,
            destination,
            route,
            map_key=f"route_map_{len(st.session_state.route_history)}",
            transport_label=result["transport_label"],
            travel_mode=result["travel_mode"],
        )

        st.caption(
            "Route estimates by TomTom; map tiles by OpenStreetMap. "
            "Bus mode is not a public-transit timetable service."
        )


# RECENT ROUTES
elif page == "Recent Routes":
    show_hero(
        "Recent Route Checks",
        "Review routes calculated during this browser session.",
    )

    history = st.session_state.route_history

    if history:
        st.dataframe(
            pd.DataFrame(history[::-1]),
            use_container_width=True,
            hide_index=True,
        )

        if st.button("Clear Recent Routes"):
            st.session_state.route_history = []
            st.session_state.route_result = None
            st.rerun()

    else:
        st.info(
            "No routes calculated yet. "
            "Open Route Planner to check your first journey."
        )

    st.caption(
        "This history is stored in the current Streamlit session, "
        "not permanently in a database."
    )


# HISTORICAL ML DEMO
elif page == "Historical ML Demo":
    show_hero(
        "Historical ML Demonstration",
        "A separate Random Forest model trained on historical traffic data.",
    )

    st.warning(
        "This model uses US I-94 highway data. It does not predict "
        "Chennai-specific traffic or provide live route estimates."
    )

    try:
        df = load_historical_data()
        model = load_ml_model()

        if df is None:
            st.error("Historical dataset not found in the data folder.")

        else:
            with st.form("ml_demo_form"):
                ml_date = st.date_input(
                    "Date for historical-pattern estimate",
                    value=date.today(),
                    key="ml_date",
                )
                ml_time = st.time_input(
                    "Time for historical-pattern estimate",
                    value=time(18, 0),
                    key="ml_time",
                )
                ml_submit = st.form_submit_button(
                    "Predict Historical Traffic",
                    type="primary",
                    use_container_width=True,
                )

            if ml_submit:
                features = pd.DataFrame(
                    [
                        {
                            "hour": ml_time.hour,
                            "day_of_week": ml_date.weekday(),
                            "month": ml_date.month,
                        }
                    ]
                )

                estimate = max(
                    0,
                    float(model.predict(features)[0]),
                )

                st.metric(
                    "Estimated Historical Traffic Volume",
                    f"{estimate:,.0f} vehicles/hour",
                )

                st.caption(
                    "This is an estimate from the historical I-94 model, "
                    "not a prediction for the route planner."
                )

            st.subheader("Historical Dataset Overview")

            a, b, c = st.columns(3)

            a.metric("Historical Records", f"{len(df):,}")
            b.metric(
                "Average Volume",
                f"{df['traffic_volume'].mean():,.0f}",
            )
            c.metric(
                "Maximum Recorded Volume",
                f"{df['traffic_volume'].max():,.0f}",
            )

            with st.expander("View sample dataset rows"):
                st.dataframe(
                    df[["date_time", "traffic_volume"]].head(20),
                    use_container_width=True,
                    hide_index=True,
                )

    except Exception as error:
        st.error(
            "Historical ML demo could not load. Check that "
            "model/traffic_model.pkl has been generated locally "
            "by train_model.py."
        )
        st.caption(str(error))


# ABOUT PROJECT
elif page == "About Project":
    show_hero(
        "About TrafficAI",
        "A route-planning and traffic-analysis mini project.",
    )

    st.subheader("Problem Statement")
    st.write(
        "Travellers need an accessible way to search for locations, "
        "calculate road routes, and review travel-time and traffic estimates."
    )

    st.subheader("Main Features")
    st.write(
        "- Starting location and destination search\n"
        "- Exact-place selection to reduce location mismatches\n"
        "- Car, motorcycle, and bus road-route calculation\n"
        "- Distance and estimated travel time\n"
        "- Traffic-delay information when returned by the API\n"
        "- Interactive map and recent route checks\n"
        "- Separate historical ML demonstration"
    )

    st.subheader("Technology Stack")

    a, b, c = st.columns(3)
    a.markdown("### Python")
    a.write("Application logic and API requests")
    b.markdown("### Streamlit")
    b.write("Interactive multi-page web dashboard")
    c.markdown("### TomTom")
    c.write("Location search and traffic-aware route calculation")

    st.subheader("Important Project Limitations")

    st.write(
        "TomTom provides road-route and traffic estimates. Motorcycle and "
        "bus modes are beta functionality and may not be available for every "
        "route. Bus mode does not provide public bus numbers, stops, or "
        "schedules. Results depend on provider coverage and are estimates, "
        "not guarantees."
    )

    st.write(
        "The separate Random Forest demonstration uses historical "
        "US I-94 traffic data; it is not used to calculate Chennai route traffic."
    )

    st.markdown(
        "[TomTom Routing API documentation]"
        "(https://docs.tomtom.com/routing-api/documentation/"
        "tomtom-maps/v1/calculate-route)"
    )

    st.markdown(
        "[TomTom Search API documentation]"
        "(https://docs.tomtom.com/search-api/documentation/"
        "search-service/fuzzy-search)"
    )


# FOOTER
st.divider()
st.caption(
    "TrafficAI | Route Traffic Intelligence | "
    "Estimates depend on available provider data."
)