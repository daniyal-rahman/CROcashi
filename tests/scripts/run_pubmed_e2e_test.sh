#!/bin/bash

# PubMed E2E Test Runner Script
# This script provides easy access to run the PubMed end-to-end test with different configurations

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
CONFIG_FILE=""
TRIAL_ID=""
VERBOSE=false
ASSETS=""
INDICATIONS=""
QUICK_TEST=false

# Function to print usage
print_usage() {
    echo -e "${BLUE}PubMed E2E Test Runner${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c, --config FILE     Configuration file path"
    echo "  -t, --trial-id ID     Clinical trial ID to test"
    echo "  -a, --assets LIST     Space-separated asset names"
    echo "  -i, --indications LIST Space-separated indications"
    echo "  -v, --verbose         Enable verbose logging"
    echo "  -q, --quick           Quick test with minimal results"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run default test (NCT04368728)"
    echo "  $0 --trial-id NCT04535194            # Test specific trial"
    echo "  $0 --assets Keytruda Pembrolizumab   # Test specific assets"
    echo "  $0 --config config/my_config.json    # Use custom config"
    echo "  $0 --quick                           # Quick test (10 results)"
    echo ""
}

# Function to print status
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check Python version
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    REQUIRED_VERSION="3.7"
    
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        print_error "Python 3.7+ is required, found $PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
    
    # Check if test script exists
    TEST_SCRIPT="$SCRIPT_DIR/test_pubmed_e2e.py"
    if [ ! -f "$TEST_SCRIPT" ]; then
        print_error "Test script not found: $TEST_SCRIPT"
        exit 1
    fi
    
    print_success "Test script found"
    
    # Check if config directory exists
    CONFIG_DIR="$PROJECT_ROOT/config"
    if [ ! -d "$CONFIG_DIR" ]; then
        print_warning "Config directory not found: $CONFIG_DIR"
    else
        print_success "Config directory found"
    fi
}

# Function to build command arguments
build_command() {
    local cmd="python3 $SCRIPT_DIR/test_pubmed_e2e.py"
    
    if [ -n "$CONFIG_FILE" ]; then
        cmd="$cmd --config $CONFIG_FILE"
    fi
    
    if [ -n "$TRIAL_ID" ]; then
        cmd="$cmd --trial-id $TRIAL_ID"
    fi
    
    if [ -n "$ASSETS" ]; then
        cmd="$cmd --assets $ASSETS"
    fi
    
    if [ -n "$INDICATIONS" ]; then
        cmd="$cmd --indications $INDICATIONS"
    fi
    
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi
    
    echo "$cmd"
}

# Function to run the test
run_test() {
    print_status "Starting PubMed E2E test..."
    
    # Build command
    local cmd=$(build_command)
    print_status "Executing: $cmd"
    echo ""
    
    # Change to project root for proper imports
    cd "$PROJECT_ROOT"
    
    # Run the test
    if eval "$cmd"; then
        print_success "Test completed successfully!"
        return 0
    else
        print_error "Test failed with exit code $?"
        return 1
    fi
}

# Function to show test results
show_results() {
    print_status "Looking for test reports..."
    
    # Find the most recent report
    local reports=($(find . -name "pubmed_e2e_test_report_*.json" -type f 2>/dev/null | sort -r))
    
    if [ ${#reports[@]} -eq 0 ]; then
        print_warning "No test reports found"
        return
    fi
    
    local latest_report="${reports[0]}"
    print_success "Latest report: $latest_report"
    
    # Show summary if jq is available
    if command -v jq &> /dev/null; then
        echo ""
        print_status "Test Summary:"
        echo "=============="
        
        # Extract key metrics
        local duration=$(jq -r '.duration_seconds // "N/A"' "$latest_report" 2>/dev/null)
        local success_rate=$(jq -r '.test_summary.success_rate // "N/A"' "$latest_report" 2>/dev/null)
        local total_tests=$(jq -r '.test_summary.total_tests // "N/A"' "$latest_report" 2>/dev/null)
        local successful_tests=$(jq -r '.test_summary.successful_tests // "N/A"' "$latest_report" 2>/dev/null)
        
        echo "Duration: ${duration}s"
        echo "Success Rate: ${success_rate}%"
        echo "Tests: ${successful_tests}/${total_tests}"
        
        # Show errors if any
        local error_count=$(jq -r '.errors | length // 0' "$latest_report" 2>/dev/null)
        if [ "$error_count" -gt 0 ]; then
            echo ""
            print_warning "Errors found: $error_count"
            jq -r '.errors[]' "$latest_report" 2>/dev/null | while read -r error; do
                echo "  - $error"
            done
        fi
        
    else
        print_warning "Install 'jq' for better report parsing"
        echo "Report location: $latest_report"
    fi
}

# Function to cleanup old reports
cleanup_reports() {
    print_status "Cleaning up old test reports..."
    
    # Keep only the last 5 reports
    local reports=($(find . -name "pubmed_e2e_test_report_*.json" -type f 2>/dev/null | sort -r))
    
    if [ ${#reports[@]} -gt 5 ]; then
        local to_delete=${reports[@]:5}
        for report in $to_delete; do
            rm -f "$report"
            print_status "Removed old report: $report"
        done
        print_success "Cleanup completed"
    else
        print_status "No cleanup needed (${#reports[@]} reports found)"
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -t|--trial-id)
            TRIAL_ID="$2"
            shift 2
            ;;
        -a|--assets)
            ASSETS="$2"
            shift 2
            ;;
        -i|--indications)
            INDICATIONS="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quick)
            QUICK_TEST=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Handle quick test mode
if [ "$QUICK_TEST" = true ]; then
    if [ -z "$CONFIG_FILE" ]; then
        # Create quick test config
        QUICK_CONFIG="$SCRIPT_DIR/quick_test_config.json"
        cat > "$QUICK_CONFIG" << EOF
{
  "test_trial_id": "NCT04368728",
  "test_assets": ["mRNA-1273"],
  "test_indications": ["COVID-19"],
  "max_results": 10,
  "email": "test@example.com"
}
EOF
        CONFIG_FILE="$QUICK_CONFIG"
        print_status "Created quick test config: $CONFIG_FILE"
    fi
fi

# Main execution
main() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  PubMed E2E Test Runner${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Show configuration
    print_status "Test Configuration:"
    echo "  Config File: ${CONFIG_FILE:-"Default"}"
    echo "  Trial ID: ${TRIAL_ID:-"NCT04368728 (Default)"}"
    echo "  Assets: ${ASSETS:-"mRNA-1273, Moderna (Default)"}"
    echo "  Indications: ${INDICATIONS:-"COVID-19, SARS-CoV-2 (Default)"}"
    echo "  Verbose: $VERBOSE"
    echo "  Quick Test: $QUICK_TEST"
    echo ""
    
    # Run the test
    if run_test; then
        print_success "All tests completed successfully!"
        show_results
        cleanup_reports
        exit 0
    else
        print_error "Test execution failed"
        show_results
        exit 1
    fi
}

# Run main function
main "$@"
