-- High-value vulnerable sites (never stolen but high risk)
SELECT s.site_id, s.site_name, s.lat, s.lng, s.rev_class,
       COUNT(t.site_id) as nearby_thefts,
       AVG(ST_Distance(s.geom, t.geom)) as avg_distance_to_theft
FROM all_sites s
CROSS JOIN theft_incidents t  
WHERE ST_DWithin(s.geom, t.geom, 5000)
  AND s.site_id NOT IN (SELECT DISTINCT site_id FROM theft_incidents)
  AND s.rev_class IN ('Gold', 'Silver')
GROUP BY s.site_id, s.site_name, s.lat, s.lng, s.rev_class
ORDER BY nearby_thefts DESC, avg_distance_to_theft ASC;

-- Theft progression analysis
SELECT kabupaten, kecamatan,
       COUNT(*) as incidents,
       COUNT(DISTINCT site_id) as unique_sites,
       MAX(event_date) as last_incident,
       string_agg(DISTINCT material_kehilangan, '; ') as common_targets
FROM theft_incidents 
GROUP BY kabupaten, kecamatan
ORDER BY incidents DESC;