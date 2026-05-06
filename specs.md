# Especificaciones: AI Requirements Architect

## Metodología: Specification-Driven Development (SDD)

Estas especificaciones definen el comportamiento esperado del sistema. Deben fallar inicialmente y guiar la implementación.

---

## Feature: Captura de Audio

### Scenario: Detección de dispositivo de audio en macOS
```gherkin
Given sistema operativo macOS
And BlackHole 2ch instalado
When la aplicación inicia
Then debe listar "BlackHole 2ch" en dispositivos de entrada disponibles
And el usuario puede seleccionarlo como fuente de audio
```

### Scenario: Detección de dispositivo de audio en Windows
```gherkin
Given sistema operativo Windows 10/11
And VB-Cable instalado
When la aplicación inicia
Then debe listar "CABLE Output (VB-Audio Virtual Cable)" en dispositivos de entrada
And el usuario puede seleccionarlo como fuente de audio
```

### Scenario: Inicio de captura de audio
```gherkin
Given dispositivo de audio seleccionado
When el usuario presiona "Iniciar Sesión"
Then el SpeechRecognizer de Azure se inicializa con idioma "es-ES"
And la transcripción en vivo comienza a mostrarse en el panel izquierdo
And el buffer de texto comienza a acumularse
```

---

## Feature: Transcripción en Tiempo Real

### Scenario: Acumulación de buffer cada 30 segundos
```gherkin
Given captura de audio activa
When han transcurrido 30 segundos de transcripción continua
Then el buffer de texto se marca como "listo para análisis"
And se mantiene el contexto de ventana deslizante (últimos 30s + histórico acumulado)
```

### Scenario: Transcripción en español
```gherkin
Given audio en español: "Necesitamos un sistema de login con dos factores"
When Azure Speech SDK procesa el audio
Then la transcripción muestra exactamente: "Necesitamos un sistema de login con dos factores"
And no hay caracteres corruptos o de otro idioma
```

---

## Feature: Pipeline Multi-Agente

### Scenario: Agente Analista - Extracción de entidades
```gherkin
Given transcripción: "El usuario quiere login con Google y recibir notificaciones por email. El admin debe poder banear usuarios."
When se ejecuta POST a Ollama con prompt de Agente Analista
Then el output JSON contiene:
  """
  {
    "requisitos_funcionales": [
      {"id": "RF1", "descripcion": "Login con Google", "tipo": "autenticación"},
      {"id": "RF2", "descripcion": "Recibir notificaciones por email", "tipo": "notificación"},
      {"id": "RF3", "descripcion": "Admin puede banear usuarios", "tipo": "administración"}
    ],
    "entidades": ["usuario", "admin", "login", "notificaciones", "email"],
    "stakeholders": ["usuario", "admin"]
  }
  """
And el tiempo de respuesta es < 2000ms en MacBook Air M4
```

### Scenario: Agente Arquitecto - Evaluación técnica
```gherkin
Given output de Analista:
  """
  {"requisitos": ["Login con Google", "Notificaciones email"], 
   "entidades": ["usuario", "email"]}
  """
When se ejecuta POST a Ollama con prompt de Agente Arquitecto
Then el output contiene:
  - Dependencia: "Integración con OAuth 2.0 de Google"
  - Dependencia: "Servicio SMTP o proveedor de email (SendGrid/AWS SES)"
  - Decisión pendiente: "Base de datos para usuarios (SQL vs NoSQL)"
  - Riesgo: "Rate limiting en API de Google"
And el tiempo de respuesta es < 2000ms en MacBook Air M4
```

### Scenario: Agente QA - Detección de ambigüedades
```gherkin
Given:
  - Output Analista: {"requisitos": ["El sistema debe ser rápido", "Muchos usuarios concurrentes"]}
  - Output Arquitecto: {"riesgos": ["Escalabilidad desconocida"]}
When se ejecuta POST a Ollama con prompt de Agente QA
Then el output contiene exactamente 5 preguntas:
  1. "¿Qué significa 'rápido'? Tiempo de respuesta objetivo en segundos?"
  2. "¿Cuántos es 'muchos usuarios concurrentes'? Número específico."
  3. "¿El sistema debe soportar picos de tráfico? ¿Qué volumen?"
  4. "¿Login rápido implica <1s, <3s, u otro SLA?"
  5. "¿Concurrentes = simultáneos activos o total sesiones del día?"
And todas las preguntas están en español
And el tiempo de respuesta es < 2000ms en MacBook Air M4
```

### Scenario: Pipeline completo - Latencia aceptable
```gherkin
Given chunk de transcripción de 30 segundos
When se ejecuta pipeline Analista → Arquitecto → QA secuencialmente
Then la latencia total es < 10000ms (10 segundos)
And el output final contiene:
  - requisitos_extraidos (del Analista)
  - consideraciones_tecnicas (del Arquitecto)
  - preguntas_sugeridas (del QA, máximo 5)
```

---

## Feature: Interfaz de Usuario (Streamlit)

### Scenario: Layout inicial
```gherkin
Given la aplicación ejecutándose en localhost:8501
When el usuario abre la página por primera vez
Then se muestra:
  - Panel izquierdo (60% ancho): "Transcripción en vivo" (vacío inicialmente)
  - Panel derecho (40% ancho):
    * Sección "Preguntas Sugeridas" (vacío)
    * Sección "Requisitos Detectados" (vacío)
    * Sección "Alertas Técnicas" (vacío)
  - Botón "Iniciar Sesión" habilitado
  - Toggle "Pausar Análisis" deshabilitado
  - Botón "Exportar Markdown" deshabilitado
```

### Scenario: Durante sesión activa
```gherkin
Given sesión iniciada y captura activa
When llegan nuevos resultados del pipeline
Then:
  - Panel izquierdo: scroll automático muestra última transcripción
  - Sección "Preguntas Sugeridas": muestra máximo 5 últimas preguntas del QA
  - Sección "Requisitos Detectados": lista acumulada de todos los RF del Analista
  - Sección "Alertas Técnicas": lista acumulada de riesgos del Arquitecto
  - Toggle "Pausar Análisis" está habilitado
  - Botón "Exportar Markdown" está habilitado
```

### Scenario: Toggle "Pausar Análisis"
```gherkin
Given sesión activa y análisis corriendo
When el usuario activa "Pausar Análisis"
Then la transcripción continúa mostrándose en vivo
But las llamadas a Ollama (pipeline) se detienen
And un indicador "Análisis Pausado" es visible
```

---

## Feature: Persistencia en Markdown

### Scenario: Estructura del archivo generado
```gherkin
Given sesión finalizada con:
  - Duración: 15 minutos
  - 8 requisitos detectados
  - 12 preguntas generadas total
When el usuario presiona "Exportar Markdown"
Then se genera archivo en:
  - macOS: ~/AIAnalyst/sessions/sesion_2024-01-15_143022.md
  - Windows: %USERPROFILE%\AIAnalyst\sessions\sesion_2024-01-15_143022.md
And el contenido contiene headers:
  - # Sesión de Requisitos - {timestamp}
  - ## Resumen Ejecutivo (con duración, count de requisitos/preguntas)
  - ## Requisitos Funcionales (tabla markdown con ID, descripción, timestamp)
  - ## Entidades de Negocio (lista)
  - ## Consideraciones Técnicas (lista)
  - ## Preguntas Pendientes (lista numerada 1-5+ priorizadas)
  - ## Transcripción Completa (log con timestamps)
```

### Scenario: Continuidad de archivo temporal
```gherkin
Given sesión activa durante 10 minutos
When ocurre un error o cierre inesperado
Then existe archivo temporal .md parcial en el directorio de sesiones
And contiene toda la información acumulada hasta el momento del cierre
```

---

## Feature: Multiplataforma

### Scenario: Paths cross-platform
```gherkin
Given código ejecutándose en cualquier OS
When se usa pathlib.Path para rutas de archivo
Then:
  - macOS: usa forward slashes, expande ~ a /Users/{user}
  - Windows: usa backslashes automáticamente, expande %USERPROFILE%
And los directorios se crean con exist_ok=True
```

### Scenario: Detección de OS para audio
```gherkin
Given la aplicación iniciando
When detecta el sistema operativo
Then:
  - macOS: busca dispositivos con nombre conteniendo "BlackHole"
  - Windows: busca dispositivos con nombre conteniendo "CABLE" o "VB-Audio"
And muestra error claro si no se encuentra dispositivo de loopback
```

---

## Feature: Manejo de Errores

### Scenario: Ollama no disponible
```gherkin
Given Ollama no está corriendo en localhost:11434
When el usuario inicia sesión
Then se muestra error: "Ollama no detectado. Ejecuta 'ollama serve' primero."
And el botón "Iniciar Sesión" se deshabilita hasta que Ollama responda
```

### Scenario: Azure Speech Service error
```gherkin
Given clave de Azure inválida o expirada
When se intenta inicializar SpeechRecognizer
Then se muestra error: "Error de autenticación con Azure. Verifica AZURE_SPEECH_KEY."
And se sugiere: "Plan F0 limitado a 5h/mes. ¿Necesitas upgrade a S0?"
```

### Scenario: Gemma 4 no disponible (fallback)
```gherkin
Given Ollama corriendo pero modelo "gemma4" no descargado
When se intenta ejecutar pipeline
Then el sistema:
  1. Intenta usar "gemma4:4b"
  2. Si falla, intenta "gemma3:4b"
  3. Si falla, muestra: "Modelo no disponible. Ejecuta: ollama pull gemma3:4b"
```

### Scenario: Latencia excesiva en pipeline
```gherkin
Given pipeline toma >15 segundos en completarse
When ocurre timeout
Then:
  - Se muestra warning: "Análisis lento detectado. Considerando batch de 60s."
  - La sesión continúa (no se detiene)
  - Se registra métrica de latencia para debugging
```

---

## Feature: Configuración por Variables de Entorno

### Scenario: Variables requeridas
```gherkin
Given archivo .env o variables de entorno seteadas
When la aplicación inicia
Then requiere:
  - AZURE_SPEECH_KEY (non-empty string)
  - AZURE_SPEECH_REGION (default: "westeurope")
  - OLLAMA_URL (default: "http://localhost:11434")
  - ANALYSIS_INTERVAL_SECONDS (default: "30", integer)
And falla al iniciar con mensaje claro si falta AZURE_SPEECH_KEY
```

---

## Feature: Performance

### Scenario: Memoria Ollama controlada
```gherkin
Given Gemma 4 cargado en Ollama
When se ejecutan las 3 llamadas de agente
Then el uso de RAM de Ollama es < 4GB total
And no hay memory leaks entre llamadas consecutivas
```

### Scenario: CPU vs GPU en M4
```gherkin
Given MacBook Air M4 (Apple Silicon)
When Ollama ejecuta Gemma 4
Then utiliza Neural Engine / GPU si está disponible
And el tiempo de inferencia por agente es < 2000ms
```

---

## Definición de Done (para SDD)

Una especificación está "implementada" cuando:
1. Existe código que intenta satisfacerla
2. Existe test automatizado que verifica el comportamiento
3. El test pasa en ambos: macOS (M4) y Windows (x86_64)
4. Está documentada en el archivo de especificaciones con estado: ✅

## Prioridad de Implementación

| Prioridad | Feature | Justificación |
|-----------|---------|---------------|
| P0 | Captura de Audio + Transcripción | Bloqueante, sin esto no hay producto |
| P0 | Pipeline 3-Agent básico | Core value proposition |
| P1 | UI Streamlit funcional | Para poder usar y probar |
| P1 | Exportar Markdown | Output requerido por PRD |
| P2 | Manejo de Errores | Robustez básica |
| P2 | Multiplataforma completa | Windows support |
| P3 | Performance tuning | Optimizaciones post-MVP |
