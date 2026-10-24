"""Render projected-foot ArcGIS geometry with explicitly hypothetical study areas."""
import argparse
import json
from pathlib import Path


def esri_polygon(geometry, repair=False, diagnostics=None):
    from shapely.geometry import Polygon
    result = Polygon()
    # Even/odd fill handles disjoint outer rings and holes, independent of winding.
    for ring in geometry['rings']:
        polygon = Polygon(ring)
        if not polygon.is_valid:
            if not repair:
                raise ValueError('Invalid GIS ring; inspect rather than silently repairing')
            from shapely import make_valid
            from shapely.validation import explain_validity
            from shapely.ops import unary_union
            reason, before = explain_validity(polygon), polygon.area
            repaired = make_valid(polygon)
            def parts(shape):
                if shape.geom_type == 'Polygon':
                    return [shape]
                return [part for child in getattr(shape, 'geoms', []) for part in parts(child)]
            polygon = unary_union(parts(repaired))
            if diagnostics is not None:
                diagnostics.append({'reason': reason, 'area_before_sqft': before,
                                    'area_after_sqft': polygon.area})
        result = result.symmetric_difference(polygon)
    return result


def render(bundle, config, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from shapely.geometry import LineString, box
    from shapely.affinity import rotate
    if bundle.get('units') != 'feet':
        raise ValueError('Map dimensions require a projected CRS in feet')
    if bundle['spatial_reference'] != config['spatial_reference']:
        raise ValueError('Map config and data CRS differ')
    subject = esri_polygon(bundle['parcel']['features'][0]['geometry'])
    fig, ax = plt.subplots(figsize=(11, 10), layout='constrained')
    ax.set_facecolor('#f4f5ee')

    def draw(poly, **style):
        parts = [poly] if poly.geom_type == 'Polygon' else getattr(poly, 'geoms', [])
        for part in parts:
            if part.geom_type != 'Polygon':
                continue
            ax.fill(*part.exterior.xy, **style)
            for hole in part.interiors:
                ax.fill(*hole.xy, color=ax.get_facecolor(), zorder=style.get('zorder', 1) + .01)

    layers = bundle['layers']
    for feature in layers.get('neighbors', {}).get('features', []):
        draw(esri_polygon(feature['geometry']), facecolor='#e0e5d7', edgecolor='#a6b19f', linewidth=.7)
    draw(subject, facecolor='#fcfff5', edgecolor='#225a40', linewidth=2.5, zorder=2)
    buildings = [esri_polygon(f['geometry']) for f in layers.get('buildings', {}).get('features', [])]
    for home in buildings:
        draw(home, facecolor='#596579', zorder=4)
    for name, spec in config.get('contour_layers', {}).items():
        for feature in layers.get(name, {}).get('features', []):
            for path in feature['geometry'].get('paths', []):
                line = LineString(path).intersection(subject)
                segments = [line] if line.geom_type == 'LineString' else getattr(line, 'geoms', [])
                for segment in segments:
                    if segment.geom_type == 'LineString':
                        ax.plot(*segment.xy, color='#a8987b', linewidth=.7, zorder=3)
                        if segment.length > 40:
                            mid = segment.interpolate(.5, normalized=True)
                            ax.text(mid.x, mid.y, str(feature['attributes'].get(spec['elevation_field'], '?')), fontsize=6, color='#78664d', zorder=5)
    roads = []
    for guide in config.get('street_guides', []):
        road = LineString(guide['coordinates'])
        roads.append(road)
        draw(road.buffer(guide['illustrative_offset_ft']).intersection(subject), facecolor='#e2ab61', alpha=.25, zorder=3)
    contour_elevations = []
    for name, spec in config.get('contour_layers', {}).items():
        for feature in layers.get(name, {}).get('features', []):
            if any(LineString(path).intersects(subject) for path in feature['geometry'].get('paths', [])):
                value = feature['attributes'].get(spec['elevation_field'])
                if isinstance(value, (int, float)):
                    contour_elevations.append(value)
    zoning = []
    geometry_repairs = []
    for feature in layers.get('zoning', {}).get('features', []):
        area = subject.intersection(esri_polygon(feature['geometry'], config.get('repair_invalid_thematic_geometry', False), geometry_repairs)).area
        zoning.append({'attributes': feature['attributes'], 'intersection_sqft': area,
                       'parcel_percent': 100 * area / subject.area})
    results = []
    colors = {'garden': '#4d9658', 'shed': '#387da3', 'workshop': '#8064a8'}
    for study in config.get('study_areas', []):
        x, y = study['origin']
        width, depth = study['width_ft'], study['depth_ft']
        if min(width, depth) <= 0:
            raise ValueError('Study dimensions must be positive')
        shape = rotate(box(x, y, x + width, y + depth), study.get('rotation_degrees', 0), origin=(x, y))
        color = colors.get(study['kind'], '#8064a8')
        draw(shape, facecolor=color, edgecolor=color, alpha=.3, linestyle='--', linewidth=2, zorder=6)
        center = shape.centroid
        ax.text(center.x, center.y, f"{study['label']}\n{width} × {depth} ft", fontsize=7, ha='center', va='center', zorder=7)
        results.append({'label': study['label'], 'inside_mapped_parcel': subject.covers(shape),
                        'building_overlap': any(shape.intersects(home) for home in buildings),
                        'nearest_building_ft': min((shape.distance(home) for home in buildings), default=None),
                        'mapped_street_edge_ft': min((shape.distance(road) for road in roads), default=None), 'legally_approved': False})
    for label in config.get('labels', []):
        ax.annotate(label['text'], label['point'], fontsize=8, ha='center', zorder=8)
    xmin, ymin, xmax, ymax = subject.bounds
    margin = config.get('margin_ft', 80)
    ax.set_xlim(xmin - margin, xmax + margin)
    ax.set_ylim(ymin - margin, ymax + margin)
    ax.set_aspect('equal')
    ax.ticklabel_format(useOffset=False, style='plain')
    ax.tick_params(labelsize=7)
    ax.set_xlabel(f"Projected easting (ft), EPSG:{bundle['spatial_reference']}")
    ax.set_ylabel('Projected northing (ft)')
    ax.annotate('N', xy=(.94, .96), xytext=(.94, .85), xycoords='axes fraction', ha='center', arrowprops={'arrowstyle': '->'})
    bx, by = xmin, ymin - margin * .65
    ax.plot([bx, bx + 50], [by, by], color='black', linewidth=3)
    ax.text(bx + 25, by - 12, '50 ft', ha='center', fontsize=8)
    ax.set_title(config['title'] + '\nCounty GIS feasibility study — hypothetical alternatives', loc='left')
    ax.legend(handles=[Patch(facecolor='#596579', label='Mapped building'), Patch(facecolor='#e2ab61', alpha=.4, label='Illustrative street offsets')], loc='upper left', fontsize=7)
    note = ('NOT A SURVEY OR APPROVAL. Rectangles are alternatives, not a combined site plan.\n'
            'Street bands use supplied mapped edges, not verified legal setback/ROW lines.\n'
            'Septic/reserve, easements, utilities and trees are unknown unless separately verified.\n'
            'Unavailable or outdated layers do not establish absence of constraints.')
    fig.supxlabel(note + '\n' + config.get('source_note', ''), fontsize=8)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return {'parcel_area_sqft': subject.area, 'parcel_area_acres': subject.area / 43560,
            'parcel_perimeter_ft': subject.length,
            'bounding_extent_ft': {'east_west': xmax - xmin, 'north_south': ymax - ymin},
            'building_footprints': [{'area_sqft': home.area, 'nearest_parcel_edge_ft': home.distance(subject.boundary)} for home in buildings],
            'street_guide_lengths_ft': [road.length for road in roads],
            'crossing_contour_elevation_range_ft': [min(contour_elevations), max(contour_elevations)] if contour_elevations else None,
            'zoning_intersections': zoning,
            'thematic_geometry_repairs': geometry_repairs,
            'layer_feature_counts': {name: len(layer.get('features', [])) for name, layer in layers.items()},
            'sources': bundle.get('sources', []),
            'studies': results, 'layer_errors': bundle.get('errors', {}),
            'warning': 'Geometry fit only; not legal, septic, sunlight, slope or construction approval.'}


def main():
    from .research_io import write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    metrics = render(json.loads(Path(args.bundle).read_text()), json.loads(Path(args.config).read_text()), args.out)
    write_json(str(args.out) + '.metrics.json', metrics)
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
