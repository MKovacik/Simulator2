"""
Test script for Deutsche Telekom Tariff Simulator
------------------------------------------------
This script tests the core components of the simulator to ensure they work together properly.
"""

import os
import sys
import time
import unittest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import core components
from src.core.llm_adapter import LMStudioLLM
from src.agents.crew_manager import TelekomCrewManager
from src.data.personas import PERSONAS

class TestTelekomSimulator(unittest.TestCase):
    """Test cases for the Deutsche Telekom Tariff Simulator."""
    
    def setUp(self):
        """Set up test environment."""
        self.llm = LMStudioLLM()
        self.crew_manager = TelekomCrewManager()
        
    def test_llm_adapter(self):
        """Test the LM Studio adapter."""
        print("\nTesting LM Studio adapter...")
        try:
            response = self.llm._call("Say hello in German")
            print(f"LLM response: {response}")
            self.assertIsInstance(response, str)
            self.assertTrue(len(response) > 0)
            print("✅ LLM adapter test passed")
        except Exception as e:
            print(f"❌ LLM adapter test failed: {str(e)}")
            raise
    
    def test_crew_manager_initialization(self):
        """Test crew manager initialization."""
        print("\nTesting crew manager initialization...")
        try:
            self.assertIsNotNone(self.crew_manager.customer_agent)
            self.assertIsNotNone(self.crew_manager.telekom_agent)
            self.assertIsNotNone(self.crew_manager.terminator_agent)
            print("✅ Crew manager initialization test passed")
        except Exception as e:
            print(f"❌ Crew manager initialization test failed: {str(e)}")
            raise
    
    def test_customer_intro_task(self):
        """Test customer intro task execution."""
        print("\nTesting customer intro task...")
        try:
            # Get a persona
            persona = PERSONAS[0]
            
            # Create and execute customer intro task
            task = self.crew_manager.get_customer_intro(
                persona_name=persona["name"],
                persona_needs=persona["needs"]
            )
            
            # Execute the task
            start_time = time.time()
            print("Executing customer intro task (this may take a minute)...")
            response = self.crew_manager.execute_single_task(task)
            elapsed = time.time() - start_time
            
            print(f"Task completed in {elapsed:.1f} seconds")
            print(f"Response: {response}")
            
            self.assertIsInstance(response, str)
            self.assertTrue(len(response) > 10)
            print("✅ Customer intro task test passed")
        except Exception as e:
            print(f"❌ Customer intro task test failed: {str(e)}")
            raise
    
    def test_terminator_task(self):
        """Test terminator task execution."""
        print("\nTesting terminator task...")
        try:
            # Test with a message that doesn't select a plan
            no_selection_msg = "I'm still considering my options. What's the difference between the Basic 5GB and Internet+ 20GB plans?"
            no_selection_task = self.crew_manager.get_terminator_task(user_message=no_selection_msg)
            
            start_time = time.time()
            print("Executing terminator task with no selection (this may take a minute)...")
            no_selection_response = self.crew_manager.execute_single_task(no_selection_task)
            elapsed = time.time() - start_time
            
            print(f"Task completed in {elapsed:.1f} seconds")
            print(f"Response: {no_selection_response}")
            
            self.assertIsInstance(no_selection_response, str)
            self.assertTrue(no_selection_response.upper().startswith("NO"))
            
            # Test with a message that selects a plan
            selection_msg = "I'd like to select the Premium Unlimited plan. It meets all my needs."
            selection_task = self.crew_manager.get_terminator_task(user_message=selection_msg)
            
            start_time = time.time()
            print("Executing terminator task with selection (this may take a minute)...")
            selection_response = self.crew_manager.execute_single_task(selection_task)
            elapsed = time.time() - start_time
            
            print(f"Task completed in {elapsed:.1f} seconds")
            print(f"Response: {selection_response}")
            
            self.assertIsInstance(selection_response, str)
            self.assertTrue(selection_response.upper().startswith("YES"))
            
            print("✅ Terminator task test passed")
        except Exception as e:
            print(f"❌ Terminator task test failed: {str(e)}")
            raise

def run_tests():
    """Run the test suite."""
    print("=" * 50)
    print("Deutsche Telekom Tariff Simulator Test Suite")
    print("=" * 50)
    
    # Check if LM Studio is running
    print("Checking if LM Studio API is available...")
    import requests
    try:
        lm_studio_url = os.getenv('LMSTUDIO_BASE_URL', 'http://127.0.0.1:1234/v1')
        response = requests.get(f"{lm_studio_url}/models")
        if response.status_code == 200:
            print("✅ LM Studio API is available")
        else:
            print(f"❌ LM Studio API returned status code {response.status_code}")
            print("Please make sure LM Studio is running with the API server enabled")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to LM Studio API")
        print("Please make sure LM Studio is running with the API server enabled")
        return
    
    # Run tests
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
    
    print("\n" + "=" * 50)
    print("Test suite completed")
    print("=" * 50)

if __name__ == '__main__':
    run_tests()
