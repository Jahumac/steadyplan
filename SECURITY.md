# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SteadyPlan, please report it responsibly by emailing the maintainer at [security@steadyplan.co.uk](mailto:security@steadyplan.co.uk).

We take all security issues seriously and will respond to valid reports within 48 hours. 

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |

## Security Enhancements

### Recent Security Fixes

1. **Input Validation Improvements** (v1.0.5)
   - Added explicit validation for all numeric parameters in API endpoints
   - Implemented proper type checking for account IDs to prevent type confusion attacks
   - Enhanced account ownership verification to prevent unauthorized access to user data

2. **Error Handling Enhancements**
   - Improved logging in error handlers for better debugging
   - Standardized error response formats across all endpoints

3. **Data Integrity Improvements**
   - Added checks to ensure accounts belong to authenticated users
   - Implemented robust parameter validation for all API endpoints

## Security Best Practices

### For Users
- Always run SteadyPlan on a secure, private network
- Use strong passwords for your accounts
- Keep your SteadyPlan instance updated with the latest security patches
- Regularly backup your data using the built-in export/restore functionality

### For Administrators
- Restrict network access to your SteadyPlan instance
- Consider using HTTPS with a reverse proxy for public access
- Monitor logs for suspicious activity
- Regularly review and rotate API tokens and assistant access credentials

## Known Security Considerations

### Network Exposure
SteadyPlan is designed for home network use. When exposing it publicly:
- Use HTTPS with a reverse proxy (e.g., Nginx, Traefik)
- Implement additional authentication layers
- Set `APP_ENV=production` for production deployments
- Use `TRUST_PROXY_HEADERS=1` if behind a reverse proxy

### Data Privacy
- Your financial database (`data/finance.db`) is stored locally and never leaves your machine
- No bank or broker linking is performed by default
- External price lookups (optional) only send ticker symbols, not account balances or transaction details

### Access Control
- Multi-user support allows for different access levels
- Assistant access tokens are scoped to specific endpoints and can be revoked
- Admin users manage access and permissions for all users

## Contact

For security-related questions, please contact:
- Email: [security@steadyplan.co.uk](mailto:security@steadyplan.co.uk)
- GitHub Issues: [https://github.com/Jahumac/steadyplan/issues](https://github.com/Jahumac/steadyplan/issues)