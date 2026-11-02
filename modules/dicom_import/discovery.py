"""Recursive DICOM discovery with explicit, directory-qualified selection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Series:
    selection_id: str
    directory: Path
    relative_directory: str
    series_uid: str
    files: tuple[str, ...]

    def summary(self):
        return dict(selection_id=self.selection_id, directory=str(self.directory),
                    relative_directory=self.relative_directory,
                    series_uid=self.series_uid, file_count=len(self.files))


def discover(directory: str | Path) -> list[Series]:
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('DICOM discovery requires a directory')
    result = []
    for current, subdirs, files in os.walk(root, followlinks=False):
        # Do not visit directory aliases twice or follow links outside the input.
        subdirs[:] = sorted(d for d in subdirs if not (Path(current) / d).is_symlink())
        if not files:
            continue
        folder = Path(current).resolve()
        if not folder.is_relative_to(root):
            raise ValueError('DICOM directory escapes the selected root')
        relative = folder.relative_to(root).as_posix()
        for uid in sorted(sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(folder)) or ()):
            ordered = tuple(sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(folder), uid))
            if not ordered:
                continue
            for name in ordered:
                path = Path(name).resolve(strict=True)
                if not path.is_file() or path.parent != folder:
                    raise ValueError('DICOM series contains an external or invalid file')
            token = hashlib.sha256((relative + '\0' + uid).encode()).hexdigest()[:24]
            result.append(Series(token, folder, relative, uid, ordered))
    assert len({r.selection_id for r in result}) == len(result)
    return sorted(result, key=lambda r: (r.relative_directory, r.series_uid))


def select(records: list[Series], selection: str | None = None) -> Series:
    if not records:
        raise ValueError('No readable DICOM series found')
    if selection is None:
        if len(records) != 1:
            raise ValueError('Multiple DICOM series: select a directory-qualified selection_id')
        return records[0]
    selected = [r for r in records if r.selection_id == selection]
    if not selected:
        selected = [r for r in records if r.series_uid == selection]
    if len(selected) != 1:
        raise ValueError('DICOM selection is missing or ambiguous; use selection_id')
    return selected[0]


def create_selected_case(system_root: str | Path, case_id: str,
                         directory: str | Path, selection: str | None = None) -> Path:
    """Use the existing geometry/source-hash/atomic-case contract unchanged."""
    series = select(discover(directory), selection)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from system.contracts import create_case
    return create_case(system_root, case_id, series.directory, series.series_uid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('list', 'import'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--selection')
    parser.add_argument('--case-id')
    parser.add_argument('--system-root', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.action == 'list':
        print(json.dumps(dict(directory=str(args.input.resolve()),
                              series=[r.summary() for r in discover(args.input)]),
                         ensure_ascii=False))
    else:
        if not args.case_id:
            parser.error('import requires --case-id')
        case = create_selected_case(args.system_root, args.case_id, args.input, args.selection)
        print(json.dumps(dict(case=str(case), input=str(case / 'input/ct.nrrd'))))


if __name__ == '__main__':
    main()
