# Advanced Analytics & Predictive Models for Vandalism Prevention

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class AdvancedVandalismAnalytics:
    def __init__(self):
        self.risk_model = None
        self.anomaly_detector = None
        self.scaler = StandardScaler()
        self.feature_importance = None
        
    def prepare_features(self, sites_df, incidents_df):
        """Prepare features for machine learning models"""
        features_list = []
        
        for _, site in sites_df.iterrows():
            site_features = {
                'site_id': site['site_id'],
                'lat': site['lat'],
                'lng': site['lng'],
                'classification_score': self._encode_classification(site.get('classification', 'Bronze')),
                'equipment_value': self._calculate_equipment_value(site.get('detail', '')),
            }
            
            # Calculate proximity features
            site_features.update(self._calculate_proximity_features(site, incidents_df))
            
            # Calculate temporal features
            site_features.update(self._calculate_temporal_features(site, incidents_df))
            
            # Target variable: has this site been stolen from?
            site_features['has_been_stolen'] = 1 if site['site_id'] in incidents_df['site_id'].values else 0
            
            features_list.append(site_features)
        
        return pd.DataFrame(features_list)
    
    def _encode_classification(self, classification):
        """Encode site classification to numeric value"""
        mapping = {'Bronze': 1, 'Silver': 2, 'Gold': 3, 'Platinum': 4}
        return mapping.get(classification, 1)
    
    def _calculate_equipment_value(self, equipment_detail):
        """Calculate equipment value score"""
        if not equipment_detail:
            return 1
        
        equipment_detail = equipment_detail.lower()
        score = 1  # Base score
        
        # High-value equipment indicators
        if 'lte' in equipment_detail:
            score += 2
        if 'dcs' in equipment_detail:
            score += 1
        if '2100' in equipment_detail or '1800' in equipment_detail:
            score += 1
        
        return min(score, 5)  # Cap at 5
    
    def _calculate_proximity_features(self, site, incidents_df):
        """Calculate proximity-based features"""
        from geopy.distance import geodesic
        
        if incidents_df.empty:
            return {
                'min_distance_to_incident': 999,
                'incidents_within_5km': 0,
                'incidents_within_10km': 0,
                'avg_distance_to_incidents': 999
            }
        
        site_coords = (site['lat'], site['lng'])
        distances = []
        
        for _, incident in incidents_df.iterrows():
            incident_coords = (incident['lat'], incident['lng'])
            distance = geodesic(site_coords, incident_coords).kilometers
            distances.append(distance)
        
        distances = np.array(distances)
        
        return {
            'min_distance_to_incident': np.min(distances),
            'incidents_within_5km': np.sum(distances <= 5),
            'incidents_within_10km': np.sum(distances <= 10),
            'avg_distance_to_incidents': np.mean(distances)
        }
    
    def _calculate_temporal_features(self, site, incidents_df):
        """Calculate temporal features"""
        if incidents_df.empty:
            return {
                'recent_incidents_30d': 0,
                'recent_incidents_90d': 0,
                'days_since_last_incident': 999
            }
        
        # Convert dates for calculation
        try:
            current_date = datetime.now()
            incident_dates = pd.to_datetime(incidents_df['event_date'], format='%d/%m/%Y', errors='coerce')
            incident_dates = incident_dates.dropna()
            
            if incident_dates.empty:
                return {
                    'recent_incidents_30d': 0,
                    'recent_incidents_90d': 0,
                    'days_since_last_incident': 999
                }
            
            # Calculate temporal features
            days_30_ago = current_date - timedelta(days=30)
            days_90_ago = current_date - timedelta(days=90)
            
            recent_30d = len(incident_dates[incident_dates >= days_30_ago])
            recent_90d = len(incident_dates[incident_dates >= days_90_ago])
            
            last_incident = incident_dates.max()
            days_since_last = (current_date - last_incident).days if pd.notna(last_incident) else 999
            
            return {
                'recent_incidents_30d': recent_30d,
                'recent_incidents_90d': recent_90d,
                'days_since_last_incident': min(days_since_last, 999)
            }
        except:
            return {
                'recent_incidents_30d': 0,
                'recent_incidents_90d': 0,
                'days_since_last_incident': 999
            }
    
    def train_risk_prediction_model(self, features_df):
        """Train machine learning model to predict theft risk"""
        # Prepare features and target
        feature_columns = [col for col in features_df.columns if col not in ['site_id', 'has_been_stolen']]
        X = features_df[feature_columns]
        y = features_df['has_been_stolen']
        
        # Handle missing values
        X = X.fillna(X.median())
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Train Random Forest model
        self.risk_model = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            class_weight='balanced'
        )
        
        self.risk_model.fit(X_train, y_train)
        
        # Evaluate model
        train_score = self.risk_model.score(X_train, y_train)
        test_score = self.risk_model.score(X_test, y_test)
        
        # Feature importance
        self.feature_importance = dict(zip(feature_columns, self.risk_model.feature_importances_))
        
        # Predictions
        y_pred = self.risk_model.predict(X_test)
        
        return {
            'train_accuracy': train_score,
            'test_accuracy': test_score,
            'classification_report': classification_report(y_test, y_pred),
            'feature_importance': self.feature_importance,
            'model_trained': True
        }
    
    def predict_theft_probability(self, site_features):
        """Predict theft probability for a site"""
        if self.risk_model is None:
            raise ValueError("Model not trained yet. Call train_risk_prediction_model first.")
        
        # Prepare features
        feature_columns = list(self.feature_importance.keys())
        X = [[site_features.get(col, 0) for col in feature_columns]]
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Get probability
        probability = self.risk_model.predict_proba(X_scaled)[0][1]  # Probability of theft
        
        return {
            'theft_probability': round(probability * 100, 2),
            'risk_level': self._get_risk_level_from_probability(probability),
            'confidence': round(max(self.risk_model.predict_proba(X_scaled)[0]) * 100, 2)
        }
    
    def _get_risk_level_from_probability(self, probability):
        """Convert probability to risk level"""
        if probability >= 0.8:
            return 'CRITICAL'
        elif probability >= 0.6:
            return 'HIGH'
        elif probability >= 0.4:
            return 'MEDIUM'
        elif probability >= 0.2:
            return 'LOW'
        else:
            return 'MINIMAL'
    
    def detect_spatial_clusters(self, incidents_df, eps=0.01, min_samples=2):
        """Detect spatial clusters of theft incidents"""
        if incidents_df.empty:
            return []
        
        # Prepare coordinates
        coordinates = incidents_df[['lat', 'lng']].values
        
        # Apply DBSCAN clustering
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(coordinates)
        
        # Add cluster labels to incidents
        incidents_df['cluster'] = clustering.labels_
        
        # Analyze clusters
        clusters = []
        for cluster_id in set(clustering.labels_):
            if cluster_id == -1:  # Noise points
                continue
            
            cluster_incidents = incidents_df[incidents_df['cluster'] == cluster_id]
            
            cluster_info = {
                'cluster_id': cluster_id,
                'incident_count': len(cluster_incidents),
                'center_lat': cluster_incidents['lat'].mean(),
                'center_lng': cluster_incidents['lng'].mean(),
                'radius_km': self._calculate_cluster_radius(cluster_incidents),
                'sites_affected': cluster_incidents['site_id'].nunique(),
                'most_common_materials': cluster_incidents['material_kehilangan'].mode().iloc[0] if not cluster_incidents['material_kehilangan'].empty else 'Unknown',
                'date_range': {
                    'first_incident': cluster_incidents['event_date'].min(),
                    'last_incident': cluster_incidents['event_date'].max()
                }
            }
            
            clusters.append(cluster_info)
        
        # Sort by incident count
        clusters.sort(key=lambda x: x['incident_count'], reverse=True)
        
        return clusters
    
    def _calculate_cluster_radius(self, cluster_incidents):
        """Calculate radius of incident cluster"""
        from geopy.distance import geodesic
        
        center_lat = cluster_incidents['lat'].mean()
        center_lng = cluster_incidents['lng'].mean()
        center = (center_lat, center_lng)
        
        max_distance = 0
        for _, incident in cluster_incidents.iterrows():
            incident_coords = (incident['lat'], incident['lng'])
            distance = geodesic(center, incident_coords).kilometers
            max_distance = max(max_distance, distance)
        
        return round(max_distance, 2)
    
    def generate_patrol_recommendations(self, high_risk_sites, clusters):
        """Generate optimized patrol recommendations"""
        recommendations = []
        
        # High-risk site patrols
        for site in high_risk_sites:
            if site['risk_analysis']['total_risk_score'] >= 70:
                recommendations.append({
                    'type': 'high_risk_site_patrol',
                    'priority': 'HIGH',
                    'site_id': site['site_id'],
                    'location': f"{site['location']}",
                    'coordinates': site['coordinates'],
                    'recommended_frequency': 'Daily',
                    'best_times': ['06:00-08:00', '18:00-20:00'],  # Based on typical theft patterns
                    'reason': f"Risk score: {site['risk_analysis']['total_risk_score']}"
                })
        
        # Cluster-based patrols
        for cluster in clusters:
            if cluster['incident_count'] >= 3:
                recommendations.append({
                    'type': 'cluster_patrol',
                    'priority': 'MEDIUM',
                    'cluster_id': cluster['cluster_id'],
                    'center_coordinates': {
                        'lat': cluster['center_lat'],
                        'lng': cluster['center_lng']
                    },
                    'patrol_radius': cluster['radius_km'] + 2,  # Add buffer
                    'recommended_frequency': 'Every 2 days',
                    'reason': f"Cluster with {cluster['incident_count']} incidents affecting {cluster['sites_affected']} sites"
                })
        
        return recommendations
    
    def calculate_prevention_roi(self, incidents_df, prevention_cost_per_site=5000):
        """Calculate ROI of prevention measures"""
        if incidents_df.empty:
            return {
                'total_losses': 0,
                'prevention_roi': 0,
                'break_even_prevention_rate': 0
            }
        
        # Estimate losses per incident
        material_loss_estimates = {
            'kabel': 2000,  # Cable theft
            'battery': 3000,  # Battery theft
            'sfp': 1500,  # SFP units
            'rectifier': 2500,  # Power equipment
            'optical': 4000  # Optical equipment
        }
        
        total_estimated_losses = 0
        
        for _, incident in incidents_df.iterrows():
            materials = str(incident.get('material_kehilangan', '')).lower()
            incident_loss = 1000  # Base loss (downtime, replacement, etc.)
            
            for material_type, loss_value in material_loss_estimates.items():
                if material_type in materials:
                    incident_loss += loss_value
            
            total_estimated_losses += incident_loss
        
        # Calculate ROI metrics
        total_sites = len(incidents_df['site_id'].unique())
        total_prevention_cost = total_sites * prevention_cost_per_site
        
        # ROI calculation
        if total_prevention_cost > 0:
            roi_percentage = ((total_estimated_losses - total_prevention_cost) / total_prevention_cost) * 100
        else:
            roi_percentage = 0
        
        # Break-even analysis
        break_even_rate = (prevention_cost_per_site / (total_estimated_losses / len(incidents_df))) * 100 if len(incidents_df) > 0 else 0
        
        return {
            'total_estimated_losses': total_estimated_losses,
            'total_prevention_cost': total_prevention_cost,
            'roi_percentage': round(roi_percentage, 2),
            'break_even_prevention_rate': round(break_even_rate, 2),
            'average_loss_per_incident': round(total_estimated_losses / len(incidents_df), 2) if len(incidents_df) > 0 else 0,
            'incidents_prevented_to_break_even': round(total_prevention_cost / (total_estimated_losses / len(incidents_df)), 0) if len(incidents_df) > 0 else 0
        }
    
    def generate_executive_summary(self, analysis_results):
        """Generate executive summary for management"""
        total_sites = len(analysis_results)
        critical_sites = len([s for s in analysis_results if s['risk_analysis']['total_risk_score'] >= 80])
        high_risk_sites = len([s for s in analysis_results if s['risk_analysis']['total_risk_score'] >= 60])
        
        summary = {
            'overview': {
                'total_sites_analyzed': total_sites,
                'critical_risk_sites': critical_sites,
                'high_risk_sites': high_risk_sites,
                'sites_requiring_immediate_attention': critical_sites + high_risk_sites,
                'overall_risk_level': 'HIGH' if critical_sites > 0 else 'MEDIUM' if high_risk_sites > 0 else 'LOW'
            },
            'key_findings': [
                f"{critical_sites} sites require immediate security intervention",
                f"{high_risk_sites} sites need enhanced monitoring",
                f"Top risk factors: proximity to previous incidents, equipment value, site classification"
            ],
            'immediate_actions': [
                "Deploy additional security to critical sites",
                "Implement enhanced monitoring systems",
                "Increase patrol frequency in high-risk areas",
                "Review and upgrade physical security measures"
            ],
            'financial_impact': {
                'estimated_monthly_risk_exposure': f"${(critical_sites * 5000 + high_risk_sites * 2000):,}",
                'recommended_security_investment': f"${(critical_sites * 1000 + high_risk_sites * 500):,}",
                'potential_monthly_savings': f"${(critical_sites * 4000 + high_risk_sites * 1500):,}"
            }
        }
        
        return summary

# Example usage
if __name__ == "__main__":
    # Initialize advanced analytics
    analytics = AdvancedVandalismAnalytics()
    
    # Sample usage would be:
    # 1. Load your data
    # 2. Prepare features
    # 3. Train models
    # 4. Generate predictions and recommendations
    
    print("Advanced Vandalism Analytics System Initialized")
    print("Key capabilities:")
    print("- Machine learning risk prediction")
    print("- Spatial clustering analysis") 
    print("- Patrol optimization")
    print("- ROI calculation")
    print("- Executive reporting")