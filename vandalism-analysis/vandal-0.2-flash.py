# Flask API Endpoints for Vandalism Risk Analysis

from flask import Flask, jsonify, request, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta
import os
import random # For dummy estimated loss
from geopy.distance import geodesic # For risk analysis

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'tsel_rap_testing'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

# --- VandalismRiskAnalyzer Class (Integrated from vandal_risk_analysis.py) ---
class VandalismRiskAnalyzer:
    def __init__(self):
        self.risk_weights = {
            'proximity_risk': 0.30,
            'classification_risk': 0.25, 
            'equipment_value': 0.20,
            'temporal_risk': 0.15,
            'frequency_risk': 0.10
        }
        
        self.classification_risk = {
            'Bronze': 0.8,
            'Silver': 0.6, 
            'Gold': 0.3,
            'Platinum': 0.1
        }
        
        # High-value equipment scoring
        self.equipment_values = {
            'kabel power rru': 8,
            'kabel optik': 9,
            'sfp': 7,
            'battery': 6,
            'rectifier': 5
        }

    def calculate_proximity_risk(self, site_coords, theft_incidents, max_distance_km=10):
        """Calculate risk based on proximity to previous theft incidents"""
        if not theft_incidents:
            return 0
            
        min_distance = float('inf')
        incident_count_nearby = 0
        
        # Ensure coordinates are floats
        site_coords = (float(site_coords[0]), float(site_coords[1]))

        for incident in theft_incidents:
            try:
                incident_lat = float(incident['lat'])
                incident_long = float(incident['long']) # Use 'long' as per table schema
                distance = geodesic(site_coords, (incident_lat, incident_long)).kilometers
                min_distance = min(min_distance, distance)
                
                if distance <= 5:  # Within 5km
                    incident_count_nearby += 1
            except (ValueError, TypeError):
                continue # Skip if coordinates are invalid
        
        if min_distance == float('inf'):
            return 0
            
        distance_score = max(0, (max_distance_km - min_distance) / max_distance_km) * 100
        frequency_bonus = min(incident_count_nearby * 10, 30)  # Max 30 bonus points
        
        return min(100, distance_score + frequency_bonus)

    def calculate_temporal_risk(self, current_time, theft_incidents):
        """Calculate risk based on temporal patterns"""
        if not theft_incidents:
            return 50  # Default medium risk
            
        hour_counts = {}
        month_counts = {}
        
        for incident in theft_incidents:
            try:
                # event_hour is 'HH.MM.SS' or similar. Parse only hour.
                hour_str = incident['event_hour'].split('.')[0]
                hour = int(hour_str)
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
                
                # event_date is already a date object, extract month
                month = incident['event_date'].month
                month_counts[month] = month_counts.get(month, 0) + 1
            except (ValueError, AttributeError, TypeError):
                continue
        
        current_hour = current_time.hour
        current_month = current_time.month
        
        total_incidents = len(theft_incidents)
        hour_risk = (hour_counts.get(current_hour, 0) / total_incidents) * 100 if total_incidents > 0 else 50
        month_risk = (month_counts.get(current_month, 0) / total_incidents) * 100 if total_incidents > 0 else 50
        
        return (hour_risk + month_risk) / 2

    def calculate_equipment_risk(self, site_equipment):
        """Calculate risk based on equipment value and type"""
        if not site_equipment:
            return 30  # Default low-medium risk
            
        equipment_text = site_equipment.lower()
        risk_score = 0
        
        for equipment, value in self.equipment_values.items():
            if equipment in equipment_text:
                risk_score += value
                
        # Normalize to 0-100 scale, assuming max possible score is 40 (sum of highest values)
        return min(100, (risk_score / 40) * 100)

    def calculate_area_frequency_risk(self, site_location, theft_incidents, radius_km=15):
        """Calculate risk based on theft frequency in the area"""
        area_incidents = []
        site_location = (float(site_location[0]), float(site_location[1]))

        for incident in theft_incidents:
            try:
                incident_lat = float(incident['lat'])
                incident_long = float(incident['long'])
                distance = geodesic(site_location, (incident_lat, incident_long)).kilometers
                if distance <= radius_km:
                    area_incidents.append(incident)
            except (ValueError, TypeError):
                continue
        
        if not area_incidents:
            return 10  # Low risk if no incidents in area
            
        incident_dates = []
        for incident in area_incidents:
            try:
                # event_date is already a date object
                incident_dates.append(incident['event_date'])
            except (AttributeError, TypeError):
                continue
        
        if not incident_dates:
            return 10
            
        recent_date = max(incident_dates)
        one_year_ago = recent_date - timedelta(days=365)
        recent_incidents = [d for d in incident_dates if d >= one_year_ago]
        
        monthly_rate = len(recent_incidents) / 12
        return min(100, monthly_rate * 25) # Scale to 0-100, adjust multiplier as needed

    def calculate_comprehensive_risk_score(self, site_data, theft_incidents):
        """Calculate comprehensive risk score for a site"""
        try:
            site_coords = (float(site_data['lat']), float(site_data['long']))
        except (ValueError, TypeError):
            return {
                'total_risk_score': 0,
                'risk_level': 'MINIMAL',
                'components': {
                    'proximity_risk': 0, 'classification_risk': 0, 
                    'equipment_risk': 0, 'temporal_risk': 0, 'frequency_risk': 0
                }
            }
        
        # Calculate individual risk components
        proximity_risk = self.calculate_proximity_risk(site_coords, theft_incidents)
        
        classification_risk_score = self.classification_risk.get(
            site_data.get('rev_class', 'Bronze'), 0.8 # Use rev_class from vandalism_events
        ) * 100
        
        equipment_risk = self.calculate_equipment_risk(site_data.get('material_kehilangan_detail', '')) # Use material_kehilangan_detail as equipment
        
        temporal_risk = self.calculate_temporal_risk(datetime.now(), theft_incidents)
        
        frequency_risk = self.calculate_area_frequency_risk(site_coords, theft_incidents)
        
        # Calculate weighted final score
        final_score = (
            proximity_risk * self.risk_weights['proximity_risk'] +
            classification_risk_score * self.risk_weights['classification_risk'] +
            equipment_risk * self.risk_weights['equipment_value'] +
            temporal_risk * self.risk_weights['temporal_risk'] +
            frequency_risk * self.risk_weights['frequency_risk']
        )
        
        risk_details = {
            'total_risk_score': round(final_score, 2),
            'risk_level': self.get_risk_level(final_score),
            'components': {
                'proximity_risk': round(proximity_risk, 2),
                'classification_risk': round(classification_risk_score, 2),
                'equipment_risk': round(equipment_risk, 2),
                'temporal_risk': round(temporal_risk, 2),
                'frequency_risk': round(frequency_risk, 2)
            }
        }
        
        return risk_details

    def get_risk_level(self, score):
        """Convert numeric score to risk level"""
        if score >= 80:
            return 'CRITICAL'
        elif score >= 60:
            return 'HIGH'
        elif score >= 40:
            return 'MEDIUM'
        elif score >= 20:
            return 'LOW'
        else:
            return 'MINIMAL'

    def analyze_site_portfolio(self, all_sites, theft_incidents):
        """Analyze entire site portfolio for risk assessment"""
        results = []
        
        for site in all_sites:
            risk_analysis = self.calculate_comprehensive_risk_score(site, theft_incidents)
            # Recommendations are not used by the dashboard's /api/analytics/risk-assessment
            # recommendations = self.generate_preventive_recommendations(risk_analysis, site) 
            
            site_result = {
                'site_id': site['site_id'],
                'site_name': site['site_name'],
                'location': f"{site.get('kelurahan', 'N/A')}, {site.get('kecamatan', 'N/A')}",
                'risk_analysis': risk_analysis,
                # 'recommendations': recommendations, # Not sending recommendations here as per dashboard need
                'coordinates': {'lat': float(site['lat']), 'long': float(site['long'])} # Using 'long' as per table schema
            }
            
            results.append(site_result)
        
        # Sort by risk score (highest first)
        results.sort(key=lambda x: x['risk_analysis']['total_risk_score'], reverse=True)
        
        return results

# Initialize the analyzer globally (or as needed)
analyzer = VandalismRiskAnalyzer()


# --- Flask Routes ---

@app.route('/')
def dashboard():
    """Render the main dashboard HTML page"""
    return render_template('vandalism-analysis.html')

@app.route('/api/regions', methods=['GET'])
def get_regions():
    """Get all distinct regions (kabupaten) from vandalism_events"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = "SELECT DISTINCT kabupaten FROM public.vandalism_events WHERE kabupaten IS NOT NULL ORDER BY kabupaten"
        cur.execute(query)
        regions = [row['kabupaten'] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': regions
        })
        
    except Exception as e:
        print(f"Error fetching regions: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/theft-incidents', methods=['GET'])
def get_theft_incidents():
    """Get all theft incidents with optional filtering"""
    try:
        year_filter = request.args.get('year')
        region_filter = request.args.get('region') # Maps to kabupaten
        rev_class_filter = request.args.get('rev_class')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = """
        SELECT 
            site_id,
            site_name,
            CAST(lat AS FLOAT) as latitude,
            CAST(long AS FLOAT) as longitude,
            rev_class,
            kelurahan,
            kecamatan,
            kabupaten,
            event_date,
            event_hour,
            material_kehilangan_detail
        FROM public.vandalism_events 
        WHERE 1=1
        """
        
        params = []
        
        if year_filter:
            query += " AND EXTRACT(YEAR FROM event_date) = %s"
            params.append(int(year_filter))
            
        if region_filter and region_filter.lower() != 'all':
            query += " AND kabupaten ILIKE %s"
            params.append(f'%{region_filter}%') # Use ILIKE for case-insensitive contains
            
        if rev_class_filter and rev_class_filter.lower() != 'all':
            query += " AND rev_class ILIKE %s"
            params.append(f'%{rev_class_filter}%')
        
        query += " ORDER BY event_date DESC"
        
        cur.execute(query, params)
        incidents = cur.fetchall()
        
        incidents_list = []
        for incident in incidents:
            incident_dict = dict(incident)
            incident_dict['event_date'] = incident_dict['event_date'].isoformat() # Convert date to ISO string
            # Add dummy estimated loss
            incident_dict['estimated_loss'] = random.randint(5000000, 500000000) # IDR 5M to 500M
            incidents_list.append(incident_dict)
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(incidents_list),
            'data': incidents_list
        })
        
    except Exception as e:
        print(f"Error in get_theft_incidents: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Provides summary statistics for the dashboard."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Total Incidents 2024
        cur.execute("SELECT COUNT(*) FROM public.vandalism_events WHERE EXTRACT(YEAR FROM event_date) = 2024")
        incidents_2024 = cur.fetchone()['count'] or 0

        # Total Incidents 2025
        cur.execute("SELECT COUNT(*) FROM public.vandalism_events WHERE EXTRACT(YEAR FROM event_date) = 2025")
        incidents_2025 = cur.fetchone()['count'] or 0

        # Monthly Trend (for MoM comparison - simplified, actual MoM would need specific month data)
        # Fetching last two months for a simple MoM
        cur.execute("""
            SELECT
                EXTRACT(YEAR FROM event_date) as year,
                EXTRACT(MONTH FROM event_date) as month,
                COUNT(*) as count
            FROM public.vandalism_events
            WHERE event_date >= date_trunc('month', current_date) - interval '2 month'
            GROUP BY year, month
            ORDER BY year DESC, month DESC
            LIMIT 2
        """)
        recent_months_data = cur.fetchall()
        
        mom_percentage_change = 0
        if len(recent_months_data) == 2:
            current_month_incidents = recent_months_data[0]['count']
            previous_month_incidents = recent_months_data[1]['count']
            if previous_month_incidents > 0:
                mom_percentage_change = ((current_month_incidents - previous_month_incidents) / previous_month_incidents) * 100
        elif len(recent_months_data) == 1:
            # If only one month data, assume 100% increase if there were incidents, else 0%
            mom_percentage_change = 100 if recent_months_data[0]['count'] > 0 else 0


        # YoY Change
        yoy_percentage_change = 0
        if incidents_2024 > 0:
            yoy_percentage_change = ((incidents_2025 - incidents_2024) / incidents_2024) * 100
        elif incidents_2025 > 0:
            yoy_percentage_change = 100 # If no incidents in 2024 but some in 2025


        # Revenue Class Breakdown (with dummy estimated_loss)
        cur.execute("""
            SELECT 
                rev_class,
                COUNT(*) as incidents
            FROM public.vandalism_events
            GROUP BY rev_class
            ORDER BY incidents DESC
        """)
        rev_class_breakdown_raw = cur.fetchall()
        
        rev_class_breakdown = []
        total_estimated_loss = 0
        for row in rev_class_breakdown_raw:
            # Generate dummy loss for each incident within this rev_class for summation
            dummy_incidents_loss = row['incidents'] * random.randint(5000000, 500000000) 
            rev_class_breakdown.append({
                'rev_class': row['rev_class'] or 'Unknown',
                'incidents': row['incidents'],
                'estimated_loss': dummy_incidents_loss # Dummy aggregated loss for class
            })
            total_estimated_loss += dummy_incidents_loss # Summing for overall total loss

        # Dummy high risk zones count for now, will link to actual analysis later
        high_risk_zones_count = 0 # Will be populated by /api/analytics/high-risk-zones separately

        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'yoy_analysis': {
                    'summary': {
                        'incidents_2024': incidents_2024,
                        'incidents_2025': incidents_2025,
                        'percentage_change': round(yoy_percentage_change, 2)
                    }
                },
                'mom_analysis': { # Using same structure as YoY for dashboard consistency
                    'summary': {
                        'percentage_change': round(mom_percentage_change, 2)
                    }
                },
                'total_estimated_loss': total_estimated_loss, # Passed directly for the stat card
                'high_risk_zones_count': high_risk_zones_count, # This will be set by JS after /api/analytics/high-risk-zones
                'rev_class_breakdown': rev_class_breakdown
            }
        })

    except Exception as e:
        print(f"Error in get_analytics_summary: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analytics/monthly-trend', methods=['GET'])
def get_monthly_trend():
    """Get monthly incident trends."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT
                EXTRACT(YEAR FROM event_date) as year,
                EXTRACT(MONTH FROM event_date) as month_num,
                TO_CHAR(event_date, 'Mon') as month_name,
                COUNT(*) as incidents
            FROM public.vandalism_events
            GROUP BY year, month_num, month_name
            ORDER BY year ASC, month_num ASC
        """
        cur.execute(query)
        monthly_data = cur.fetchall()
        
        # Sort data by year and month number to ensure correct order
        sorted_monthly_data = sorted(monthly_data, key=lambda x: (x['year'], x['month_num']))

        cur.close()
        conn.close()

        # Format for Chart.js
        formatted_data = [
            {'month_name': f"{item['month_name']} {int(item['year']) % 100}", 'incidents': item['incidents']}
            for item in sorted_monthly_data
        ]

        return jsonify({
            'success': True,
            'data': formatted_data
        })

    except Exception as e:
        print(f"Error in get_monthly_trend: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analytics/high-risk-zones', methods=['GET'])
def get_high_risk_zones():
    """Identify and return high-risk geographical zones based on incident density."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Fetch all incidents and sites to pass to the analyzer
        cur.execute("""
            SELECT site_id, site_name, CAST(lat AS FLOAT) as lat, CAST(long AS FLOAT) as long,
                   rev_class, kelurahan, kecamatan, kabupaten, material_kehilangan_detail as detail,
                   event_date, event_hour, material_kehilangan_detail
            FROM public.vandalism_events
            ORDER BY event_date DESC
        """)
        all_incidents = cur.fetchall()

        # Use the incidents themselves as 'sites' for simplicity in this context
        # For a more robust system, 'all_sites' table would be separate
        cur.execute("""
            SELECT DISTINCT site_id, site_name, CAST(lat AS FLOAT) as lat, CAST(long AS FLOAT) as long,
                   rev_class, kelurahan, kecamatan, kabupaten, material_kehilangan_detail as detail
            FROM public.vandalism_events
        """)
        all_sites_for_risk = cur.fetchall()
        
        cur.close()
        conn.close()

        # Convert RealDictRow to dict for compatibility with VandalismRiskAnalyzer
        incidents_for_analyzer = [dict(row) for row in all_incidents]
        sites_for_analyzer = [dict(row) for row in all_sites_for_risk]

        # Analyze site portfolio to get risk scores
        analysis_results = analyzer.analyze_site_portfolio(sites_for_analyzer, incidents_for_analyzer)

        high_risk_zones = []
        total_high_risk_zones = 0
        
        # Define a threshold for 'High' risk level from analyzer
        HIGH_RISK_THRESHOLD_SCORE = 60 # As per VandalismRiskAnalyzer's get_risk_level
        
        # Group sites by risk level and identify clusters
        for site in analysis_results:
            if site['risk_analysis']['total_risk_score'] >= HIGH_RISK_THRESHOLD_SCORE:
                total_high_risk_zones += 1
                # For high risk zones on map, create a simplified representation
                # This logic can be expanded for true clustering
                high_risk_zones.append({
                    'site_id': site['site_id'], # Keep site_id for identification
                    'center_latitude': site['coordinates']['lat'],
                    'center_longitude': site['coordinates']['long'],
                    'radius': random.uniform(1.0, 5.0), # Dummy radius in km
                    'risk_level': site['risk_analysis']['risk_level'],
                    'incident_count': random.randint(3, 10) # Dummy incident count for display
                })

        return jsonify({
            'success': True,
            'total_zones': total_high_risk_zones,
            'data': high_risk_zones
        })

    except Exception as e:
        print(f"Error in get_high_risk_zones: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analytics/risk-assessment', methods=['GET'])
def get_risk_assessment():
    """Provides a list of sites with their predictive risk assessment."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Fetch all sites and incidents required by the analyzer
        cur.execute("""
            SELECT site_id, site_name, CAST(lat AS FLOAT) as lat, CAST(long AS FLOAT) as long,
                   rev_class, kelurahan, kecamatan, kabupaten, material_kehilangan_detail as detail
            FROM public.vandalism_events
        """)
        all_sites_for_risk = cur.fetchall()

        cur.execute("""
            SELECT site_id, site_name, CAST(lat AS FLOAT) as lat, CAST(long AS FLOAT) as long,
                   event_date, event_hour, material_kehilangan_detail, rev_class
            FROM public.vandalism_events
            ORDER BY event_date DESC
        """)
        all_incidents = cur.fetchall()
        
        cur.close()
        conn.close()

        # Convert RealDictRow to dict for compatibility
        sites_for_analyzer = [dict(row) for row in all_sites_for_risk]
        incidents_for_analyzer = [dict(row) for row in all_incidents]

        # Analyze portfolio
        analysis_results = analyzer.analyze_site_portfolio(sites_for_analyzer, incidents_for_analyzer)

        # Format results for the dashboard table
        formatted_results = []
        for site in analysis_results:
            formatted_results.append({
                'site_name': site['site_name'],
                'kabupaten': site['location'].split(', ')[1] if ', ' in site['location'] else site['location'], # Extract kabupaten from 'location'
                'risk_score': site['risk_analysis']['total_risk_score'],
                'risk_level': site['risk_analysis']['risk_level'],
                'rev_class': next((s['rev_class'] for s in sites_for_analyzer if s['site_id'] == site['site_id']), 'Unknown') # Get rev_class from original site data
            })
        
        # Sort by risk score (highest first) as expected by dashboard
        formatted_results.sort(key=lambda x: x['risk_score'], reverse=True)

        return jsonify({
            'success': True,
            'data': formatted_results
        })

    except Exception as e:
        print(f"Error in get_risk_assessment: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # This assumes `vandalism-analysis.html` is in a 'templates' directory
    # For local testing, ensure 'vandalism-analysis.html' is in a folder named 'templates'
    # relative to where app.py is run.
    app.run(debug=True, host='0.0.0.0', port=5001)
