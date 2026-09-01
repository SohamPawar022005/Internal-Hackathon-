import { Routes, Route, Link } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import CitizenSubmit from './pages/CitizenSubmit';
import TrackComplaint from './pages/TrackComplaint';
import OfficerDashboard from './pages/OfficerDashboard';
import AdminDashboard from './pages/AdminDashboard';

/**
 * App — top-level router and navigation shell.
 *
 * Routes:
 *   /                → CitizenSubmit (home / submit form)
 *   /track/:id       → TrackComplaint
 *   /officer         → OfficerDashboard
 *   /admin           → AdminDashboard
 */
export default function App() {
  return (
    <>
      <Toaster position="top-right" />
      <nav className="bg-slate-900 text-white p-4 flex gap-6 text-sm font-medium">
        <Link to="/" className="hover:text-blue-400">Submit</Link>
        <Link to="/track/1" className="hover:text-blue-400">Track</Link>
        <Link to="/officer" className="hover:text-blue-400">Officer</Link>
        <Link to="/admin" className="hover:text-blue-400">Admin</Link>
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<CitizenSubmit />} />
          <Route path="/track/:id" element={<TrackComplaint />} />
          <Route path="/officer" element={<OfficerDashboard />} />
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </main>
    </>
  );
}
