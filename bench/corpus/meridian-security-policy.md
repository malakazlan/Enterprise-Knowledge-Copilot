# Meridian Dynamics — Security Policy

## Authentication

Passwords must be at least 14 characters long. Multi-factor authentication is
mandatory for all systems that support it, without exception.

## Incident response

A SEV-1 incident (customer-facing outage or suspected breach) requires paging
the on-call engineer within 5 minutes of detection. The incident commander
must post a status update every 30 minutes until resolution.

## Backups

Production databases are backed up nightly at 02:00 UTC. Backups are retained
for 35 days and restore drills are performed quarterly.

## Devices

Company laptops are encrypted with full-disk encryption. Lost or stolen
devices must be reported to security@meridian.example within 4 hours.
