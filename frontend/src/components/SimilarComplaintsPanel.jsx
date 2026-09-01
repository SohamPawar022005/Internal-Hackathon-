/**
 * SimilarComplaintsPanel — shows ML-identified similar complaints.
 *
 * Props:
 *   complaints: Array<{ id, title, similarity_score, status }>
 *
 * TODO:
 *   - Render list of similar complaints with similarity percentage
 *   - Link each to /track/:id
 *   - Show status badge for each
 */

export default function SimilarComplaintsPanel({ complaints = [] }) {
  return (
    <div className="bg-white rounded-lg border p-4">
      <h3 className="font-semibold mb-2">Similar Complaints</h3>
      {complaints.length === 0 ? (
        <p className="text-gray-400 text-sm">No similar complaints found</p>
      ) : (
        <p className="text-gray-500 text-sm">TODO: render {complaints.length} similar complaints</p>
      )}
    </div>
  );
}
