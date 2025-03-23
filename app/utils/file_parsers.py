import pandas as pd
import os
import re
import csv
from werkzeug.exceptions import BadRequest
from datetime import datetime

def parse_alarm_file(file_path, category, preview=True):
    """
    Parse alarm data from various file formats (CSV, Excel, TXT).
    
    Args:
        file_path (str): Path to the uploaded file
        category (str): The alarm category
        preview (bool): Whether to return a preview or full data
    
    Returns:
        list: List of dictionaries containing alarm data
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")
    
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext == '.csv':
            return parse_csv(file_path, preview)
        elif file_ext in ['.xlsx', '.xls']:
            return parse_excel(file_path, preview)
        elif file_ext == '.txt':
            return parse_txt(file_path, preview)
        else:
            raise BadRequest(f"Unsupported file format: {file_ext}")
    except Exception as e:
        raise Exception(f"Error parsing file: {str(e)}")

def parse_csv(file_path, preview=True):
    """Parse CSV file."""
    try:
        df = pd.read_csv(file_path)
        return process_dataframe(df, preview)
    except Exception as e:
        # Try with different encoding
        try:
            df = pd.read_csv(file_path, encoding='latin1')
            return process_dataframe(df, preview)
        except Exception as inner_e:
            raise Exception(f"Failed to parse CSV: {str(inner_e)}")

def parse_excel(file_path, preview=True):
    """Parse Excel file."""
    try:
        df = pd.read_excel(file_path)
        return process_dataframe(df, preview)
    except Exception as e:
        raise Exception(f"Failed to parse Excel: {str(e)}")

def parse_txt(file_path, preview=True):
    """Parse TXT file (assumes tab, comma, or pipe delimited)."""
    try:
        # Try different delimiters
        for delimiter in ['\t', ',', '|']:
            try:
                df = pd.read_csv(file_path, delimiter=delimiter)
                if len(df.columns) > 1:  # Found a valid delimiter
                    return process_dataframe(df, preview)
            except:
                continue
        
        # If we're here, try to parse as fixed-width
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        if not lines:
            raise Exception("Empty file")
        
        # Try to identify column positions based on header/first line
        header = lines[0].strip()
        
        # If header contains common site ID patterns
        site_id_matches = re.findall(r'[A-Z]{3}\d{4}', header)
        if site_id_matches:
            # Parse as a list of site IDs with descriptions
            result = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                site_matches = re.findall(r'([A-Z]{3}\d{4})', line)
                if site_matches:
                    site_id = site_matches[0]
                    description = line.replace(site_id, '').strip()
                    result.append({
                        'site_id': site_id,
                        'description': description or f"Issue reported for {site_id}"
                    })
            
            if preview:
                return result[:10]
            return result
        
        # Default: try to parse each line as a separate record
        result = []
        for line in lines[1:] if len(lines) > 1 else lines:  # Skip header if exists
            line = line.strip()
            if not line:
                continue
            
            # Try to extract site ID using regex pattern
            site_id_match = re.search(r'([A-Z]{3}\d{4})', line)
            if site_id_match:
                site_id = site_id_match.group(1)
                description = line.replace(site_id, '').strip()
                result.append({
                    'site_id': site_id,
                    'description': description or f"Issue reported for {site_id}"
                })
        
        if not result:
            raise Exception("Could not identify site IDs in the file")
        
        if preview:
            return result[:10]
        return result
        
    except Exception as e:
        raise Exception(f"Failed to parse TXT: {str(e)}")

def process_dataframe(df, preview=True):
    """Process a pandas DataFrame into the expected format."""
    # Check required columns
    required_columns = ['site_id']
    
    # Try to find columns that might contain site ID
    potential_site_id_columns = [col for col in df.columns if 'site' in str(col).lower() or 'id' in str(col).lower()]
    
    if not any(col in df.columns for col in required_columns) and potential_site_id_columns:
        # Use the first potential site ID column
        df = df.rename(columns={potential_site_id_columns[0]: 'site_id'})
    
    if 'site_id' not in df.columns:
        raise BadRequest("File must contain a 'site_id' column")
    
    # Create description from other columns if not present
    if 'description' not in df.columns:
        # Use other columns except site_id to form description
        other_cols = [col for col in df.columns if col != 'site_id']
        if other_cols:
            df['description'] = df[other_cols].apply(lambda row: ' - '.join(str(val) for val in row if pd.notna(val)), axis=1)
        else:
            df['description'] = f"Issue reported on {datetime.now().strftime('%Y-%m-%d')}"
    
    # Convert to list of dictionaries
    result = []
    for _, row in df.iterrows():
        site_id = str(row['site_id']).strip()
        # Skip rows without valid site ID
        if not site_id or pd.isna(site_id):
            continue
            
        # Ensure site ID is in the expected format (e.g., ABC1234)
        if not re.match(r'^[A-Z]{3}\d{4}$', site_id):
            continue
            
        result.append({
            'site_id': site_id,
            'description': str(row['description']) if pd.notna(row['description']) else f"Issue reported for {site_id}"
        })
    
    if preview:
        return result[:10]
    return result 