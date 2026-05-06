"""
UI Streamlit - AI Requirements Architect

Implementa:
- Layout 60/40 (transcripción / insights)
- Controles: Iniciar Sesión, Pausar Análisis, Exportar Markdown
- Selectores de dispositivo de audio multiplataforma
- Visualización en tiempo real de transcripción y análisis
- Integración con AudioCapture y AgentPipeline
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Cargar variables de entorno ANTES de importar módulos que las usan
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Importar módulos locales
from audio_capture import AudioCapture, list_audio_devices, find_loopback_device
from agent_pipeline import AgentPipeline, OllamaClient, ExportAgent


@dataclass
class SessionState:
    """Estado de la sesión de análisis."""
    is_running: bool = False
    is_paused: bool = False
    use_turbo_mode: bool = True
    transcription_buffer: List[str] = field(default_factory=list)
    requisitos: List[Dict[str, Any]] = field(default_factory=list)
    preguntas: List[str] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)
    session_start_time: Optional[datetime] = None
    selected_device: Optional[str] = None
    audio_capture: Optional[AudioCapture] = None
    agent_pipeline: Optional[AgentPipeline] = None
    
    def start_session(self):
        """Inicia una nueva sesión."""
        self.is_running = True
        self.is_paused = False
        self.session_start_time = datetime.now()
        self.transcription_buffer.clear()
        self.requisitos.clear()
        self.preguntas.clear()
        self.alertas.clear()
    
    def stop_session(self):
        """Detiene la sesión actual."""
        self.is_running = False
        self.is_paused = False
        if self.audio_capture:
            self.audio_capture.stop_session()
    
    def toggle_pause(self):
        """Alterna pausa del análisis."""
        self.is_paused = not self.is_paused
    
    def get_duration_minutes(self) -> int:
        """Calcula duración de la sesión en minutos."""
        if not self.session_start_time:
            return 0
        return int((datetime.now() - self.session_start_time).total_seconds() / 60)


def get_sessions_dir() -> Path:
    """
    Obtiene directorio para guardar sesiones (cross-platform).
    Se guarda en la carpeta 'sessions' dentro del directorio del proyecto.
    
    Returns:
        Path al directorio de sesiones
    """
    base_dir = Path(__file__).parent.parent / 'sessions'
    
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def format_transcription(buffer: List[str]) -> str:
    """
    Formatea el buffer de transcripción para display.
    
    Args:
        buffer: Lista de entradas de transcripción
        
    Returns:
        String formateado con saltos de línea
    """
    return "\n\n".join(buffer)


def export_markdown(state: SessionState) -> Optional[str]:
    """
    Exporta la sesión actual a un archivo Markdown, incluyendo un análisis
    completo y preguntas respondidas generadas por el ExportAgent.
    
    Args:
        state: Estado de la sesión
        
    Returns:
        Path al archivo exportado, o None si error
    """
    if not state.session_start_time:
        return None
    
    timestamp = state.session_start_time.strftime("%Y-%m-%d_%H%M%S")
    filename = f"sesion_{timestamp}.md"
    filepath = get_sessions_dir() / filename
    
    duration = state.get_duration_minutes()

    # 1. Obtener la transcripción completa
    if state.audio_capture:
        buffer = state.audio_capture.get_transcription_history()
    else:
        buffer = state.transcription_buffer
        
    full_transcription = "\n".join(buffer)

    # 2. Generar análisis y extraer preguntas respondidas
    export_data = {"analisis_completo": "No se pudo generar.", "preguntas_respondidas": []}
    if full_transcription.strip():
        try:
            export_agent = ExportAgent()
            export_data = export_agent.analyze(full_transcription)
        except Exception as e:
            print(f"Error al ejecutar ExportAgent: {e}")
    
    content = f"""# Sesión de Requisitos - {state.session_start_time.strftime("%Y-%m-%d %H:%M:%S")}

## Análisis Completo de la Conversación
{export_data.get('analisis_completo', 'No disponible.')}

## Resumen Ejecutivo
- **Duración:** {duration} minutos
- **Requisitos identificados:** {len(state.requisitos)}
- **Preguntas pendientes:** {len(state.preguntas)}
- **Alertas técnicas:** {len(state.alertas)}

## Requisitos Funcionales
| ID | Descripción | Tipo |
|----|-------------|------|
"""
    
    for req in state.requisitos:
        tipo = req.get('tipo', '-')
        desc = req.get('descripcion', '-')
        req_id = req.get('id', '-')
        content += f"| {req_id} | {desc} | {tipo} |\n"

    content += f"""
## Preguntas Respondidas
"""
    respondidas = export_data.get('preguntas_respondidas', [])
    if respondidas:
        for pr in respondidas:
            if isinstance(pr, dict):
                pregunta = pr.get('pregunta', '')
                respuesta = pr.get('respuesta', '')
                content += f"**Q: {pregunta}**\n*A: {respuesta}*\n\n"
            else:
                content += f"- {pr}\n\n"
    else:
        content += "No se detectaron preguntas respondidas explícitamente en esta sesión.\n"
    
    content += f"""
## Preguntas Pendientes (por prioridad)
"""
    
    for i, pregunta in enumerate(state.preguntas[:10], 1):  # Top 10
        content += f"{i}. {pregunta}\n"
    
    content += f"""
## Alertas Técnicas
"""
    
    for alerta in state.alertas:
        content += f"- {alerta}\n"
    
    content += f"""
## Transcripción Completa
"""
    
    for entry in buffer:
        content += f"{entry}\n\n"
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return str(filepath)
    except Exception as e:
        st.error(f"Error al exportar: {e}")
        return None


def render_header():
    """Renderiza el encabezado de la aplicación."""
    st.title("🎯 AI Requirements Architect")
    st.markdown("*Asistente de toma de requisitos con IA local*")
    st.divider()


def render_device_selector(state: SessionState) -> Optional[str]:
    """
    Renderiza selector de dispositivo de audio.
    
    Args:
        state: Estado de la sesión
        
    Returns:
        Nombre del dispositivo seleccionado, o None
    """
    st.subheader("🔊 Configuración de Audio")
    
    # Listar dispositivos de entrada
    devices = list_audio_devices()
    input_devices = [d for d in devices if d.get('is_input', False)]
    
    if not input_devices:
        st.error("⚠️ No se encontraron dispositivos de entrada de audio.")
        st.info("Instala BlackHole (macOS) o VB-Cable (Windows)")
        return None
    
    device_names = [d['name'] for d in input_devices]
    
    # Auto-detectar loopback recomendado
    recommended = find_loopback_device()
    
    # Crear opciones con indicador de recomendado
    options = []
    default_index = 0
    for i, name in enumerate(device_names):
        display_name = name
        if recommended and recommended.lower() in name.lower():
            display_name += " ⭐ (recomendado)"
            default_index = i
        options.append(display_name)
    
    selected_display = st.selectbox(
        "Selecciona dispositivo de audio:",
        options=options,
        index=default_index,
        help="Selecciona BlackHole (macOS) o VB-Cable (Windows) para capturar audio de Teams"
    )
    
    # Extraer nombre original sin el indicador
    selected_name = selected_display.replace(" ⭐ (recomendado)", "")
    state.selected_device = selected_name
    
    # Mostrar información del OS
    import platform
    os_name = platform.system()
    if os_name == 'Darwin':
        st.caption("🍎 macOS detectado - Usa BlackHole para captura de sistema")
    elif os_name == 'Windows':
        st.caption("🪟 Windows detectado - Usa VB-Cable para captura de sistema")
    
    return selected_name


def render_controls(state: SessionState):
    """
    Renderiza controles de la sesión.
    
    Args:
        state: Estado de la sesión
    """
    st.subheader("⏯️ Controles")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if not state.is_running:
            if st.button("▶️ Iniciar Sesión", use_container_width=True):
                return "start"
        else:
            if st.button("⏹️ Detener Sesión", use_container_width=True, type="secondary"):
                return "stop"
    
    with col2:
        if state.is_running:
            pause_label = "▶️ Reanudar" if state.is_paused else "⏸️ Pausar Análisis"
            if st.button(pause_label, use_container_width=True):
                return "pause"
    
    with col3:
        has_data = len(state.transcription_buffer) > 0
        export_disabled = not has_data or state.is_running
        
        if st.button("📄 Exportar Markdown", use_container_width=True, disabled=export_disabled):
            return "export"
    
    # Estado actual
    if state.is_running:
        status = "⏸️ Pausado" if state.is_paused else "🔴 Grabando y analizando"
        st.caption(f"Estado: {status}")
        if state.session_start_time:
            mins = state.get_duration_minutes()
            st.caption(f"Duración: {mins} min")
    
    return None


def render_transcription_panel(state: SessionState):
    """
    Renderiza panel de transcripción en vivo (60% del ancho).
    
    Args:
        state: Estado de la sesión
    """
    st.subheader("📝 Transcripción en Vivo")
    
    # Obtener historial directamente desde la fuente (AudioCapture) si está disponible
    if state.audio_capture:
        buffer = state.audio_capture.get_transcription_history()
    else:
        # Fallback al buffer local (estado inicial o cargado)
        buffer = state.transcription_buffer
    
    # Contenedor dinámico que se actualiza en cada renderizado
    transcription_container = st.empty()
    
    # Debug: Mostrar longitud del buffer en texto plano
    if buffer:
        st.write(f"📢 Debug UI: {len(buffer)} frases recibidas")
    
    # Formatear y mostrar transcripción
    transcription_text = format_transcription(buffer)
    
    # Usar markdown con altura fija y scroll - fondo oscuro
    transcription_container.markdown(
        f"""
        <div style="height: 400px; overflow-y: auto; padding: 10px; 
                    background-color: #1a1a2e; border-radius: 5px;
                    font-family: monospace; font-size: 14px; color: #e0e0e0;
                    border: 1px solid #444;">
            {transcription_text.replace(chr(10), '<br>') if transcription_text else '<i style="color: #888;">Esperando transcripción...</i>'}
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Fallback: Si el div falla, mostramos texto plano
    if buffer:
        with st.expander("Ver texto plano (Debug)"):
            st.text_area("Raw Transcription", value=transcription_text, height=200)
    
    # Mostrar estadísticas
    if buffer:
        st.caption(f"Entradas: {len(buffer)} | Actualizando en vivo...")


def render_insights(state: SessionState):
    """
    Renderiza panel de insights (40% del ancho).
    
    Args:
        state: Estado de la sesión
    """
    st.subheader("💡 Insights del Análisis")
    
    # Preguntas Sugeridas (prioridad alta)
    with st.expander(f"❓ Preguntas Sugeridas ({len(state.preguntas)})", expanded=True):
        if state.preguntas:
            for i, pregunta in enumerate(state.preguntas[:10], 1):
                st.markdown(f"**{i}.** {pregunta}")
        else:
            st.info("Aún no hay preguntas. El análisis comenzará pronto...")
    
    # Requisitos Detectados
    with st.expander(f"✅ Requisitos Detectados ({len(state.requisitos)})", expanded=True):
        if state.requisitos:
            # Convertir a formato para dataframe
            req_data = [
                {"ID": r.get('id', '-'), "Descripción": r.get('descripcion', '-'), "Tipo": r.get('tipo', '-')}
                for r in state.requisitos[-10:]  # Últimos 10
            ]
            st.dataframe(req_data, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no se han detectado requisitos...")
    
    # Alertas Técnicas
    with st.expander(f"⚠️ Alertas Técnicas ({len(state.alertas)})", expanded=True):
        if state.alertas:
            for alerta in state.alertas[-5:]:  # Últimas 5
                st.markdown(f"- {alerta}")
        else:
            st.info("Sin alertas por ahora...")


def create_transcription_callback():
    """
    Crea callback para recibir transcripción en tiempo real.
    NOTA: No debe acceder a st.session_state porque se ejecuta en un hilo de Azure.
    """
    def callback(text: str):
        # Solo loguear en consola, los datos se recuperan de audio_capture.get_transcription_history()
        # en el ciclo de renderizado de Streamlit (activado por autorefresh)
        print(f"[LIVE] {text}")
    
    return callback


def create_analysis_callback(state: SessionState):
    """
    Crea callback para recibir chunks de texto y procesarlos con la IA.
    """
    def callback(chunk: str):
        if state.is_paused or not state.agent_pipeline:
            return
        
        try:
            mode = "Turbo" if state.use_turbo_mode else "Deep"
            print(f"[AI] Iniciando análisis en modo {mode}...")
            # El pipeline ahora recibe el flag de turbo y las preguntas pendientes
            pipeline_result = state.agent_pipeline.process(
                chunk, 
                turbo=state.use_turbo_mode,
                current_questions=state.preguntas
            )
            
            # Extraer resultados de cada agente
            analista = pipeline_result.get('analista', {})
            arquitecto = pipeline_result.get('arquitecto', {})
            qa = pipeline_result.get('qa', {})
            
            # Agregar requisitos nuevos (evitar duplicados por ID)
            nuevos_requisitos = analista.get('requisitos_funcionales', [])
            for req in nuevos_requisitos:
                req_id = req.get('id')
                if req_id and not any(r.get('id') == req_id for r in state.requisitos):
                    state.requisitos.append(req)
            
            # Agregar alertas (riesgos y dependencias)
            riesgos = arquitecto.get('riesgos', [])
            dependencias = arquitecto.get('dependencias', [])
            for riesgo in riesgos:
                if riesgo not in state.alertas:
                    state.alertas.append(f"⚠️ Riesgo: {riesgo}")
            for dep in dependencias:
                if dep not in state.alertas:
                    state.alertas.append(f"🔗 Dependencia: {dep}")
            
            # Actualizar preguntas pendientes gestionadas por el LLM (máximo 10)
            if 'preguntas' in qa:
                state.preguntas = qa.get('preguntas', [])[:10]
                print(f"[AI] Estado de QA actualizado: {len(state.preguntas)} preguntas pendientes")
                # Debug info en sidebar a través de una variable de estado temporal
                state.debug_info = f"Última actualización de QA: {datetime.now().strftime('%H:%M:%S')}"
            else:
                print(f"[AI WARNING] El agente QA no devolvió clave 'preguntas'")
            
            print(f"[AI] Análisis completado con éxito")
            
        except Exception as e:
            print(f"[AI ERROR] Error en el pipeline: {e}")
    
    return callback


def start_capture_and_analysis(state: SessionState, device_name: str):
    """
    Inicia captura de audio y pipeline de análisis.
    """
    try:
        # Inicializar AudioCapture
        state.audio_capture = AudioCapture(
            device_name=device_name,
            language="es-ES"
        )
        
        # Configurar callbacks
        transcription_cb = create_transcription_callback()
        analysis_cb = create_analysis_callback(state)
        
        state.audio_capture.set_transcription_callback(transcription_cb)
        state.audio_capture.set_analysis_callback(analysis_cb)
        
        # Inicializar pipeline
        state.agent_pipeline = AgentPipeline()
        
        # Iniciar captura
        state.audio_capture.start_session()
        state.start_session()
        
        st.sidebar.success(f"✅ Sesión iniciada con: {device_name}")
        
    except Exception as e:
        import traceback
        st.sidebar.error(f"❌ Error: {e}")
        st.sidebar.code(traceback.format_exc())
        state.stop_session()


def stop_capture(state: SessionState):
    """Detiene la captura y análisis."""
    state.stop_session()
    st.success("⏹️ Sesión detenida")


def toggle_pause(state: SessionState):
    """Alterna pausa del análisis."""
    state.toggle_pause()
    if state.is_paused:
        st.info("⏸️ Análisis pausado. La transcripción continúa.")
    else:
        st.success("▶️ Análisis reanudado")


def main():
    """Función principal de la aplicación Streamlit."""
    st.set_page_config(
        page_title="AI Requirements Architect",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Inicializar estado en session_state de Streamlit
    if 'session' not in st.session_state:
        st.session_state.session = SessionState()
    
    state = st.session_state.session

    # Autorefresh SOLO si está corriendo
    if state.is_running:
        # Usamos limit=100000 para que no se detenga (el default es 100) y una key dinámica
        st_autorefresh(interval=1000, limit=100000, key=f"refresh_{state.session_start_time}")
    
    # Forzar refresco visual con timestamp
    st.sidebar.caption(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")
    
    # Header
    render_header()
    
    # Sidebar: Selector de dispositivo
    with st.sidebar:
        device_name = render_device_selector(state)
        st.divider()
    
    # Main content: Layout 60/40
    if device_name:
        col_transcription, col_insights = st.columns([3, 2])  # 60% / 40%
        
        with col_transcription:
            render_transcription_panel(state)
        
        with col_insights:
            render_insights(state)
    else:
        st.warning("⚠️ Selecciona un dispositivo de audio en el panel lateral para comenzar")
    
    # Inicializar mensajes en session_state
    if 'status_message' not in st.session_state:
        st.session_state.status_message = ""
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""
    
    # Mostrar mensajes persistentes
    if st.session_state.status_message:
        st.sidebar.success(st.session_state.status_message)
    if st.session_state.error_message:
        st.sidebar.error(st.session_state.error_message)
    
    # Controles
    st.sidebar.subheader("⚙️ Configuración")
    state.use_turbo_mode = st.sidebar.toggle(
        "Modo Turbo (Rápido)", 
        value=state.use_turbo_mode,
        help="Mucho más rápido en Mac. Un solo agente unifica todo el análisis."
    )
    st.sidebar.subheader("⏯️ Controles")
    
    # Botón iniciar
    if st.sidebar.button("▶️ INICIAR CAPTURA", type="primary", use_container_width=True):
        st.session_state.status_message = ""
        st.session_state.error_message = ""
        if device_name and not state.is_running:
            try:
                start_capture_and_analysis(state, device_name)
                st.session_state.status_message = f"✅ Captura iniciada con {device_name}"
                st.rerun()
            except Exception as e:
                st.session_state.error_message = f"Error: {str(e)}"
        else:
            st.session_state.error_message = f"Falta device o ya está corriendo"
    
    # Botón detener
    if state.is_running:
        if st.sidebar.button("⏹️ DETENER", type="secondary", use_container_width=True):
            stop_capture(state)
            st.session_state.status_message = "⏹️ Sesión detenida"
            st.rerun()
    
    # Botón exportar (solo si está detenido y hay datos)
    if not state.is_running and state.session_start_time:
        if state.audio_capture:
            has_data = len(state.audio_capture.get_transcription_history()) > 0
        else:
            has_data = len(state.transcription_buffer) > 0
            
        if has_data:
            if st.sidebar.button("📄 EXPORTAR MARKDOWN", type="primary", use_container_width=True):
                with st.spinner("⏳ Generando análisis completo y exportando..."):
                    path = export_markdown(state)
                    if path:
                        st.session_state.status_message = f"✅ Exportado a: {path}"
                    else:
                        st.session_state.error_message = "❌ Error al exportar."
    
    # Limpiar mensajes después de mostrarlos
    if st.session_state.status_message or st.session_state.error_message:
        # Se mantendrán hasta el próximo click
        pass
    
    # Mostrar estado
    st.sidebar.divider()
    st.sidebar.write(f"**Estado:** {'🔴 CORRIENDO' if state.is_running else '⚪ Detenido'}")
    
    if state.is_running:
        if state.audio_capture:
            # Mostrar errores de Azure si existen
            if state.audio_capture.last_error:
                st.sidebar.error(f"⚠️ {state.audio_capture.last_error}")
            
            # Mostrar tamaño del buffer
            history = state.audio_capture.get_transcription_history()
            buffer_len = len(history)
            st.sidebar.metric("Entradas de audio", buffer_len)
            
            # Mostrar estado del análisis de IA
            if state.audio_capture._analysis_in_progress:
                st.sidebar.info("🧠 IA: Analizando reunión...")
            elif buffer_len > 0:
                st.sidebar.success("🧠 IA: Análisis al día")
        
        if state.session_start_time:
            st.sidebar.write(f"**Duración:** {state.get_duration_minutes()} min")
            
        # Sección de depuración técnica (colapsable)
        with st.sidebar.expander("🛠️ Depuración de Datos", expanded=False):
            st.write(f"Total Requisitos: {len(state.requisitos)}")
            st.write(f"Total Preguntas: {len(state.preguntas)}")
            st.write(f"Total Alertas: {len(state.alertas)}")
            if st.button("Limpiar Estado"):
                state.requisitos.clear()
                state.preguntas.clear()
                state.alertas.clear()
                st.rerun()


if __name__ == "__main__":
    main()
