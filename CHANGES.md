# Changelog

## [1.0.5] - 2026-07-14

### Security Fixes

- **Input Validation Improvements**: Added explicit validation for all numeric parameters in API endpoints to prevent type confusion attacks
- **Account Ownership Verification**: Enhanced account access checks to prevent unauthorized access to user data
- **Error Handling**: Improved logging in error handlers for better debugging and monitoring
- **API Parameter Validation**: Added robust validation for account_id and item_id parameters in all API endpoints
- **Data Integrity**: Implemented checks to ensure accounts belong to authenticated users before operations

### Documentation

- Added SECURITY.md with comprehensive security policy and vulnerability reporting
- Updated README.md to include security information and link to SECURITY.md
- Added documentation about security best practices for users and administrators

### Code Quality

- Standardized validation helper functions for consistent parameter validation
- Improved consistency in error handling across API endpoints
- Enhanced code comments and documentation for security measures

[1.0.5]: https://github.com/Jahumac/steadyplan/compare/v1.0.4...v1.0.5