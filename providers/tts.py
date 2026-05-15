# providers/tts.py
import os
import logging
from typing import Optional
from google.cloud import texttospeech
from google.oauth2 import service_account
import config

logger = logging.getLogger(__name__)

class TTSProviderError(Exception):
    """Exception raised when TTS provider fails."""
    pass

def initialize_google_tts_client():
    """Initialize Google Cloud TTS client with appropriate credentials."""
    try:
        # Check if we have API key authentication
        api_key = getattr(config, 'GOOGLE_CLOUD_TTS_API_KEY', None)
        if api_key and api_key != "":
            # For Google Cloud services with API key, we need to use transport with API key
            from google.api_core import gapic_v1
            from google.api_core import client_info
            from google.auth import credentials as auth_credentials
            
            # Create credentials from API key
            class ApiKeyCredentials(auth_credentials.Credentials):
                def __init__(self, api_key):
                    self.api_key = api_key
                    self.token = None
                    
                def refresh(self, request):
                    self.token = self.api_key
                    
            credentials = ApiKeyCredentials(api_key)
            client = texttospeech.TextToSpeechClient(credentials=credentials)
            logger.info("[TTS] Initialized Google Cloud TTS with API key")
            return client
         
        # Check if we have service account credentials
        service_account_path = getattr(config, 'GOOGLE_APPLICATION_CREDENTIALS', None)
        if service_account_path and os.path.exists(service_account_path):
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path
            )
            client = texttospeech.TextToSpeechClient(credentials=credentials)
            logger.info("[TTS] Initialized Google Cloud TTS with service account")
            return client
            
        # Fallback to default credentials (should work if running on GCP or with gcloud auth)
        client = texttospeech.TextToSpeechClient()
        logger.info("[TTS] Initialized Google Cloud TTS with default credentials")
        return client
        
    except Exception as e:
        logger.error(f"[TTS] Failed to initialize Google Cloud TTS client: {e}")
        # Don't raise exception here - let the calling code handle fallback
        return None

def synthesize_speech(text: str, output_path: str, voice_name: str = "en-US-Standard-C", 
                     language_code: str = "en-US", speaking_rate: float = 1.0) -> bool:
    """
    Synthesize speech using Google Cloud Text-to-Speech.
    
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
        client = initialize_google_tts_client()
        
        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Build the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name
        )
        
        # Select the type of audio file
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=speaking_rate
        )
        
        # Perform the text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        # Write the response to the output file
        with open(output_path, "wb") as out:
            out.write(response.audio_content)
            
        logger.info(f"[TTS] Audio content written to file: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"[TTS] Failed to synthesize speech: {e}")
        return False