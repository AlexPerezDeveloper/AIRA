"""
Pipeline Multi-Agente con Ollama/Gemma - AI Requirements Architect

Implementa:
- Agente Analista: extrae requisitos y entidades (JSON)
- Agente Arquitecto: evalúa dependencias técnicas
- Agente QA: detecta ambigüedades, genera 5 preguntas
- Pipeline orquestador: secuencial con manejo de errores
- Fallback: Gemma 3 si Gemma 4 no disponible
"""

import json
import time
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import ollama


class OllamaClient:
    """
    Cliente para comunicarse con Ollama API.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Inicializa cliente Ollama.
        
        Args:
            base_url: URL del servidor Ollama (default: localhost:11434)
        """
        self.base_url = base_url
        # Configurar cliente ollama
        try:
            self._client = ollama.Client(host=base_url)
        except Exception as e:
            raise RuntimeError(
                f"No se pudo conectar a Ollama en {base_url}. "
                f"Asegúrate de ejecutar 'ollama serve' primero. Error: {e}"
            )
    
    def generate(
        self,
        prompt: str,
        model: str = "llama3",
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        timeout: int = 30
    ) -> str:
        """
        Genera texto usando modelo de Ollama.
        
        Args:
            prompt: Prompt del usuario
            model: Nombre del modelo (default: gemma4)
            system_prompt: System prompt opcional
            temperature: Creatividad (0.0-1.0)
            timeout: Timeout en segundos
            
        Returns:
            Texto generado
            
        Raises:
            RuntimeError: Si hay error de conexión o modelo no existe
        """
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        try:
            response = self._client.chat(
                model=model,
                messages=messages,
                options={'temperature': temperature}
            )
            return response['message']['content']
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "refused" in error_msg:
                raise RuntimeError(
                    f"No se pudo conectar a Ollama en {self.base_url}. "
                    f"Ejecuta 'ollama serve' e intenta nuevamente."
                )
            elif "not found" in error_msg:
                raise RuntimeError(
                    f"Modelo '{model}' no encontrado. "
                    f"Ejecuta: ollama pull {model}"
                )
            else:
                raise RuntimeError(f"Error en Ollama: {e}")


class AnalystAgent:
    """
    Agente Analista: extrae requisitos funcionales, entidades y stakeholders.
    """
    
    SYSTEM_PROMPT = """Eres un Product Owner y Analista Técnico de Software altamente experimentado. Analiza la siguiente transcripción de una reunión de desarrollo tecnológico en español.

Extrae:
1. Requisitos funcionales y no funcionales mencionados (formato: [ACCION] [OBJETO] [CONTEXTO])
2. Entidades de negocio, datos y componentes técnicos identificados
3. Stakeholders y roles técnicos mencionados

Responde ÚNICAMENTE con JSON válido en este formato exacto:
{
    "requisitos_funcionales": [
        {"id": "RF1", "descripcion": "...", "tipo": "..."}
    ],
    "entidades": ["..."],
    "stakeholders": ["..."]
}

Solo facts técnicos, no interpretaciones. Si no hay requisitos claros, devuelve arrays vacíos."""
    
    def __init__(self, client: Optional[OllamaClient] = None, model: str = "llama3"):
        """
        Inicializa agente analista.
        
        Args:
            client: Cliente Ollama (crea uno nuevo si es None)
            model: Modelo a usar
        """
        self.client = client or OllamaClient()
        self.model = model
    
    def analyze(self, transcription: str) -> Dict[str, Any]:
        """
        Analiza transcripción y extrae información estructurada.
        
        Args:
            transcription: Texto transcribido de la reunión
            
        Returns:
            Dict con requisitos_funcionales, entidades, stakeholders
            
        Raises:
            ValueError: Si transcripción está vacía
        """
        if not transcription or not transcription.strip():
            raise ValueError("Transcripción no puede estar vacía")
        
        prompt = f"""Transcripción: {transcription}

Extrae los requisitos, entidades y stakeholders en JSON válido."""
        
        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2  # Baja temperatura para consistencia
            )
            print(f"[AnalystAgent] Respuesta recibida ({len(response)} chars)")
            return self._parse_response(response)
        except RuntimeError as e:
            # Si Gemma 4 no existe, intentar con Gemma 3
            if "llama3" in str(e).lower() and self.model == "llama3":
                return self.analyze(transcription)
            raise
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parsea respuesta JSON de forma ultra-robusta."""
        try:
            # 1. Intentar JSON puro
            clean_response = response.strip()
            return json.loads(clean_response)
        except json.JSONDecodeError:
            # 2. Intentar bloque markdown
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except: pass
            
            # 3. Intentar encontrar el primer { y el último }
            try:
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(response[start:end+1])
            except: pass
            
            print(f"[AnalystAgent] Falló el parseo. Texto: {response[:100]}...")
            return {"requisitos_funcionales": [], "entidades": [], "stakeholders": []}


class ArchitectAgent:
    """
    Agente Arquitecto: evalúa dependencias técnicas, decisiones pendientes y riesgos.
    """
    
    SYSTEM_PROMPT = """Eres un Arquitecto de Software Principal y Tech Lead, experto en tecnologías modernas (Cloud, Microservicios, IA, DevOps). Recibes un análisis de requisitos.

Evalúa:
1. Dependencias técnicas implícitas (APIs, bases de datos, integraciones, librerías, infraestructura)
2. Decisiones arquitectónicas críticas que deben tomarse (stack tecnológico, patrones, seguridad, escalabilidad)
3. Riesgos técnicos, deuda técnica o bloqueos potenciales

Responde ÚNICAMENTE con JSON válido en este formato:
{
    "dependencias": ["..."],
    "decisiones_pendientes": ["..."],
    "riesgos": ["..."]
}

Sé extremadamente específico y técnico. Si no hay consideraciones claras, devuelve arrays vacíos."""
    
    def __init__(self, client: Optional[OllamaClient] = None, model: str = "llama3"):
        self.client = client or OllamaClient()
        self.model = model
    
    def analyze(self, analyst_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza output del Analista y genera consideraciones técnicas.
        
        Args:
            analyst_output: Output del Agente Analista
            
        Returns:
            Dict con dependencias, decisiones_pendientes, riesgos
        """
        if not analyst_output:
            raise ValueError("Output del Analista no puede estar vacío")
        
        prompt = f"""Análisis del Analista:
{json.dumps(analyst_output, ensure_ascii=False, indent=2)}

Genera dependencias técnicas, decisiones pendientes y riesgos en JSON válido."""
        
        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2
            )
            print(f"[ArchitectAgent] Respuesta recibida ({len(response)} chars)")
            return self._parse_response(response)
        except RuntimeError as e:
            if "gemma4" in str(e).lower() and self.model == "gemma4":
                self.model = "gemma3"
                return self.analyze(analyst_output)
            raise
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parsea respuesta JSON de forma ultra-robusta."""
        try:
            clean_response = response.strip()
            return json.loads(clean_response)
        except json.JSONDecodeError:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                try: return json.loads(json_match.group(1))
                except: pass
            
            try:
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(response[start:end+1])
            except: pass
            
            return {"dependencias": [], "decisiones_pendientes": [], "riesgos": []}


class QAAgent:
    """
    Agente QA: detecta ambigüedades y genera preguntas específicas.
    """
    
    SYSTEM_PROMPT = """Eres un QA Engineer Senior y SDET experto en calidad de software. Tienes el análisis de requisitos, consideraciones técnicas y una lista de preguntas pendientes.

Tu tarea: 
1. Evaluar si la información actual responde alguna de las preguntas pendientes. Si es así, elimínala de la lista.
2. Mantener las preguntas pendientes que NO han sido respondidas.
3. Detectar términos ambiguos y generar nuevas preguntas técnicas para aclarar los gaps importantes.
4. Devolver la lista combinada (pendientes no respondidas + nuevas) hasta un máximo de 10 preguntas.

Responde ÚNICAMENTE con JSON válido:
{
    "preguntas": [
        "¿Cuál es el SLA de tiempo de respuesta objetivo en milisegundos para cumplir con el requisito de 'rápido'?",
        "..."
    ]
}

Preguntas en español, enfocadas en tecnología, específicas y accionables para los desarrolladores."""
    
    def __init__(self, client: Optional[OllamaClient] = None, model: str = "llama3"):
        self.client = client or OllamaClient()
        self.model = model
    
    def analyze(
        self,
        analyst_output: Dict[str, Any],
        architect_output: Dict[str, Any],
        current_questions: List[str] = None
    ) -> Dict[str, Any]:
        """
        Analiza outputs previos y genera preguntas de clarificación.
        
        Args:
            analyst_output: Output del Agente Analista
            architect_output: Output del Agente Arquitecto
            current_questions: Preguntas pendientes actuales
            
        Returns:
            Dict con lista de preguntas
        """
        if not analyst_output:
            raise ValueError("Output del Analista no puede estar vacío")
        if architect_output is None:
            architect_output = {}
        if current_questions is None:
            current_questions = []
        
        prompt = f"""Análisis de Requisitos:
{json.dumps(analyst_output, ensure_ascii=False, indent=2)}

Consideraciones Técnicas:
{json.dumps(architect_output, ensure_ascii=False, indent=2)}"""

        if current_questions:
            prompt += f"\n\nPreguntas pendientes:\n{json.dumps(current_questions, ensure_ascii=False)}"
            prompt += "\n\nEvalúa si las preguntas pendientes se han respondido. Conserva las que no, genera nuevas y devuelve una lista combinada de hasta 10 preguntas en formato JSON válido."
        else:
            prompt += "\n\nGenera hasta 10 preguntas específicas en JSON válido para aclarar ambigüedades."
        
        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.3  # Ligeramente más creativo para variedad de preguntas
            )
            print(f"[QAAgent] Respuesta recibida ({len(response)} chars)")
            return self._parse_response(response)
        except RuntimeError as e:
            if "gemma4" in str(e).lower() and self.model == "gemma4":
                self.model = "gemma3"
                return self.analyze(analyst_output, architect_output, current_questions)
            raise
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parsea respuesta JSON de forma ultra-robusta."""
        try:
            clean_response = response.strip()
            return json.loads(clean_response)
        except json.JSONDecodeError:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                try: 
                    parsed = json.loads(json_match.group(1))
                    if "preguntas" in parsed: return parsed
                except: pass
            
            try:
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    parsed = json.loads(response[start:end+1])
                    if "preguntas" in parsed: return parsed
            except: pass
            
            return {"preguntas": ["¿Puedes darme más detalles sobre lo conversado?"]}


class AgentPipeline:
    """Orquestador del pipeline: Modo Deep (Lento/Detallado) vs Modo Turbo (Rápido/Directo)."""
    
    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        model: str = "llama3",
        fallback_model: str = "llama3"
    ):
        self.client = client or OllamaClient()
        self.model = model
        
        # Agentes para modo Deep
        self.analyst = AnalystAgent(client=self.client, model=model)
        self.architect = ArchitectAgent(client=self.client, model=model)
        self.qa = QAAgent(client=self.client, model=model)
        
        # Agente para modo Turbo
        self.turbo = TurboAgent(client=self.client, model=model)
    
    def process(self, transcription: str, turbo: bool = False, current_questions: List[str] = None) -> Dict[str, Any]:
        """Ejecuta el pipeline en el modo seleccionado."""
        if current_questions is None:
            current_questions = []
            
        if turbo:
            return self.turbo.analyze(transcription, current_questions)
            
        # Modo Deep (Secuencial)
        analyst_output = self.analyst.analyze(transcription)
        architect_output = self.architect.analyze(analyst_output)
        qa_output = self.qa.analyze(analyst_output, architect_output, current_questions)
        
        return {
            "analista": analyst_output,
            "arquitecto": architect_output,
            "qa": qa_output
        }


class TurboAgent:
    """Agente optimizado para velocidad extrema."""
    
    SYSTEM_PROMPT = """Eres un Tech Lead Experto y Rápido. Analiza transcripciones de reuniones de desarrollo de software y responde SOLAMENTE con un JSON.
Estructura:
{
  "qa": { "preguntas": ["Lista de preguntas técnicas no respondidas (máx 10)"] },
  "analista": { "requisitos_funcionales": [{"id": "R1", "descripcion": "Breve descripción técnica"}] },
  "arquitecto": { "riesgos": ["Máximo 2 riesgos técnicos"], "dependencias": ["Máximo 2 dependencias técnicas"] }
}
REGLAS: Solo JSON, idioma Español, enfoque altamente tecnológico e ingenieril. Si hay preguntas previas, evalúa si la transcripción las responde. Si se responden, ignóralas; si no, mantenlas y agrega nuevas hasta un máximo de 10."""

    def __init__(self, client: OllamaClient, model: str):
        self.client = client
        self.model = model

    def analyze(self, transcription: str, current_questions: List[str] = None) -> Dict[str, Any]:
        if current_questions is None:
            current_questions = []
            
        prompt = f"Analiza rápido:\n{transcription}"
        if current_questions:
            prompt += f"\n\nPreguntas pendientes (evalúa si se responden y descártalas si es así):\n{json.dumps(current_questions, ensure_ascii=False)}"
        try:
            response = self.client.generate(
                prompt=prompt, 
                model=self.model, 
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.1  # Más bajo = más rápido y preciso
            )
            return self._parse_response(response)
        except:
            return {"analista": {}, "arquitecto": {}, "qa": {}}

    def _parse_response(self, response: str) -> Dict[str, Any]:
        try:
            # Lógica de extracción robusta
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                return json.loads(response[start:end+1])
        except: pass
        return {"analista": {}, "arquitecto": {}, "qa": {}}


if __name__ == "__main__":
    # Demo manual
    print("Demo del Pipeline Multi-Agente")
    print("=" * 40)
    
    # Verificar Ollama disponible
    try:
        client = OllamaClient()
        print("✓ Conexión a Ollama OK")
    except RuntimeError as e:
        print(f"✗ {e}")
        exit(1)
    
    # Test pipeline
    pipeline = AgentPipeline(client=client)
    
    test_transcription = "El usuario quiere login con Google y notificaciones por email. El sistema debe ser rápido."
    
    print(f"\nTranscripción: {test_transcription}")
    print("\nProcesando...")
    
    try:
        result = pipeline.process(test_transcription)
        
        print(f"\n✓ Completado en {result['metadata']['latency_seconds']}s")
        print(f"  Modelo: {result['metadata']['model_used']}")
        print(f"\nRequisitos: {len(result['analista'].get('requisitos_funcionales', []))}")
        print(f"Dependencias: {len(result['arquitecto'].get('dependencias', []))}")
        print(f"Preguntas: {len(result['qa'].get('preguntas', []))}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
