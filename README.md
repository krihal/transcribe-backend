# scribe-backend

Backend built on FastAPI for the Sunet transcription service (Sunet Scribe).

## Author

This project is developed by [Sunet](https://www.sunet.se). Contributor: Kristofer Hallin.

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

Copyright (c) 2025-2026 Sunet. Contributor: Kristofer Hallin.

## Third-party Notices

This repository includes a `NOTICE` file containing attribution
information for third-party components.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## Features

- **Transcription Jobs**: Create, manage, and track audio/video transcription jobs
- **User Management**: Multi-tenant user system with realms, groups, and role-based access
- **OIDC Authentication**: OpenID Connect integration for secure authentication
- **Email Notifications**: Automated notifications for job status updates
- **File Encryption**: RSA-based encryption for secure file storage
- **External Integrations**: Support for Kaltura and other external services
- **Database Migrations**: Alembic-powered schema migrations

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (recommended package manager)
- PostgreSQL (production) or SQLite (development)

## Development Environment Setup

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd scribe-backend
uv sync
```

### 2. Configure Environment Variables

Create a `.env` file in the project root with the following settings:

```env
# API configuration
API_DATABASE_URL="sqlite:///jobs.db"
API_DEBUG=True
API_PREFIX="/api/v1"
API_VERSION="0.1.0"
API_TITLE="Sunet Scribe REST backend"
API_DESCRIPTION="A REST API for the Sunet Scribe service."
API_FILE_STORAGE_DIR=<Your file storage directory>
API_SECRET_KEY=<Your secret key>
API_CLIENT_VERIFICATION_ENABLED=True
API_CLIENT_VERIFICATION_HEADER="x-client-legacy"
API_WORKER_CLIENT_DN=<Your worker client DN>
API_KALTURA_CLIENT_DN=<Your Kaltura client DN>
API_PRIVATE_KEY_PASSWORD=<Your private key password>

# SMTP configuration
API_SMTP_HOST=<Your SMTP host>
API_SMTP_PORT=<Your SMTP port>
API_SMTP_USERNAME=<Your SMTP username>
API_SMTP_PASSWORD=<Your SMTP password>
API_SMTP_SENDER=<Your SMTP sender address>
API_SMTP_SSL=<True or False for SSL usage>

# OIDC configuration
OIDC_CLIENT_ID=<Your OIDC client ID>
OIDC_CLIENT_SECRET=<Your OIDC client secret>
OIDC_METADATA_URL=<Your OIDC provider metadata URL>
OIDC_SCOPE=openid,profile,email
OIDC_REFRESH_URI=<Your token refresh endpoint>
OIDC_REDIRECT_URI=<Your OIDC redirect endpoint>
OIDC_FRONTEND_URI=<Your frontend application URI>
```

### 3. Run the Application

```bash
uv run uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

## API Documentation

Once the application is running, access the interactive API documentation:

- **Swagger UI**: `http://localhost:8000/api/docs`
- **OpenAPI Spec**: `http://localhost:8000/api/openapi.json`

### API Endpoints

| Tag | Description |
|-----|-------------|
| `/api/v1/transcriber` | Transcription operations |
| `/api/v1/job` | Job management operations |
| `/api/v1/user` | User management operations |
| `/api/v1/external` | External service operations |
| `/api/v1/healthcheck` | Health check operations |
| `/api/v1/admin` | Administrative operations |

### Authentication Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/login` | Initiate OIDC login flow |
| `/api/auth` | OIDC callback endpoint |
| `/api/logout` | Logout and redirect to frontend |
| `/api/refresh` | Refresh access token |

## Database

### Migrations with Alembic

Run database migrations:

```bash
uv run alembic upgrade head
```

Create a new migration:

```bash
uv run alembic revision --autogenerate -m "Description of changes"
```

### Database Models

- **Job**: Transcription job with status tracking, language settings, and output format
- **JobResult**: Stores transcription results (JSON and SRT formats)
- **User**: User accounts with encryption keys and notification preferences
- **Group**: User groups with quotas and model access permissions
- **Customer**: Customer organizations with pricing plans
- **Model**: Available transcription model types

## Docker

Build and run with Docker:

```bash
docker build -t scribe-backend .
docker run -p 8000:8000 --env-file .env scribe-backend
```

## Testing

Run tests with pytest:

```bash
uv run pytest
```

## Project Structure

```
scribe-backend/
├── app.py              # FastAPI application entry point
├── alembic/            # Database migrations
├── auth/               # Authentication (OIDC, client verification)
├── db/                 # Database models and operations
├── routers/            # API route handlers
├── utils/              # Utilities (crypto, logging, settings)
└── tests/              # Test files
```
