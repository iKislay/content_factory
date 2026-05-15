#!/usr/bin/env python3
"""
Test script for Google Cloud TTS integration
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from providers.tts import synthesize_speech

def test_tts():
    """Test Google Cloud TTS functionality"""
    print("[TEST] Testing Google Cloud TTS...")
    
    # Test text
    test_text = "Hello, this is a test of the Google Cloud Text-to-Speech system."
    
    # Output file
    output_file = "test_output.wav"
    
    try:
        # Attempt synthesis
        success = synthesize_speech(
            text=test_text,
            output_path=output_file,
            voice_name="en-US-Standard-C",
            language_code="en-US",
            speaking_rate=1.0
        )
        
        if success and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            print(f"[TEST SUCCESS] Audio file created: {output_file} ({file_size} bytes)")
            return True
        else:
            print("[TEST FAILED] Audio file was not created")
            return False
            
    except Exception as e:
        print(f"[TEST ERROR] Exception occurred: {e}")
        return False

if __name__ == "__main__":
    success = test_tts()
    sys.exit(0 if success else 1)