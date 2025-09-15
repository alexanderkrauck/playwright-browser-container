# Generic Auto-Deployment CI for Docker Compose Projects

This directory contains scripts for automated deployment of any Docker Compose project when changes are made to the repository.

## Features

- **🚀 Fully Generic**: Works with any Docker Compose project
- **🔍 Auto-Detection**: Automatically detects project name, container names, and ports
- **🌍 Multi-Environment**: Supports prod/dev/staging environments
- **💚 Health Checks**: Automatic service health verification
- **📝 Comprehensive Logging**: Detailed deployment logs with timestamps
- **🔄 Smart Cleanup**: Configurable image retention and cleanup

## Files

### `auto-deploy.sh`
Main deployment script that:
- Auto-detects project configuration from directory structure
- Rebuilds Docker containers using docker-compose
- Restarts services with zero-downtime deployment
- Performs automatic health checks on exposed ports
- Logs all deployment activities with timestamps

### `config.env`
Configuration file with deployment settings:
- Branch deployment rules
- Health check endpoints (auto-detected if not specified)
- Container settings and cleanup policies
- Logging and notification preferences

## Quick Start

1. **Copy the `.ci` directory** to your Docker Compose project root
2. **Make the script executable**: `chmod +x .ci/auto-deploy.sh`
3. **Deploy**: `./.ci/auto-deploy.sh`

That's it! The script will auto-detect your project configuration.

## Usage

### Manual Deployment
```bash
# Deploy current branch
./.ci/auto-deploy.sh

# Deploy specific branch
./.ci/auto-deploy.sh main
```

### Automatic Deployment
The script can be triggered automatically via:
- Git hooks (post-commit, post-receive)
- CI/CD pipelines (GitHub Actions, GitLab CI)
- Cron jobs for scheduled deployments
- File watchers for development

## Auto-Detection Features

The script automatically detects:
- **Project Name**: From directory name
- **Container Names**: From docker-compose.yml service names
- **Health Check Ports**: From docker-compose.yml port mappings
- **Environment**: Based on git branch

## Configuration

Edit `config.env` to customize:
- Which branches trigger deployment (`DEPLOY_ON_BRANCHES`)
- Health check URLs (`HEALTH_CHECK_URLS`)
- Docker build options (`DOCKER_BUILD_NO_CACHE`, `DOCKER_BUILD_PULL`)
- Image cleanup policy (`KEEP_OLD_IMAGES`)
- Logging and notification settings

## Logs

Deployment logs are stored in `.ci/logs/` with timestamps:
- `deploy-YYYYMMDD-HHMMSS.log`
- Includes build output, deployment status, and health checks
- Configurable retention period

## Health Checks

After deployment, the script automatically:
1. Verifies containers are running
2. Tests all exposed ports from docker-compose.yml
3. Checks custom health check URLs (if configured)
4. Reports service availability

## Environment Support

Supports multiple environments based on git branch:
- `main/master` → Production environment
- `develop/development` → Development environment
- `staging` → Staging environment
- Other branches → Custom environments with branch suffix

## Example docker-compose.yml Support

Works with any docker-compose.yml structure:
```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"  # Auto-detected for health checks

  api:
    build: ./api
    ports:
      - "3000:3000"  # Auto-detected for health checks
```

## Integration Examples

### Git Hook (post-commit)
```bash
#!/bin/bash
./.ci/auto-deploy.sh
```

### GitHub Actions
```yaml
- name: Deploy
  run: ./.ci/auto-deploy.sh
```

### Cron Job
```bash
# Deploy every 5 minutes if changes detected
*/5 * * * * cd /path/to/project && git pull && ./.ci/auto-deploy.sh
```

## Troubleshooting

### Deployment Not Triggering
1. Check current branch: `git branch --show-current`
2. Verify branch is in config: `grep DEPLOY_ON_BRANCHES .ci/config.env`
3. Check script is executable: `ls -la .ci/auto-deploy.sh`

### Build Failures
1. Check deployment logs in `.ci/logs/`
2. Try manual build: `docker-compose build`
3. Check Docker daemon: `systemctl status docker`

### Container Not Starting
1. Check port conflicts: `ss -tulpn | grep [PORT]`
2. Review docker-compose.yml configuration
3. Check Docker logs: `docker logs [CONTAINER_NAME]`

## Advanced Configuration

### Custom Health Checks
```bash
# In config.env
HEALTH_CHECK_URLS="http://localhost:8000/health http://localhost:3000/api/status"
```

### Branch-Specific Settings
```bash
# In config.env - customize per branch
case "$BRANCH" in
    main|master)
        export CUSTOM_ENV_VAR="production"
        ;;
    develop)
        export CUSTOM_ENV_VAR="development"
        ;;
esac
```

### Notification Integration
```bash
# In config.env - uncomment to enable
# SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
# EMAIL_ON_FAILURE="admin@example.com"
```

## Clean Up

### Remove Old Logs
```bash
# Remove logs older than 30 days
find .ci/logs -name "*.log" -mtime +30 -delete
```

### Clean Docker Images
```bash
# Remove unused images (configured via KEEP_OLD_IMAGES)
docker image prune -f
```