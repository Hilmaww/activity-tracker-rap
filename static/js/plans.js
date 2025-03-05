// Site selection and management
class PlanManager {
    constructor() {
        this.initializeEventListeners();
        this.initializeSelect2();
        this.setupFormValidation();
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

    addNewSiteRow() {
        const siteCount = $('.planned-site').length;
        $('#planned-sites').append(this.getSiteRowTemplate(siteCount + 1));
        
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
        
        if (value > 1440) {
            input.val(1440);
            toastr.warning('Maximum duration is 24 hours');
        }
    }

    handleAjaxError(xhr) {
        toastr.error(xhr.responseJSON?.message || 'Action failed');
    }

    validateForm(event) {
        const isValid = this.isFormValid();
        const totalDuration = this.getTotalDuration();

        if (!isValid) {
            event.preventDefault();
            toastr.error('Please fill in all required fields');
            return false;
        }
        
        if (totalDuration > 480) {
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

    initializeSelect2ForElement(element) {
        $(element).select2({
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

    getSiteRowTemplate(siteCount) {
        return `
            <div class="planned-site">
                <div class="form-group">
                    <label for="site-select-${siteCount}">Site</label>
                    <select class="site-select" id="site-select-${siteCount}" name="site_id[]"></select>
                </div>
                <div class="form-group">
                    <label for="planned_actions_${siteCount}">Planned Actions</label>
                    <textarea name="planned_actions[]" class="form-control" id="planned_actions_${siteCount}"></textarea>
                </div>
                <div class="form-group">
                    <label for="duration_${siteCount}">Duration (minutes)</label>
                    <input type="number" name="duration[]" class="form-control" id="duration_${siteCount}" min="15" max="480" value="15">
                </div>
                <button type="button" class="remove-site btn btn-danger">Remove</button>
                <div class="drag-handle">Drag</div>
                <div class="visit-order">${siteCount}</div>
            </div>
        `;
    }

    setupFormValidation() {
        // Validate duration inputs on change
        $(document).on('change', 'input[name="duration[]"]', (e) => this.validateDuration(e));

        // Validate form on submit
        $('#plan-form').on('submit', (e) => this.validateForm(e));

    }

}

// Initialize on document ready
$(document).ready(() => {
    if ($('#plan-form').length) {
        window.planManager = new PlanManager();
    }

    // Initialize Select2 for site selection
    $('.site-select').select2({
        theme: 'bootstrap-5',
        placeholder: 'Search for a site...'
    });

    $('#add-site').off('click').on('click', function() {
        const newSite = $('.planned-site:first').clone();
        newSite.find('input, textarea').val(''); // Clear input values
        newSite.find('.select2').remove(); // Remove previous Select2 instance
        newSite.find('select').val(''); // Reset select value
        $('#planned-sites').append(newSite); // Append the new site

        // Reinitialize Select2 for the new site
        newSite.find('.site-select').select2({
            theme: 'bootstrap-5',
            placeholder: 'Search for a site...'
        });
    });

    $(document).on('click', '.remove-site', function() {
        if ($('.planned-site').length > 1) {
            $(this).closest('.planned-site').remove();
        }
    });
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
        error: this.handleAjaxError
    });
} 