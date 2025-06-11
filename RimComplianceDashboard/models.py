from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from app import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='GP')  # GP, RIM Team, Admin
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    department = db.relationship('Department', backref='users')
    acknowledgments = db.relationship('Acknowledgment', 
                                    foreign_keys='Acknowledgment.gp_id',
                                    backref='gp_user', lazy='dynamic')
    rim_liaisons = db.relationship('Acknowledgment', 
                                 foreign_keys='Acknowledgment.rim_liaison_id',
                                 backref='rim_liaison_user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    acknowledgments = db.relationship('Acknowledgment', backref='department', lazy='dynamic')

    def __repr__(self):
        return f'<Department {self.name}>'

class Acknowledgment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    gp_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rim_liaison_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Form fields
    business_activity_folder_location = db.Column(db.Text)
    key_records_managed = db.Column(db.Text)
    retention_schedule_acknowledged = db.Column(db.Boolean, default=False)
    acknowledgment_statement = db.Column(db.Boolean, default=False)
    additional_notes = db.Column(db.Text)
    signature_name = db.Column(db.String(100))
    signature_date = db.Column(db.Date)
    
    # Status and tracking
    status = db.Column(db.String(20), default='Not Started')  # Not Started, In Progress, Submitted, Approved, Needs Revision
    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    due_date = db.Column(db.Date)
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    attachments = db.relationship('Attachment', backref='acknowledgment', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Acknowledgment {self.id} - {self.status}>'

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    acknowledgment_id = db.Column(db.Integer, db.ForeignKey('acknowledgment.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    uploader = db.relationship('User')

    def __repr__(self):
        return f'<Attachment {self.original_filename}>'

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))  # User, Department, Acknowledgment, etc.
    resource_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User')

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_id}>'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='info')  # info, warning, success, error
    is_read = db.Column(db.Boolean, default=False)
    acknowledgment_id = db.Column(db.Integer, db.ForeignKey('acknowledgment.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    recipient = db.relationship('User')
    acknowledgment = db.relationship('Acknowledgment')

    def __repr__(self):
        return f'<Notification {self.title}>'
