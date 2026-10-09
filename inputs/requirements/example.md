# Air System - Project Management Module

## Overview
The air system is a web-based management platform for managing air quality
monitoring projects. Users can create, edit, and view projects, as well as
configure system settings.

## Features

### 1. Login
- URL: http://cloud.air-sys.com:27056
- Username/password authentication
- Session timeout after 30 minutes of inactivity

### 2. Dashboard
- Shows total project count, active projects, alerts
- Quick links to recent projects
- Charts showing air quality trends

### 3. Project List
- Table displaying all projects with columns: Name, Status, Creator, Created Date
- Filter by status (active/archived/all)
- Search by project name
- Pagination (20 items per page)
- Click project name to enter project detail

### 4. Create Project
- Form fields: Project Name (required), Description, Location, Monitor Type (dropdown)
- Submit and Cancel buttons
- Name must be unique, max 50 characters

### 5. System Configuration
- Admin only access
- Settings: Alert thresholds, Data retention period, Export format
- Save button with confirmation dialog
