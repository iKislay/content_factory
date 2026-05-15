# providers/tts.py
import os
import logging
import requests
import json
from typing import Optional
import config

logger = logging.getLogger(__name__)

class TTSProviderError(Exception):
    """Exception raised when TTS provider fails."""
    pass

def synthesize_speech(text: str, output_path: str, voice_name: str = "en-US-Standard-C", 
                     language_code: str = "en-US", speaking_rate: float = 1.0) -> bool:
    """
    Synthesize speech using Google Cloud Text-to-Speech API via REST.
    
    Args:
        text: Text to synthesize
        output_path: Path to save the audio file
        voice_name: Voice to use for synthesis
        language_code: Language code
        speaking_rate: Speaking rate (0.25 to 4.0)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        api_key = getattr(config, 'GOOGLE_CLOUD_TTS_API_KEY', None)
        if not api_key or api_key == "":
            logger.error("[TTS] GOOGLE_CLOUD_TTS_API_KEY not set")
            return False
            
        # Google Cloud Text-to-Speech API endpoint
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        
        # Request body
        payload = {
            "input": {
                "text": text
            },
            "voice": {
                "languageCode": language_code,
                "name": voice_name
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "speakingRate": speaking_rate
            }
        }
        
        # Make the API request
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code != 200:
            logger.error(f"[TTS] API request failed with status {response.status_code}: {response.text}")
            return False
            
        # Parse response
        result = response.json()
        
        if "audioContent" not in result:
            logger.error("[TTS] No audio content in response")
            return False
            
        # Decode base64 audio content
        import base64
        audio_content = base64.b64decode(result["audioContent"])
        
        # Write to file
        with open(output_path, "wb") as out:
            out.write(audio_content)
            
        logger.info(f"[TTS] Audio content written to file: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"[TTS] Failed to synthesize speech: {e}")
        return False