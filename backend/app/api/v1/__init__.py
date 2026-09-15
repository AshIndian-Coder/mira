"""API v1 routes.

This package contains all API v1 route handlers organized by domain:
- auth: Authentication and user management
- users: User CRUD operations
- ingestion: Material data upload and ingestion
- matching: AI-powered material matching
- review: Match review and approval workflow
- cnmc: CNMC code generation and management
- mapping: CPSE-to-CNMC mapping management
- dashboard: Analytics and statistics
- roi: ROI calculation and savings analysis
- audit: Audit trail and integrity verification
- sap: SAP integration endpoints
"""

from app.api.v1 import router
