# test_system.py
#**************************************************************************************************
#   Comprehensive Test Suite for AutoCAD Drawing Processing System
#   Tests all major components and integrations
#**************************************************************************************************
import unittest
import os
import tempfile
import shutil
from pathlib import Path
import json

from colorama import init, Fore, Style
init(autoreset=True)

# Import modules to test
from DWG_Processor import DWGProcessor  # Changed to match your filename
from semanticMemory import (
    add_to_database, get_from_database, search_similar_files,
    file_exists_in_database, get_database_stats, generate_embedding_id
)
from utils import clean_specs, is_valid_specs
from config import validate_config

class TestDWGProcessor(unittest.TestCase):
    """Test DWG processing functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.processor = DWGProcessor()
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_processor_initialization(self):
        """Test DWGProcessor initializes correctly."""
        self.assertIsNotNone(self.processor)
        self.assertIsInstance(self.processor.supported_entities, list)
        self.assertIn('LINE', self.processor.supported_entities)
        self.assertIn('CIRCLE', self.processor.supported_entities)
    
    def test_entity_extraction(self):
        """Test entity data extraction."""
        # This would require a mock DXF entity
        # For now, test that the method exists
        self.assertTrue(hasattr(self.processor, '_extract_entity_data'))
    
    def test_csv_conversion_structure(self):
        """Test CSV conversion with mock data."""
        mock_data = {
            'entities': [
                {'type': 'LINE', 'layer': 'Layer1', 'color': 7, 
                 'start': '0,0', 'end': '10,10', 'length': '14.14'}
            ],
            'layers': [
                {'name': 'Layer1', 'color': 7, 'linetype': 'CONTINUOUS', 'on': True}
            ],
            'blocks': [
                {'name': 'Block1', 'entity_count': 5}
            ],
            'metadata': {},
            'text_content': ''
        }
        
        csv_output = self.processor.convert_to_csv(mock_data)
        self.assertIsInstance(csv_output, str)
        self.assertIn('LINE', csv_output)
        self.assertIn('Layer1', csv_output)

class TestSemanticMemory(unittest.TestCase):
    """Test ChromaDB vector database functionality."""
    
    def test_embedding_id_generation(self):
        """Test stable ID generation."""
        path1 = "/test/file.dwg"
        path2 = "/test/file.dwg"
        path3 = "/test/other.dwg"
        
        id1 = generate_embedding_id(path1)
        id2 = generate_embedding_id(path2)
        id3 = generate_embedding_id(path3)
        
        # Same path should give same ID
        self.assertEqual(id1, id2)
        # Different path should give different ID
        self.assertNotEqual(id1, id3)
        # IDs should be hex strings
        self.assertEqual(len(id1), 64)  # SHA256 produces 64 hex chars
    
    def test_database_stats(self):
        """Test database statistics retrieval."""
        stats = get_database_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn('total_files', stats)
        self.assertIn('pdf_files', stats)
        self.assertIn('dwg_files', stats)

class TestUtils(unittest.TestCase):
    """Test utility functions."""
    
    def test_clean_specs(self):
        """Test specification cleaning."""
        dirty_specs = {
            'title': 'Test Drawing',
            'noise': 'is the sole property',
            'empty': '   ',
            'valid_list': ['Item1', 'rev date description', 'Item2'],
            'empty_value': ''
        }
        
        cleaned = clean_specs(dirty_specs)
        self.assertIn('title', cleaned)
        self.assertNotIn('noise', cleaned)
        self.assertNotIn('empty', cleaned)
        self.assertNotIn('empty_value', cleaned)
        
        # Check list cleaning
        if 'valid_list' in cleaned:
            self.assertNotIn('rev date description', cleaned['valid_list'])
            self.assertIn('Item1', cleaned['valid_list'])
    
    def test_is_valid_specs(self):
        """Test specification validation."""
        valid_specs = {'title': 'Test', 'scale': '1:100'}
        empty_specs = {}
        all_empty = {'a': '', 'b': None, 'c': []}
        
        self.assertTrue(is_valid_specs(valid_specs))
        self.assertFalse(is_valid_specs(empty_specs))
        self.assertFalse(is_valid_specs(all_empty))

class TestConfiguration(unittest.TestCase):
    """Test configuration validation."""
    
    def test_config_validation(self):
        """Test configuration validation function."""
        warnings = validate_config()
        self.assertIsInstance(warnings, list)
        # Each warning should be a string
        for warning in warnings:
            self.assertIsInstance(warning, str)

class TestEndToEndWorkflow(unittest.TestCase):
    """Test complete workflows."""
    
    def test_add_and_retrieve_workflow(self):
        """Test adding and retrieving a file."""
        # Create a mock file path
        test_path = "/test/mock_drawing.dwg"
        test_description = "Test drawing for unit testing"
        test_specs = {"title": "Test", "scale": "1:100"}
        
        # Add to database
        success = add_to_database(test_path, test_description, test_specs, silent=True)
        self.assertTrue(success)
        
        # Check if exists
        exists = file_exists_in_database(test_path)
        self.assertTrue(exists)
        
        # Retrieve
        data = get_from_database(test_path)
        self.assertIsNotNone(data)
        self.assertEqual(data['filepath'], os.path.abspath(test_path))
        self.assertEqual(data['description'], test_description)

def run_test_suite():
    """Run all tests with colored output."""
    print(Fore.CYAN + "="*80)
    print(Fore.GREEN + "🧪 Running AutoCAD Drawing Processing System Tests")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDWGProcessor))
    suite.addTests(loader.loadTestsFromTestCase(TestSemanticMemory))
    suite.addTests(loader.loadTestsFromTestCase(TestUtils))
    suite.addTests(loader.loadTestsFromTestCase(TestConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndWorkflow))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print(Fore.CYAN + "\n" + "="*80)
    print(Fore.GREEN + "📊 Test Summary")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    print(f"Tests Run: {result.testsRun}")
    print(Fore.GREEN + f"✓ Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    if result.failures:
        print(Fore.RED + f"✗ Failures: {len(result.failures)}")
    if result.errors:
        print(Fore.RED + f"✗ Errors: {len(result.errors)}")
    print(Fore.CYAN + "="*80 + Style.RESET_ALL)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_test_suite()
    exit(0 if success else 1)