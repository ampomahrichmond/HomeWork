// RPA Magic - Main JavaScript File

// Global application object
window.RPAMagic = {
    version: '1.0.0',
    debug: true,
    
    // Configuration
    config: {
        notificationRefreshInterval: 30000, // 30 seconds
        autoSaveInterval: 60000, // 1 minute
        fadeInDuration: 300,
        toastDuration: 5000
    },
    
    // Initialize application
    init: function() {
        this.setupGlobalEventListeners();
        this.initializeComponents();
        this.startNotificationPolling();
        this.setupFormValidation();
        this.initializeTooltips();
        this.setupAutoSave();
        
        if (this.debug) {
            console.log('RPA Magic initialized successfully');
        }
    },
    
    // Setup global event listeners
    setupGlobalEventListeners: function() {
        // Handle page visibility changes
        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'visible') {
                RPAMagic.refreshNotifications();
            }
        });
        
        // Handle form submissions with loading states
        document.addEventListener('submit', function(e) {
            const form = e.target;
            if (form.tagName === 'FORM') {
                RPAMagic.handleFormSubmission(form);
            }
        });
        
        // Handle AJAX errors globally
        window.addEventListener('unhandledrejection', function(e) {
            RPAMagic.handleAjaxError(e.reason);
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            RPAMagic.handleKeyboardShortcuts(e);
        });
    },
    
    // Initialize components
    initializeComponents: function() {
        // Initialize Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
        // Initialize Bootstrap popovers
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function(popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
        
        // Initialize custom components
        this.initializeDatePickers();
        this.initializeFileUploads();
        this.initializeSearchBoxes();
        this.initializeDataTables();
    },
    
    // Notification system
    startNotificationPolling: function() {
        // Initial load
        this.refreshNotifications();
        
        // Set up polling
        setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.refreshNotifications();
            }
        }, this.config.notificationRefreshInterval);
    },
    
    refreshNotifications: function() {
        fetch('/api/notifications/count')
            .then(response => response.json())
            .then(data => {
                this.updateNotificationBadge(data.count);
            })
            .catch(error => {
                if (this.debug) {
                    console.error('Error refreshing notifications:', error);
                }
            });
    },
    
    updateNotificationBadge: function(count) {
        const badge = document.getElementById('notification-count');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
                badge.classList.add('animate__animated', 'animate__pulse');
            } else {
                badge.style.display = 'none';
                badge.classList.remove('animate__animated', 'animate__pulse');
            }
        }
    },
    
    // Form handling
    setupFormValidation: function() {
        // Custom validation for acknowledgment forms
        const ackForms = document.querySelectorAll('form[id*="acknowledgment"]');
        ackForms.forEach(form => {
            this.setupAcknowledgmentValidation(form);
        });
        
        // Real-time validation for all forms
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            const inputs = form.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                input.addEventListener('blur', function() {
                    RPAMagic.validateField(this);
                });
                
                input.addEventListener('input', function() {
                    if (this.classList.contains('is-invalid')) {
                        RPAMagic.validateField(this);
                    }
                });
            });
        });
    },
    
    setupAcknowledgmentValidation: function(form) {
        const submitButtons = form.querySelectorAll('button[type="submit"]');
        
        submitButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                const action = this.getAttribute('onclick') || '';
                
                if (action.includes('submit')) {
                    const isValid = RPAMagic.validateAcknowledgmentForm(form);
                    if (!isValid) {
                        e.preventDefault();
                        return false;
                    }
                    
                    // Show confirmation dialog
                    const confirmed = confirm(
                        'Are you sure you want to submit this acknowledgment? ' +
                        'Once submitted, you will not be able to edit it unless a revision is requested.'
                    );
                    
                    if (!confirmed) {
                        e.preventDefault();
                        return false;
                    }
                }
            });
        });
    },
    
    validateAcknowledgmentForm: function(form) {
        let isValid = true;
        const errors = [];
        
        // Check required acknowledgment checkbox
        const ackCheckbox = form.querySelector('#acknowledgment_statement');
        if (ackCheckbox && !ackCheckbox.checked) {
            this.showFieldError(ackCheckbox, 'You must acknowledge your responsibilities');
            errors.push('Acknowledgment statement is required');
            isValid = false;
        }
        
        // Check signature fields
        const signatureName = form.querySelector('#signature_name');
        if (signatureName && !signatureName.value.trim()) {
            this.showFieldError(signatureName, 'Digital signature is required');
            errors.push('Digital signature is required');
            isValid = false;
        }
        
        const signatureDate = form.querySelector('#signature_date');
        if (signatureDate && !signatureDate.value) {
            this.showFieldError(signatureDate, 'Signature date is required');
            errors.push('Signature date is required');
            isValid = false;
        }
        
        if (!isValid) {
            this.showToast('Please correct the form errors before submitting', 'error');
            // Scroll to first error
            const firstError = form.querySelector('.is-invalid');
            if (firstError) {
                firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                firstError.focus();
            }
        }
        
        return isValid;
    },
    
    validateField: function(field) {
        let isValid = true;
        const value = field.value.trim();
        
        // Remove existing validation classes
        field.classList.remove('is-valid', 'is-invalid');
        this.clearFieldError(field);
        
        // Check if field is required
        if (field.hasAttribute('required') && !value) {
            this.showFieldError(field, 'This field is required');
            isValid = false;
        }
        
        // Specific field type validations
        if (isValid && value) {
            switch (field.type) {
                case 'email':
                    isValid = this.validateEmail(value);
                    if (!isValid) {
                        this.showFieldError(field, 'Please enter a valid email address');
                    }
                    break;
                case 'password':
                    if (field.name === 'password' && value.length < 6) {
                        this.showFieldError(field, 'Password must be at least 6 characters long');
                        isValid = false;
                    }
                    break;
                case 'tel':
                    isValid = this.validatePhone(value);
                    if (!isValid) {
                        this.showFieldError(field, 'Please enter a valid phone number');
                    }
                    break;
            }
        }
        
        // Add validation class
        field.classList.add(isValid ? 'is-valid' : 'is-invalid');
        
        return isValid;
    },
    
    showFieldError: function(field, message) {
        field.classList.add('is-invalid');
        
        // Remove existing error message
        this.clearFieldError(field);
        
        // Add new error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback';
        errorDiv.textContent = message;
        field.parentNode.appendChild(errorDiv);
    },
    
    clearFieldError: function(field) {
        const existingError = field.parentNode.querySelector('.invalid-feedback');
        if (existingError) {
            existingError.remove();
        }
    },
    
    validateEmail: function(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },
    
    validatePhone: function(phone) {
        const phoneRegex = /^[\+]?[\d\s\-\(\)]{10,}$/;
        return phoneRegex.test(phone.replace(/\s/g, ''));
    },
    
    // Auto-save functionality
    setupAutoSave: function() {
        const forms = document.querySelectorAll('form[data-autosave="true"]');
        
        forms.forEach(form => {
            const formId = form.id || 'form_' + Math.random().toString(36).substr(2, 9);
            
            // Load saved data
            this.loadFormData(form, formId);
            
            // Setup auto-save
            const inputs = form.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                input.addEventListener('input', debounce(() => {
                    this.saveFormData(form, formId);
                }, 2000));
            });
        });
    },
    
    saveFormData: function(form, formId) {
        const formData = new FormData(form);
        const data = {};
        
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        localStorage.setItem('rpa_form_' + formId, JSON.stringify(data));
        
        if (this.debug) {
            console.log('Form data auto-saved for form:', formId);
        }
    },
    
    loadFormData: function(form, formId) {
        const savedData = localStorage.getItem('rpa_form_' + formId);
        
        if (savedData) {
            try {
                const data = JSON.parse(savedData);
                
                Object.keys(data).forEach(key => {
                    const field = form.querySelector(`[name="${key}"]`);
                    if (field && !field.value) {
                        if (field.type === 'checkbox') {
                            field.checked = data[key] === 'on';
                        } else {
                            field.value = data[key];
                        }
                    }
                });
                
                if (this.debug) {
                    console.log('Form data loaded for form:', formId);
                }
            } catch (e) {
                console.error('Error loading saved form data:', e);
            }
        }
    },
    
    clearSavedFormData: function(formId) {
        localStorage.removeItem('rpa_form_' + formId);
    },
    
    // Handle form submissions
    handleFormSubmission: function(form) {
        const submitButton = form.querySelector('button[type="submit"]:focus') || 
                           form.querySelector('button[type="submit"]');
        
        if (submitButton) {
            // Show loading state
            this.setButtonLoading(submitButton, true);
            
            // Clear auto-saved data on successful submission
            const formId = form.id || 'unknown';
            setTimeout(() => {
                this.clearSavedFormData(formId);
            }, 1000);
        }
    },
    
    setButtonLoading: function(button, loading) {
        if (loading) {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
            button.classList.add('loading');
        } else {
            button.disabled = false;
            button.classList.remove('loading');
            // Original text would need to be stored beforehand
        }
    },
    
    // Initialize date pickers
    initializeDatePickers: function() {
        const dateInputs = document.querySelectorAll('input[type="date"]');
        
        dateInputs.forEach(input => {
            // Set max date to today for signature dates
            if (input.name === 'signature_date') {
                const today = new Date().toISOString().split('T')[0];
                input.max = today;
                
                // Set default to today if empty
                if (!input.value) {
                    input.value = today;
                }
            }
        });
    },
    
    // Initialize file uploads
    initializeFileUploads: function() {
        const fileInputs = document.querySelectorAll('input[type="file"]');
        
        fileInputs.forEach(input => {
            input.addEventListener('change', function(e) {
                RPAMagic.handleFileUpload(this, e);
            });
        });
    },
    
    handleFileUpload: function(input, event) {
        const files = event.target.files;
        const maxSize = 16 * 1024 * 1024; // 16MB
        const allowedTypes = ['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'];
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            
            // Check file size
            if (file.size > maxSize) {
                this.showToast(`File "${file.name}" is too large. Maximum file size is 16MB.`, 'error');
                input.value = '';
                return;
            }
            
            // Check file type
            const extension = file.name.split('.').pop().toLowerCase();
            if (!allowedTypes.includes(extension)) {
                this.showToast(`File type "${extension}" is not allowed.`, 'error');
                input.value = '';
                return;
            }
        }
        
        // Show file preview
        this.showFilePreview(input, files);
    },
    
    showFilePreview: function(input, files) {
        const previewContainer = input.parentNode.querySelector('.file-preview') || 
                               this.createFilePreviewContainer(input);
        
        previewContainer.innerHTML = '';
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const fileItem = document.createElement('div');
            fileItem.className = 'file-preview-item d-flex align-items-center justify-content-between p-2 bg-light rounded mb-2';
            
            fileItem.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="fas fa-paperclip me-2 text-muted"></i>
                    <span class="file-name">${file.name}</span>
                    <small class="text-muted ms-2">(${this.formatFileSize(file.size)})</small>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            previewContainer.appendChild(fileItem);
        }
    },
    
    createFilePreviewContainer: function(input) {
        const container = document.createElement('div');
        container.className = 'file-preview mt-2';
        input.parentNode.insertBefore(container, input.nextSibling);
        return container;
    },
    
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    // Initialize search boxes
    initializeSearchBoxes: function() {
        const searchInputs = document.querySelectorAll('input[data-search-target]');
        
        searchInputs.forEach(input => {
            input.addEventListener('input', debounce(function() {
                const target = this.getAttribute('data-search-target');
                RPAMagic.performSearch(this.value, target);
            }, 300));
        });
    },
    
    performSearch: function(searchTerm, target) {
        const targetElement = document.querySelector(target);
        if (!targetElement) return;
        
        const searchableItems = targetElement.querySelectorAll('[data-searchable]');
        const term = searchTerm.toLowerCase();
        
        searchableItems.forEach(item => {
            const text = item.textContent.toLowerCase();
            const shouldShow = !term || text.includes(term);
            item.style.display = shouldShow ? '' : 'none';
        });
    },
    
    // Initialize data tables
    initializeDataTables: function() {
        const tables = document.querySelectorAll('table[data-sortable="true"]');
        
        tables.forEach(table => {
            this.makeSortable(table);
        });
    },
    
    makeSortable: function(table) {
        const headers = table.querySelectorAll('th[data-sortable]');
        
        headers.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', function() {
                RPAMagic.sortTable(table, this);
            });
            
            // Add sort icon
            const icon = document.createElement('i');
            icon.className = 'fas fa-sort ms-2';
            header.appendChild(icon);
        });
    },
    
    sortTable: function(table, header) {
        const columnIndex = Array.from(header.parentNode.children).indexOf(header);
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        const currentSort = header.getAttribute('data-sort') || 'asc';
        const newSort = currentSort === 'asc' ? 'desc' : 'asc';
        
        // Update header attributes and icons
        table.querySelectorAll('th').forEach(th => {
            th.removeAttribute('data-sort');
            const icon = th.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-sort ms-2';
            }
        });
        
        header.setAttribute('data-sort', newSort);
        const headerIcon = header.querySelector('i');
        if (headerIcon) {
            headerIcon.className = `fas fa-sort-${newSort === 'asc' ? 'up' : 'down'} ms-2`;
        }
        
        // Sort rows
        rows.sort((a, b) => {
            const aValue = a.children[columnIndex].textContent.trim();
            const bValue = b.children[columnIndex].textContent.trim();
            
            // Try to parse as numbers
            const aNum = parseFloat(aValue);
            const bNum = parseFloat(bValue);
            
            let comparison = 0;
            if (!isNaN(aNum) && !isNaN(bNum)) {
                comparison = aNum - bNum;
            } else {
                comparison = aValue.localeCompare(bValue);
            }
            
            return newSort === 'asc' ? comparison : -comparison;
        });
        
        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));
    },
    
    // Toast notifications
    showToast: function(message, type = 'info', duration = null) {
        duration = duration || this.config.toastDuration;
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        // Create toast container if it doesn't exist
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }
        
        toastContainer.appendChild(toast);
        
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: duration
        });
        
        bsToast.show();
        
        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', function() {
            this.remove();
        });
    },
    
    // Initialize tooltips
    initializeTooltips: function() {
        // Re-initialize tooltips for dynamically added content
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]:not([data-tooltip-initialized])'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            tooltipTriggerEl.setAttribute('data-tooltip-initialized', 'true');
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    },
    
    // Keyboard shortcuts
    handleKeyboardShortcuts: function(e) {
        // Ctrl/Cmd + S to save form
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            const activeForm = document.activeElement.closest('form');
            if (activeForm) {
                const saveButton = activeForm.querySelector('button[onclick*="save_draft"]') ||
                                 activeForm.querySelector('button[type="submit"]');
                if (saveButton) {
                    saveButton.click();
                }
            }
        }
        
        // Escape to close modals
        if (e.key === 'Escape') {
            const openModal = document.querySelector('.modal.show');
            if (openModal) {
                const modal = bootstrap.Modal.getInstance(openModal);
                if (modal) {
                    modal.hide();
                }
            }
        }
    },
    
    // AJAX error handling
    handleAjaxError: function(error) {
        if (this.debug) {
            console.error('AJAX Error:', error);
        }
        
        this.showToast('An error occurred while processing your request. Please try again.', 'error');
    },
    
    // Utility functions
    utils: {
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        throttle: function(func, limit) {
            let inThrottle;
            return function() {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },
        
        formatDate: function(date, format = 'YYYY-MM-DD') {
            if (!date) return '';
            
            const d = new Date(date);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            
            return format
                .replace('YYYY', year)
                .replace('MM', month)
                .replace('DD', day);
        }
    }
};

// Utility functions (global scope for backward compatibility)
function debounce(func, wait) {
    return RPAMagic.utils.debounce(func, wait);
}

function throttle(func, limit) {
    return RPAMagic.utils.throttle(func, limit);
}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    RPAMagic.init();
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RPAMagic;
}
