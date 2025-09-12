# Local CI/CD for Playwright Browser Container

This directory contains the local CI/CD automation for the playwright-browser-container project.

## Overview

When you commit to specific branches locally, the system automatically:
1. Detects the commit via Git hook
2. Rebuilds the Docker image
3. Stops the old container
4. Starts the new container with the updated code

## Configured Branches

By default, the following branches trigger auto-deployment:
- `main` / `master` - Production environment
- `develop` / `development` - Development environment  
- `staging` - Staging environment

## How It Works

1. **Git Hook** (`.git/hooks/post-commit`)
   - Triggers after every local commit
   - Checks if the branch should trigger deployment
   - Runs the deployment script in the background

2. **Deployment Script** (`auto-deploy.sh`)
   - Builds the new Docker image
   - Gracefully stops the old container
   - Starts the new container
   - Performs health checks
   - Logs everything to `.ci/logs/`

3. **Configuration** (`config.env`)
   - Customize which branches trigger deployment
   - Configure build options
   - Set health check parameters

## Usage

### Normal Workflow
```bash
# Make your changes
vim Dockerfile

# Commit to a configured branch
git add .
git commit -m "Update Dockerfile"

# Auto-deployment starts automatically!
# Check the logs
tail -f .ci/logs/deploy-*.log
```

### Manual Deployment
```bash
# If you need to manually trigger deployment
.ci/auto-deploy.sh [branch-name]
```

### Configuration

Edit `.ci/config.env` to customize:
- Which branches trigger deployment
- Number of old images to keep
- Health check URLs
- Logging verbosity

### Monitoring

#### Check Deployment Logs
```bash
# View latest deployment log
ls -lt .ci/logs/ | head -2

# Watch deployment in real-time
tail -f .ci/logs/deploy-*.log
```

#### Check Container Status
```bash
# See if container is running
docker ps | grep playwright-browser

# Check container logs
docker logs playwright-browser
```

## Troubleshooting

### Deployment Not Triggering
1. Check current branch: `git branch --show-current`
2. Verify branch is in config: `grep DEPLOY_ON_BRANCHES .ci/config.env`
3. Check hook is executable: `ls -la .git/hooks/post-commit`

### Build Failures
1. Check deployment logs in `.ci/logs/`
2. Try manual build: `docker-compose build`
3. Check Docker daemon: `systemctl status docker`

### Container Not Starting
1. Check port conflicts: `ss -tulpn | grep -E "6080|8931"`
2. Review docker-compose.yml configuration
3. Check Docker logs: `docker logs playwright-browser`

## Disable Auto-Deployment

To temporarily disable:
```bash
# Rename the hook
mv .git/hooks/post-commit .git/hooks/post-commit.disabled
```

To re-enable:
```bash
# Restore the hook
mv .git/hooks/post-commit.disabled .git/hooks/post-commit
```

## Clean Up

### Remove Old Logs
```bash
# Remove logs older than 30 days
find .ci/logs -name "*.log" -mtime +30 -delete
```

### Clean Docker Images
```bash
# Remove unused images
docker image prune -f

# Remove all stopped containers
docker container prune -f
```

## Advanced Features

### Multi-Branch Deployment
Different branches can deploy to different ports/configurations by modifying the `auto-deploy.sh` script.

### Health Checks
The system performs basic health checks on:
- noVNC interface (port 6080)
- Playwright MCP endpoint (port 8931)

### Rollback
Keep old images for quick rollback:
```bash
# List available images
docker images | grep playwright-browser

# Run previous version
docker run -d --name playwright-browser-rollback [IMAGE_ID]
```

## Support

Check logs in `.ci/logs/` for detailed deployment information and troubleshooting.