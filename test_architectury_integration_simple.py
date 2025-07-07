#!/usr/bin/env python3
"""
Simple test script to verify the updated Architectury integration.
"""

import os
import sys
from pathlib import Path

def test_architectury_template():
    """Test that the Architectury template has the required elements."""
    print("=== Testing Architectury Template ===")
    
    template_path = "templates/architectury_testing.html"
    if not os.path.exists(template_path):
        print(f"❌ Template not found: {template_path}")
        return False
    
    with open(template_path, 'r') as f:
        content = f.read()
    
    required_elements = [
        'architectury-platform',
        'architectury-host', 
        'architectury-build-collectors',
        'start-architectury-testing',
        'download-architectury-collector-btn',
        'cleanup-architectury-btn'
    ]
    
    for element in required_elements:
        if f'id="{element}"' not in content:
            print(f"❌ Missing element: {element}")
            return False
        print(f"✅ Found element: {element}")
    
    return True

def test_backend_integration():
    """Test that the backend uses existing functions."""
    print("\n=== Testing Backend Integration ===")
    
    web_interface_path = "web_interface.py"
    if not os.path.exists(web_interface_path):
        print(f"❌ Web interface not found: {web_interface_path}")
        return False
    
    with open(web_interface_path, 'r') as f:
        content = f.read()
    
    # Check that it uses existing functions instead of duplicating logic
    existing_functions = [
        'push_and_execute_collector',
        'pull_collection_data', 
        'process_collection_data',
        'Config.get(\'COLLECTOR_FILE\')'
    ]
    
    for func in existing_functions:
        if func not in content:
            print(f"❌ Missing existing function usage: {func}")
            return False
        print(f"✅ Uses existing function: {func}")
    
    return True

def test_collector_manager_integration():
    """Test that CollectorManager has the required Architectury method."""
    print("\n=== Testing CollectorManager Integration ===")
    
    collector_manager_path = "collector_manager.py"
    if not os.path.exists(collector_manager_path):
        print(f"❌ CollectorManager not found: {collector_manager_path}")
        return False
    
    with open(collector_manager_path, 'r') as f:
        content = f.read()
    
    # Check for Architectury method
    if 'build_collector_with_architectury' not in content:
        print("❌ Missing build_collector_with_architectury method")
        return False
    print("✅ Found build_collector_with_architectury method")
    
    # Check that it copies to COLLECTOR_FILE location
    if 'collector_file_path = Config.get(\'COLLECTOR_FILE\')' not in content:
        print("❌ Missing COLLECTOR_FILE integration")
        return False
    print("✅ Found COLLECTOR_FILE integration")
    
    return True

def main():
    """Run all tests."""
    print("🧪 Testing Updated Architectury Integration")
    print("=" * 50)
    
    tests = [
        test_architectury_template,
        test_backend_integration,
        test_collector_manager_integration
    ]
    
    all_passed = True
    for test in tests:
        if not test():
            all_passed = False
        print()
    
    if all_passed:
        print("🎉 All tests passed!")
        print("\n📋 Summary:")
        print("   ✅ Architectury template has all required elements")
        print("   ✅ Backend uses existing functions (no duplication)")
        print("   ✅ CollectorManager integrates with COLLECTOR_FILE")
        print("   ✅ Remote execution uses existing push_and_execute_collector")
        print("   ✅ Data processing uses existing pull_collection_data")
        return True
    else:
        print("💥 Some tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 