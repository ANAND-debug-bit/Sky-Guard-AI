"""
SkyGuard AI - Indian AWS Station Metadata
Defines geographic coordinates, elevation (meters), and climate zone classifications.
"""

STATIONS = [
    # Northern Plains
    {"station_id": "DEL001", "name": "New Delhi (Safdarjung)", "lat": 28.584, "lon": 77.206, "elevation_m": 216.0, "climate_zone": "Plains"},
    {"station_id": "DEL002", "name": "Delhi (Palam)", "lat": 28.567, "lon": 77.100, "elevation_m": 237.0, "climate_zone": "Plains"},
    {"station_id": "LKO001", "name": "Lucknow (Amausi)", "lat": 26.760, "lon": 80.880, "elevation_m": 128.0, "climate_zone": "Plains"},
    {"station_id": "JAI001", "name": "Jaipur (Sanganer)", "lat": 26.820, "lon": 75.800, "elevation_m": 390.0, "climate_zone": "Semi-Arid"},
    
    # Coastal (Western & Eastern)
    {"station_id": "BOM001", "name": "Mumbai (Santacruz)", "lat": 19.117, "lon": 72.850, "elevation_m": 14.0, "climate_zone": "Coastal"},
    {"station_id": "BOM002", "name": "Mumbai (Colaba)", "lat": 18.900, "lon": 72.817, "elevation_m": 11.0, "climate_zone": "Coastal"},
    {"station_id": "MAA001", "name": "Chennai (Meenambakkam)", "lat": 13.000, "lon": 80.180, "elevation_m": 16.0, "climate_zone": "Coastal"},
    {"station_id": "CCU001", "name": "Kolkata (Dum Dum)", "lat": 22.650, "lon": 88.450, "elevation_m": 6.0, "climate_zone": "Coastal"},
    {"station_id": "COK001", "name": "Kochi (Willingdon)", "lat": 9.933, "lon": 76.267, "elevation_m": 3.0, "climate_zone": "Tropical Coastal"},

    # High Altitude / Mountainous
    {"station_id": "SHI001", "name": "Shimla", "lat": 31.104, "lon": 77.173, "elevation_m": 2205.0, "climate_zone": "Mountain"},
    {"station_id": "SXR001", "name": "Srinagar", "lat": 34.083, "lon": 74.797, "elevation_m": 1587.0, "climate_zone": "Mountain"},
    
    # Central & Deccan Plateau
    {"station_id": "NAG001", "name": "Nagpur (Sonegaon)", "lat": 21.092, "lon": 79.051, "elevation_m": 310.0, "climate_zone": "Tropical Savanna"},
    {"station_id": "BLR001", "name": "Bengaluru (HAL)", "lat": 12.950, "lon": 77.668, "elevation_m": 920.0, "climate_zone": "Plateau"},
    {"station_id": "HYD001", "name": "Hyderabad (Begumpet)", "lat": 17.450, "lon": 78.470, "elevation_m": 531.0, "climate_zone": "Deccan"},

    # North-East
    {"station_id": "GAU001", "name": "Guwahati (Borjhar)", "lat": 26.106, "lon": 91.585, "elevation_m": 54.0, "climate_zone": "Subtropical Humid"}
]