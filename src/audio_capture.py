"""
Captura de Audio + Transcripción Azure - AI Requirements Architect

Implementa:
- Detección de dispositivos de audio (macOS/Windows)
- Integración con Azure Speech SDK
- Buffer de transcripción con ventana deslizante
- Callbacks para procesamiento en tiempo real
"""

import os
import time
import platform
from datetime import datetime
from typing import List, Dict, Callable, Optional, Any
import threading
import queue

# Audio
import sounddevice as sd

# Azure
import azure.cognitiveservices.speech as speechsdk


def list_audio_devices() -> List[Dict[str, Any]]:
    """
    Lista todos los dispositivos de audio disponibles.
    
    Returns:
        Lista de diccionarios con información de cada dispositivo:
        - name: nombre del dispositivo
        - index: índice del dispositivo
        - is_input: True si es dispositivo de entrada (micrófono)
        - is_output: True si es dispositivo de salida (altavoces)
    """
    devices = []
    
    try:
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            devices.append({
                'name': device['name'],
                'index': i,
                'is_input': device['max_input_channels'] > 0,
                'is_output': device['max_output_channels'] > 0,
                'default_samplerate': device['default_samplerate']
            })
    except Exception as e:
        print(f"Error al listar dispositivos: {e}")
        # Fallback: retornar lista vacía, el caller debe manejar
    
    return devices


def find_loopback_device() -> Optional[str]:
    """
    Busca automáticamente el dispositivo de loopback según el OS.
    
    macOS: busca "BlackHole"
    Windows: busca "CABLE" o "VB-Audio"
    
    Returns:
        Nombre del dispositivo encontrado, o None si no se encuentra
    """
    system = platform.system()
    devices = list_audio_devices()
    
    search_terms = []
    
    if system == 'Darwin':  # macOS
        search_terms = ['blackhole']
    elif system == 'Windows':
        search_terms = ['cable', 'vb-audio', 'virtual cable']
    else:
        return None
    
    for device in devices:
        device_name_lower = device['name'].lower()
        if any(term in device_name_lower for term in search_terms):
            if device['is_input']:  # Necesitamos dispositivo de entrada
                return device['name']
    
    return None


class AudioCapture:
    """
    Captura audio del sistema y transcribe mediante Azure Speech Services.
    """
    
    def __init__(
        self,
        device_name: Optional[str] = None,
        language: str = "es-ES",
        window_seconds: int = 30
    ):
        """
        Inicializa el capturador de audio.
        
        Args:
            device_name: Nombre del dispositivo de audio (e.g., "BlackHole 2ch")
            language: Código de idioma para Azure Speech (default: "es-ES")
            window_seconds: Tamaño de ventana deslizante para análisis
            
        Raises:
            ValueError: Si no se proporciona device_name y no se encuentra loopback
        """
        if device_name is None:
            device_name = find_loopback_device()
            if device_name is None:
                available = [d['name'] for d in list_audio_devices() if d['is_input']]
                raise ValueError(
                    f"No se encontró dispositivo de loopback automáticamente. "
                    f"Dispositivos disponibles: {available}. "
                    f"Instala BlackHole (macOS) o VB-Cable (Windows)."
                )
        
        self.device_name = device_name
        self.language = language
        self.window_seconds = window_seconds
        
        # Buffer de transcripción
        self.text_buffer: List[str] = []
        self.buffer_lock = threading.Lock()
        self.buffer_ready = False
        self.last_analysis_time = 0.0
        
        # Configuración de análisis
        self.analysis_interval = int(os.environ.get('ANALYSIS_INTERVAL_SECONDS', '30'))
        
        # Azure Speech
        self._speech_config: Optional[speechsdk.SpeechConfig] = None
        self._audio_config: Optional[speechsdk.AudioConfig] = None
        self._recognizer: Optional[speechsdk.SpeechRecognizer] = None
        
        # Callbacks
        self._transcription_callback: Optional[Callable[[str], None]] = None
        self._analysis_callback: Optional[Callable[[str], None]] = None
        
        # Estado
        self.is_running = False
        self.last_error: Optional[str] = None
        self._analysis_in_progress = False  # Evitar solapamiento de IA
        self._stop_event = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
    
    def set_transcription_callback(self, callback: Callable[[str], None]) -> None:
        """
        Registra callback para recibir transcripción en tiempo real.
        
        Args:
            callback: Función que recibe el texto transcribido
        """
        self._transcription_callback = callback
    
    def set_analysis_callback(self, callback: Callable[[str], None]) -> None:
        """
        Registra callback para recibir chunks listos para análisis.
        
        Args:
            callback: Función que recibe el texto del chunk
        """
        self._analysis_callback = callback
    
    def _init_speech_recognizer(self) -> speechsdk.SpeechRecognizer:
        """
        Inicializa el recognizer de Azure Speech.
        
        Returns:
            SpeechRecognizer configurado
            
        Raises:
            ValueError: Si faltan credenciales de Azure
        """
        speech_key = os.environ.get('AZURE_SPEECH_KEY')
        speech_region = os.environ.get('AZURE_SPEECH_REGION', 'westeurope')
        
        if not speech_key:
            raise ValueError(
                "AZURE_SPEECH_KEY no configurada. "
                "Obtén una key en: https://portal.azure.com/ "
                "Plan F0: 5h/mes gratis."
            )
        
        # Configuración
        self._speech_config = speechsdk.SpeechConfig(
            subscription=speech_key,
            region=speech_region
        )
        self._speech_config.speech_recognition_language = self.language
        
        # Configuración de audio desde dispositivo específico
        # En macOS, Azure prefiere use_default_microphone=True.
        # Solo usamos device_name si es estrictamente necesario y no es el default.
        is_default = False
        try:
            default_in = sd.query_devices(kind='input')
            if self.device_name and default_in and self.device_name == default_in['name']:
                is_default = True
        except:
            pass

        if not self.device_name or is_default:
            print("Usando dispositivo de audio predeterminado del sistema")
            self._audio_config = speechsdk.AudioConfig(use_default_microphone=True)
        else:
            print(f"Intentando configurar AudioConfig con dispositivo: {self.device_name}")
            # Nota: En macOS esto puede fallar si no es un System Device ID válido (UUID)
            self._audio_config = speechsdk.AudioConfig(device_name=self.device_name)
        
        # Crear recognizer
        self._recognizer = speechsdk.SpeechRecognizer(
            speech_config=self._speech_config,
            audio_config=self._audio_config
        )
        
        # Configurar callbacks
        self._recognizer.recognizing.connect(self._on_recognizing)
        self._recognizer.recognized.connect(self._on_recognized)
        self._recognizer.session_started.connect(self._on_session_started)
        self._recognizer.session_stopped.connect(self._on_session_stopped)
        self._recognizer.canceled.connect(self._on_canceled)
        
        return self._recognizer
    
    def _on_recognizing(self, evt: speechsdk.SpeechRecognitionEventArgs) -> None:
        """Callback durante reconocimiento en progreso (resultados parciales)"""
        if evt.result.text:
            # Transcripción parcial - opcionalmente notificar
            pass
    
    def _on_recognized(self, evt: speechsdk.SpeechRecognitionEventArgs) -> None:
        """Callback cuando se completa una frase"""
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self._on_transcription(text)
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            # No se reconoció audio - silencio o ruido
            pass
    
    def _on_session_started(self, evt: speechsdk.SessionEventArgs) -> None:
        """Callback cuando inicia la sesión"""
        print(f"Sesión de transcripción iniciada: {evt.session_id}")
    
    def _on_session_stopped(self, evt: speechsdk.SessionEventArgs) -> None:
        """Callback cuando se detiene la sesión"""
        print(f"Sesión de transcripción detenida: {evt.session_id}")
    
    def _on_canceled(self, evt: speechsdk.SpeechRecognitionCanceledEventArgs) -> None:
        """Callback cuando ocurre cancelación/error"""
        error_msg = f"Transcripción cancelada. Razón: {evt.reason}"
        if evt.reason == speechsdk.CancellationReason.Error:
            error_msg += f" - Error: {evt.error_details}"
            print(f"[ERROR] {error_msg}")
        else:
            print(f"[INFO] {error_msg}")
        
        self.last_error = error_msg
    
    def _on_transcription(self, text: str) -> None:
        """
        Procesa texto transcribido: agrega al buffer y notifica callbacks.
        
        Args:
            text: Texto transcribido por Azure
        """
        if not text.strip():
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}"
        
        with self.buffer_lock:
            self.text_buffer.append(entry)
            
            # Verificar si debemos realizar análisis
            current_time = time.time()
            if not self._analysis_in_progress and (current_time - self.last_analysis_time >= self.analysis_interval):
                self.last_analysis_time = current_time
                
                # Obtener solo las últimas N entradas para la ventana de análisis (ej: últimas 15)
                # Esto evita que el procesamiento se vuelva más lento con el tiempo
                analysis_window = self.text_buffer[-15:]
                chunk = "\n".join(analysis_window)
                
                if self._analysis_callback:
                    # Iniciar análisis en un hilo separado para no bloquear la captura de audio
                    threading.Thread(
                        target=self._run_analysis_safely,
                        args=(chunk,),
                        daemon=True
                    ).start()
        
        # Notificar callback de transcripción en tiempo real
        if self._transcription_callback:
            try:
                self._transcription_callback(entry)
            except Exception as e:
                print(f"Error en transcription_callback: {e}")
    
    def _run_analysis_safely(self, chunk: str) -> None:
        """Ejecuta el análisis asegurando que no se solapen tareas pesadas."""
        if self._analysis_in_progress:
            return
            
        try:
            self._analysis_in_progress = True
            if self._analysis_callback:
                self._analysis_callback(chunk)
        except Exception as e:
            print(f"Error en analysis_callback: {e}")
        finally:
            self._analysis_in_progress = False
    
    def _get_chunk_unlocked(self) -> str:
        """Versión interna sin lock - usar solo cuando se tenga el lock."""
        return "\n".join(self.text_buffer)
    
    def get_analysis_chunk(self) -> str:
        """
        Obtiene el chunk de texto listo para análisis.
        
        Returns:
            String con el contenido acumulado del buffer
        """
        with self.buffer_lock:
            return self._get_chunk_unlocked()
    
    def clear_buffer(self) -> None:
        """Limpia el buffer de transcripción."""
        with self.buffer_lock:
            self.text_buffer.clear()
            self.buffer_ready = False
    
    def start_session(self) -> None:
        """
        Inicia la sesión de captura y transcripción.
        
        Raises:
            ValueError: Si faltan credenciales de Azure
            RuntimeError: Si ya hay una sesión activa
        """
        if self.is_running:
            raise RuntimeError("Ya hay una sesión activa")
        
        # Inicializar recognizer
        recognizer = self._init_speech_recognizer()
        
        self.is_running = True
        self._stop_event.clear()
        self.last_analysis_time = time.time()
        
        # Iniciar reconocimiento continuo
        recognizer.start_continuous_recognition()
        
        print(f"Sesión iniciada. Dispositivo: {self.device_name}")
        print(f"Idioma: {self.language}")
        print(f"Intervalo de análisis: {self.analysis_interval}s")
    
    def stop_session(self) -> None:
        """Detiene la sesión de captura."""
        if not self.is_running:
            return
        
        self._stop_event.set()
        self.is_running = False
        
        if self._recognizer:
            self._recognizer.stop_continuous_recognition()
        
        print("Sesión detenida")
    
    def get_transcription_history(self) -> List[str]:
        """
        Obtiene el historial completo de transcripción.
        
        Returns:
            Lista de entradas de transcripción
        """
        with self.buffer_lock:
            return self.text_buffer.copy()


if __name__ == "__main__":
    # Demo/test manual
    print("Dispositivos de audio disponibles:")
    for device in list_audio_devices():
        print(f"  [{device['index']}] {device['name']} "
              f"(in:{device['is_input']} out:{device['is_output']})")
    
    print("\nBuscando dispositivo de loopback...")
    loopback = find_loopback_device()
    if loopback:
        print(f"Encontrado: {loopback}")
    else:
        print("No encontrado. Instala BlackHole (macOS) o VB-Cable (Windows)")
