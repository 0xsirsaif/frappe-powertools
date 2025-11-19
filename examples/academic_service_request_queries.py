"""
Query examples for AcademicServiceRequestModel using the ORM.

Note: To use the `.objects` manager, add the `@attach_manager` decorator:

    from frappe_powertools.orm import attach_manager
    
    @attach_manager
    class AcademicServiceRequestModel(DocModel):
        ...
"""

from frappe_powertools.orm import DocModel, query_for, attach_manager
from medad_eservices.medad_eservices.doctype.academic_service_request.academic_service_request import (
    AcademicServiceRequestModel,
    ServiceRequestAttachmentItem,
)


# ============================================================================
# Basic Queries
# ============================================================================

# Get all requests for a specific service
def get_requests_by_service(service_name: str):
    """Get all requests for a specific service."""
    return (
        AcademicServiceRequestModel.objects.filter(service=service_name).all()
    )


# Get a single request by name
def get_request_by_name(request_name: str):
    """Get a single request by its name."""
    return (
        AcademicServiceRequestModel.objects.filter(name=request_name).first()
    )


# Get requests by user
def get_requests_by_user(user_email: str):
    """Get all requests for a specific user."""
    return (
        AcademicServiceRequestModel.objects
        .filter(user=user_email)
        .order_by("-creation")
        .all()
    )


# Get requests by unique_id (student ID)
def get_requests_by_student(unique_id: str):
    """Get all requests for a specific student (by unique_id)."""
    return (
        AcademicServiceRequestModel.objects.filter(unique_id=unique_id).order_by("-creation").all()
    )


# ============================================================================
# Filtering by Status
# ============================================================================

# Get requests by status
def get_requests_by_status(status: str):
    """Get all requests with a specific status."""
    return (
        AcademicServiceRequestModel.objects.filter(request_status=status).all()
    )


# Get paid requests
def get_paid_requests():
    """Get all paid requests."""
    return (
        AcademicServiceRequestModel.objects
        .filter(is_paid=True)
        .all()
    )


# Get completed requests
def get_completed_requests():
    """Get all requests that are submission complete."""
    return (
        AcademicServiceRequestModel.objects
        .filter(request_submission_complete=True)
        .all()
    )


# ============================================================================
# Combining Filters
# ============================================================================

# Get user's requests for a specific service
def get_user_service_requests(user_email: str, service_name: str):
    """Get a user's requests for a specific service."""
    return (
        AcademicServiceRequestModel.objects
        .filter(user=user_email, service=service_name)
        .order_by("-creation")
        .all()
    )


# Get requests by service and status
def get_service_requests_by_status(service_name: str, status: str):
    """Get requests for a service with a specific status."""
    return (
        AcademicServiceRequestModel.objects
        .filter(service=service_name, request_status=status)
        .all()
    )


# Get unpaid requests for a specific service
def get_unpaid_service_requests(service_name: str):
    """Get unpaid requests for a specific service."""
    return (
        AcademicServiceRequestModel.objects
        .filter(service=service_name, is_paid=False)
        .all()
    )


# ============================================================================
# Using Prefetch for Child Tables
# ============================================================================

# Get request with attachments prefetched
def get_request_with_attachments(request_name: str):
    """Get a request with its attachments prefetched."""
    return (
        AcademicServiceRequestModel.objects
        .filter(name=request_name)
        .prefetch("attachments")
        .first()
    )


# Get multiple requests with attachments
def get_requests_with_attachments(service_name: str):
    """Get all requests for a service with attachments prefetched."""
    requests = (
        AcademicServiceRequestModel.objects
        .filter(service=service_name)
        .prefetch("attachments")
        .all()
    )
    
    # Access attachments like: request.attachments
    for request in requests:
        if request.attachments:
            print(f"Request {request.name} has {len(request.attachments)} attachments")
            for attachment in request.attachments:
                print(f"  - {attachment.file_name}: {attachment.attachment}")
    
    return requests


# ============================================================================
# Using select_related for Link Fields
# ============================================================================

# Get request with linked academic_term and financial_item
def get_request_with_links(request_name: str):
    """Get a request with linked fields (academic_term, financial_item) populated."""
    return (
        AcademicServiceRequestModel.objects
        .filter(name=request_name)
        .select_related("academic_term", "financial_item")
        .first()
    )


# Get requests with all related data
def get_requests_with_all_relations(service_name: str):
    """Get requests with child tables and linked fields."""
    return (
        AcademicServiceRequestModel.objects
        .filter(service=service_name)
        .prefetch("attachments")
        .select_related("academic_term", "financial_item")
        .order_by("-creation")
        .all()
    )


# ============================================================================
# Ordering and Limiting
# ============================================================================

# Get latest requests
def get_latest_requests(limit: int = 10):
    """Get the latest N requests."""
    return (
        AcademicServiceRequestModel.objects
        .order_by("-creation")
        .limit(limit)
        .all()
    )


# Get oldest unpaid requests
def get_oldest_unpaid_requests(limit: int = 5):
    """Get the oldest N unpaid requests."""
    return (
        AcademicServiceRequestModel.objects
        .filter(is_paid=False)
        .order_by("creation")
        .limit(limit)
        .all()
    )


# ============================================================================
# Complex Queries (Real-world Scenarios)
# ============================================================================

# Get user's pending requests with attachments
def get_user_pending_requests(user_email: str):
    """Get a user's pending (not complete) requests with attachments."""
    return (
        AcademicServiceRequestModel.objects
        .filter(user=user_email, request_submission_complete=False)
        .prefetch("attachments")
        .select_related("academic_term", "financial_item")
        .order_by("-creation")
        .all()
    )


# Get service requests for a specific academic term
def get_requests_by_academic_term(academic_term: str):
    """Get requests for a specific academic term with linked data."""
    return (
        AcademicServiceRequestModel.objects
        .filter(academic_term=academic_term)
        .select_related("academic_term", "financial_item")
        .all()
    )


# Get requests with financial transactions
def get_requests_with_transactions(service_name: str):
    """Get requests that have financial transactions."""
    return (
        AcademicServiceRequestModel.objects
        .filter(service=service_name)
        .filter(financial_transaction__isnull=False)  # Note: This requires custom filter support
        .select_related("financial_item")
        .all()
    )


# ============================================================================
# Using query_for() Helper (Alternative to .objects)
# ============================================================================

# Using query_for when .objects is not available
def get_requests_using_query_for(service_name: str):
    """Example using query_for() helper instead of .objects."""
    from frappe_powertools.orm import query_for
    
    query = query_for(AcademicServiceRequestModel)
    return (
        query
        .filter(service=service_name)
        .prefetch("attachments")
        .select_related("academic_term")
        .order_by("-creation")
        .all()
    )


# ============================================================================
# Working with Results
# ============================================================================

def example_working_with_results():
    """Example of how to work with query results."""
    # Get requests
    requests = (
        AcademicServiceRequestModel.objects
        .filter(service="SERVICE-001")
        .prefetch("attachments")
        .select_related("academic_term", "financial_item")
        .order_by("-creation")
        .limit(10)
        .all()
    )
    
    # Process results
    for request in requests:
        print(f"Request: {request.name}")
        print(f"  Service: {request.service}")
        print(f"  Status: {request.request_status}")
        print(f"  Academic Term: {request.academic_term}")
        print(f"  Financial Item: {request.financial_item}")
        print(f"  Is Paid: {request.is_paid}")
        print(f"  Submission Complete: {request.request_submission_complete}")
        
        # Access prefetched attachments
        if hasattr(request, "attachments") and request.attachments:
            print(f"  Attachments ({len(request.attachments)}):")
            for attachment in request.attachments:
                print(f"    - {attachment.file_name}: {attachment.attachment}")
        
        # Access extras (any fields not in the model)
        if request.extras:
            print(f"  Extra fields: {list(request.extras.keys())}")
        
        print()


# ============================================================================
# Pagination Pattern
# ============================================================================

def get_paginated_requests(page: int = 1, page_size: int = 20):
    """Example pagination pattern."""
    offset = (page - 1) * page_size
    
    # Note: ReadQuery doesn't have offset() yet, but you can use limit with offset calculation
    # For now, this is a conceptual example
    requests = (
        AcademicServiceRequestModel.objects
        .order_by("-creation")
        .limit(page_size)
        .all()
    )
    
    return requests


# ============================================================================
# Common Query Patterns from Existing Code
# ============================================================================

def get_user_service_requests_orm(user_email: str, service_name: str):
    """
    ORM equivalent of query_get_user_req() from queries/medad_eservices.py
    """
    return (
        AcademicServiceRequestModel.objects
        .filter(service=service_name, user=user_email)
        .prefetch("attachments")
        .select_related("academic_term", "financial_item")
        .order_by("-creation")
        .all()
    )


def get_user_requests_by_term_orm(user_email: str, unique_id: str, academic_term: str = None):
    """
    ORM equivalent of query_get_user_service_requests() from queries/medad_eservices.py
    """
    query = (
        AcademicServiceRequestModel.objects
        .filter(user=user_email) | AcademicServiceRequestModel.objects.filter(unique_id=unique_id)
    )
    
    # Note: OR filter requires custom support, this is conceptual
    # For now, you might need to do two queries and combine
    
    if academic_term:
        query = query.filter(academic_term=academic_term)
    
    return query.order_by("-creation").all()


# ============================================================================
# Usage in API/Background Jobs
# ============================================================================

def process_unpaid_requests():
    """Example: Process unpaid requests in a background job."""
    unpaid_requests = (
        AcademicServiceRequestModel.objects
        .filter(is_paid=False)
        .select_related("financial_item")
        .order_by("creation")
        .all()
    )
    
    for request in unpaid_requests:
        # Process payment logic
        print(f"Processing payment for request {request.name}")
        print(f"  Financial Item: {request.financial_item}")
        print(f"  User: {request.user}")
        # ... payment processing logic ...


def get_requests_for_reporting(academic_term: str, service_name: str = None):
    """Example: Get requests for reporting/analytics."""
    query = (
        AcademicServiceRequestModel.objects
        .filter(academic_term=academic_term)
        .prefetch("attachments")
        .select_related("academic_term", "financial_item")
    )
    
    if service_name:
        query = query.filter(service=service_name)
    
    return query.order_by("-creation").all()

