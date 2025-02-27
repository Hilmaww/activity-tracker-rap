// Site selection and management
class PlanManager {
    constructor() {
        this.initializeEventListeners();
        this.initializeSelect2();
        this.setupFormValidation();
        this.setupDragAndDrop();
    }

    initializeEventListeners() {
        // Add site button
        $('#add-site').on('click', () => this.addNewSiteRow());
        
        // Remove site button
        $(document).on('click', '.remove-site', (e) => this.removeSiteRow(e));
        
        // Duration input validation
        $(document).on('change', 'input[name="duration[]"]', (e) => this.validateDuration(e));
        
        // Form submission
        $('#plan-form').on('submit', (e) => this.validateForm(e));
        
        // Auto-save draft
        let timeout;
        $('#plan-form').on('input', () => {
            clearTimeout(timeout);
            timeout = setTimeout(() => this.autosaveDraft(), 2000);
        });
    }

    initializeSelect2() {
        $('.site-select').select2({
            theme: 'bootstrap-5',
            placeholder: 'Search for a site...',
            ajax: {
                url: '/api/sites/search',
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        term: params.term || '',
                        page: params.page || 1
                    };
                },
                processResults: function(data) {
                    return {
                        results: data.sites.map(site => ({
                            id: site.id,
                            text: `${site.site_id} - ${site.name}`,
                            location: site.location
                        })),
                        pagination: data.pagination
                    };
                },
                cache: true
            },
            minimumInputLength: 2,
            templateResult: this.formatSiteResult
        });
    }

    formatSiteResult(site) {
        if (!site.id) return site.text;
        
        return $(`
            <div class="site-result">
                <div class="site-name">${site.text}</div>
                ${site.location ? `
                    <small class="text-muted">
                        <i class="fas fa-map-marker-alt"></i> ${site.location}
                    </small>
                ` : ''}
            </div>
        `);
    }

    setupDragAndDrop() {
        $('#planned-sites').sortable({
            handle: '.drag-handle',
            update: (event, ui) => {
                this.updateVisitOrder();
                this.autosaveDraft();
            }
        });
    }

    addNewSiteRow() {
        const siteCount = $('.planned-site').length;
        const template = this.getSiteRowTemplate(siteCount + 1);
        $('#planned-sites').append(template);
        
        // Initialize Select2 for new row
        const newSelect = $('#planned-sites .planned-site:last-child .site-select');
        this.initializeSelect2ForElement(newSelect);
        
        // Smooth scroll to new row
        $('html, body').animate({
            scrollTop: newSelect.offset().top - 100
        }, 500);
    }

    removeSiteRow(event) {
        if ($('.planned-site').length > 1) {
            $(event.target).closest('.planned-site').fadeOut(300, function() {
                $(this).remove();
                this.updateVisitOrder();
                this.autosaveDraft();
            }.bind(this));
        } else {
            toastr.warning('At least one site is required');
        }
    }

    validateDuration(event) {
        const input = $(event.target);
        const value = parseInt(input.val());
        
        if (value < 15) {
            input.val(15);
            toastr.warning('Minimum duration is 15 minutes');
        }
        
        if (value > 480) {
            input.val(480);
            toastr.warning('Maximum duration is 480 minutes (8 hours)');
        }
    }

    autosaveDraft() {
        const formData = new FormData($('#plan-form')[0]);
        formData.append('auto_save', 'true');
        
        $.ajax({
            url: $('#plan-form').attr('action'),
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: (response) => {
                if (response.success) {
                    toastr.success('Draft saved');
                }
            },
            error: () => {
                toastr.error('Failed to save draft');
            }
        });
    }

    validateForm(event) {
        if (!this.isFormValid()) {
            event.preventDefault();
            toastr.error('Please fill in all required fields');
            return false;
        }
        
        if (this.getTotalDuration() > 480) {
            event.preventDefault();
            toastr.error('Total duration cannot exceed 8 hours');
            return false;
        }
        
        return true;
    }

    isFormValid() {
        let valid = true;
        
        // Check if date is selected and not in past
        const planDate = new Date($('#plan_date').val());
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        if (planDate < today) {
            valid = false;
            $('#plan_date').addClass('is-invalid');
        }
        
        // Validate each site row
        $('.planned-site').each(function() {
            const siteSelect = $(this).find('.site-select');
            const actions = $(this).find('textarea[name="planned_actions[]"]');
            const duration = $(this).find('input[name="duration[]"]');
            
            if (!siteSelect.val()) {
                valid = false;
                siteSelect.next('.select2').addClass('is-invalid');
            }
            
            if (!actions.val().trim()) {
                valid = false;
                actions.addClass('is-invalid');
            }
            
            if (!duration.val() || duration.val() < 15) {
                valid = false;
                duration.addClass('is-invalid');
            }
        });
        
        return valid;
    }

    getTotalDuration() {
        return Array.from(document.getElementsByName('duration[]'))
            .reduce((total, input) => total + (parseInt(input.value) || 0), 0);
    }

    updateVisitOrder() {
        $('.planned-site').each((index, element) => {
            $(element).find('.visit-order').text(index + 1);
        });
    }
}

// Initialize on document ready
$(document).ready(() => {
    if ($('#plan-form').length) {
        window.planManager = new PlanManager();
    }
});

// Handle plan approval/rejection
function handlePlanAction(planId, action) {
    const url = `/plans/${planId}/${action}`;
    const confirmMessages = {
        approve: 'Are you sure you want to approve this plan?',
        reject: 'Please provide a reason for rejection:'
    };
    
    if (action === 'reject') {
        Swal.fire({
            title: 'Reject Plan',
            input: 'textarea',
            inputLabel: confirmMessages[action],
            showCancelButton: true,
            inputValidator: (value) => {
                if (!value) {
                    return 'You need to provide a reason!';
                }
            }
        }).then((result) => {
            if (result.isConfirmed) {
                submitPlanAction(url, { reason: result.value });
            }
        });
    } else {
        Swal.fire({
            title: 'Confirm Action',
            text: confirmMessages[action],
            icon: 'question',
            showCancelButton: true
        }).then((result) => {
            if (result.isConfirmed) {
                submitPlanAction(url);
            }
        });
    }
}

function submitPlanAction(url, data = {}) {
    $.ajax({
        url: url,
        type: 'POST',
        data: data,
        headers: {
            'X-CSRFToken': $('meta[name="csrf-token"]').attr('content')
        },
        success: function(response) {
            toastr.success(response.message);
            setTimeout(() => window.location.reload(), 1500);
        },
        error: function(xhr) {
            toastr.error(xhr.responseJSON?.message || 'Action failed');
        }
    });
} 