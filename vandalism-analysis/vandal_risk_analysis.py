# Vandalism Risk Analysis System for Telecom Sites

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
from geopy.distance import geodesic
import json

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
        
        for incident in theft_incidents:
            distance = geodesic(site_coords, (incident['lat'], incident['lng'])).kilometers
            min_distance = min(min_distance, distance)
            
            if distance <= 5:  # Within 5km
                incident_count_nearby += 1
        
        # Risk decreases with distance, increases with nearby incident count
        if min_distance == float('inf'):
            return 0
            
        distance_score = max(0, (max_distance_km - min_distance) / max_distance_km) * 100
        frequency_bonus = min(incident_count_nearby * 10, 30)  # Max 30 bonus points
        
        return min(100, distance_score + frequency_bonus)

    def calculate_temporal_risk(self, current_time, theft_incidents):
        """Calculate risk based on temporal patterns"""
        if not theft_incidents:
            return 50  # Default medium risk
            
        # Analyze time patterns from historical data
        hour_counts = {}
        month_counts = {}
        
        for incident in theft_incidents:
            try:
                incident_time = datetime.strptime(incident['event_time'], '%H,%M')
                hour = incident_time.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
                
                incident_date = datetime.strptime(incident['event_date'], '%d/%m/%Y')
                month = incident_date.month
                month_counts[month] = month_counts.get(month, 0) + 1
            except:
                continue
        
        current_hour = current_time.hour
        current_month = current_time.month
        
        # Calculate risk multipliers
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
                
        # Normalize to 0-100 scale
        return min(100, (risk_score / 40) * 100)  # Max expected score ~40

    def calculate_area_frequency_risk(self, site_location, theft_incidents, radius_km=15):
        """Calculate risk based on theft frequency in the area"""
        area_incidents = []
        
        for incident in theft_incidents:
            distance = geodesic(site_location, (incident['lat'], incident['lng'])).kilometers
            if distance <= radius_km:
                area_incidents.append(incident)
        
        if not area_incidents:
            return 10  # Low risk if no incidents in area
            
        # Calculate incidents per month in the area
        incident_dates = []
        for incident in area_incidents:
            try:
                date = datetime.strptime(incident['event_date'], '%d/%m/%Y')
                incident_dates.append(date)
            except:
                continue
        
        if not incident_dates:
            return 10
            
        # Calculate frequency over last 12 months
        recent_date = max(incident_dates)
        one_year_ago = recent_date - timedelta(days=365)
        recent_incidents = [d for d in incident_dates if d >= one_year_ago]
        
        monthly_rate = len(recent_incidents) / 12
        return min(100, monthly_rate * 25)  # Scale to 0-100

    def calculate_comprehensive_risk_score(self, site_data, theft_incidents):
        """Calculate comprehensive risk score for a site"""
        site_coords = (site_data['lat'], site_data['lng'])
        
        # Calculate individual risk components
        proximity_risk = self.calculate_proximity_risk(site_coords, theft_incidents)
        
        classification_risk_score = self.classification_risk.get(
            site_data.get('classification', 'Bronze'), 0.8
        ) * 100
        
        equipment_risk = self.calculate_equipment_risk(site_data.get('detail', ''))
        
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

    def generate_preventive_recommendations(self, risk_analysis, site_data):
        """Generate specific recommendations based on risk analysis"""
        recommendations = []
        score = risk_analysis['total_risk_score']
        components = risk_analysis['components']
        
        if components['proximity_risk'] > 60:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'Increase security patrols',
                'detail': 'Site is within high-risk proximity of recent theft incidents'
            })
        
        if components['classification_risk'] > 50:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'Upgrade physical security',
                'detail': f"Site classification ({site_data.get('classification')}) indicates vulnerability"
            })
        
        if components['equipment_risk'] > 70:
            recommendations.append({
                'priority': 'HIGH', 
                'action': 'Install equipment protection',
                'detail': 'High-value equipment detected - consider cable locks and enclosures'
            })
        
        if components['temporal_risk'] > 60:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'Time-based security measures',
                'detail': 'Historical patterns suggest increased risk during current time period'
            })
        
        if score >= 80:
            recommendations.append({
                'priority': 'CRITICAL',
                'action': 'Immediate security assessment',
                'detail': 'Overall risk score indicates immediate attention required'
            })
        
        return recommendations

    def analyze_site_portfolio(self, all_sites, theft_incidents):
        """Analyze entire site portfolio for risk assessment"""
        results = []
        
        for site in all_sites:
            risk_analysis = self.calculate_comprehensive_risk_score(site, theft_incidents)
            recommendations = self.generate_preventive_recommendations(risk_analysis, site)
            
            site_result = {
                'site_id': site['site_id'],
                'site_name': site['site_name'],
                'location': site['kelurahan'] + ', ' + site['kecamatan'],
                'risk_analysis': risk_analysis,
                'recommendations': recommendations,
                'coordinates': {'lat': site['lat'], 'lng': site['lng']}
            }
            
            results.append(site_result)
        
        # Sort by risk score (highest first)
        results.sort(key=lambda x: x['risk_analysis']['total_risk_score'], reverse=True)
        
        return results

# Example usage and Flask integration helpers
class FlaskIntegrationHelper:
    @staticmethod
    def format_for_api(analysis_results):
        """Format analysis results for API response"""
        return {
            'summary': {
                'total_sites': len(analysis_results),
                'high_risk_sites': len([s for s in analysis_results if s['risk_analysis']['total_risk_score'] >= 60]),
                'critical_sites': len([s for s in analysis_results if s['risk_analysis']['total_risk_score'] >= 80])
            },
            'sites': analysis_results
        }
    
    @staticmethod
    def get_high_priority_alerts(analysis_results, threshold=70):
        """Get sites requiring immediate attention"""
        alerts = []
        for site in analysis_results:
            if site['risk_analysis']['total_risk_score'] >= threshold:
                alerts.append({
                    'site_id': site['site_id'],
                    'site_name': site['site_name'],
                    'risk_score': site['risk_analysis']['total_risk_score'],
                    'risk_level': site['risk_analysis']['risk_level'],
                    'urgent_actions': [r for r in site['recommendations'] if r['priority'] in ['HIGH', 'CRITICAL']]
                })
        return alerts

# Example implementation
if __name__ == "__main__":
    # Initialize analyzer
    analyzer = VandalismRiskAnalyzer()
    
    # Sample data structure (replace with your actual data)
    sample_site = {
        'site_id': 'RAP463',
        'site_name': 'Perumahan LPK 1-2',
        'lat': 2.06562,
        'lng': 99.8695,
        'classification': 'Silver',
        'kelurahan': 'Danobale',
        'kecamatan': 'Rantau Selatan',
        'detail': 'DCS 1800, LTE 900, LTE 1800, LTE 2100'
    }
    
    sample_theft_incidents = [{
        'site_id': 'RAP329',
        'lat': 2.07838,
        'lng': 99.714,
        'event_date': '24/09/2023',
        'event_time': '15,03',
        'materials': 'Kabel Power RRU dan kabel Power RBS'
    }]
    
    # Calculate risk
    risk_result = analyzer.calculate_comprehensive_risk_score(sample_site, sample_theft_incidents)
    print("Risk Analysis Result:")
    print(json.dumps(risk_result, indent=2))