"""Test-only, exact AST source extraction of the supplied Python rule."""
def _pareto_route_summaries(records: list[dict], limit: int = 8) -> list[dict]:
    """Return non-dominated routes: shorter/closer/smoother/wider is better."""
    front = []
    for i, candidate in enumerate(records):
        dominated = False
        for j, other in enumerate(records):
            if i == j:
                continue
            no_worse = (
                other['path_length_mm'] <= candidate['path_length_mm']
                and other['gap_mm'] <= candidate['gap_mm']
                and other['bend_radians'] <= candidate['bend_radians']
                and other['minimum_diameter_mm'] >= candidate['minimum_diameter_mm']
            )
            strictly_better = (
                other['path_length_mm'] < candidate['path_length_mm']
                or other['gap_mm'] < candidate['gap_mm']
                or other['bend_radians'] < candidate['bend_radians']
                or other['minimum_diameter_mm'] > candidate['minimum_diameter_mm']
            )
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    front.sort(key=lambda r: (r['gap_mm'], r['path_length_mm'], r['bend_radians']))
    return [
        {
            'airway_endpoint_xyz_mm': r['endpoint_xyz_mm'],
            'airway_to_lesion_gap_mm': r['gap_mm'],
            'route_length_mm': r['path_length_mm'],
            'route_turn_cost_radians': r['bend_radians'],
            'minimum_route_diameter_mm': r['minimum_diameter_mm'],
            'weighted_score': r['score'],
        }
        for r in front[:max(1, int(limit))]
    ]
