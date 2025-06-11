import os
import uuid
from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from app import app, db, mail
from models import User, Department, Acknowledgment, Attachment, AuditLog, Notification
from forms import LoginForm, UserForm, DepartmentForm, AcknowledgmentForm, SearchForm
import utils
from utils import log_audit, send_notification_email, generate_pdf_report, allowed_file

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.is_active and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            log_audit(user.id, 'User Login', 'User', user.id, 'User logged in successfully')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    log_audit(current_user.id, 'User Logout', 'User', current_user.id, 'User logged out')
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

# Main routes
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    form = SearchForm()
    
    # Get all acknowledgments for demo mode (no authentication)
    query = Acknowledgment.query
    
    # Apply search filters
    if request.args.get('search'):
        search_term = f"%{request.args.get('search')}%"
        query = query.join(User).join(Department).filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                Department.name.ilike(search_term)
            )
        )
    
    if request.args.get('department'):
        dept_id = request.args.get('department')
        if dept_id and dept_id.isdigit() and int(dept_id) > 0:
            query = query.filter_by(department_id=int(dept_id))
    
    if request.args.get('status'):
        query = query.filter_by(status=request.args.get('status'))
    
    acknowledgments = query.order_by(Acknowledgment.updated_at.desc()).all()
    
    # Get statistics for dashboard
    all_acks = Acknowledgment.query
    stats = {
        'total': all_acks.count(),
        'not_started': all_acks.filter_by(status='Not Started').count(),
        'in_progress': all_acks.filter_by(status='In Progress').count(),
        'submitted': all_acks.filter_by(status='Submitted').count(),
        'approved': all_acks.filter_by(status='Approved').count(),
        'needs_revision': all_acks.filter_by(status='Needs Revision').count()
    }
    
    return render_template('dashboard.html', 
                         acknowledgments=acknowledgments, 
                         form=form, 
                         stats=stats,
                         utils=utils)

@app.route('/acknowledgment/new')
@app.route('/acknowledgment/<int:id>/edit')
def acknowledgment_form(id=None):
    acknowledgment = None
    if id:
        acknowledgment = Acknowledgment.query.get_or_404(id)
    
    form = AcknowledgmentForm()
    
    if request.method == 'GET' and acknowledgment:
        # Populate form with existing data
        form.rim_liaison_id.data = acknowledgment.rim_liaison_id
        form.business_activity_folder_location.data = acknowledgment.business_activity_folder_location
        form.key_records_managed.data = acknowledgment.key_records_managed
        form.retention_schedule_acknowledged.data = acknowledgment.retention_schedule_acknowledged
        form.acknowledgment_statement.data = acknowledgment.acknowledgment_statement
        form.additional_notes.data = acknowledgment.additional_notes
        form.signature_name.data = acknowledgment.signature_name
        form.signature_date.data = acknowledgment.signature_date
    
    return render_template('acknowledgment_form.html', form=form, acknowledgment=acknowledgment)

@app.route('/acknowledgment/save', methods=['POST'])
@app.route('/acknowledgment/<int:id>/save', methods=['POST'])
def save_acknowledgment(id=None):
    form = AcknowledgmentForm()
    
    if not form.validate_on_submit():
        flash('Please correct the errors in the form.', 'error')
        return render_template('acknowledgment_form.html', form=form)
    
    acknowledgment = None
    if id:
        acknowledgment = Acknowledgment.query.get_or_404(id)
        # Check permissions
        if current_user.role == 'GP' and acknowledgment.gp_id != current_user.id:
            flash('You do not have permission to edit this acknowledgment.', 'error')
            return redirect(url_for('dashboard'))
    else:
        # Create new acknowledgment
        acknowledgment = Acknowledgment(
            gp_id=form.gp_id.data if form.gp_id.data > 0 else None,
            department_id=form.department_id.data if form.department_id.data > 0 else None,
            status='In Progress'
        )
        db.session.add(acknowledgment)
    
    # Update acknowledgment fields
    acknowledgment.department_id = form.department_id.data if form.department_id.data > 0 else None
    acknowledgment.gp_id = form.gp_id.data if form.gp_id.data > 0 else None
    acknowledgment.rim_liaison_id = form.rim_liaison_id.data if form.rim_liaison_id.data > 0 else None
    acknowledgment.business_activity_folder_location = form.business_activity_folder_location.data
    acknowledgment.key_records_managed = form.key_records_managed.data
    acknowledgment.retention_schedule_acknowledged = form.retention_schedule_acknowledged.data
    acknowledgment.acknowledgment_statement = form.acknowledgment_statement.data
    acknowledgment.additional_notes = form.additional_notes.data
    acknowledgment.signature_name = form.signature_name.data
    acknowledgment.signature_date = form.signature_date.data
    
    # Handle action (save draft or submit)
    action = form.action.data
    if action == 'submit':
        acknowledgment.status = 'Submitted'
        acknowledgment.submitted_at = datetime.utcnow()
        flash_message = 'Acknowledgment submitted successfully!'
        
        # Send notification to RIM liaison
        if acknowledgment.rim_liaison_id:
            notification = Notification(
                recipient_id=acknowledgment.rim_liaison_id,
                title='New Acknowledgment Submission',
                message=f'A new acknowledgment has been submitted by {current_user.full_name} from {acknowledgment.department.name}.',
                notification_type='info',
                acknowledgment_id=acknowledgment.id
            )
            db.session.add(notification)
            
            # Send email notification
            send_notification_email(acknowledgment.rim_liaison_user.email, 
                                  'New RIM Acknowledgment Submission',
                                  f'A new acknowledgment has been submitted by {current_user.full_name}.')
    else:
        acknowledgment.status = 'In Progress'
        flash_message = 'Draft saved successfully!'
    
    # Handle file uploads
    if form.attachments.data:
        for file in form.attachments.data:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                
                attachment = Attachment(
                    acknowledgment_id=acknowledgment.id,
                    filename=unique_filename,
                    original_filename=filename,
                    file_size=os.path.getsize(file_path),
                    mime_type=file.content_type,
                    uploaded_by=current_user.id
                )
                db.session.add(attachment)
    
    db.session.commit()
    
    # Log audit
    log_audit(current_user.id, f'Acknowledgment {action.title()}', 'Acknowledgment', 
              acknowledgment.id, f'Acknowledgment {action}ed')
    
    flash(flash_message, 'success')
    return redirect(url_for('dashboard'))

@app.route('/acknowledgment/<int:id>/review', methods=['POST'])
@login_required
def review_acknowledgment(id):
    if current_user.role not in ['RIM Team', 'Admin']:
        flash('You do not have permission to review acknowledgments.', 'error')
        return redirect(url_for('dashboard'))
    
    acknowledgment = Acknowledgment.query.get_or_404(id)
    action = request.form.get('action')
    
    if action == 'approve':
        acknowledgment.status = 'Approved'
        acknowledgment.approved_at = datetime.utcnow()
        message = 'Acknowledgment approved successfully!'
        
        # Notify GP
        notification = Notification(
            recipient_id=acknowledgment.gp_id,
            title='Acknowledgment Approved',
            message='Your RIM acknowledgment has been approved.',
            notification_type='success',
            acknowledgment_id=acknowledgment.id
        )
        db.session.add(notification)
        
    elif action == 'request_revision':
        acknowledgment.status = 'Needs Revision'
        comments = request.form.get('comments', '')
        message = 'Revision requested successfully!'
        
        # Notify GP
        notification = Notification(
            recipient_id=acknowledgment.gp_id,
            title='Acknowledgment Requires Revision',
            message=f'Your RIM acknowledgment requires revision. Comments: {comments}',
            notification_type='warning',
            acknowledgment_id=acknowledgment.id
        )
        db.session.add(notification)
    
    db.session.commit()
    log_audit(current_user.id, f'Acknowledgment {action.replace("_", " ").title()}', 
              'Acknowledgment', acknowledgment.id, f'Acknowledgment {action}')
    
    flash(message, 'success')
    return redirect(url_for('dashboard'))

# Department management
@app.route('/departments')
def departments():
    from utils import format_date, format_datetime
    departments = Department.query.order_by(Department.name).all()
    return render_template('departments.html', departments=departments, utils={'format_date': format_date, 'format_datetime': format_datetime})

@app.route('/department/new')
@app.route('/department/<int:id>/edit')
def department_form(id=None):
    department = Department.query.get_or_404(id) if id else None
    form = DepartmentForm()
    
    if request.method == 'GET' and department:
        form.name.data = department.name
        form.description.data = department.description
    
    return render_template('department_form.html', form=form, department=department)

@app.route('/department/save', methods=['POST'])
@app.route('/department/<int:id>/save', methods=['POST'])
def save_department(id=None):
    
    form = DepartmentForm()
    if not form.validate_on_submit():
        department = Department.query.get_or_404(id) if id else None
        return render_template('department_form.html', form=form, department=department)
    
    if id:
        department = Department.query.get_or_404(id)
        action = 'updated'
    else:
        department = Department()
        action = 'created'
        db.session.add(department)
    
    department.name = form.name.data
    department.description = form.description.data
    
    db.session.commit()
    log_audit(current_user.id, f'Department {action.title()}', 'Department', 
              department.id, f'Department {action}')
    
    flash(f'Department {action} successfully!', 'success')
    return redirect(url_for('departments'))

@app.route('/department/<int:id>/delete', methods=['POST'])
@login_required
def delete_department(id):
    if current_user.role != 'Admin':
        flash('You do not have permission to delete departments.', 'error')
        return redirect(url_for('departments'))
    
    department = Department.query.get_or_404(id)
    
    # Check if department has users or acknowledgments
    if department.users or department.acknowledgments.count() > 0:
        flash('Cannot delete department with existing users or acknowledgments.', 'error')
        return redirect(url_for('departments'))
    
    db.session.delete(department)
    db.session.commit()
    
    log_audit(current_user.id, 'Department Deleted', 'Department', id, 
              f'Department "{department.name}" deleted')
    flash('Department deleted successfully!', 'success')
    return redirect(url_for('departments'))

# User management
@app.route('/users')
def users():
    users = User.query.order_by(User.last_name, User.first_name).all()
    return render_template('users.html', users=users)

@app.route('/user/new')
@app.route('/user/<int:id>/edit')
def user_form(id=None):
    user = User.query.get_or_404(id) if id else None
    form = UserForm()
    
    if request.method == 'GET' and user:
        form.username.data = user.username
        form.email.data = user.email
        form.first_name.data = user.first_name
        form.last_name.data = user.last_name
        form.role.data = user.role
        form.department_id.data = user.department_id or 0
        form.is_active.data = user.is_active
    
    return render_template('user_form.html', form=form, user=user)

@app.route('/user/save', methods=['POST'])
@app.route('/user/<int:id>/save', methods=['POST'])
@login_required
def save_user(id=None):
    if current_user.role != 'Admin':
        flash('You do not have permission to manage users.', 'error')
        return redirect(url_for('users'))
    
    form = UserForm()
    if not form.validate_on_submit():
        user = User.query.get_or_404(id) if id else None
        return render_template('user_form.html', form=form, user=user)
    
    if id:
        user = User.query.get_or_404(id)
        action = 'updated'
    else:
        user = User()
        action = 'created'
        db.session.add(user)
    
    user.username = form.username.data
    user.email = form.email.data
    user.first_name = form.first_name.data
    user.last_name = form.last_name.data
    user.role = form.role.data
    user.department_id = form.department_id.data if form.department_id.data > 0 else None
    user.is_active = form.is_active.data
    
    # Only update password if provided
    if form.password.data:
        user.password_hash = generate_password_hash(form.password.data)
    
    db.session.commit()
    log_audit(current_user.id, f'User {action.title()}', 'User', 
              user.id, f'User {action}')
    
    flash(f'User {action} successfully!', 'success')
    return redirect(url_for('users'))

# File download
@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# Notifications
@app.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(recipient_id=current_user.id)\
                                    .order_by(Notification.created_at.desc()).all()
    
    # Mark all as read
    Notification.query.filter_by(recipient_id=current_user.id, is_read=False)\
                     .update({'is_read': True})
    db.session.commit()
    
    return render_template('notifications.html', notifications=notifications)

# Audit trail
@app.route('/audit')
@login_required
def audit_trail():
    if current_user.role not in ['RIM Team', 'Admin']:
        flash('You do not have permission to view audit logs.', 'error')
        return redirect(url_for('dashboard'))
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('audit_trail.html', logs=logs)

# Export to PDF
@app.route('/export/pdf')
@login_required
def export_pdf():
    if current_user.role not in ['RIM Team', 'Admin']:
        flash('You do not have permission to export data.', 'error')
        return redirect(url_for('dashboard'))
    
    acknowledgments = Acknowledgment.query.all()
    pdf_file = generate_pdf_report(acknowledgments)
    
    return send_from_directory('reports', pdf_file, as_attachment=True)

# Compliance Report
@app.route('/compliance/report')
def compliance_report():
    # Get compliance statistics
    total_acknowledgments = Acknowledgment.query.count()
    approved_count = Acknowledgment.query.filter_by(status='Approved').count()
    pending_count = Acknowledgment.query.filter_by(status='Submitted').count()
    overdue_count = Acknowledgment.query.filter_by(status='Needs Revision').count()
    
    # Get department statistics
    dept_stats = []
    departments = Department.query.all()
    for dept in departments:
        dept_acks = Acknowledgment.query.filter_by(department_id=dept.id).count()
        dept_approved = Acknowledgment.query.filter_by(department_id=dept.id, status='Approved').count()
        compliance_rate = (dept_approved / dept_acks * 100) if dept_acks > 0 else 0
        
        dept_stats.append({
            'department': dept.name,
            'total_acknowledgments': dept_acks,
            'approved': dept_approved,
            'compliance_rate': round(compliance_rate, 1)
        })
    
    overall_compliance = (approved_count / total_acknowledgments * 100) if total_acknowledgments > 0 else 0
    
    return render_template('compliance_report.html', 
                         total_acknowledgments=total_acknowledgments,
                         approved_count=approved_count,
                         pending_count=pending_count,
                         overdue_count=overdue_count,
                         overall_compliance=round(overall_compliance, 1),
                         dept_stats=dept_stats)

# Status-based acknowledgment views
@app.route('/acknowledgments/new')
def new_acknowledgments():
    form = SearchForm()
    acknowledgments = Acknowledgment.query.filter_by(status='Not Started')
    
    # Apply search filters
    if form.search.data:
        acknowledgments = acknowledgments.filter(
            or_(
                Acknowledgment.signature_name.contains(form.search.data),
                Acknowledgment.business_activity_folder_location.contains(form.search.data)
            )
        )
    
    if form.department.data and form.department.data != 0:
        acknowledgments = acknowledgments.filter_by(department_id=form.department.data)
    
    acknowledgments = acknowledgments.order_by(Acknowledgment.created_at.desc()).all()
    
    return render_template('status_list.html', 
                         acknowledgments=acknowledgments,
                         form=form,
                         status='Not Started',
                         title='New Acknowledgments',
                         utils=utils)

@app.route('/acknowledgments/in-progress')
def in_progress():
    form = SearchForm()
    acknowledgments = Acknowledgment.query.filter_by(status='In Progress')
    
    # Apply search filters
    if form.search.data:
        acknowledgments = acknowledgments.filter(
            or_(
                Acknowledgment.signature_name.contains(form.search.data),
                Acknowledgment.business_activity_folder_location.contains(form.search.data)
            )
        )
    
    if form.department.data and form.department.data != 0:
        acknowledgments = acknowledgments.filter_by(department_id=form.department.data)
    
    acknowledgments = acknowledgments.order_by(Acknowledgment.created_at.desc()).all()
    
    return render_template('status_list.html', 
                         acknowledgments=acknowledgments,
                         form=form,
                         status='In Progress',
                         title='In Progress Acknowledgments',
                         utils=utils)

@app.route('/acknowledgments/submitted')
def submitted():
    form = SearchForm()
    acknowledgments = Acknowledgment.query.filter_by(status='Submitted')
    
    # Apply search filters
    if form.search.data:
        acknowledgments = acknowledgments.filter(
            or_(
                Acknowledgment.signature_name.contains(form.search.data),
                Acknowledgment.business_activity_folder_location.contains(form.search.data)
            )
        )
    
    if form.department.data and form.department.data != 0:
        acknowledgments = acknowledgments.filter_by(department_id=form.department.data)
    
    acknowledgments = acknowledgments.order_by(Acknowledgment.submitted_at.desc()).all()
    
    return render_template('status_list.html', 
                         acknowledgments=acknowledgments,
                         form=form,
                         status='Submitted',
                         title='Submitted Acknowledgments',
                         utils=utils)

@app.route('/acknowledgments/approved')
def approved():
    form = SearchForm()
    acknowledgments = Acknowledgment.query.filter_by(status='Approved')
    
    # Apply search filters
    if form.search.data:
        acknowledgments = acknowledgments.filter(
            or_(
                Acknowledgment.signature_name.contains(form.search.data),
                Acknowledgment.business_activity_folder_location.contains(form.search.data)
            )
        )
    
    if form.department.data and form.department.data != 0:
        acknowledgments = acknowledgments.filter_by(department_id=form.department.data)
    
    acknowledgments = acknowledgments.order_by(Acknowledgment.approved_at.desc()).all()
    
    return render_template('status_list.html', 
                         acknowledgments=acknowledgments,
                         form=form,
                         status='Approved',
                         title='Approved Acknowledgments',
                         utils=utils)

@app.route('/departments/bulk-delete', methods=['POST'])
def bulk_delete_departments():
    try:
        data = request.get_json()
        department_ids = data.get('department_ids', [])
        
        if not department_ids:
            return jsonify({'success': False, 'message': 'No departments selected'})
        
        # Convert string IDs to integers
        department_ids = [int(id) for id in department_ids]
        
        # Find departments and check constraints
        departments = Department.query.filter(Department.id.in_(department_ids)).all()
        
        blocked_departments = []
        for dept in departments:
            if dept.users or dept.acknowledgments.count() > 0:
                blocked_departments.append(dept.name)
        
        if blocked_departments:
            return jsonify({
                'success': False, 
                'message': f'Cannot delete departments with assigned users or acknowledgments: {", ".join(blocked_departments)}'
            })
        
        # Delete departments
        deleted_count = 0
        for dept in departments:
            db.session.delete(dept)
            deleted_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} department(s)'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# API endpoints for AJAX
@app.route('/api/notifications/count')
def notification_count():
    # Return 0 for demo mode (no authentication)
    return jsonify({'count': 0})
