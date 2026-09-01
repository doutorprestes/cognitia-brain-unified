"""Módulo para transcrição de áudio via faster-whisper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Instância global do modelo
_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            # Usar um modelo pequeno (base ou small) para CPU/GPU local
            logger.info("Carregando modelo faster-whisper (medium)...")
            _whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
        except ImportError as e:
            logger.error("faster-whisper não instalado.")
            raise RuntimeError("Instale com: pip install faster-whisper") from e
    return _whisper_model


def transcrever_audio(audio_path: Path) -> Optional[str]:
    """Transcreve o áudio passado e retorna o texto completo."""
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(str(audio_path), beam_size=5)
        
        texto = []
        for segment in segments:
            texto.append(segment.text)
            
        return " ".join(texto).strip()
    except Exception as e:
        logger.error(f"Erro ao transcrever {audio_path.name}: {e}")
        return None
