import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()

def create_app():
    # Create Flask app
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///rpa_magic.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Upload configuration
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # Mail configuration
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'localhost')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@rpamagic.com')
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    
    # Login manager settings
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Create upload directory
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    with app.app_context():
        # Import models to create tables
        import models
        db.create_all()
        
        # Create default admin user if it doesn't exist
        from models import User, Department, Acknowledgment
        from werkzeug.security import generate_password_hash
        from datetime import date
        
        admin = User.query.filter_by(email='admin@rpamagic.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@rpamagic.com',
                first_name='System',
                last_name='Administrator',
                role='Admin',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(admin)
        
        # Create Financial Institution departments if none exist
        if Department.query.count() == 0:
            departments = [
                {'name': 'Data Management', 'description': 'Comprehensive data lifecycle management, storage, and data architecture oversight'},
                {'name': 'Finance', 'description': 'Financial operations, accounting, budget management, and financial reporting'},
                {'name': 'Audit', 'description': 'Internal audit functions, compliance verification, and risk assessment'},
                {'name': 'Data Governance', 'description': 'Data policies, standards, privacy regulations, and data compliance oversight'},
                {'name': 'Data Stewardship', 'description': 'Data quality assurance, data definitions, and business data ownership'},
                {'name': 'Infrastructure Development', 'description': 'IT infrastructure, cloud platforms, and technology foundation development'},
                {'name': 'Construction', 'description': 'Physical infrastructure projects, facility management, and construction oversight'},
                {'name': 'Process Automation', 'description': 'Business process optimization, workflow automation, and efficiency initiatives'},
                {'name': 'AI Integrations', 'description': 'Artificial intelligence implementations, machine learning projects, and AI strategy'},
                {'name': 'Data Quality', 'description': 'Data validation, cleansing, monitoring, and quality assurance programs'},
                {'name': 'Data Products', 'description': 'Data product development, analytics solutions, and data-driven business tools'},
                {'name': 'Marketing', 'description': 'Marketing campaigns, brand management, customer engagement, and market research'},
                {'name': 'Data Engineering', 'description': 'Data pipeline development, ETL processes, and data infrastructure engineering'},
                {'name': 'Business Intelligence', 'description': 'Reporting, dashboards, analytics, and business intelligence solutions'},
                {'name': 'Customer Analytics', 'description': 'Customer behavior analysis, segmentation, and customer data insights'},
                {'name': 'Risk Management', 'description': 'Enterprise risk assessment, mitigation strategies, and risk monitoring'},
                {'name': 'Cybersecurity', 'description': 'Information security, threat protection, and cybersecurity governance'},
                {'name': 'Operations', 'description': 'Daily business operations, operational efficiency, and process management'}
            ]
            
            for dept_data in departments:
                dept = Department(
                    name=dept_data['name'],
                    description=dept_data['description']
                )
                db.session.add(dept)
        
        # Create sample users for Financial Institution
        if User.query.count() <= 1:  # Only admin exists
            sample_users = [
                {'username': 'john.smith', 'email': 'john.smith@edwardjones.com', 'first_name': 'John', 'last_name': 'Smith', 'role': 'GP', 'department': 'Data Management'},
                {'username': 'sarah.wilson', 'email': 'sarah.wilson@edwardjones.com', 'first_name': 'Sarah', 'last_name': 'Wilson', 'role': 'RIM Team', 'department': 'Data Governance'},
                {'username': 'mike.johnson', 'email': 'mike.johnson@edwardjones.com', 'first_name': 'Mike', 'last_name': 'Johnson', 'role': 'GP', 'department': 'Finance'},
                {'username': 'lisa.brown', 'email': 'lisa.brown@edwardjones.com', 'first_name': 'Lisa', 'last_name': 'Brown', 'role': 'RIM Team', 'department': 'Audit'},
                {'username': 'david.davis', 'email': 'david.davis@edwardjones.com', 'first_name': 'David', 'last_name': 'Davis', 'role': 'GP', 'department': 'Data Stewardship'},
                {'username': 'maria.garcia', 'email': 'maria.garcia@edwardjones.com', 'first_name': 'Maria', 'last_name': 'Garcia', 'role': 'GP', 'department': 'Infrastructure Development'},
                {'username': 'robert.chen', 'email': 'robert.chen@edwardjones.com', 'first_name': 'Robert', 'last_name': 'Chen', 'role': 'RIM Team', 'department': 'Data Quality'},
                {'username': 'jessica.taylor', 'email': 'jessica.taylor@edwardjones.com', 'first_name': 'Jessica', 'last_name': 'Taylor', 'role': 'GP', 'department': 'Process Automation'},
                {'username': 'alex.rodriguez', 'email': 'alex.rodriguez@edwardjones.com', 'first_name': 'Alex', 'last_name': 'Rodriguez', 'role': 'GP', 'department': 'AI Integrations'},
                {'username': 'emily.white', 'email': 'emily.white@edwardjones.com', 'first_name': 'Emily', 'last_name': 'White', 'role': 'RIM Team', 'department': 'Data Products'},
                {'username': 'james.miller', 'email': 'james.miller@edwardjones.com', 'first_name': 'James', 'last_name': 'Miller', 'role': 'GP', 'department': 'Marketing'},
                {'username': 'rachel.kim', 'email': 'rachel.kim@edwardjones.com', 'first_name': 'Rachel', 'last_name': 'Kim', 'role': 'GP', 'department': 'Data Engineering'},
                {'username': 'thomas.anderson', 'email': 'thomas.anderson@edwardjones.com', 'first_name': 'Thomas', 'last_name': 'Anderson', 'role': 'RIM Team', 'department': 'Business Intelligence'},
                {'username': 'stephanie.jones', 'email': 'stephanie.jones@edwardjones.com', 'first_name': 'Stephanie', 'last_name': 'Jones', 'role': 'GP', 'department': 'Customer Analytics'},
                {'username': 'kevin.wong', 'email': 'kevin.wong@edwardjones.com', 'first_name': 'Kevin', 'last_name': 'Wong', 'role': 'GP', 'department': 'Risk Management'},
                {'username': 'michelle.clark', 'email': 'michelle.clark@edwardjones.com', 'first_name': 'Michelle', 'last_name': 'Clark', 'role': 'RIM Team', 'department': 'Cybersecurity'}
            ]
            
            for user_data in sample_users:
                dept = Department.query.filter_by(name=user_data['department']).first()
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    first_name=user_data['first_name'],
                    last_name=user_data['last_name'],
                    role=user_data['role'],
                    department_id=dept.id if dept else None,
                    password_hash=generate_password_hash('password123')
                )
                db.session.add(user)
        
        # Create sample acknowledgments
        if Acknowledgment.query.count() == 0:
            users = User.query.filter(User.role == 'GP').all()
            rim_liaisons = User.query.filter(User.role == 'RIM Team').all()
            
            for i, user in enumerate(users):
                if user.department_id:
                    liaison = rim_liaisons[i % len(rim_liaisons)] if rim_liaisons else None
                    ack = Acknowledgment(
                        department_id=user.department_id,
                        gp_id=user.id,
                        rim_liaison_id=liaison.id if liaison else None,
                        business_activity_folder_location=f'//shared/departments/{user.department.name}/records',
                        key_records_managed='Financial reports, client communications, compliance documentation',
                        retention_schedule_acknowledged=True,
                        acknowledgment_statement=True,
                        signature_name=user.full_name,
                        signature_date=date.today(),
                        status=['Not Started', 'In Progress', 'Submitted', 'Approved'][i % 4],
                        additional_notes=f'RIM compliance acknowledgment for {user.department.name} department'
                    )
                    db.session.add(ack)
        
        db.session.commit()
        logging.info("Database initialized with Financial Institution sample data")
    
    return app

# Create app instance
app = create_app()

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))
