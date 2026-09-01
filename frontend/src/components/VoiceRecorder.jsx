import { useState, useRef, useCallback, useEffect } from 'react';
import RoutingCard from './RoutingCard';

/**
 * VoiceRecorder — browser-native audio recording with transcript confirmation.
 *
 * Uses MediaRecorder API (no external library). Records audio, uploads to
 * POST /complaints/voice, shows the returned transcript + detected language
 * + routed department for citizen confirmation before finalizing. If the
 * backend returns TTS audio, plays it.
 *
 * Props:
 *   onTranscriptConfirmed(response) — called when the citizen confirms the
 *     transcript. Receives the full VoiceComplaintResponse from the backend.
 *   languageHint — bare ISO code the citizen picked, or "auto".
 *   locationLat, locationLng — optional GPS coordinates to send with audio.
 */

const RECORDING_STATES = {
  IDLE: 'idle',
  RECORDING: 'recording',
  UPLOADING: 'uploading',
  CONFIRMING: 'confirming',
  DONE: 'done',
  ERROR: 'error',
};

export default function VoiceRecorder({
  onTranscriptConfirmed,
  languageHint = 'auto',
  locationLat = null,
  locationLng = null,
}) {
  const [state, setState] = useState(RECORDING_STATES.IDLE);
  const [transcript, setTranscript] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [voiceResponse, setVoiceResponse] = useState(null);
  const [elapsed, setElapsed] = useState(0);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioPlayerRef = useRef(null);

  // ── Timer for recording duration ────────────────────────────────────
  useEffect(() => {
    if (state === RECORDING_STATES.RECORDING) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [state]);

  // ── Start recording ─────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const mediaRecorder = new MediaRecorder(stream, { mimeType });

      chunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
      };

      mediaRecorder.start(250); // collect chunks every 250ms
      mediaRecorderRef.current = mediaRecorder;
      setState(RECORDING_STATES.RECORDING);
      setErrorMsg('');
    } catch (err) {
      setErrorMsg('Microphone access denied. Please allow microphone access and try again.');
      setState(RECORDING_STATES.ERROR);
    }
  }, []);

  // ── Stop recording and upload ───────────────────────────────────────
  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current) return;

    // Wait for the recorder to actually stop and fire onstop
    await new Promise((resolve) => {
      mediaRecorderRef.current.onstop = () => {
        mediaRecorderRef.current.stream?.getTracks().forEach((t) => t.stop());
        resolve();
      };
      mediaRecorderRef.current.stop();
    });

    const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
    if (blob.size === 0) {
      setErrorMsg('No audio recorded. Please try again.');
      setState(RECORDING_STATES.ERROR);
      return;
    }

    // Upload to backend
    setState(RECORDING_STATES.UPLOADING);
    try {
      const formData = new FormData();
      formData.append('audio', blob, 'recording.webm');
      if (locationLat != null) formData.append('location_lat', locationLat);
      if (locationLng != null) formData.append('location_lng', locationLng);
      if (languageHint && languageHint !== 'auto') formData.append('language', languageHint);

      const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const resp = await fetch(`${BASE_URL}/complaints/voice`, {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(
          err.detail || 'Could not understand the audio. Please try again or use the text form.'
        );
      }

      const data = await resp.json();
      setTranscript(data.transcript);
      setVoiceResponse(data);
      setState(RECORDING_STATES.CONFIRMING);

      // Play confirmation audio if available
      if (data.confirmation_audio_base64) {
        try {
          const audioSrc = `data:audio/wav;base64,${data.confirmation_audio_base64}`;
          if (audioPlayerRef.current) {
            audioPlayerRef.current.src = audioSrc;
            audioPlayerRef.current.play().catch(() => {});
          }
        } catch {
          // Silently skip if audio playback fails
        }
      }
    } catch (err) {
      setErrorMsg(err.message);
      setState(RECORDING_STATES.ERROR);
    }
  }, [locationLat, locationLng, languageHint]);

  // ── Confirm transcript ──────────────────────────────────────────────
  const handleConfirm = useCallback(() => {
    if (voiceResponse && onTranscriptConfirmed) {
      onTranscriptConfirmed(voiceResponse);
    }
    setState(RECORDING_STATES.DONE);
  }, [voiceResponse, onTranscriptConfirmed]);

  // ── Reset to try again ─────────────────────────────────────────────
  const handleReset = useCallback(() => {
    setTranscript('');
    setVoiceResponse(null);
    setErrorMsg('');
    setState(RECORDING_STATES.IDLE);
  }, []);

  // ── Format elapsed time ─────────────────────────────────────────────
  const formatTime = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  return (
    <div className="space-y-4">
      {/* Hidden audio element for TTS playback */}
      <audio ref={audioPlayerRef} className="hidden" />

      {/* ── IDLE ─────────────────────────────────────────────────── */}
      {state === RECORDING_STATES.IDLE && (
        <div className="text-center">
          <button
            onClick={startRecording}
            className="group relative inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-red-500 to-rose-600 text-white shadow-lg hover:shadow-red-500/40 hover:scale-105 transition-all duration-200"
            aria-label="Start recording"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </button>
          <p className="mt-3 text-sm text-gray-500">Tap to start recording</p>
        </div>
      )}

      {/* ── RECORDING ────────────────────────────────────────────── */}
      {state === RECORDING_STATES.RECORDING && (
        <div className="text-center">
          <button
            onClick={stopRecording}
            className="relative inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-600 text-white shadow-lg animate-pulse"
            aria-label="Stop recording"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>

          {/* Simple recording indicator */}
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
            <span className="text-sm font-medium text-red-600">
              Recording… {formatTime(elapsed)}
            </span>
          </div>

          {/* Visual waveform bars */}
          <div className="mt-3 flex items-end justify-center gap-1 h-8">
            {[...Array(12)].map((_, i) => (
              <div
                key={i}
                className="w-1 bg-red-400 rounded-full animate-bounce"
                style={{
                  height: `${12 + Math.random() * 20}px`,
                  animationDelay: `${i * 0.05}s`,
                  animationDuration: `${0.4 + Math.random() * 0.3}s`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── UPLOADING ────────────────────────────────────────────── */}
      {state === RECORDING_STATES.UPLOADING && (
        <div className="text-center py-6">
          <div className="inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="mt-3 text-sm text-gray-600">Transcribing your audio…</p>
        </div>
      )}

      {/* ── CONFIRMING ───────────────────────────────────────────── */}
      {state === RECORDING_STATES.CONFIRMING && (
        <div className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">
                We heard{voiceResponse?.detected_language && voiceResponse.detected_language !== 'en'
                  ? ` (${voiceResponse.detected_language})`
                  : ''}:
              </p>
              {voiceResponse?.detected_language && (
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                  language: {voiceResponse.detected_language}
                  {voiceResponse?.refinement?.chosen_backend
                    ? ` · via ${voiceResponse.refinement.chosen_backend}`
                    : ''}
                </span>
              )}
            </div>
            <p className="text-gray-800 text-sm leading-relaxed" lang={voiceResponse?.detected_language}>
              "{transcript}"
            </p>

            {voiceResponse?.transcript_english &&
              voiceResponse.transcript_english !== transcript && (
                <div className="mt-3 border-t border-blue-200 pt-2">
                  <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-0.5">
                    In English:
                  </p>
                  <p className="text-gray-700 text-sm italic leading-relaxed">
                    "{voiceResponse.transcript_english}"
                  </p>
                </div>
              )}

            {voiceResponse?.refinement?.agreement != null &&
              voiceResponse.refinement.mode === 'orchestrate' && (
                <p className="mt-2 text-xs text-blue-500">
                  {Math.round(voiceResponse.refinement.agreement * 100)}% engine
                  agreement on the language.
                </p>
              )}
          </div>

          {voiceResponse?.routing && (
            <RoutingCard routing={voiceResponse.routing} />
          )}

          <p className="text-sm text-gray-600 text-center">
            Is this correct? Review the transcript before submitting.
          </p>

          <div className="flex gap-3 justify-center">
            <button
              onClick={handleConfirm}
              className="px-5 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
            >
              ✓ Yes, submit this
            </button>
            <button
              onClick={handleReset}
              className="px-5 py-2 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors"
            >
              ✗ Try again
            </button>
          </div>
        </div>
      )}

      {/* ── DONE ─────────────────────────────────────────────────── */}
      {state === RECORDING_STATES.DONE && (
        <div className="text-center space-y-3">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 text-green-600">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </div>
          <p className="text-sm text-green-700 font-medium">Voice complaint submitted!</p>
          <button
            onClick={handleReset}
            className="text-sm text-blue-600 hover:underline"
          >
            Submit another
          </button>
        </div>
      )}

      {/* ── ERROR ────────────────────────────────────────────────── */}
      {state === RECORDING_STATES.ERROR && (
        <div className="space-y-3">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-700">{errorMsg}</p>
          </div>
          <div className="text-center">
            <button
              onClick={handleReset}
              className="text-sm text-blue-600 hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
