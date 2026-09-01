/**
 * API Client — axios instance and one function per backend endpoint.
 *
 * Base URL is mockable: defaults to localhost:8000 for local dev,
 * or /api when proxied through Vite in Docker.
 */

import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ── Auth ──────────────────────────────────────────────────────────────
export const login = (role, name) =>
  api.post('/auth/login', { role, name });

export const getMe = () =>
  api.get('/auth/me');

// ── Complaints (citizen) ─────────────────────────────────────────────
export const submitComplaint = (data) =>
  api.post('/complaints/', data);

export const submitVoiceComplaint = (
  audioBlob,
  { locationLat, locationLng, address, ward, language } = {}
) => {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  if (locationLat != null) formData.append('location_lat', locationLat);
  if (locationLng != null) formData.append('location_lng', locationLng);
  if (address) formData.append('address', address);
  if (ward) formData.append('ward', ward);
  if (language && language !== 'auto') formData.append('language', language);
  return api.post('/complaints/voice', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

// Live "this will be routed to …" preview — no complaint is created.
export const getRoutePreview = ({ title, description, language }) =>
  api.post('/complaints/route-preview', { title, description, language });

// Languages offered in the intake picker (voice + text).
export const getIntakeLanguages = () =>
  api.get('/complaints/languages');

// ASR/TTS backend health + configured fallback chain.
export const getVoiceBackends = () =>
  api.get('/complaints/voice/backends');

export const getMyComplaints = () =>
  api.get('/complaints/my');

export const trackComplaint = (id) =>
  api.get(`/complaints/track/${id}`);

export const getTimeline = (id) =>
  api.get(`/complaints/${id}/timeline`);

// ── Officer ──────────────────────────────────────────────────────────
export const getOfficerComplaints = () =>
  api.get('/officer/complaints');

export const updateStatus = (id, data) =>
  api.put(`/officer/complaints/${id}/status`, data);

export const addComment = (id, data) =>
  api.post(`/officer/complaints/${id}/comment`, data);

// ── Admin ────────────────────────────────────────────────────────────
export const getDashboardStats = () =>
  api.get('/admin/dashboard/stats');

export const getDepartmentStats = () =>
  api.get('/admin/dashboard/department-stats');

export const getCategoryDistribution = () =>
  api.get('/admin/dashboard/category-distribution');

export const getAllComplaints = (page = 1, perPage = 20) =>
  api.get('/admin/complaints', { params: { page, per_page: perPage } });

// ── Geo ──────────────────────────────────────────────────────────────
export const getGeoComplaints = () =>
  api.get('/geo/complaints');

export const getHeatmapData = () =>
  api.get('/geo/heatmap');

export default api;
