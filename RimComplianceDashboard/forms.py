from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, SelectField, BooleanField, DateField, PasswordField, HiddenField, MultipleFileField
from wtforms.validators import DataRequired, Email, Length, Optional, EqualTo
from wtforms.widgets import TextArea
from models import Department, User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=80)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=80)])
    role = SelectField('Role', choices=[('GP', 'General Partner'), ('RIM Team', 'RIM Team'), ('Admin', 'Administrator')], validators=[DataRequired()])
    department_id = SelectField('Department', coerce=int, validators=[Optional()])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('password', message='Passwords must match')])
    is_active = BooleanField('Active')

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.department_id.choices = [(0, 'No Department')] + [(d.id, d.name) for d in Department.query.all()]

class DepartmentForm(FlaskForm):
    name = StringField('Department Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional()])

class AcknowledgmentForm(FlaskForm):
    department_id = SelectField('Department', coerce=int, validators=[DataRequired()])
    gp_id = SelectField('General Partner', coerce=int, validators=[DataRequired()])
    rim_liaison_id = SelectField('RIM Liaison', coerce=int, validators=[Optional()])
    business_activity_folder_location = TextAreaField('Business Activity Folder Location', validators=[Optional()])
    key_records_managed = TextAreaField('Key Records Managed', validators=[Optional()])
    retention_schedule_acknowledged = BooleanField('I acknowledge that I have reviewed the retention schedule')
    acknowledgment_statement = BooleanField('I acknowledge my responsibilities under the RIM program', validators=[DataRequired()])
    additional_notes = TextAreaField('Additional Notes/Comments', validators=[Optional()])
    signature_name = StringField('Digital Signature (Full Name)', validators=[DataRequired(), Length(max=100)])
    signature_date = DateField('Signature Date', validators=[DataRequired()])
    attachments = MultipleFileField('Supporting Documents', validators=[FileAllowed(['pdf', 'doc', 'docx', 'txt', 'jpg', 'png'], 'Only PDF, DOC, DOCX, TXT, JPG, and PNG files allowed')])
    action = HiddenField('Action')

    def __init__(self, *args, **kwargs):
        super(AcknowledgmentForm, self).__init__(*args, **kwargs)
        # Populate departments
        departments = Department.query.all()
        self.department_id.choices = [(0, 'Select Department')] + [(d.id, d.name) for d in departments]
        
        # Populate General Partners (users with GP role)
        gp_users = User.query.filter_by(role='GP', is_active=True).all()
        self.gp_id.choices = [(0, 'Select General Partner')] + [(u.id, u.full_name) for u in gp_users]
        
        # Populate RIM liaisons (users with RIM Team role)
        rim_users = User.query.filter_by(role='RIM Team', is_active=True).all()
        self.rim_liaison_id.choices = [(0, 'Select RIM Liaison')] + [(u.id, u.full_name) for u in rim_users]

class SearchForm(FlaskForm):
    search = StringField('Search')
    department = SelectField('Department', coerce=int)
    status = SelectField('Status')
    
    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)
        self.department.choices = [(0, 'All Departments')] + [(d.id, d.name) for d in Department.query.all()]
        self.status.choices = [
            ('', 'All Statuses'),
            ('Not Started', 'Not Started'),
            ('In Progress', 'In Progress'),
            ('Submitted', 'Submitted'),
            ('Approved', 'Approved'),
            ('Needs Revision', 'Needs Revision')
        ]
