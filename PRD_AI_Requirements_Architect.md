# PRD: AI Requirements Architect (Gemma 4 + Azure)

## 1. Visión General
Aplicación web de escritorio (Streamlit) **multiplataforma (macOS & Windows)** diseñada para asistir en la toma de requisitos durante reuniones de Microsoft Teams. Captura el audio en tiempo real mediante loopback de sistema (BlackHole en macOS, VB-Cable/Virtual Audio Cable en Windows), lo transcribe mediante Azure Speech Services y utiliza un sistema de **multi-agentes secuencial** basado en **Gemma 4** (local via Ollama) para identificar vacíos de información y sugerir preguntas estratégicas en español.

## 2. Objetivos del MVP
* **Captura Real-Time:** Transcripción continua de audio con procesamiento automático cada 30 segundos.
* **Razonamiento Local:** Procesamiento de requisitos sin enviar datos confidenciales a la nube (excepto el audio para transcripción).
* **Multi-Agente Real:** 3 llamadas secuenciales a Gemma 4 (Analista → Arquitecto → QA).
* **Output Estructurado:** Documento de requisitos + listado de preguntas pendientes en formato Markdown.

## 3. Stack Tecnológico

| Componente | Tecnología | Compatibilidad | Notas |
|------------|-----------|----------------|-------|
| **Transcripción** | Azure Speech SDK (Plan F0) | macOS, Windows | 5h/mes gratis, idioma español |
| **LLM Local** | Gemma 4 via Ollama | macOS, Windows | Apple Silicon (M4) y x86_64 |
| **Audio Loopback** | BlackHole (macOS) / VB-Cable (Windows) | OS-specific | Captura audio del sistema |
| **Orquestación** | 3-Agent Pipeline | Cross-platform | Analista → Arquitecto → QA |
| **UI** | Streamlit | Cross-platform | Web-based, hot-reload |
| **Persistencia** | Markdown files | Cross-platform | Un archivo por sesión |

## 4. Arquitectura del Sistema

### A. Capa de Captura (Audio Loopback Multiplataforma)

**Fuentes de Audio por OS:**
| OS | Driver Recomendado | Instalación |
|----|-------------------|-------------|
| **macOS** | BlackHole 2ch | `brew install blackhole-2ch` |
| **Windows** | VB-Cable (gratis) | Descargar de vb-audio.com |

**Configuración:**
- **SDK:** `azure-cognitiveservices-speech` con `SpeechRecognizer` en modo continuo.
- **Idioma:** `es-ES` (español de España) o `es-MX` según preferencia.
- **Buffer:** Acumulación de texto en ventanas deslizantes de 30 segundos.
- **Selección de dispositivo:** El usuario elige el dispositivo de entrada en la UI de Streamlit (listado dinámico según OS).

### B. Capa de Inteligencia (Pipeline 3-Agent)

```
Transcripción (30s) → Agente Analista → Agente Arquitecto → Agente QA → Output
```

| Agente | Rol | Output |
|--------|-----|--------|
| **Analista** | Extrae entidades, funcionalidades, stakeholders mencionados | Lista de requisitos funcionales + entidades |
| **Arquitecto** | Evalúa dependencias técnicas, integraciones necesarias, riesgos | Bloqueos identificados + decisiones técnicas pendientes |
| **QA** | Detecta ambigüedades, criterios de aceptación faltantes | Preguntas específicas para aclarar gaps |

**Optimización para M4:**
- Gemma 4 4B (Q4_K_M) → ~3GB RAM, inferencia <2s por agente en Apple Silicon.
- Pipeline secuencial total: ~6s latencia aceptable para MVP.
- Ollama API: `POST http://localhost:11434/api/generate` por cada agente.

### C. Capa de Presentación (Streamlit)

**Layout:**
- **Panel izquierdo (60%):** Transcripción en vivo con scroll automático.
- **Panel derecho (40%):** 
  - Preguntas sugeridas (últimas 5, priorizadas por QA Agent).
  - Requisitos detectados (acumulado de Analista).
  - Alertas técnicas (de Arquitecto).

**Controles:**
- Botón "Iniciar Sesión" (comienza captura + procesamiento).
- Toggle "Pausar Análisis" (sigue transcribiendo, no llama a Gemma).
- Botón "Exportar Markdown" (genera archivo con timestamp).

## 5. Flujo de Datos

```
1. Audio del sistema → Azure Speech SDK → Texto (es-ES)
2. Cada 30s: Buffer de texto → Ollama/Gemma 4/Agente Analista
3. Output Analista → Agente Arquitecto (contexto + requisitos)
4. Output Arquitecto → Agente QA (contexto + requisitos + riesgos)
5. QA produce: Preguntas sugeridas
6. Streamlit actualiza panels + append a archivo .md temporal
7. Al finalizar: Archivo markdown estructurado con todo el análisis
```

## 6. Prompts del Sistema (3-Agent)

### Agente Analista
```
Eres un analista de negocio experto. Analiza la siguiente transcripción de una reunión de requisitos en español.
Extrae:
1. Requisitos funcionales mencionados (formato: [ACCION] [OBJETO] [CONTEXTo])
2. Entidades de negocio identificadas (usuarios, sistemas, datos)
3. Stakeholders mencionados

Transcripción: {transcripcion}
Output en JSON estructurado. Solo facts, no interpretaciones.
```

### Agente Arquitecto
```
Eres un arquitecto de software. Recibes este análisis de requisitos:
{output_analista}

Evalúa:
1. Dependencias técnicas implícitas (APIs, bases de datos, integraciones)
2. Decisiones arquitectónicas que deben tomarse
3. Riesgos técnicos o bloqueos potenciales

Output: Lista de consideraciones técnicas y preguntas de arquitectura pendientes.
```

### Agente QA
```
Eres un QA Engineer enfocado en claridad de requisitos. Tienes:
- Requisitos: {output_analista}
- Consideraciones técnicas: {output_arquitecto}

Detecta:
1. Términos ambiguos ("rápido", "fácil", "mucho", "algunos")
2. Criterios de aceptación faltantes
3. Casos edge no considerados

Genera exactamente 5 preguntas específicas para aclarar los gaps más importantes.
Output: Lista numerada de preguntas en español.
```

## 7. Estructura del Output Markdown

```markdown
# Sesión de Requisitos - {timestamp}

## Resumen Ejecutivo
- Duración: {X} minutos
- Requisitos identificados: {N}
- Preguntas pendientes: {M}

## Requisitos Funcionales
| ID | Descripción | Origen (timestamp) |
|----|-------------|-------------------|
| RF1 | ... | 05:23 |

## Entidades de Negocio
- [Lista de entidades detectadas por Analista]

## Consideraciones Técnicas
- [Riesgos/dependencias detectadas por Arquitecto]

## Preguntas Pendientes (por prioridad)
1. [Pregunta QA #1]
2. [Pregunta QA #2]
...

## Transcripción Completa
[Log completo con timestamps]
```

## 8. Setup y Dependencias

### Requisitos Hardware

| OS | Mínimo | Recomendado |
|----|--------|-------------|
| **macOS** | Apple Silicon (M1+) / 8GB RAM | MacBook Air/Pro M4, 16GB RAM |
| **Windows** | Intel i5 8th gen / 8GB RAM | Intel i7 / AMD Ryzen 7, 16GB RAM |

- Espacio libre: ~4GB para Ollama + modelo Gemma 4
- GPU: No requerida (CPU inference via Ollama)

---

### Instalación en macOS

```bash
# 1. Ollama + Gemma 4
brew install ollama
ollama pull gemma4:4b

# 2. Python deps
pip install streamlit azure-cognitiveservices-speech

# 3. Audio loopback - BlackHole
brew install blackhole-2ch

# 4. Configurar BlackHole:
# - Abrir Audio MIDI Setup (Aplicaciones > Utilidades)
# - Crear dispositivo multi-salida con:
#   * BlackHole 2ch (para captura)
#   * Tus altavoces/audífonos (para escuchar)
# - En Teams: seleccionar el dispositivo multi-salida como output
```

### Instalación en Windows

```powershell
# 1. Ollama + Gemma 4
# Descargar desde https://ollama.com/download/windows
# Ejecutar: ollama pull gemma4:4b

# 2. Python deps
pip install streamlit azure-cognitiveservices-speech

# 3. Audio loopback - VB-Cable
# Descargar desde https://vb-audio.com/Cable/
# Instalar VB-Cable Virtual Audio Device

# 4. Configurar Windows:
# - Panel de Control > Sonido > Grabar
# - Habilitar "Listen to this device" en VB-Cable Output
# - En Teams: seleccionar VB-Cable Virtual Device como output
```

---

### Variables de Entorno

**macOS (`.zshrc`):**
```bash
export AZURE_SPEECH_KEY="tu-key"
export AZURE_SPEECH_REGION="westeurope"
export OLLAMA_URL="http://localhost:11434"
export ANALYSIS_INTERVAL_SECONDS="30"
export AUDIO_DEVICE_NAME="BlackHole 2ch"  # o nombre alternativo
```

**Windows (PowerShell / Environment Variables):**
```powershell
$env:AZURE_SPEECH_KEY="tu-key"
$env:AZURE_SPEECH_REGION="westeurope"
$env:OLLAMA_URL="http://localhost:11434"
$env:ANALYSIS_INTERVAL_SECONDS="30"
$env:AUDIO_DEVICE_NAME="CABLE Output (VB-Audio Virtual Cable)"
```

## 9. Roadmap Post-MVP

| Prioridad | Feature |
|-----------|---------|
| P1 | Soporte multidioma (detección automática es/en) |
| P2 | Integración con Notion/Confluence (API) |
| P3 | Modo "post-reunión": upload de archivo de audio |
| P4 | Historial de sesiones y búsqueda |

## 10. Consideraciones Multiplataforma

### Audio Loopback por OS

| Aspecto | macOS | Windows |
|---------|-------|---------|
| **Driver** | BlackHole (open source) | VB-Cable (gratis) o Virtual Audio Cable (comercial) |
| **Setup** | Audio MIDI Setup + Multi-Output Device | Panel de Control Sonido + "Listen to this device" |
| **Teams config** | Multi-output device | VB-Cable como output |
| **Requisitos** | macOS 10.14+ | Windows 10/11 |

### Diferencias de Implementación

- **Detección de dispositivos de audio:**
  - macOS: `pyaudio` o `sounddevice` con CoreAudio backend
  - Windows: `pyaudio` con WASAPI backend, o `sounddevice` con PortAudio
  
- **Paths de archivo:**
  - Usar `pathlib.Path` en Python para cross-platform compatibility
  - Archivos Markdown guardados en `~/AIAnalyst/sessions/` (macOS) o `%USERPROFILE%\AIAnalyst\sessions\` (Windows)

- **Ollama:**
  - macOS: Instalador .dmg o Homebrew
  - Windows: Instalador .exe desde ollama.com
  - API REST idéntica en ambos: `localhost:11434`

### Testing Multiplataforma

- Validar en macOS 14+ ( Sonoma/Sequoia ) con Apple Silicon
- Validar en Windows 10/11 con x86_64
- Probar detección automática del dispositivo de audio por nombre parcial

## 11. Notas Técnicas Generales

- **Gemma 4:** Asume disponibilidad en Ollama. Si no está disponible al momento de implementar, usar Gemma 3 4B como fallback.
- **Latencia:** Pipeline de 3 agentes = ~6s total en M4, ~10s en Windows x86_64 típico. Si es muy lento, considerar batching de 60s en vez de 30s.
- **Costo Azure:** F0 limita a 5h/mes. Para uso regular, migrar a S0 (~€0.8/hora de audio).
- **Fallback de audio:** Si el loopback no está configurado, permitir upload de archivo de audio (WAV/MP3) como alternativa.
