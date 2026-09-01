import { useEffect, useState } from 'react';
import { getIntakeLanguages } from '../api/client';

/**
 * LanguagePicker — dropdown of intake languages (voice + text).
 *
 * The list comes from GET /complaints/languages so it always matches what
 * the backend ASR/TTS actually supports. Falls back to a small static
 * list if the request fails.
 *
 * Props:
 *   value     — selected bare ISO code, or "auto"
 *   onChange(code)
 *   label     — optional field label
 */

const FALLBACK = [
  { code: 'auto', name: 'Auto-detect', native: 'Auto' },
  { code: 'en', name: 'English', native: 'English' },
  { code: 'hi', name: 'Hindi', native: 'हिन्दी' },
  { code: 'mr', name: 'Marathi', native: 'मराठी' },
  { code: 'bn', name: 'Bengali', native: 'বাংলা' },
  { code: 'ta', name: 'Tamil', native: 'தமிழ்' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
  { code: 'gu', name: 'Gujarati', native: 'ગુજરાતી' },
  { code: 'pa', name: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
];

export default function LanguagePicker({ value = 'auto', onChange, label = 'Language' }) {
  const [langs, setLangs] = useState(FALLBACK);

  useEffect(() => {
    let alive = true;
    getIntakeLanguages()
      .then((res) => {
        if (alive && Array.isArray(res.data) && res.data.length) setLangs(res.data);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  return (
    <label className="block">
      <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      >
        {langs.map((l) => (
          <option key={l.code} value={l.code}>
            {l.native && l.native !== l.name ? `${l.name} — ${l.native}` : l.name}
          </option>
        ))}
      </select>
    </label>
  );
}
