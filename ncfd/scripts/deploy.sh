#!/bin/bash

# NCFD Production Deployment Script
# Usage: ./scripts/deploy.sh [staging|production] [version]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${1:-staging}"
VERSION="${2:-latest}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Environment-specific configurations
case $ENVIRONMENT in
    staging)
        COMPOSE_FILE="docker-compose.staging.yml"
        ENV_FILE=".env.staging"
        DOMAIN="staging.ncfd.example.com"
        ;;
    production)
        COMPOSE_FILE="docker-compose.prod.yml"
        ENV_FILE=".env.prod"
        DOMAIN="ncfd.example.com"
        ;;
    *)
        echo -e "${RED}Error: Invalid environment. Use 'staging' or 'production'${NC}"
        exit 1
        ;;
esac

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running"
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose >/dev/null 2>&1; then
        error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check if required files exist
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    if [[ ! -f "$ENV_FILE" ]]; then
        error "Environment file not found: $ENV_FILE"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Backup current deployment
backup_deployment() {
    log "Creating backup of current deployment..."
    
    BACKUP_DIR="$PROJECT_DIR/backups/$ENVIRONMENT/$TIMESTAMP"
    mkdir -p "$BACKUP_DIR"
    
    # Backup environment file
    cp "$ENV_FILE" "$BACKUP_DIR/"
    
    # Backup compose file
    cp "$COMPOSE_FILE" "$BACKUP_DIR/"
    
    # Backup database (if running)
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "db"; then
        log "Backing up database..."
        docker-compose -f "$COMPOSE_FILE" exec -T db pg_dump -U ncfd_prod ncfd_prod > "$BACKUP_DIR/database_backup.sql" || warning "Database backup failed"
    fi
    
    success "Backup created at: $BACKUP_DIR"
}

# Stop current deployment
stop_deployment() {
    log "Stopping current deployment..."
    
    if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
        docker-compose -f "$COMPOSE_FILE" down --remove-orphans
        success "Current deployment stopped"
    else
        log "No running deployment found"
    fi
}

# Pull latest images
pull_images() {
    log "Pulling latest Docker images..."
    
    docker-compose -f "$COMPOSE_FILE" pull
    success "Images pulled successfully"
}

# Deploy new version
deploy_new_version() {
    log "Deploying new version: $VERSION"
    
    # Set version environment variable
    export NCFD_VERSION="$VERSION"
    
    # Start services
    docker-compose -f "$COMPOSE_FILE" up -d --remove-orphans
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    timeout=300
    counter=0
    
    while [[ $counter -lt $timeout ]]; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "unhealthy"; then
            log "Some services are unhealthy, waiting..."
            sleep 10
            counter=$((counter + 10))
        else
            success "All services are healthy"
            break
        fi
    done
    
    if [[ $counter -ge $timeout ]]; then
        error "Services did not become healthy within timeout"
        docker-compose -f "$COMPOSE_FILE" logs
        exit 1
    fi
}

# Run health checks
run_health_checks() {
    log "Running health checks..."
    
    # Wait a bit for services to fully initialize
    sleep 30
    
    # Run production smoke tests
    if [[ -f "$PROJECT_DIR/scripts/production_smoke_test.py" ]]; then
        log "Running production smoke tests..."
        cd "$PROJECT_DIR"
        
        # Set environment variables for health checks
        export POSTGRES_DSN="postgresql://ncfd_prod:ncfd_prod@localhost:5432/ncfd_prod"
        export REDIS_HOST="localhost"
        export REDIS_PORT="6379"
        
        if python3.12 scripts/production_smoke_test.py; then
            success "Health checks passed"
        else
            error "Health checks failed"
            exit 1
        fi
    else
        warning "Production smoke test script not found, skipping health checks"
    fi
}

# Update DNS/load balancer (placeholder)
update_infrastructure() {
    log "Updating infrastructure configuration..."
    
    # This would typically update DNS, load balancer, etc.
    # For now, just log the action
    log "Infrastructure update completed (placeholder)"
}

# Rollback function
rollback() {
    error "Deployment failed, rolling back..."
    
    # Stop new deployment
    docker-compose -f "$COMPOSE_FILE" down --remove-orphans
    
    # Restore from backup
    if [[ -d "$PROJECT_DIR/backups/$ENVIRONMENT/$TIMESTAMP" ]]; then
        log "Restoring from backup..."
        cp "$PROJECT_DIR/backups/$ENVIRONMENT/$TIMESTAMP/$ENV_FILE" "$ENV_FILE"
        cp "$PROJECT_DIR/backups/$ENVIRONMENT/$TIMESTAMP/$COMPOSE_FILE" "$COMPOSE_FILE"
        
        # Restart previous deployment
        docker-compose -f "$COMPOSE_FILE" up -d
        warning "Rolled back to previous deployment"
    else
        error "Backup not found, cannot rollback"
    fi
    
    exit 1
}

# Main deployment process
main() {
    log "Starting deployment to $ENVIRONMENT environment (version: $VERSION)"
    
    # Set trap for rollback on failure
    trap rollback ERR
    
    # Change to project directory
    cd "$PROJECT_DIR"
    
    # Run deployment steps
    check_prerequisites
    backup_deployment
    stop_deployment
    pull_images
    deploy_new_version
    run_health_checks
    update_infrastructure
    
    success "Deployment to $ENVIRONMENT completed successfully!"
    
    # Display deployment info
    echo
    echo "Deployment Summary:"
    echo "==================="
    echo "Environment: $ENVIRONMENT"
    echo "Version: $VERSION"
    echo "Timestamp: $TIMESTAMP"
    echo "Domain: $DOMAIN"
    echo "Backup Location: $PROJECT_DIR/backups/$ENVIRONMENT/$TIMESTAMP"
    echo
    
    # Show running services
    log "Current deployment status:"
    docker-compose -f "$COMPOSE_FILE" ps
}

# Run main function
main "$@"
