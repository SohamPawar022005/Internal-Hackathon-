/**
 * CitizenSubmit — complaint submission with Type / Speak intake modes.
 *
 *   • "Type" tab  — full text form (title, description, location, language)
 *                   with a live "this will be routed to …" preview.
 *   • "Speak" tab — VoiceRecorder (record → transcribe → confirm), using
 *                   the same language selection.
 *
 * Both modes hit the same backend pipeline: route to a department, detect
 * crisis, score priority.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import VoiceRecorder from '../components/VoiceRecorder';
import LanguagePicker from '../components/LanguagePicker';
import RoutingCard from '../components/RoutingCard';
import { submitComplaint, getRoutePreview } from '../api/client';

const TABS = { TYPE: 'type', SPEAK: 'speak' };

const PRIORITY_STYLES = {
  critical: 'text-red-700 bg-red-50 border-red-200',
  high: 'text-orange-700 bg-orange-50 border-orange-200',
  medium: 'text-amber-700 bg-amber-50 border-amber-200',
  low: 'text-slate-700 bg-slate-50 border-slate-200',
};

export default function CitizenSubmit() {
  const [activeTab, setActiveTab] = useState(TABS.TYPE);
  const [language, setLanguage] = useState('auto');
  const [submitted, setSubmitted] = useState(null);

  // ── Type-form state ────────────────────────────────────────────────
  const [form, setForm] = useState({ title: '', description: '', address: '', ward: '' });
  const [coords, setCoords] = useState({ lat: null, lng: null });
  const [busy, setBusy] = useState(false);

  // ── Live routing preview (debounced) ──────────────────────────────
  const [preview, setPreview] = useState(null);
  const debounceRef = useRef(null);

  const runPreview = useCallback((title, description, lang) => {
    const text = `${title} ${description}`.trim();
    if (text.length < 8) {
      setPreview(null);
      return;
    }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      getRoutePreview({ title, description, language: lang === 'auto' ? null : lang })
        .then((res) => setPreview(res.data))
        .catch(() => setPreview(null));
    }, 450);
  }, []);

  useEffect(() => {
    runPreview(form.title, form.description, language);
    return () => clearTimeout(debounceRef.current);
  }, [form.title, form.description, language, runPreview]);

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation not available in this browser.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        toast.success('Location captured.');
      },
      () => toast.error('Could not get your location.'),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) {
      toast.error('Please fill in the title and description.');
      return;
    }
    setBusy(true);
    try {
      const { data } = await submitComplaint({
        title: form.title.trim(),
        description: form.description.trim(),
        address: form.address.trim() || null,
        ward: form.ward.trim() || null,
        language: language === 'auto' ? null : language,
        location_lat: coords.lat,
        location_lng: coords.lng,
      });
      setSubmitted(data);
      toast.success(`Complaint #${data.id} registered!`);
      setForm({ title: '', description: '', address: '', ward: '' });
      setPreview(null);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Submission failed. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const handleVoiceConfirmed = (voiceResponse) => {
    setSubmitted(voiceResponse.complaint);
    toast.success(`Complaint #${voiceResponse.complaint.id} registered via voice!`);
  };

  const tabBtn = (tab, label, icon) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
        activeTab === tab
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
    >
      <span className="inline-flex items-center gap-1.5">{icon}{label}</span>
    </button>
  );

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">Submit a Complaint</h1>
      <p className="text-sm text-gray-500 mb-6">
        Type it or speak it — in your language. We route it to the right
        department automatically.
      </p>

      {/* Language applies to both tabs */}
      <div className="mb-5 max-w-xs">
        <LanguagePicker value={language} onChange={setLanguage} label="Complaint language" />
      </div>

      <div className="flex border-b border-gray-200 mb-6">
        {tabBtn(TABS.TYPE, 'Type', (
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 10H3" /><path d="M21 6H3" /><path d="M21 14H3" /><path d="M17 18H3" />
          </svg>
        ))}
        {tabBtn(TABS.SPEAK, 'Speak', (
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" x2="12" y1="19" y2="22" />
          </svg>
        ))}
      </div>

      {/* ── Type Tab ─────────────────────────────────────────────── */}
      {activeTab === TABS.TYPE && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="block text-sm font-medium text-gray-700 mb-1">Title</span>
            <input
              type="text"
              value={form.title}
              onChange={setField('title')}
              maxLength={255}
              placeholder="e.g. No water supply for 3 days / पाणी येत नाही"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-gray-700 mb-1">Description</span>
            <textarea
              value={form.description}
              onChange={setField('description')}
              rows={5}
              placeholder="Describe the problem, where it is, and how long it has been happening. You can write in Hindi, Marathi, Tamil, etc."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Address / landmark</span>
              <input
                type="text"
                value={form.address}
                onChange={setField('address')}
                placeholder="Optional"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Ward</span>
              <input
                type="text"
                value={form.ward}
                onChange={setField('ward')}
                placeholder="Optional"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </label>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={useMyLocation}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" />
              </svg>
              {coords.lat ? 'Location captured ✓' : 'Use my location'}
            </button>
          </div>

          {/* Live routing preview */}
          {preview && (
            <div>
              <p className="text-xs font-medium text-gray-400 mb-1.5">Preview — where this will go</p>
              <RoutingCard routing={preview} />
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {busy ? 'Submitting…' : 'Submit complaint'}
          </button>
        </form>
      )}

      {/* ── Speak Tab ────────────────────────────────────────────── */}
      {activeTab === TABS.SPEAK && (
        <div className="py-2">
          <p className="text-sm text-gray-600 mb-4">
            Describe your complaint by speaking. We'll transcribe it, show you
            the text and the department it will go to, and let you re-record if
            it isn't right.
          </p>
          <VoiceRecorder
            languageHint={language}
            locationLat={coords.lat}
            locationLng={coords.lng}
            onTranscriptConfirmed={handleVoiceConfirmed}
          />
        </div>
      )}

      {/* ── Submission result ────────────────────────────────────── */}
      {submitted && (
        <div className="mt-8 space-y-4">
          <div className="rounded-lg border border-green-200 bg-green-50 p-4">
            <h3 className="text-sm font-semibold text-green-800 mb-2">Complaint Registered</h3>
            <dl className="grid grid-cols-2 gap-y-1 text-sm text-green-800">
              <dt className="font-medium">Tracking ID</dt><dd>#{submitted.id}</dd>
              <dt className="font-medium">Category</dt><dd>{submitted.category_name}</dd>
              <dt className="font-medium">Department</dt><dd>{submitted.department_name}</dd>
              <dt className="font-medium">Language</dt><dd>{submitted.language}</dd>
              <dt className="font-medium">Status</dt><dd>{submitted.status}</dd>
            </dl>
          </div>

          {submitted.routing && <RoutingCard routing={submitted.routing} />}

          {submitted.priority_level && (
            <div className={`rounded-lg border p-4 ${PRIORITY_STYLES[submitted.priority_level] || PRIORITY_STYLES.low}`}>
              <p className="text-sm font-semibold capitalize mb-1">
                Priority: {submitted.priority_level}
                {typeof submitted.priority_score === 'number'
                  ? ` (${Math.round(submitted.priority_score * 100)}%)`
                  : ''}
              </p>
              {Array.isArray(submitted.priority_reasons) && submitted.priority_reasons.length > 0 && (
                <ul className="list-disc pl-5 text-xs space-y-0.5">
                  {submitted.priority_reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
            </div>
          )}

          <button
            onClick={() => setSubmitted(null)}
            className="text-sm text-blue-600 hover:underline"
          >
            Submit another complaint
          </button>
        </div>
      )}
    </div>
  );
}
