# Activity Tracker for BTS Sites

## Overview
This project is an **Activity Tracker** for BTS (Base Transceiver Station) sites, designed to **increase availability, reduce MTTR (Mean Time to Repair), and optimize site recovery/maintenance**. It uses **machine learning (ML)** and **large language models (LLM)** for smart decision-making.

## Features
- **User Authentication**: Secure login system with role-based access control (TSEL users, ENOM users, Admins).
- **Ticketing System**: Create, manage, and resolve site-related tickets.
- **Daily Plans Management**: Assign site visits, track actions, and generate reports.
- **Geospatial Optimization**: Uses **Mapbox** to visualize site locations.
- **Automated Reports**: Provides insights on ticket trends, resolution times, and site conditions.
- **Dashboard**: Displays real-time ticket statuses, planned actions, and trends.

## Tech Stack
- **Backend**: Python (Flask), SQLAlchemy, PostgreSQL
- **Frontend**: HTML, CSS, JavaScript, Bootstrap, Select2
- **Security**: Flask-WTF (CSRF Protection), Flask-Limiter (Rate Limiting), Secure Authentication
- **Deployment**: Nginx, Gunicorn, Systemd, GitHub Actions (CI/CD)

## Installation
### 1. Clone Repository
```bash
git clone https://github.com/your-repo/activity-tracker.git
cd activity-tracker
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file and set up:
```
# Database Configuration
DB_USERNAME=your_db_username
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_NAME=your_db_name

# User Credentials
TSEL_ADMIN_PASSWORD=your_secure_tsel_password
ENOM_USER_PASSWORD=your_secure_enom_password

# Other configurations...
FLASK_APP=<your_flask_app_here>
SQLALCHEMY_DATABASE_URI = <your_database_uri_here>
MAPBOX_TOKEN=<your_mapbox_token_here>
```

### 5. Initialize Database
```bash
flask db upgrade
```

### 6. Run the Application
```bash
flask run
```

## Usage
### 1. User Roles
- **TSEL Users**: Create and track tickets.
- **ENOM Engineers**: Update ticket statuses, add action logs.
- **Admin**: Manage users, oversee site performance.

### 2. Managing Tickets
- Create new tickets via `/tickets/new`
- View all tickets `/tickets`
- Update ticket status `/tickets/<ticket_id>/update_status`
- Close tickets `/tickets/<ticket_id>/close`

### 3. Creating Daily Plans
- Assign ENOM engineers to specific site visits.
- Update planned actions and report outcomes.
- Approve or reject submitted plans.

### 4. Dashboard
- View live statistics of **open, in-progress, resolved, and closed tickets**.
- Track **MTTR and site visit trends** over time.

## Deployment
### 1. Configure Gunicorn & Nginx
- Use **Gunicorn** as the WSGI server.
- Set up **Nginx** as a reverse proxy.

### 2. Systemd Service
```bash
sudo systemctl restart enom_activity_tracker_service
```

### 3. GitHub Actions for CI/CD
The repository includes a **GitHub Actions workflow** (`.github/workflows/deploy.yml`) for automatic deployment upon push to `master`.

## Security & Logging
- **Rate Limiting**: Protects against brute-force login attempts.
- **Logging**: All application logs are stored in `/var/log/enom_tracker/app.log`.
- **SQL Injection Protection**: Safe queries using SQLAlchemy.

## Contributing
- Fork the repo and create a feature branch.
- Ensure tests pass before submitting a PR.

## License
MIT License.

