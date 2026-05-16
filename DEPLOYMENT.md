# Deployment

## Docker Compose (recommended)

1. Create a .env file at the repo root with your API keys and secrets (see .env.example).
2. Build and start the stack:
   - docker compose up --build

The API will be available at http://localhost:8000 and the frontend at http://localhost:3000.

## Environment variables

Frontend:

- NEXT_PUBLIC_API_BASE (default in compose: http://localhost:8000/api)
- NEXT_PUBLIC_WS_BASE (default in compose: ws://localhost:8000/ws/pipeline)

Backend:

- See .env.example for required API keys and secrets.

## Notes

- Output artifacts are persisted to ./output and temporary assets to ./temp.
- The SQLite database is stored in ./state.db and mounted into the container.
