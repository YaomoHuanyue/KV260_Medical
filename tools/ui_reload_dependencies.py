"""Portable dependency closure for reopening a released UI's source cases."""
from pathlib import Path
import hashlib
import json
import re


def source_dependencies(system, released_names):
    system = Path(system).resolve()
    folders = {Path(name).parent for name in released_names
               if Path(name).name == 'airway_mask.nii.gz'}
    protected = {}

    def keep(path, expected=None, label='UI source'):
        assert path.resolve().is_relative_to(system) and not path.is_symlink(), 'Escaping ' + label + ' dependency'
        assert path.is_file(), 'Missing declared ' + label + ': ' + str(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is not None:
            assert digest == expected, 'Changed declared ' + label + ': ' + str(path)
        protected[path.relative_to(system).as_posix()] = digest

    for folder in folders:
        report = system / folder / 'airway_detail_report.json'
        if report.is_file():
            assert not report.is_symlink(), 'Symbolic airway audit report'
            detail = json.loads(report.read_text(encoding='utf-8'))
            name, expected = detail.get('mask_file'), detail.get('mask_sha256')
            assert (isinstance(name, str) and name and Path(name).name == name
                    and '/' not in name and '\\' not in name and ':' not in name
                    and name not in ('.', '..')), 'Invalid airway audit mask dependency'
            assert isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'Invalid airway audit mask SHA256'
            keep(report, label='airway audit report')
            keep(report.parent / name, expected, 'airway audit mask')
        navigation = system / folder.parent / 'navigation'
        route_report = navigation / 'route.json'
        if not route_report.is_file():
            continue  # A segmentation-only case legitimately has no route.
        route = json.loads(route_report.read_text(encoding='utf-8'))
        keep(route_report, label='navigation report')
        if route.get('schema') == 'kv260.navigation.route.v1' and route.get('point_count', 0) > 1:
            # Both are required by the unmodified backend.prepare. A cached
            # camera does not make the source camera disposable on case reload.
            for name in ('route.npz', 'camera.npz'):
                keep(navigation / name, label='navigation reload payload')
        for name in ('centerline.json', 'centerline.npz', 'branches.json',
                     'instrument_profiles.json', 'alternative_routes.json',
                     'anatomical_generations.json', 'anatomical_generations.npz'):
            if (navigation / name).exists():
                keep(navigation / name, label='navigation source')
    from active_video_dependencies import dependencies as active_video_dependencies
    for name, expected in active_video_dependencies(system).items():
        assert name not in protected or protected[name] == expected, 'Conflicting video/source dependency: ' + name
        protected[name] = expected
    return protected
