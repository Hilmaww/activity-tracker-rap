# Flask API Endpoints for Vandalism Risk Analysis

from flask import Flask, jsonify, request
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'telecom_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'port': os.getenv('DB_PORT', '5432')
}

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

@app.route('/api/theft-incidents', methods=['GET'])
def get_theft_incidents():
    """Get all theft incidents with optional filtering"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        site_class = request.args.get('classification')
        kabupaten = request.args.get('kabupaten')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Base query
        query = """
        SELECT 
            site_id,
            site_name,
            lat,
            lng,
            rev_class as classification,
            kelurahan,
            kecamatan,
            kabupaten,
            detail as equipment_detail,
            tower_owner,
            event_date,
            event_time,
            month,
            material_kehilangan as stolen_materials,
            detail_material_stolen,
            damage_caused,
            action_recovery
        FROM theft_incidents 
        WHERE 1=1
        """
        
        params = []
        
        # Add filters
        if start_date:
            query += " AND event_date >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND event_date <= %s" 
            params.append(end_date)
            
        if site_class:
            query += " AND rev_class = %s"
            params.append(site_class)
            
        if kabupaten:
            query += " AND kabupaten = %s"
            params.append(kabupaten)
        
        query += " ORDER BY event_date DESC"
        
        cur.execute(query, params)
        incidents = cur.fetchall()
        
        # Convert to list of dicts
        incidents_list = []
        for incident in incidents:
            incident_dict = dict(incident)
            # Convert date to string if it's a date object
            if incident_dict.get('event_date'):
                if isinstance(incident_dict['event_date'], str):
                    incident_dict['event_date'] = incident_dict['event_date']
                else:
                    incident_dict['event_date'] = incident_dict['event_date'].strftime('%d/%m/%Y')
            incidents_list.append(incident_dict)
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(incidents_list),
            'data': incidents_list
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/all-sites', methods=['GET'])
def get_all_sites():
    """Get all sites with basic information"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = """
        SELECT 
            site_id,
            site_name,
            lat,
            lng,
            rev_class as classification,
            kelurahan,
            kecamatan,
            kabupaten,
            detail as equipment_detail,
            tower_owner,
            status,
            CASE 
                WHEN site_id IN (SELECT DISTINCT site_id FROM theft_incidents) 
                THEN true 
                ELSE false 
            END as has_theft_history
        FROM all_sites 
        ORDER BY site_name
        """
        
        cur.execute(query)
        sites = cur.fetchall()
        
        sites_list = [dict(site) for site in sites]
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(sites_list),
            'data': sites_list
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/risk-analysis', methods=['GET'])
def get_risk_analysis():
    """Get comprehensive risk analysis for all sites"""
    try:
        from risk_analyzer import VandalismRiskAnalyzer, FlaskIntegrationHelper
        
        # Get sites and incidents data
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all sites
        sites_query = """
        SELECT site_id, site_name, lat, lng, rev_class as classification,
               kelurahan, kecamatan, kabupaten, detail, tower_owner, status
        FROM all_sites
        """
        cur.execute(sites_query)
        all_sites = [dict(row) for row in cur.fetchall()]
        
        # Get theft incidents
        incidents_query = """
        SELECT site_id, site_name, lat, lng, event_date, event_time,
               material_kehilangan, detail_material_stolen
        FROM theft_incidents
        ORDER BY event_date DESC
        """
        cur.execute(incidents_query)
        theft_incidents = [dict(row) for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        # Initialize analyzer
        analyzer = VandalismRiskAnalyzer()
        
        # Analyze portfolio
        analysis_results = analyzer.analyze_site_portfolio(all_sites, theft_incidents)
        
        # Format for API
        helper = FlaskIntegrationHelper()
        formatted_results = helper.format_for_api(analysis_results)
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'analysis': formatted_results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/high-risk-sites', methods=['GET'])
def get_high_risk_sites():
    """Get sites with high risk scores requiring immediate attention"""
    try:
        threshold = request.args.get('threshold', 70, type=float)
        
        # Call risk analysis
        risk_response = get_risk_analysis()
        risk_data = risk_response.get_json()
        
        if not risk_data['success']:
            return risk_data, 500
        
        from risk_analyzer import FlaskIntegrationHelper
        helper = FlaskIntegrationHelper()
        
        # Get high priority alerts
        all_results = risk_data['analysis']['sites']
        high_risk_alerts = helper.get_high_priority_alerts(all_results, threshold)
        
        return jsonify({
            'success': True,
            'threshold': threshold,
            'count': len(high_risk_alerts),
            'alerts': high_risk_alerts
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/site-risk/<site_id>', methods=['GET'])
def get_site_risk_detail(site_id):
    """Get detailed risk analysis for a specific site"""
    try:
        from risk_analyzer import VandalismRiskAnalyzer
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get specific site
        site_query = """
        SELECT site_id, site_name, lat, lng, rev_class as classification,
               kelurahan, kecamatan, kabupaten, detail, tower_owner, status
        FROM all_sites WHERE site_id = %s
        """
        cur.execute(site_query, (site_id,))
        site = cur.fetchone()
        
        if not site:
            return jsonify({
                'success': False,
                'error': 'Site not found'
            }), 404
        
        site_dict = dict(site)
        
        # Get all theft incidents for context
        incidents_query = """
        SELECT site_id, site_name, lat, lng, event_date, event_time,
               material_kehilangan, detail_material_stolen
        FROM theft_incidents
        """
        cur.execute(incidents_query)
        theft_incidents = [dict(row) for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        # Calculate risk for this specific site
        analyzer = VandalismRiskAnalyzer()
        risk_analysis = analyzer.calculate_comprehensive_risk_score(site_dict, theft_incidents)
        recommendations = analyzer.generate_preventive_recommendations(risk_analysis, site_dict)
        
        return jsonify({
            'success': True,
            'site': site_dict,
            'risk_analysis': risk_analysis,
            'recommendations': recommendations,
            'analysis_timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/area-analysis', methods=['GET'])
def get_area_analysis():
    """Get risk analysis grouped by geographical areas"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Area-based analysis query
        query = """
        WITH area_stats AS (
            SELECT 
                kabupaten,
                kecamatan,
                COUNT(*) as total_sites,
                COUNT(CASE WHEN site_id IN (SELECT site_id FROM theft_incidents) THEN 1 END) as sites_with_theft,
                AVG(lat) as center_lat,
                AVG(lng) as center_lng
            FROM all_sites
            GROUP BY kabupaten, kecamatan
        ),
        theft_stats AS (
            SELECT 
                kabupaten,
                kecamatan,
                COUNT(*) as total_thefts,
                COUNT(DISTINCT site_id) as unique_sites_stolen,
                MAX(event_date) as last_incident_date
            FROM theft_incidents
            GROUP BY kabupaten, kecamatan
        )
        SELECT 
            a.kabupaten,
            a.kecamatan,
            a.total_sites,
            a.sites_with_theft,
            a.center_lat,
            a.center_lng,
            COALESCE(t.total_thefts, 0) as total_thefts,
            COALESCE(t.unique_sites_stolen, 0) as unique_sites_stolen,
            t.last_incident_date,
            ROUND(
                (COALESCE(t.total_thefts, 0)::float / a.total_sites) * 100, 2
            ) as theft_rate_percentage
        FROM area_stats a
        LEFT JOIN theft_stats t ON a.kabupaten = t.kabupaten AND a.kecamatan = t.kecamatan
        ORDER BY theft_rate_percentage DESC, total_thefts DESC
        """
        
        cur.execute(query)
        area_data = [dict(row) for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        # Categorize areas by risk level
        high_risk_areas = [area for area in area_data if area['theft_rate_percentage'] > 20]
        medium_risk_areas = [area for area in area_data if 5 < area['theft_rate_percentage'] <= 20]
        low_risk_areas = [area for area in area_data if area['theft_rate_percentage'] <= 5]
        
        return jsonify({
            'success': True,
            'summary': {
                'total_areas': len(area_data),
                'high_risk_areas': len(high_risk_areas),
                'medium_risk_areas': len(medium_risk_areas),
                'low_risk_areas': len(low_risk_areas)
            },
            'areas': {
                'high_risk': high_risk_areas,
                'medium_risk': medium_risk_areas,
                'low_risk': low_risk_areas
            },
            'all_areas': area_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/temporal-analysis', methods=['GET'])
def get_temporal_analysis():
    """Get temporal patterns of theft incidents"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = """
        SELECT 
            event_date,
            event_time,
            EXTRACT(HOUR FROM TO_TIMESTAMP(event_time, 'HH24,MI')) as hour_of_day,
            EXTRACT(DOW FROM TO_DATE(event_date, 'DD/MM/YYYY')) as day_of_week,
            EXTRACT(MONTH FROM TO_DATE(event_date, 'DD/MM/YYYY')) as month,
            COUNT(*) as incident_count
        FROM theft_incidents
        WHERE event_date IS NOT NULL AND event_time IS NOT NULL
        GROUP BY event_date, event_time, hour_of_day, day_of_week, month
        ORDER BY TO_DATE(event_date, 'DD/MM/YYYY') DESC
        """
        
        cur.execute(query)
        temporal_data = [dict(row) for row in cur.fetchall()]
        
        # Aggregate by time periods
        hourly_stats = {}
        monthly_stats = {}
        dow_stats = {}
        
        for record in temporal_data:
            hour = int(record['hour_of_day']) if record['hour_of_day'] else 12
            month = int(record['month']) if record['month'] else 1
            dow = int(record['day_of_week']) if record['day_of_week'] else 1
            
            hourly_stats[hour] = hourly_stats.get(hour, 0) + 1
            monthly_stats[month] = monthly_stats.get(month, 0) + 1
            dow_stats[dow] = dow_stats.get(dow, 0) + 1
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'patterns': {
                'hourly_distribution': hourly_stats,
                'monthly_distribution': monthly_stats,
                'day_of_week_distribution': dow_stats
            },
            'raw_data': temporal_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)