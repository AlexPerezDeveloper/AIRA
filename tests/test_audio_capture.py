"""
Tests para Captura de Audio - Specification-Driven Development

Specs cubiertas:
- Detección de dispositivo de audio en macOS y Windows
- Inicio de captura de audio con Azure Speech SDK
- Transcripción en español
- Acumulación de buffer cada 30 segundos
"""

import pytest
import sys
import os

# Añadir src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from audio_capture import AudioCapture, list_audio_devices


class TestListAudioDevices:
    """Feature: Detección de dispositivo de audio"""
    
    def test_list_devices_returns_list(self):
        """Scenario: Listar dispositivos disponibles"""
        devices = list_audio_devices()
        assert isinstance(devices, list)
        assert len(devices) > 0  # Al menos el micrófono del sistema
    
    def test_list_devices_contains_input_devices(self):
        """Scenario: Detectar dispositivos de entrada"""
        devices = list_audio_devices()
        input_devices = [d for d in devices if d.get('is_input', False)]
        assert len(input_devices) >= 1
    
    def test_macos_detects_blackhole(self):
        """Scenario: macOS detecta BlackHole
        
        Nota: Este test solo corre en macOS y si BlackHole está instalado
        """
        import platform
        if platform.system() != 'Darwin':
            pytest.skip("Solo macOS")
        
        devices = list_audio_devices()
        blackhole_devices = [d for d in devices 
                           if 'blackhole' in d.get('name', '').lower()]
        
        # Puede fallar si BlackHole no está instalado - es OK para SDD
        if not blackhole_devices:
            pytest.skip("BlackHole no instalado - instalar con: brew install blackhole-2ch")
        
        assert len(blackhole_devices) >= 1
    
    def test_windows_detects_vbcable(self):
        """Scenario: Windows detecta VB-Cable
        
        Nota: Este test solo corre en Windows y si VB-Cable está instalado
        """
        import platform
        if platform.system() != 'Windows':
            pytest.skip("Solo Windows")
        
        devices = list_audio_devices()
        cable_devices = [d for d in devices 
                        if 'cable' in d.get('name', '').lower() 
                        or 'vb-audio' in d.get('name', '').lower()]
        
        if not cable_devices:
            pytest.skip("VB-Cable no instalado - descargar de vb-audio.com")
        
        assert len(cable_devices) >= 1


class TestAudioCaptureInit:
    """Feature: Inicialización del capturador"""
    
    def test_audio_capture_requires_device_name(self):
        """Scenario: Configuración requerida"""
        with pytest.raises(ValueError):
            AudioCapture(device_name=None)
    
    def test_audio_capture_accepts_device_name(self):
        """Scenario: Configuración con dispositivo válido"""
        capture = AudioCapture(device_name="Mock Device")
        assert capture.device_name == "Mock Device"
        assert capture.language == "es-ES"  # Default
    
    def test_audio_capture_accepts_custom_language(self):
        """Scenario: Configuración de idioma español"""
        capture = AudioCapture(device_name="Test", language="es-MX")
        assert capture.language == "es-MX"


class TestBufferManagement:
    """Feature: Acumulación de buffer cada 30 segundos"""
    
    def test_buffer_initially_empty(self):
        """Scenario: Buffer vacío al inicio"""
        capture = AudioCapture(device_name="Test")
        assert len(capture.text_buffer) == 0
        assert capture.buffer_ready == False
    
    def test_buffer_accumulates_text(self):
        """Scenario: Acumular transcripción (con timestamp)"""
        capture = AudioCapture(device_name="Test")
        capture._on_transcription("Hola mundo")
        assert len(capture.text_buffer) == 1
        # El buffer incluye timestamp: [HH:MM:SS] Hola mundo
        assert "Hola mundo" in capture.text_buffer[0]
        assert "[" in capture.text_buffer[0] and "]" in capture.text_buffer[0]
    
    def test_buffer_window_management(self):
        """Scenario: Ventana deslizante de 30 segundos"""
        capture = AudioCapture(device_name="Test", window_seconds=30)
        
        # Simular múltiples transcripciones
        for i in range(10):
            capture._on_transcription(f"Texto {i}")
        
        # El buffer debe mantener el histórico
        assert len(capture.text_buffer) == 10
        
        # Obtener chunk para análisis
        chunk = capture.get_analysis_chunk()
        assert isinstance(chunk, str)
        assert "Texto" in chunk
    
    def test_analysis_interval_configuration(self):
        """Scenario: Intervalo configurable via env var"""
        import os
        os.environ['ANALYSIS_INTERVAL_SECONDS'] = '60'
        
        capture = AudioCapture(device_name="Test")
        assert capture.analysis_interval == 60
        
        # Cleanup
        del os.environ['ANALYSIS_INTERVAL_SECONDS']


class TestAzureSpeechIntegration:
    """Feature: Integración con Azure Speech SDK
    
    Estos tests requieren variables de entorno configuradas:
    - AZURE_SPEECH_KEY
    - AZURE_SPEECH_REGION
    """
    
    def test_azure_credentials_required(self):
        """Scenario: Error si faltan credenciales de Azure"""
        import os
        
        # Limpiar env vars
        original_key = os.environ.pop('AZURE_SPEECH_KEY', None)
        original_region = os.environ.pop('AZURE_SPEECH_REGION', None)
        
        try:
            capture = AudioCapture(device_name="Test")
            
            # Intentar inicializar Azure debe fallar sin credenciales
            with pytest.raises((ValueError, RuntimeError)):
                capture._init_speech_recognizer()
        finally:
            # Restore
            if original_key:
                os.environ['AZURE_SPEECH_KEY'] = original_key
            if original_region:
                os.environ['AZURE_SPEECH_REGION'] = original_region
    
    @pytest.mark.skipif(
        not os.environ.get('AZURE_SPEECH_KEY'),
        reason="AZURE_SPEECH_KEY no configurado"
    )
    def test_speech_recognizer_initializes_with_valid_credentials(self):
        """Scenario: Azure Speech SDK se inicializa con credenciales válidas"""
        capture = AudioCapture(device_name="Test", language="es-ES")
        recognizer = capture._init_speech_recognizer()
        assert recognizer is not None


class TestTranscriptionCallback:
    """Feature: Callback de transcripción en tiempo real"""
    
    def test_transcription_callback_receives_text(self):
        """Scenario: Transcripción en español recibida (con timestamp)"""
        capture = AudioCapture(device_name="Test")
        received_text = []
        
        def mock_callback(text):
            received_text.append(text)
        
        capture.set_transcription_callback(mock_callback)
        capture._on_transcription("Necesitamos login con Google")
        
        assert len(received_text) == 1
        # El callback recibe el texto con timestamp
        assert "Necesitamos login con Google" in received_text[0]
        assert "[" in received_text[0] and "]" in received_text[0]
    
    def test_transcription_spanish_characters(self):
        """Scenario: Caracteres españoles correctamente manejados (con timestamp)"""
        capture = AudioCapture(device_name="Test")
        spanish_text = "El usuario quiere niños, acción, y cañón"
        
        capture._on_transcription(spanish_text)
        # El buffer contiene el texto con timestamp
        assert spanish_text in capture.text_buffer[0]
        assert capture.text_buffer[0].count("ñ") == 2  # niños y cañón
        assert "acción" in capture.text_buffer[0]


class TestStartStopSession:
    """Feature: Inicio y fin de sesión de captura"""
    
    def test_session_not_started_initially(self):
        """Scenario: Estado inicial - sesión no iniciada"""
        capture = AudioCapture(device_name="Test")
        assert capture.is_running == False
    
    def test_start_session_changes_state(self):
        """Scenario: Iniciar sesión cambia estado
        
        Nota: Este test es un mock - la implementación real requeriría Azure credentials
        """
        capture = AudioCapture(device_name="Test")
        
        # Sin Azure credentials, start_session debe fallar
        with pytest.raises((ValueError, RuntimeError)):
            capture.start_session()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
