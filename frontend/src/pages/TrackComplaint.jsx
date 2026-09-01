/**
 * TrackComplaint — view full complaint details + timeline.
 *
 * TODO:
 *   - Read complaint ID from URL params
 *   - Fetch complaint detail via trackComplaint(id)
 *   - Fetch timeline via getTimeline(id)
 *   - Display PriorityBadge, SLABadge, SimilarComplaintsPanel
 *   - Show status timeline with timestamps
 */

import { useParams } from 'react-router-dom';

export default function TrackComplaint() {
  const { id } = useParams();

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Track Complaint #{id}</h1>
      <p className="text-gray-500">TODO: TrackComplaint — complaint detail view with timeline and similar complaints</p>
    </div>
  );
}
