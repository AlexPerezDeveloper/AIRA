"""
Pipeline Multi-Agente con Ollama/Gemma - AI Requirements Architect

Implementa:
- Skill de Analista: extrae requisitos y entidades (JSON)
- Skill de Arquitecto: evalúa dependencias técnicas
- Skill de QA: detecta ambigüedades, genera 5 preguntas
- Pipeline orquestador: secuencial con manejo de errores
- Fallback: Gemma 3 si Gemma 4 no disponible
"""

import json
import time
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import ollama
import os
from pathlib import Path

def get_skill_prompt(skill_name: str, default_prompt: str) -> str:
    """Intenta cargar el prompt del agente desde un archivo .md. Si no existe, usa el por defecto."""
    # Buscamos en una carpeta 'agents' en la raíz del proyecto
    base_dir = Path(__file__).parent.parent
    md_path = base_dir / "skills" / f"{skill_name}.md"
    
    if md_path.exists():
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Error leyendo el archivo {md_path}: {e}")
            
    return default_prompt



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


class AnalystSkill:
    """
    Skill de Analista: extrae requisitos funcionales, entidades y stakeholders.
    """
    
    DEFAULT_SYSTEM_PROMPT = """Eres un Skill de Analista de la metodología BMAD (Product Owner y Analista Técnico). Analiza la siguiente transcripción de una reunión de desarrollo tecnológico en español, aplicando los principios de BMAD para estructurar requisitos de forma clara, disciplinada y repetible.

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
        self.system_prompt = get_skill_prompt("analista", self.DEFAULT_SYSTEM_PROMPT)
    
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
                system_prompt=self.system_prompt,
                temperature=0.2  # Baja temperatura para consistencia
            )
            print(f"[AnalystSkill] Respuesta recibida ({len(response)} chars)")
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
            
            print(f"[AnalystSkill] Falló el parseo. Texto: {response[:100]}...")
            return {"requisitos_funcionales": [], "entidades": [], "stakeholders": []}


class ArchitectSkill:
    """
    Skill de Arquitecto: evalúa dependencias técnicas, decisiones pendientes y riesgos.
    """
    
    DEFAULT_SYSTEM_PROMPT = """Eres un Skill de Arquitecto de la metodología BMAD (Arquitecto de Software Principal). Recibes un análisis de requisitos y tu objetivo es definir la estructura técnica, decisiones y dependencias aplicando los principios de BMAD para asegurar un desarrollo estructurado y escalable.

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
        self.system_prompt = get_skill_prompt("arquitecto", self.DEFAULT_SYSTEM_PROMPT)
    
    def analyze(self, analyst_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza output del Analista y genera consideraciones técnicas.
        
        Args:
            analyst_output: Output del Skill de Analista
            
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
                system_prompt=self.system_prompt,
                temperature=0.2
            )
            print(f"[ArchitectSkill] Respuesta recibida ({len(response)} chars)")
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


class QASkill:
    """
    Skill de QA: detecta ambigüedades y genera preguntas específicas.
    """
    
    SYSTEM_PROMPT = """Eres un Business Analyst y experto en Toma de Requisitos. Tienes el análisis de requerimientos, consideraciones técnicas y una lista de preguntas pendientes.

Tu tarea: 
1. Evaluar si la información actual responde alguna de las preguntas pendientes. Si es así, elimínala de la lista.
2. Mantener las preguntas pendientes que NO han sido respondidas.
3. Detectar ambigüedades en el negocio y generar nuevas preguntas orientadas EXCLUSIVAMENTE al Stakeholder o Product Owner para entender mejor la necesidad, el valor esperado y las reglas de negocio. NO preguntes sobre detalles de implementación técnica.
4. Devolver la lista combinada (pendientes no respondidas + nuevas) hasta un máximo de 10 preguntas.

Responde ÚNICAMENTE con JSON válido:
{
    "preguntas": [
        "¿Qué impacto en el negocio tendría si este proceso falla o no está disponible?",
        "..."
    ]
}

Preguntas en español, enfocadas en el negocio, el usuario final y el valor aportado. NUNCA hagas preguntas técnicas o de cómo desarrollarlo."""
    
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
            analyst_output: Output del Skill de Analista
            architect_output: Output del Skill de Arquitecto
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
            print(f"[QASkill] Respuesta recibida ({len(response)} chars)")
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


class SkillPipeline:
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
        self.analyst = AnalystSkill(client=self.client, model=model)
        self.architect = ArchitectSkill(client=self.client, model=model)
        self.qa = QASkill(client=self.client, model=model)
        
        # Agente para modo Turbo
        self.turbo = TurboSkill(client=self.client, model=model)
    
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


class TurboSkill:
    """Skill optimizado para velocidad extrema."""
    
    SYSTEM_PROMPT = """Eres un equipo ágil (Analista de Negocio y Arquitecto). Analiza transcripciones de reuniones de desarrollo de software y responde SOLAMENTE con un JSON.
Estructura:
{
  "qa": { "preguntas": ["Lista de preguntas dirigidas al stakeholder sobre necesidades de negocio (máx 10). NUNCA preguntas técnicas o de cómo hacerlo."] },
  "analista": { "requisitos_funcionales": [{"id": "R1", "descripcion": "Descripción del requerimiento"}] },
  "arquitecto": { "riesgos": ["Máximo 2 riesgos técnicos"], "dependencias": ["Máximo 2 dependencias técnicas"] }
}
REGLAS: Solo JSON, idioma Español. Las preguntas de 'qa' deben estar enfocadas SIEMPRE al stakeholder (el negocio, reglas, usuarios o valor), NUNCA enfocadas al equipo técnico sobre la implementación. Si hay preguntas previas, evalúa si la transcripción las responde. Si se responden, ignóralas; si no, mantenlas y agrega nuevas hasta un máximo de 10."""

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


class ExportSkill:
    """
    Skill de Exportación: Genera un análisis completo y extrae preguntas respondidas
    al finalizar la sesión.
    """
    
    SYSTEM_PROMPT = """Eres un Analista de Negocio y Arquitecto Principal. 
Analiza la siguiente transcripción COMPLETA de una sesión de toma de requisitos.

Debes generar:
1. Un resumen o análisis completo de la conversación (ideas clave, propósito del proyecto, conclusiones).
2. Una lista de las preguntas que fueron respondidas durante la conversación y cuáles fueron esas respuestas.

Responde ÚNICAMENTE con JSON válido en este formato exacto:
{
    "analisis_completo": "...",
    "preguntas_respondidas": [
        {
            "pregunta": "...",
            "respuesta": "..."
        }
    ]
}"""

    def __init__(self, client: Optional[OllamaClient] = None, model: str = "llama3"):
        self.client = client or OllamaClient()
        self.model = model

    def analyze(self, full_transcription: str) -> Dict[str, Any]:
        if not full_transcription or not full_transcription.strip():
            return {"analisis_completo": "No hay transcripción disponible.", "preguntas_respondidas": []}
            
        prompt = f"Transcripción completa de la sesión:\n{full_transcription}\n\nGenera el análisis completo y las preguntas respondidas en JSON válido."
        
        try:
            response = self.client.generate(
                prompt=prompt,
                model=self.model,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2
            )
            print(f"[ExportSkill] Respuesta recibida ({len(response)} chars)")
            return self._parse_response(response)
        except Exception as e:
            print(f"[ExportSkill] Error: {e}")
            return {"analisis_completo": f"Error al generar análisis: {e}", "preguntas_respondidas": []}

    def _parse_response(self, response: str) -> Dict[str, Any]:
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
            
            return {"analisis_completo": "No se pudo parsear el análisis estructurado.", "preguntas_respondidas": []}



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
    pipeline = SkillPipeline(client=client)
    
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
