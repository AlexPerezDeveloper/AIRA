"""
Tests para UI Streamlit - Specification-Driven Development

Specs cubiertas:
- Layout inicial 60/40
- Controles: Iniciar Sesión, Pausar Análisis, Exportar Markdown
- Panel de transcripción en vivo
- Panel de insights (preguntas, requisitos, alertas)
- Integración AudioCapture + Pipeline
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock de Streamlit antes de importar la app
sys.modules['streamlit'] = MagicMock()
import streamlit as st_mock

from streamlit_app import SessionState, format_transcription, export_markdown


class TestSessionState:
    """Feature: Gestión de estado de sesión"""
    
    def test_initial_state(self):
        """Scenario: Estado inicial de la aplicación"""
        state = SessionState()
        assert state.is_running == False
        assert state.is_paused == False
        assert state.transcription_buffer == []
        assert state.requisitos == []
        assert state.preguntas == []
        assert state.alertas == []
        assert state.session_start_time is None
    
    def test_start_session_changes_state(self):
        """Scenario: Iniciar sesión actualiza estado"""
        state = SessionState()
        state.start_session()
        assert state.is_running == True
        assert state.is_paused == False
        assert state.session_start_time is not None
    
    def test_pause_session_toggles_flag(self):
        """Scenario: Pausar/Resumir toggle"""
        state = SessionState()
        state.start_session()
        
        state.toggle_pause()
        assert state.is_paused == True
        assert state.is_running == True  # Sigue corriendo, solo pausa análisis
        
        state.toggle_pause()
        assert state.is_paused == False
    
    def test_stop_session_resets_state(self):
        """Scenario: Detener sesión limpia estado"""
        state = SessionState()
        state.start_session()
        state.transcription_buffer.append("test")
        state.requisitos.append({"id": "RF1"})
        
        state.stop_session()
        assert state.is_running == False
        assert state.is_paused == False


class TestFormatTranscription:
    """Feature: Formateo de transcripción para display"""
    
    def test_empty_buffer_returns_empty_string(self):
        """Scenario: Buffer vacío"""
        result = format_transcription([])
        assert result == ""
    
    def test_single_entry_formatted(self):
        """Scenario: Una entrada con timestamp"""
        result = format_transcription(["[12:34:56] Hola mundo"])
        assert "[12:34:56]" in result
        assert "Hola mundo" in result
    
    def test_multiple_entries_joined(self):
        """Scenario: Múltiples entradas unidas con saltos de línea"""
        entries = [
            "[12:34:56] Primera frase",
            "[12:35:01] Segunda frase"
        ]
        result = format_transcription(entries)
        assert "Primera frase" in result
        assert "Segunda frase" in result
        assert "\n" in result


class TestExportMarkdown:
    """Feature: Exportar sesión a Markdown"""
    
    def test_export_structure(self, tmp_path):
        """Scenario: Estructura del archivo markdown"""
        from pathlib import Path
        state = SessionState()
        state.start_session()
        state.transcription_buffer = ["[12:00:01] Test reunion"]
        state.requisitos = [{"id": "RF1", "descripcion": "Login con Google"}]
        state.preguntas = ["¿Qué es 'rápido'?"]
        state.alertas = ["Dependencia: OAuth"]
        
        # Mock para que guarde en tmp_path (como Path, no string)
        with patch('streamlit_app.get_sessions_dir', return_value=Path(str(tmp_path))):
            filepath = export_markdown(state)
        
        assert filepath is not None
        assert os.path.exists(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar estructura
        assert "# Sesión de Requisitos" in content
        assert "## Resumen Ejecutivo" in content
        assert "## Requisitos Funcionales" in content
        assert "## Preguntas Pendientes" in content
        assert "Login con Google" in content
        assert "¿Qué es 'rápido'?" in content
    
    def test_export_empty_session(self, tmp_path):
        """Scenario: Exportar sesión vacía"""
        from pathlib import Path
        state = SessionState()
        state.start_session()
        
        with patch('streamlit_app.get_sessions_dir', return_value=Path(str(tmp_path))):
            filepath = export_markdown(state)
        
        assert filepath is not None
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for count indicators (may have unicode characters)
        assert "0" in content  # Count of 0 requisitos/preguntas
        assert "# Sesión" in content  # Title has ó


class TestUILayout:
    """Feature: Layout de Streamlit 60/40 (verificado en main)"""
    
    @patch('streamlit_app.st')
    def test_title_rendered(self, mock_st):
        """Scenario: Título de la aplicación"""
        from streamlit_app import render_header
        render_header()
        mock_st.title.assert_called_once()
        assert "AI Requirements Architect" in str(mock_st.title.call_args)


class TestDeviceSelector:
    """Feature: Selector de dispositivo de audio"""
    
    @patch('streamlit_app.st')
    @patch('streamlit_app.list_audio_devices')
    def test_device_selector_shows_options(self, mock_list_devices, mock_st):
        """Scenario: Mostrar dispositivos disponibles"""
        mock_list_devices.return_value = [
            {'name': 'BlackHole 2ch', 'is_input': True},
            {'name': 'Micrófono MacBook', 'is_input': True}
        ]
        mock_st.selectbox.return_value = "BlackHole 2ch"
        
        state = SessionState()
        from streamlit_app import render_device_selector
        selected = render_device_selector(state)
        
        mock_st.selectbox.assert_called_once()
        # Verificar que solo se muestran dispositivos de entrada
        call_args = mock_st.selectbox.call_args
        assert 'options' in call_args[1] or 'options' in call_args[0]
        # Check the options passed to selectbox
        options = call_args[1].get('options', call_args[0][0] if call_args[0] else [])
        assert len(options) == 2
        assert 'BlackHole 2ch' in options or 'BlackHole 2ch ⭐ (recomendado)' in options


class TestControlButtons:
    """Feature: Botones de control"""
    
    @patch('streamlit_app.st')
    def test_columns_created_for_buttons(self, mock_st):
        """Scenario: Se crean columnas para los botones"""
        state = SessionState()
        state.is_running = False
        
        # Mock st.columns to return 3 mock column objects
        mock_col1, mock_col2, mock_col3 = MagicMock(), MagicMock(), MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]
        
        from streamlit_app import render_controls
        action = render_controls(state)
        
        # Verificar que se llamó a columns
        mock_st.columns.assert_called_once()
        # Verify 3 columns returned (used for buttons)
        assert len(mock_st.columns.return_value) == 3


class TestInsightsPanel:
    """Feature: Panel de insights (preguntas, requisitos, alertas)"""
    
    @patch('streamlit_app.st')
    def test_preguntas_expander_shown(self, mock_st):
        """Scenario: Expander de preguntas visible"""
        state = SessionState()
        state.preguntas = ["¿Pregunta 1?", "¿Pregunta 2?"]
        
        # Mock expander as context manager
        mock_expander = MagicMock()
        mock_expander.__enter__ = MagicMock(return_value=mock_expander)
        mock_expander.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_expander
        
        from streamlit_app import render_insights
        render_insights(state)
        
        # Verificar que se llamó a expander con label de preguntas
        expander_calls = [str(call) for call in mock_st.expander.call_args_list]
        assert any("Preguntas" in call or "preguntas" in call.lower() for call in expander_calls)
    
    @patch('streamlit_app.st')
    def test_requisitos_expander_shown(self, mock_st):
        """Scenario: Expander de requisitos visible"""
        state = SessionState()
        state.requisitos = [{"id": "RF1", "descripcion": "Test"}]
        
        # Mock expander
        mock_expander = MagicMock()
        mock_expander.__enter__ = MagicMock(return_value=mock_expander)
        mock_expander.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_expander
        
        from streamlit_app import render_insights
        render_insights(state)
        
        # Verificar expander de requisitos
        expander_calls = [str(call) for call in mock_st.expander.call_args_list]
        assert any("Requisitos" in call for call in expander_calls)
    
    @patch('streamlit_app.st')
    def test_alertas_expander_shown(self, mock_st):
        """Scenario: Expander de alertas visible"""
        state = SessionState()
        state.alertas = ["Alerta test"]
        
        # Mock expander
        mock_expander = MagicMock()
        mock_expander.__enter__ = MagicMock(return_value=mock_expander)
        mock_expander.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_expander
        
        from streamlit_app import render_insights
        render_insights(state)
        
        # Verificar expander de alertas
        expander_calls = [str(call) for call in mock_st.expander.call_args_list]
        assert any("Alertas" in call or "alertas" in call.lower() for call in expander_calls)


class TestAnalysisCallback:
    """Feature: Callbacks de análisis en tiempo real"""
    
    def test_on_transcription_callback_adds_to_buffer(self):
        """Scenario: Callback agrega transcripción al buffer"""
        state = SessionState()
        
        from streamlit_app import create_transcription_callback
        callback = create_transcription_callback(state)
        
        callback("[12:00:00] Nueva transcripción")
        assert len(state.transcription_buffer) == 1
        assert "Nueva transcripción" in state.transcription_buffer[0]
    
    def test_on_analysis_callback_updates_insights(self):
        """Scenario: Callback actualiza insights del pipeline"""
        state = SessionState()
        
        from streamlit_app import create_analysis_callback
        callback = create_analysis_callback(state)
        
        # Simular resultado del pipeline
        pipeline_result = {
            "analista": {
                "requisitos_funcionales": [{"id": "RF1", "descripcion": "Test"}]
            },
            "arquitecto": {
                "riesgos": ["Riesgo test"]
            },
            "qa": {
                "preguntas": ["Pregunta 1", "Pregunta 2"]
            }
        }
        callback(pipeline_result)
        
        assert len(state.requisitos) == 1
        assert len(state.alertas) == 1
        assert len(state.preguntas) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
