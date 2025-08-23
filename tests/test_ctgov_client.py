"""
Unit tests for the CT.gov Client.

Tests all data extraction, change detection, and API interaction capabilities.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from src.ncfd.ingest.ctgov import CTGovClient
from src.ncfd.ingest.ctgov_types import (
    TrialData, TrialPhase, TrialStatus, InterventionType, StudyType
)


class TestCTGovClient:
    """Test CT.gov client functionality."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        config = {
            'api': {
                'base_url': 'https://clinicaltrials.gov/api/v2',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1
            },
            'rate_limiting': {
                'requests_per_second': 2,
                'burst_limit': 10
            },
            'change_detection': {
                'enabled': True,
                'hash_fields': ['brief_title', 'detailed_description', 'enrollment_count'],
                'min_change_threshold': 0.1
            }
        }
        return CTGovClient(config)
    
    def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.base_url == 'https://clinicaltrials.gov/api/v2'
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client.retry_delay == 1
        assert client.requests_per_second == 2
        assert client.burst_limit == 10
        assert client.change_detection_enabled is True
    
    @patch('requests.get')
    def test_fetch_trial_metadata(self, mock_get, client):
        """Test fetching trial metadata."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT12345678",
                            "briefTitle": "Test Trial",
                            "officialTitle": "Official Test Trial Title",
                            "sponsorName": "Test Sponsor"
                        },
                        "statusModule": {
                            "overallStatus": "Recruiting",
                            "phase": "PHASE2"
                        },
                        "designModule": {
                            "studyType": "Interventional",
                            "enrollmentCount": 100
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Test fetching metadata
        trials = client.fetch_trial_metadata(
            query="cancer",
            fields=["NCTId", "BriefTitle", "OverallStatus"],
            max_results=10
        )
        
        assert len(trials) == 1
        assert trials[0]["nctId"] == "NCT12345678"
        assert trials[0]["briefTitle"] == "Test Trial"
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "clinicaltrials.gov" in call_args[0][0]
        assert "query=cancer" in call_args[0][0]
    
    @patch('requests.get')
    def test_fetch_trial_details(self, mock_get, client):
        """Test fetching detailed trial information."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Test Trial",
                    "officialTitle": "Official Test Trial Title",
                    "sponsorName": "Test Sponsor"
                },
                "statusModule": {
                    "overallStatus": "Recruiting",
                    "phase": "PHASE2",
                    "startDate": "2023-01-01",
                    "completionDate": "2024-01-01"
                },
                "designModule": {
                    "studyType": "Interventional",
                    "enrollmentCount": 100,
                    "allocation": "Randomized",
                    "interventionModel": "Parallel Assignment"
                },
                "armsInterventionsModule": {
                    "arms": [
                        {
                            "name": "Treatment Arm",
                            "type": "Experimental",
                            "description": "Test treatment"
                        }
                    ],
                    "interventions": [
                        {
                            "type": "Drug",
                            "name": "Test Drug",
                            "description": "Experimental drug"
                        }
                    ]
                },
                "outcomeMeasuresModule": {
                    "outcomeMeasures": [
                        {
                            "name": "Overall Survival",
                            "type": "Primary",
                            "description": "Time from randomization to death"
                        }
                    ]
                }
            }
        }
        mock_get.return_value = mock_response
        
        # Test fetching trial details
        trial_data = client.fetch_trial_details("NCT12345678")
        
        assert trial_data is not None
        assert trial_data.nct_id == "NCT12345678"
        assert trial_data.brief_title == "Test Trial"
        assert trial_data.sponsor_name == "Test Sponsor"
        assert trial_data.phase == TrialPhase.PHASE2
        assert trial_data.status == TrialStatus.RECRUITING
        assert trial_data.enrollment_count == 100
        assert trial_data.study_type == StudyType.INTERVENTIONAL
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "NCT12345678" in call_args[0][0]
    
    @patch('requests.get')
    def test_fetch_trial_details_not_found(self, mock_get, client):
        """Test fetching trial details when trial not found."""
        # Mock API response for not found
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Test fetching non-existent trial
        trial_data = client.fetch_trial_details("NCT99999999")
        
        assert trial_data is None
    
    @patch('requests.get')
    def test_fetch_trial_details_api_error(self, mock_get, client):
        """Test handling API errors when fetching trial details."""
        # Mock API response for error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response
        
        # Test error handling
        with pytest.raises(Exception, match="API request failed"):
            client.fetch_trial_details("NCT12345678")
    
    def test_extract_trial_data(self, client):
        """Test extracting trial data from API response."""
        # Sample API response
        api_response = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Test Trial",
                    "officialTitle": "Official Test Trial Title",
                    "sponsorName": "Test Sponsor"
                },
                "statusModule": {
                    "overallStatus": "Recruiting",
                    "phase": "PHASE2",
                    "startDate": "2023-01-01",
                    "completionDate": "2024-01-01"
                },
                "designModule": {
                    "studyType": "Interventional",
                    "enrollmentCount": 100,
                    "allocation": "Randomized",
                    "interventionModel": "Parallel Assignment"
                },
                "armsInterventionsModule": {
                    "arms": [
                        {
                            "name": "Treatment Arm",
                            "type": "Experimental",
                            "description": "Test treatment"
                        }
                    ],
                    "interventions": [
                        {
                            "type": "Drug",
                            "name": "Test Drug",
                            "description": "Experimental drug"
                        }
                    ]
                }
            }
        }
        
        # Extract trial data
        trial_data = client._extract_trial_data(api_response)
        
        assert trial_data is not None
        assert trial_data.nct_id == "NCT12345678"
        assert trial_data.brief_title == "Test Trial"
        assert trial_data.official_title == "Official Test Trial Title"
        assert trial_data.sponsor_name == "Test Sponsor"
        assert trial_data.phase == TrialPhase.PHASE2
        assert trial_data.status == TrialStatus.RECRUITING
        assert trial_data.enrollment_count == 100
        assert trial_data.study_type == StudyType.INTERVENTIONAL
        assert len(trial_data.arms) == 1
        assert len(trial_data.interventions) == 1
    
    def test_extract_trial_data_missing_fields(self, client):
        """Test extracting trial data with missing fields."""
        # API response with missing fields
        api_response = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678"
                    # Missing other fields
                }
            }
        }
        
        # Extract trial data
        trial_data = client._extract_trial_data(api_response)
        
        assert trial_data is not None
        assert trial_data.nct_id == "NCT12345678"
        assert trial_data.brief_title is None
        assert trial_data.sponsor_name is None
        assert trial_data.phase is None
        assert trial_data.status is None
    
    def test_extract_trial_data_invalid_phase(self, client):
        """Test extracting trial data with invalid phase."""
        # API response with invalid phase
        api_response = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Test Trial"
                },
                "statusModule": {
                    "overallStatus": "Recruiting",
                    "phase": "INVALID_PHASE"
                }
            }
        }
        
        # Extract trial data
        trial_data = client._extract_trial_data(api_response)
        
        assert trial_data is not None
        assert trial_data.phase is None  # Should be None for invalid phase
    
    def test_extract_trial_data_invalid_status(self, client):
        """Test extracting trial data with invalid status."""
        # API response with invalid status
        api_response = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Test Trial"
                },
                "statusModule": {
                    "overallStatus": "INVALID_STATUS",
                    "phase": "PHASE2"
                }
            }
        }
        
        # Extract trial data
        trial_data = client._extract_trial_data(api_response)
        
        assert trial_data is not None
        assert trial_data.status is None  # Should be None for invalid status
    
    def test_extract_arms_and_interventions(self, client):
        """Test extracting arms and interventions."""
        # Sample arms and interventions data
        arms_data = [
            {
                "name": "Treatment Arm",
                "type": "Experimental",
                "description": "Test treatment"
            },
            {
                "name": "Control Arm",
                "type": "Active Comparator",
                "description": "Standard treatment"
            }
        ]
        
        interventions_data = [
            {
                "type": "Drug",
                "name": "Test Drug",
                "description": "Experimental drug"
            },
            {
                "type": "Procedure",
                "name": "Test Procedure",
                "description": "Experimental procedure"
            }
        ]
        
        # Extract arms and interventions
        arms = client._extract_arms(arms_data)
        interventions = client._extract_interventions(interventions_data)
        
        assert len(arms) == 2
        assert arms[0].name == "Treatment Arm"
        assert arms[0].type == "Experimental"
        assert arms[1].name == "Control Arm"
        assert arms[1].type == "Active Comparator"
        
        assert len(interventions) == 2
        assert interventions[0].type == InterventionType.DRUG
        assert interventions[0].name == "Test Drug"
        assert interventions[1].type == InterventionType.PROCEDURE
        assert interventions[1].name == "Test Procedure"
    
    def test_extract_outcome_measures(self, client):
        """Test extracting outcome measures."""
        # Sample outcome measures data
        outcome_data = [
            {
                "name": "Overall Survival",
                "type": "Primary",
                "description": "Time from randomization to death",
                "measureType": "Time Frame"
            },
            {
                "name": "Progression-Free Survival",
                "type": "Secondary",
                "description": "Time from randomization to progression or death",
                "measureType": "Time Frame"
            }
        ]
        
        # Extract outcome measures
        outcomes = client._extract_outcome_measures(outcome_data)
        
        assert len(outcomes) == 2
        assert outcomes[0].name == "Overall Survival"
        assert outcomes[0].type == "Primary"
        assert outcomes[1].name == "Progression-Free Survival"
        assert outcomes[1].type == "Secondary"
    
    def test_change_detection(self, client):
        """Test change detection functionality."""
        # Create two trial data objects
        old_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Old Title",
            detailed_description="Old description",
            enrollment_count=100
        )
        
        new_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="New Title",  # Changed
            detailed_description="New description",  # Changed
            enrollment_count=150  # Changed
        )
        
        # Check for changes
        changes = client._detect_changes(old_trial, new_trial)
        
        assert changes.has_changes is True
        assert len(changes.changed_fields) == 3
        assert "brief_title" in changes.changed_fields
        assert "detailed_description" in changes.changed_fields
        assert "enrollment_count" in changes.changed_fields
        
        # Check change details
        title_change = next(c for c in changes.field_changes if c.field_name == "brief_title")
        assert title_change.old_value == "Old Title"
        assert title_change.new_value == "New Title"
        
        enrollment_change = next(c for c in changes.field_changes if c.field_name == "enrollment_count")
        assert enrollment_change.old_value == 100
        assert enrollment_change.new_value == 150
    
    def test_change_detection_no_changes(self, client):
        """Test change detection when no changes exist."""
        # Create identical trial data objects
        old_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Same Title",
            detailed_description="Same description",
            enrollment_count=100
        )
        
        new_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Same Title",
            detailed_description="Same description",
            enrollment_count=100
        )
        
        # Check for changes
        changes = client._detect_changes(old_trial, new_trial)
        
        assert changes.has_changes is False
        assert len(changes.changed_fields) == 0
        assert len(changes.field_changes) == 0
    
    def test_change_detection_below_threshold(self, client):
        """Test change detection with changes below threshold."""
        # Create trial data with minimal changes
        old_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Test Title",
            detailed_description="Test description",
            enrollment_count=100
        )
        
        new_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Test Title",  # Same
            detailed_description="Test description with minor change",  # Minor change
            enrollment_count=100  # Same
        )
        
        # Check for changes
        changes = client._detect_changes(old_trial, new_trial)
        
        # Should detect changes but they might be below threshold
        assert changes.has_changes is True
        assert "detailed_description" in changes.changed_fields
    
    @patch('requests.get')
    def test_fetch_updated_trials(self, mock_get, client):
        """Test fetching updated trials."""
        # Mock API response for updated trials
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT12345678",
                            "briefTitle": "Updated Trial",
                            "sponsorName": "Test Sponsor"
                        },
                        "statusModule": {
                            "overallStatus": "Completed",
                            "phase": "PHASE2"
                        },
                        "designModule": {
                            "studyType": "Interventional",
                            "enrollmentCount": 120
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Test fetching updated trials
        updated_trials = client.fetch_updated_trials(
            last_update_date="2024-01-01",
            max_results=10
        )
        
        assert len(updated_trials) == 1
        assert updated_trials[0]["nctId"] == "NCT12345678"
        assert updated_trials[0]["briefTitle"] == "Updated Trial"
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "lastUpdatePostDate" in call_args[0][0]
    
    @patch('requests.get')
    def test_fetch_trials_by_sponsor(self, mock_get, client):
        """Test fetching trials by sponsor."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT12345678",
                            "briefTitle": "Sponsor Trial",
                            "sponsorName": "Test Sponsor"
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Test fetching trials by sponsor
        sponsor_trials = client.fetch_trials_by_sponsor(
            sponsor_name="Test Sponsor",
            max_results=10
        )
        
        assert len(sponsor_trials) == 1
        assert sponsor_trials[0]["nctId"] == "NCT12345678"
        assert sponsor_trials[0]["sponsorName"] == "Test Sponsor"
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "sponsorName" in call_args[0][0]
    
    def test_rate_limiting(self, client):
        """Test rate limiting functionality."""
        # Test that rate limiting is properly configured
        assert client.requests_per_second == 2
        assert client.burst_limit == 10
        
        # Test rate limiting delay calculation
        delay = client._calculate_rate_limit_delay()
        assert delay >= 0.5  # Should be at least 0.5 seconds for 2 req/s
    
    def test_error_handling(self, client):
        """Test error handling functionality."""
        # Test handling of invalid NCT ID
        with pytest.raises(ValueError, match="Invalid NCT ID format"):
            client.fetch_trial_details("INVALID_ID")
        
        # Test handling of empty query
        with pytest.raises(ValueError, match="Query cannot be empty"):
            client.fetch_trial_metadata("", max_results=10)
        
        # Test handling of invalid max_results
        with pytest.raises(ValueError, match="max_results must be positive"):
            client.fetch_trial_metadata("cancer", max_results=0)
    
    def test_data_validation(self, client):
        """Test data validation functionality."""
        # Test valid NCT ID
        assert client._validate_nct_id("NCT12345678") is True
        
        # Test invalid NCT ID
        assert client._validate_nct_id("12345678") is False
        assert client._validate_nct_id("NCT1234567") is False  # Too short
        assert client._validate_nct_id("NCT123456789") is False  # Too long
        assert client._validate_nct_id("ABC12345678") is False  # Wrong prefix
    
    def test_build_api_url(self, client):
        """Test API URL building."""
        # Test basic URL building
        url = client._build_api_url("studies", {"query": "cancer"})
        assert "clinicaltrials.gov" in url
        assert "query=cancer" in url
        
        # Test URL with multiple parameters
        url = client._build_api_url("studies", {
            "query": "cancer",
            "fields": "NCTId,BriefTitle",
            "maxResults": 10
        })
        assert "query=cancer" in url
        assert "fields=NCTId,BriefTitle" in url
        assert "maxResults=10" in url


class TestCTGovClientIntegration:
    """Integration tests for the CT.gov client."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        config = {
            'api': {
                'base_url': 'https://clinicaltrials.gov/api/v2',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1
            },
            'rate_limiting': {
                'requests_per_second': 2,
                'burst_limit': 10
            },
            'change_detection': {
                'enabled': True,
                'hash_fields': ['brief_title', 'detailed_description', 'enrollment_count'],
                'min_change_threshold': 0.1
            }
        }
        return CTGovClient(config)
    
    @patch('requests.get')
    def test_end_to_end_trial_fetching(self, mock_get, client):
        """Test complete end-to-end trial fetching workflow."""
        # Mock API response for metadata
        metadata_response = Mock()
        metadata_response.status_code = 200
        metadata_response.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT12345678",
                            "briefTitle": "Test Trial",
                            "sponsorName": "Test Sponsor"
                        }
                    }
                }
            ]
        }
        
        # Mock API response for details
        details_response = Mock()
        details_response.status_code = 200
        details_response.json.return_value = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT12345678",
                    "briefTitle": "Test Trial",
                    "sponsorName": "Test Sponsor"
                },
                "statusModule": {
                    "overallStatus": "Recruiting",
                    "phase": "PHASE2"
                },
                "designModule": {
                    "studyType": "Interventional",
                    "enrollmentCount": 100
                }
            }
        }
        
        # Configure mock to return different responses
        mock_get.side_effect = [metadata_response, details_response]
        
        # Fetch metadata
        trials_metadata = client.fetch_trial_metadata(
            query="cancer",
            fields=["NCTId", "BriefTitle"],
            max_results=10
        )
        
        assert len(trials_metadata) == 1
        nct_id = trials_metadata[0]["nctId"]
        
        # Fetch details for the first trial
        trial_details = client.fetch_trial_details(nct_id)
        
        assert trial_details is not None
        assert trial_details.nct_id == nct_id
        assert trial_details.brief_title == "Test Trial"
        assert trial_details.sponsor_name == "Test Sponsor"
        
        # Verify API calls
        assert mock_get.call_count == 2
    
    def test_change_detection_workflow(self, client):
        """Test complete change detection workflow."""
        # Create old trial data
        old_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="Old Title",
            detailed_description="Old description",
            enrollment_count=100,
            phase=TrialPhase.PHASE2,
            status=TrialStatus.RECRUITING
        )
        
        # Create new trial data with changes
        new_trial = TrialData(
            nct_id="NCT12345678",
            brief_title="New Title",
            detailed_description="New description",
            enrollment_count=150,
            phase=TrialPhase.PHASE3,  # Changed
            status=TrialStatus.COMPLETED  # Changed
        )
        
        # Detect changes
        changes = client._detect_changes(old_trial, new_trial)
        
        assert changes.has_changes is True
        assert len(changes.changed_fields) >= 5  # Multiple fields changed
        
        # Verify specific changes
        assert "brief_title" in changes.changed_fields
        assert "detailed_description" in changes.changed_fields
        assert "enrollment_count" in changes.changed_fields
        assert "phase" in changes.changed_fields
        assert "status" in changes.changed_fields
        
        # Check change details
        for change in changes.field_changes:
            if change.field_name == "phase":
                assert change.old_value == TrialPhase.PHASE2
                assert change.new_value == TrialPhase.PHASE3
            elif change.field_name == "status":
                assert change.old_value == TrialStatus.RECRUITING
                assert change.new_value == TrialStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__])
