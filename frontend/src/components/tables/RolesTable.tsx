import type { Role, Teacher } from '../../types';

interface Props {
  roles: Role[];
  teachers: Teacher[];
  onEdit: (role: Role) => void;
  onDelete: (roleId: string) => void;
}

/** The priority ladder as a table.
 *
 *  Sorted by weight descending, so the rows read in the order the solver settles
 *  them. Ranks sharing a weight share a tier and trade freely with each other,
 *  which the Tier column makes visible rather than leaving to be inferred.
 */
export function RolesTable({ roles, teachers, onEdit, onDelete }: Props) {
  const ordered = [...roles].sort((a, b) => b.weight - a.weight);
  // Distinct weights, highest first: a rank's tier is its position among these.
  const tiers = [...new Set(ordered.map((r) => r.weight))];
  const held = (roleId: string) => teachers.filter((t) => t.role === roleId).length;

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Short</th>
            <th className="center">Weight</th>
            <th className="center">Tier</th>
            <th className="center">Teachers</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {ordered.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-row">
                No ranks yet — every teacher shares the bottom tier.
              </td>
            </tr>
          )}
          {ordered.map((r) => {
            const shared = ordered.filter((o) => o.weight === r.weight).length > 1;
            return (
              <tr key={r.id}>
                <td className="name">{r.name}</td>
                <td>{r.short}</td>
                <td className="num center">{r.weight}</td>
                <td className="num center">
                  {tiers.indexOf(r.weight) + 1}
                  {shared && <span className="muted-sm"> shared</span>}
                </td>
                <td className="num center">{held(r.id)}</td>
                <td className="right">
                  <button className="linkbtn" onClick={() => onEdit(r)}>
                    Edit
                  </button>
                  <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(r.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
