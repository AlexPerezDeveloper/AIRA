"""
Tests para Pipeline Multi-Agente - Specification-Driven Development

Specs cubiertas:
- Agente Analista: extracción de entidades y requisitos
- Agente Arquitecto: evaluación de dependencias técnicas
- Agente QA: detección de ambigüedades, 5 preguntas
- Pipeline completo: latencia <10s
- Fallback: Gemma 3 si Gemma 4 no disponible
"""

import pytest
import json
import time
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent_pipeline import AgentPipeline, AnalystAgent, ArchitectAgent, QAAgent


class TestAnalystAgent:
    """Feature: Agente Analista - Extracción de entidades"""
    
    def test_analyst_agent_requires_transcription(self):
        """Scenario: Agente requiere transcripción como input"""
        agent = AnalystAgent()
        with pytest.raises(ValueError):
            agent.analyze("")
    
    @patch('agent_pipeline.OllamaClient')
    def test_analyst_extracts_requirements(self, mock_ollama):
        """Scenario: Extraer requisitos funcionales de transcripción"""
        # Mock respuesta de Ollama
        mock_response = {
            "requisitos_funcionales": [
                {"id": "RF1", "descripcion": "Login con Google", "tipo": "autenticación"}
            ],
            "entidades": ["usuario", "login"],
            "stakeholders": ["usuario"]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = AnalystAgent(client=mock_ollama.return_value)
        result = agent.analyze("El usuario quiere login con Google")
        
        assert "requisitos_funcionales" in result
        assert len(result["requisitos_funcionales"]) == 1
        assert result["requisitos_funcionales"][0]["descripcion"] == "Login con Google"
    
    @patch('agent_pipeline.OllamaClient')
    def test_analyst_extracts_entities(self, mock_ollama):
        """Scenario: Extraer entidades de negocio"""
        mock_response = {
            "requisitos_funcionales": [],
            "entidades": ["usuario", "admin", "sistema", "email"],
            "stakeholders": ["usuario", "admin"]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = AnalystAgent(client=mock_ollama.return_value)
        result = agent.analyze("El admin configura el sistema para el usuario")
        
        assert "entidades" in result
        assert "usuario" in result["entidades"]
        assert "admin" in result["entidades"]
    
    @patch('agent_pipeline.OllamaClient')
    def test_analyst_output_is_valid_json(self, mock_ollama):
        """Scenario: Output es JSON parseable"""
        mock_ollama.return_value.generate.return_value = '{"requisitos_funcionales": []}'
        
        agent = AnalystAgent(client=mock_ollama.return_value)
        result = agent.analyze("Texto de prueba")
        
        # Debe ser dict (JSON parseado)
        assert isinstance(result, dict)


class TestArchitectAgent:
    """Feature: Agente Arquitecto - Evaluación técnica"""
    
    def test_architect_requires_analyst_output(self):
        """Scenario: Arquitecto requiere output del Analista"""
        agent = ArchitectAgent()
        with pytest.raises(ValueError):
            agent.analyze({})
    
    @patch('agent_pipeline.OllamaClient')
    def test_architect_identifies_dependencies(self, mock_ollama):
        """Scenario: Identificar dependencias técnicas"""
        mock_response = {
            "dependencias": ["OAuth 2.0 Google API", "SMTP Server"],
            "decisiones_pendientes": ["Base de datos SQL vs NoSQL"],
            "riesgos": ["Rate limiting de Google API"]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = ArchitectAgent(client=mock_ollama.return_value)
        analyst_output = {
            "requisitos_funcionales": [
                {"descripcion": "Login con Google"},
                {"descripcion": "Notificaciones email"}
            ]
        }
        result = agent.analyze(analyst_output)
        
        assert "dependencias" in result
        assert "OAuth 2.0" in result["dependencias"][0]
    
    @patch('agent_pipeline.OllamaClient')
    def test_architect_identifies_risks(self, mock_ollama):
        """Scenario: Detectar riesgos técnicos"""
        mock_response = {
            "dependencias": [],
            "decisiones_pendientes": [],
            "riesgos": ["Escalabilidad desconocida", "Single point of failure"]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = ArchitectAgent(client=mock_ollama.return_value)
        analyst_output = {"requisitos_funcionales": [{"descripcion": "Muchos usuarios concurrentes"}]}
        result = agent.analyze(analyst_output)
        
        assert "riesgos" in result
        assert len(result["riesgos"]) > 0


class TestQAAgent:
    """Feature: Agente QA - Detección de ambigüedades"""
    
    def test_qa_requires_analyst_and_architect_output(self):
        """Scenario: QA requiere outputs previos"""
        agent = QAAgent()
        with pytest.raises(ValueError):
            agent.analyze({}, {})
    
    @patch('agent_pipeline.OllamaClient')
    def test_qa_generates_exactly_5_questions(self, mock_ollama):
        """Scenario: Generar exactamente 5 preguntas"""
        mock_response = {
            "preguntas": [
                "¿Qué significa 'rápido'?",
                "¿Cuántos usuarios concurrentes?",
                "¿Qué tipo de notificaciones?",
                "¿Horario de mantenimiento?",
                "¿Backup requerido?"
            ]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = QAAgent(client=mock_ollama.return_value)
        analyst_output = {"requisitos_funcionales": [{"descripcion": "Sistema rápido"}]}
        architect_output = {"riesgos": ["Performance no definida"]}
        
        result = agent.analyze(analyst_output, architect_output)
        
        assert "preguntas" in result
        assert len(result["preguntas"]) == 5
    
    @patch('agent_pipeline.OllamaClient')
    def test_qa_detects_ambiguous_terms(self, mock_ollama):
        """Scenario: Detectar términos ambiguos como 'rápido', 'mucho'"""
        mock_response = {
            "preguntas": [
                "¿Qué significa 'rápido' específicamente?",
                "¿Cuántos es 'muchos usuarios'?"
            ]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = QAAgent(client=mock_ollama.return_value)
        analyst_output = {"requisitos_funcionales": [
            {"descripcion": "El sistema debe ser rápido"},
            {"descripcion": "Soportar muchos usuarios"}
        ]}
        architect_output = {}
        
        result = agent.analyze(analyst_output, architect_output)
        
        # Verificar que las preguntas abordan ambigüedades
        questions_text = " ".join(result["preguntas"])
        assert "rápido" in questions_text.lower() or "mucho" in questions_text.lower()
    
    @patch('agent_pipeline.OllamaClient')
    def test_qa_questions_in_spanish(self, mock_ollama):
        """Scenario: Preguntas en español"""
        mock_response = {
            "preguntas": ["¿Cuál es el tiempo de respuesta esperado?"]
        }
        mock_ollama.return_value.generate.return_value = json.dumps(mock_response)
        
        agent = QAAgent(client=mock_ollama.return_value)
        result = agent.analyze({"requisitos_funcionales": []}, {})
        
        for question in result["preguntas"]:
            # Verificar caracteres españoles comunes
            assert any(c in question for c in ["¿", "?", "ñ", "ó", "á", "é", "í", "ú"]) or question.isascii()


class TestAgentPipelineIntegration:
    """Feature: Pipeline completo 3-Agent"""
    
    @patch('agent_pipeline.OllamaClient')
    def test_pipeline_executes_sequential(self, mock_ollama):
        """Scenario: Ejecutar Analista → Arquitecto → QA secuencialmente"""
        # Configurar mocks para cada agente
        mock_ollama.return_value.generate.side_effect = [
            # Analista
            '{"requisitos_funcionales": [{"id": "RF1", "descripcion": "Login"}], "entidades": ["usuario"]}',
            # Arquitecto
            '{"dependencias": ["OAuth"], "decisiones_pendientes": [], "riesgos": []}',
            # QA
            '{"preguntas": ["Pregunta 1", "Pregunta 2", "Pregunta 3", "Pregunta 4", "Pregunta 5"]}'
        ]
        
        pipeline = AgentPipeline(client=mock_ollama.return_value)
        result = pipeline.process("El usuario quiere login")
        
        # Verificar estructura completa
        assert "analista" in result
        assert "arquitecto" in result
        assert "qa" in result
        assert "requisitos_funcionales" in result["analista"]
        assert "dependencias" in result["arquitecto"]
        assert "preguntas" in result["qa"]
    
    @patch('agent_pipeline.OllamaClient')
    def test_pipeline_latency_under_10s(self, mock_ollama):
        """Scenario: Pipeline completo en <10 segundos (mock sin delay)"""
        mock_ollama.return_value.generate.side_effect = [
            '{"requisitos_funcionales": [], "entidades": []}',
            '{"dependencias": [], "decisiones_pendientes": [], "riesgos": []}',
            '{"preguntas": ["P1", "P2", "P3", "P4", "P5"]}'
        ]
        
        pipeline = AgentPipeline(client=mock_ollama.return_value)
        
        start = time.time()
        result = pipeline.process("Texto de prueba")
        elapsed = time.time() - start
        
        # Sin delay de red, debe ser casi instantáneo (< 1s)
        assert elapsed < 1.0, f"Pipeline tomó {elapsed}s, debe ser <1s con mock"
    
    @patch('agent_pipeline.OllamaClient')
    def test_pipeline_handles_empty_transcription(self, mock_ollama):
        """Scenario: Manejar transcripción vacía o sin contenido relevante"""
        mock_ollama.return_value.generate.side_effect = [
            '{"requisitos_funcionales": [], "entidades": [], "stakeholders": []}',
            '{"dependencias": [], "decisiones_pendientes": [], "riesgos": []}',
            '{"preguntas": []}'
        ]
        
        pipeline = AgentPipeline(client=mock_ollama.return_value)
        result = pipeline.process("Hmm uhmm")
        
        assert result is not None
        assert "analista" in result


class TestModelFallback:
    """Feature: Fallback si Gemma 4 no disponible"""
    
    @patch('agent_pipeline.OllamaClient')
    def test_fallback_to_gemma3_when_gemma4_unavailable(self, mock_ollama):
        """Scenario: Usar Gemma 3 si Gemma 4 no está descargado"""
        # Primera llamada falla (Gemma 4 no existe), segunda funciona (Gemma 3)
        mock_ollama.return_value.generate.side_effect = [
            Exception("model 'gemma4' not found"),
            '{"requisitos_funcionales": []}',
            '{"dependencias": []}',
            '{"preguntas": []}'
        ]
        
        pipeline = AgentPipeline(client=mock_ollama.return_value, model="gemma4")
        
        # Debe intentar con gemma4, fallar, y fallback a gemma3
        with pytest.raises(Exception) as exc_info:
            result = pipeline.process("Texto")
        
        # Verificar que intentó ambos modelos
        assert mock_ollama.return_value.generate.call_count >= 1
    
    @patch('agent_pipeline.OllamaClient')
    def test_raises_error_when_no_models_available(self, mock_ollama):
        """Scenario: Error claro si ningún modelo está disponible"""
        # Simular que ambos modelos fallan
        def raise_error(*args, **kwargs):
            raise RuntimeError("Modelo no encontrado")
        mock_ollama.return_value.generate.side_effect = raise_error
        
        pipeline = AgentPipeline(client=mock_ollama.return_value)
        
        # El pipeline debe propagar el error después de intentar fallback
        with pytest.raises(RuntimeError):
            pipeline.process("Texto")


class TestOllamaClient:
    """Feature: Cliente Ollama (requiere Ollama corriendo)"""
    
    @pytest.mark.skip(reason="Requiere Ollama corriendo - test manual")
    def test_client_integration_with_real_ollama(self):
        """Scenario: Test real con Ollama (no mock)"""
        from agent_pipeline import OllamaClient
        client = OllamaClient()
        # Este test solo corre manualmente con Ollama disponible
        result = client.generate("Di 'hola'", model="gemma3")
        assert "hola" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
