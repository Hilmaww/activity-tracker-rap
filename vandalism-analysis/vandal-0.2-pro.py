# Flask API Endpoints for Vandalism Risk Analysis
# This script provides the backend API to power the vandalism analytics dashboard.

from flask import Flask, jsonify, request, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from collections import defaultdict
from geopy.distance import geodesic
import calendar


app = Flask(__name__)

# --- Database Configuration ---
# It's recommended to use environment variables for database credentials in production.
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'tsel_rap_testing'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None

# --- Helper Functions ---
def clean_coordinates(lat_str, lon_str):
    """
    Cleans and converts comma-decimal coordinate strings to floats.
    Handles potential errors during conversion.
    """
    try:
        # Replace comma with period and convert to float
        lat = float(lat_str.replace(',', '.'))
        lon = float(lon_str.replace(',', '.'))
        return lat, lon
    except (ValueError, AttributeError):
        # Return None if conversion fails or input is not a string
        return None, None

def find_high_risk_zones(incidents, radius_km=5, min_incidents=3):
    """
    Identifies high-risk zones based on incident density.
    A zone is 'high-risk' if it has at least `min_incidents` within `radius_km`.
    
    Returns:
        A list of dictionaries, where each dictionary represents a high-risk zone
        with its center coordinates, incident count, and a list of site IDs.
    """
    risk_zones = []
    processed_incident_ids = set()

    # Create a list of incidents with valid coordinates
    valid_incidents = []
    for inc in incidents:
        lat, lon = clean_coordinates(inc.get('lat'), inc.get('long'))
        if lat is not None and lon is not None:
            inc['latitude'] = lat
            inc['longitude'] = lon
            valid_incidents.append(inc)

    for i, incident1 in enumerate(valid_incidents):
        if incident1['id'] in processed_incident_ids:
            continue

        # Find all incidents within the radius to form a cluster
        cluster = [incident1]
        for j, incident2 in enumerate(valid_incidents):
            if i == j:
                continue # Skip self-comparison
            
            p1 = (incident1['latitude'], incident1['longitude'])
            p2 = (incident2['latitude'], incident2['longitude'])
            distance = geodesic(p1, p2).kilometers

            if distance <= radius_km:
                cluster.append(incident2)
        
        # If the cluster meets the high-risk criteria, process it
        if len(cluster) >= min_incidents:
            # Add all incidents in this cluster to the processed set
            cluster_incident_ids = {inc['id'] for inc in cluster}
            processed_incident_ids.update(cluster_incident_ids)
            
            # Calculate the centroid of the cluster
            center_lat = sum(inc['latitude'] for inc in cluster) / len(cluster)
            center_lon = sum(inc['longitude'] for inc in cluster) / len(cluster)

            risk_zones.append({
                "center_latitude": center_lat,
                "center_longitude": center_lon,
                "incident_count": len(cluster),
                "risk_level": "High",
                "radius": radius_km,
                "site_ids": [inc['site_id'] for inc in cluster]
            })
            
    return risk_zones

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves a simple welcome message for the API root."""
    return jsonify({"message": "Welcome to the Vandalism Analytics API. Use the /api endpoints to fetch data."})

@app.route('/dashboard')
def dashboard():
    """Alternative route for dashboard"""
    return render_template('vandalism-analysis.html')

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """
    Provides key metrics for the dashboard's summary cards.
    - Number of incidents in 2024 and 2025.
    - Count of identified high-risk zones.
    - Dummy data for estimated financial loss.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database connection failed"}), 500
        
    try:
        cur = conn.cursor()
        
        # Get incident counts for 2024 and 2025
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE EXTRACT(YEAR FROM event_date) = 2024) as incidents_2024,
                COUNT(*) FILTER (WHERE EXTRACT(YEAR FROM event_date) = 2025) as incidents_2025
            FROM vandalism_events;
        """)
        counts = cur.fetchone()

        # Get all incidents to calculate high-risk zones
        cur.execute("SELECT id, site_id, lat, long FROM vandalism_events;")
        all_incidents = cur.fetchall()
        high_risk_zones = find_high_risk_zones(all_incidents)
        
        cur.close()

        return jsonify({
            "success": True,
            "data": {
                "incidents_2024": counts['incidents_2024'],
                "incidents_2025": counts['incidents_2025'],
                "high_risk_zones_count": len(high_risk_zones),
                "estimated_loss": 550000000 # Dummy value as requested
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/incidents', methods=['GET'])
def get_incidents():
    """
    Fetches all incidents for the map, with optional filtering by year.
    Returns detailed information for each incident.
    """
    year_filter = request.args.get('year')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    try:
        cur = conn.cursor()
        
        query = "SELECT site_id, site_name, long, lat, rev_class, kelurahan, kecamatan, kabupaten, event_date, material_kehilangan_detail FROM vandalism_events"
        params = []
        
        if year_filter:
            query += " WHERE EXTRACT(YEAR FROM event_date) = %s"
            params.append(year_filter)

        query += " ORDER BY event_date DESC;"
        
        cur.execute(query, params)
        incidents = cur.fetchall()
        cur.close()

        # Clean coordinates for each incident
        for incident in incidents:
            lat, lon = clean_coordinates(incident.get('lat'), incident.get('long'))
            incident['latitude'] = lat
            incident['longitude'] = lon

        return jsonify({"success": True, "data": incidents})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/high-risk-zones', methods=['GET'])
def get_high_risk_zones():
    """
    Fetches all incidents and identifies high-risk zones to be displayed on the map and list.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database connection failed"}), 500
        
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, site_id, lat, long, site_name FROM vandalism_events;")
        all_incidents = cur.fetchall()
        cur.close()
        
        high_risk_zones = find_high_risk_zones(all_incidents)
        
        return jsonify({
            "success": True,
            "total_zones": len(high_risk_zones),
            "data": high_risk_zones
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()
            
@app.route('/api/monthly-trend', methods=['GET'])
def get_monthly_trend():
    """
    Provides data for the monthly trend analysis chart.
    Groups incident counts by month for a given year or all years.
    """
    year_filter = request.args.get('year')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    try:
        cur = conn.cursor()
        
        query = """
            SELECT 
                EXTRACT(MONTH FROM event_date) as month,
                COUNT(*) as incidents
            FROM vandalism_events
        """
        params = []
        if year_filter:
            query += " WHERE EXTRACT(YEAR FROM event_date) = %s"
            params.append(year_filter)
        
        query += " GROUP BY month ORDER BY month;"
        
        cur.execute(query, params)
        monthly_data = cur.fetchall()
        cur.close()

        # Format data with month names for charting
        results = []
        data_map = {item['month']: item['incidents'] for item in monthly_data}
        for month_num in range(1, 13):
            results.append({
                "month_numeric": month_num,
                "month_name": calendar.month_abbr[month_num],
                "incidents": data_map.get(float(month_num), 0)
            })

        return jsonify({"success": True, "data": results})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/revenue-impact', methods=['GET'])
def get_revenue_impact():
    """
    Provides data for the revenue class impact chart.
    Groups incident counts by the 'rev_class' field.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database connection failed"}), 500
        
    try:
        cur = conn.cursor()
        
        # Group by revenue class and count incidents, handling NULL or empty strings
        query = """
            SELECT 
                COALESCE(NULLIF(TRIM(rev_class), ''), 'Unknown') as rev_class, 
                COUNT(*) as incidents
            FROM vandalism_events
            GROUP BY rev_class
            ORDER BY incidents DESC;
        """
        
        cur.execute(query)
        impact_data = cur.fetchall()
        cur.close()
        
        # Add dummy estimated loss per class
        for item in impact_data:
            item['estimated_loss'] = item['incidents'] * 15000000 # Dummy calculation

        return jsonify({"success": True, "data": impact_data})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- Main Execution ---
if __name__ == '__main__':
    # The host '0.0.0.0' makes the server accessible from any IP address.
    # The default port is 5001 to avoid conflicts with other services.
    app.run(debug=True, host='0.0.0.0', port=5001)
