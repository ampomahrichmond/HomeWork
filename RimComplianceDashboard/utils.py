import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import request, current_app
from flask_mail import Message
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from app import db, mail
from models import AuditLog

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}

def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_audit(user_id, action, resource_type=None, resource_id=None, details=None):
    """Log user actions for audit trail"""
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log audit: {e}")

def send_notification_email(recipient_email, subject, message):
    """Send email notification"""
    try:
        msg = Message(
            subject=f"RPA Magic - {subject}",
            recipients=[recipient_email],
            body=message,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        mail.send(msg)
        current_app.logger.info(f"Email sent to {recipient_email}")
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {e}")

def generate_pdf_report(acknowledgments):
    """Generate PDF report of acknowledgments"""
    try:
        # Create reports directory if it doesn't exist
        reports_dir = 'reports'
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = f"rim_acknowledgments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(reports_dir, filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title = Paragraph("RIM Acknowledgments Report", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 20))
        
        # Generate date
        generated_date = Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                                 styles['Normal'])
        elements.append(generated_date)
        elements.append(Spacer(1, 20))
        
        # Data table
        data = [['Department', 'GP Name', 'Status', 'Submitted Date', 'RIM Liaison']]
        
        for ack in acknowledgments:
            data.append([
                ack.department.name if ack.department else 'N/A',
                ack.gp_user.full_name if ack.gp_user else 'N/A',
                ack.status,
                ack.submitted_at.strftime('%Y-%m-%d') if ack.submitted_at else 'Not Submitted',
                ack.rim_liaison_user.full_name if ack.rim_liaison_user else 'Not Assigned'
            ])
        
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        current_app.logger.info(f"PDF report generated: {filename}")
        return filename
        
    except Exception as e:
        current_app.logger.error(f"Failed to generate PDF: {e}")
        return None

def format_date(date_obj):
    """Format date for display"""
    if date_obj:
        return date_obj.strftime('%Y-%m-%d')
    return 'N/A'

def format_datetime(datetime_obj):
    """Format datetime for display"""
    if datetime_obj:
        return datetime_obj.strftime('%Y-%m-%d %H:%M')
    return 'N/A'

def get_status_badge_class(status):
    """Get Bootstrap badge class for status"""
    status_classes = {
        'Not Started': 'bg-secondary',
        'In Progress': 'bg-warning text-dark',
        'Submitted': 'bg-info',
        'Approved': 'bg-success',
        'Needs Revision': 'bg-danger'
    }
    return status_classes.get(status, 'bg-secondary')

def truncate_text(text, length=50):
    """Truncate text to specified length"""
    if text and len(text) > length:
        return text[:length] + '...'
    return text or ''
