#!/usr/bin/env python3
"""
Installation verification script for Prompt Security Pipeline
Run this to verify that everything is installed correctly
"""

import sys
from typing import List, Tuple

def check_import(module_path: str, description: str) -> Tuple[bool, str]:
    """Check if a module can be imported"""
    try:
        __import__(module_path)
        return (True, f"✓ {description}")
    except ImportError as e:
        return (False, f"✗ {description}: {str(e)}")
    except Exception as e:
        return (False, f"✗ {description}: Unexpected error: {str(e)}")

def main():
    print("=" * 70)
    print("PROMPT SECURITY PIPELINE - INSTALLATION VERIFICATION")
    print("=" * 70)
    print()
    
    checks = [
        ("app.security", "Security module"),
        ("app.security.pipeline", "Pipeline orchestrator"),
        ("app.security.layer1_heuristic", "Layer 1: Heuristic Analysis"),
        ("app.security.layer2_ml", "Layer 2: ML Classification"),
        ("app.security.layer3_canary", "Layer 3: Canary Testing"),
        ("app.security.scoring", "Scoring Service"),
        ("app.security.models", "Data Models"),
        ("httpx", "HTTPX library (for Layer 2)"),
        ("groq", "Groq library (for Layer 3)"),
    ]
    
    results: List[Tuple[bool, str]] = []
    
    print("Checking imports...")
    print("-" * 70)
    
    for module, description in checks:
        success, message = check_import(module, description)
        results.append((success, message))
        print(message)
    
    print()
    print("-" * 70)
    
    # Summary
    successes = sum(1 for success, _ in results if success)
    failures = len(results) - successes
    
    print()
    print("SUMMARY")
    print("-" * 70)
    print(f"Total checks: {len(results)}")
    print(f"Passed: {successes}")
    print(f"Failed: {failures}")
    print()
    
    if failures == 0:
        print("✅ All checks passed! Security pipeline is ready to use.")
        print()
        print("Next steps:")
        print("1. Set GROQ_API_KEY in your .env file")
        print("2. Start server: uvicorn app.main:app --reload")
        print("3. Test endpoint: curl http://localhost:8000/api/v1/security-check \\")
        print('     -H "Content-Type: application/json" \\')
        print('     -d \'{"prompt": "Test prompt"}\'')
        print()
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print()
        if any("httpx" in msg.lower() for _, msg in results if not _):
            print("To install missing dependencies:")
            print("  cd server && uv pip install httpx")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
