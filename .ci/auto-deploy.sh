#!/bin/bash
# Generic auto-deploy script for Docker Compose projects
# Triggers on local git commits to rebuild and restart Docker container

set -e

# Auto-detect project configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
BRANCH=${1:-$(git rev-parse --abbrev-ref HEAD)}

# Auto-detect container name from docker-compose.yml
if [ -f "$PROJECT_DIR/docker-compose.yml" ]; then
    # Try to extract service name from docker-compose.yml
    CONTAINER_NAME=$(grep -E "^\s+[a-zA-Z0-9_-]+:" "$PROJECT_DIR/docker-compose.yml" | head -1 | sed 's/[[:space:]]*\([^:]*\):.*/\1/' || echo "$PROJECT_NAME")
else
    CONTAINER_NAME="$PROJECT_NAME"
fi

LOG_DIR="$PROJECT_DIR/.ci/logs"
LOG_FILE="$LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).log"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to log messages
log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

# Start logging
{
    log "========================================="
    log "Auto-deployment started for $PROJECT_NAME"
    log "Branch: $BRANCH"
    log "Container: $CONTAINER_NAME"
    log "========================================="
    
    # Load configuration if exists
    if [ -f "$PROJECT_DIR/.ci/config.env" ]; then
        source "$PROJECT_DIR/.ci/config.env"
        log "Configuration loaded from config.env"
    fi
    
    # Check if branch should trigger deployment
    DEPLOY_BRANCHES="${DEPLOY_ON_BRANCHES:-main develop}"
    if ! echo "$DEPLOY_BRANCHES" | grep -w "$BRANCH" > /dev/null; then
        log "Branch '$BRANCH' is not configured for auto-deployment"
        log "Configured branches: $DEPLOY_BRANCHES"
        exit 0
    fi
    
    # Branch-specific configuration
    case $BRANCH in
        main|master)
            CONTAINER_SUFFIX=""
            COMPOSE_PROJECT_NAME="${PROJECT_NAME}-prod"
            log "Deploying to PRODUCTION environment"
            ;;
        develop|development)
            CONTAINER_SUFFIX="-dev"
            COMPOSE_PROJECT_NAME="${PROJECT_NAME}-dev"
            log "Deploying to DEVELOPMENT environment"
            ;;
        staging)
            CONTAINER_SUFFIX="-staging"
            COMPOSE_PROJECT_NAME="${PROJECT_NAME}-staging"
            log "Deploying to STAGING environment"
            ;;
        *)
            CONTAINER_SUFFIX="-$BRANCH"
            COMPOSE_PROJECT_NAME="${PROJECT_NAME}-$BRANCH"
            log "Deploying to CUSTOM environment: $BRANCH"
            ;;
    esac
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Get current commit info
    COMMIT_HASH=$(git rev-parse --short HEAD)
    COMMIT_MSG=$(git log -1 --pretty=%B)
    log "Deploying commit: $COMMIT_HASH"
    log "Commit message: $COMMIT_MSG"
    
    # Store old container ID for cleanup
    OLD_CONTAINER=$(docker ps -aq -f name="^${CONTAINER_NAME}$" 2>/dev/null || true)
    
    # Build phase
    log "Building Docker image..."
    if docker-compose build 2>&1 | tee -a "$LOG_FILE"; then
        log "✓ Docker image built successfully"
    else
        log "✗ Docker build failed!"
        exit 1
    fi
    
    # Stop old container
    if [ -n "$OLD_CONTAINER" ]; then
        log "Stopping old container: $OLD_CONTAINER"
        docker-compose down 2>&1 | tee -a "$LOG_FILE"

        # Force remove container if it still exists
        if docker ps -aq -f name="^${CONTAINER_NAME}$" > /dev/null 2>&1; then
            log "Force removing container: $CONTAINER_NAME"
            docker rm -f "$CONTAINER_NAME" 2>&1 | tee -a "$LOG_FILE"
        fi

        # Wait for cleanup to complete
        sleep 2
        log "✓ Old container stopped"
    else
        log "No existing container found"
    fi
    
    # Start new container
    log "Starting new container..."
    if COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME" docker-compose up -d 2>&1 | tee -a "$LOG_FILE"; then
        log "✓ New container started"
    else
        log "✗ Failed to start new container!"
        exit 1
    fi
    
    # Wait for container to be healthy
    log "Waiting for container to be healthy..."
    sleep 5
    
    # Health check
    CONTAINER_ID=$(docker ps -q -f name="^${CONTAINER_NAME}$")
    if [ -n "$CONTAINER_ID" ]; then
        CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_ID")
        if [ "$CONTAINER_STATUS" = "running" ]; then
            log "✓ Container is running"

            # Auto-detect exposed ports from docker-compose.yml and run health checks
            if [ -f "$PROJECT_DIR/docker-compose.yml" ]; then
                # Extract external ports from port mappings like "8000:8000" or "\"8000:8000\""
                PORTS=$(grep -oE '[-"]*[0-9]+:[0-9]+' "$PROJECT_DIR/docker-compose.yml" | sed 's/[^0-9]*\([0-9]*\):.*/\1/' | sort -u || true)

                for port in $PORTS; do
                    if [ -n "$port" ] && [ "$port" -gt 0 ] 2>/dev/null; then
                        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" | grep -q "200\|301\|302\|404"; then
                            log "✓ Service on port $port is responding"
                        else
                            log "⚠ Service on port $port is not responding (this might be normal during startup)"
                        fi
                    fi
                done

                # Use configured health check URLs if available
                if [ -n "$HEALTH_CHECK_URLS" ]; then
                    for url in $HEALTH_CHECK_URLS; do
                        if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|301\|302\|404"; then
                            log "✓ Health check URL $url is responding"
                        else
                            log "⚠ Health check URL $url is not responding"
                        fi
                    done
                fi
            fi
        else
            log "✗ Container is not running properly. Status: $CONTAINER_STATUS"
            exit 1
        fi
    else
        log "✗ Container not found after deployment!"
        exit 1
    fi
    
    # Cleanup old images (keep last N images)
    if [ "${KEEP_OLD_IMAGES:-3}" -gt 0 ]; then
        log "Cleaning up old images (keeping last ${KEEP_OLD_IMAGES:-3})..."
        docker image prune -f 2>&1 | tee -a "$LOG_FILE"
    fi
    
    # Summary
    log "========================================="
    log "✓ Deployment completed successfully!"
    log "Project: $PROJECT_NAME"
    log "Branch: $BRANCH"
    log "Commit: $COMMIT_HASH"
    log "Container: $CONTAINER_NAME"
    log "Status: Running"
    log "========================================="

} 2>&1 | tee -a "$LOG_FILE"

# Send notification (optional - uncomment if you want desktop notifications)
# if command -v notify-send >/dev/null 2>&1; then
#     notify-send "$PROJECT_NAME Container Deployed" "Branch: $BRANCH\nCommit: $COMMIT_HASH"
# fi

exit 0