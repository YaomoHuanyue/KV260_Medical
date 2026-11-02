def catalogue(input_path):
    digest = sha(input_path)
    # Test only: reproduce a new CT with no prior results, without modifying
    # the real CT bytes or hiding/moving existing project results.
    if os.environ.get('KV260_FORCE_RAW_CT_TEST')=='1':return digest,[]
    folders = list((MEDICAL / 'results').glob('*/whole_case/pipeline.json'))
    folders += list(RUNS.glob('*/pipeline.json'))
    folders += list(CANDIDATE_RUNS.glob('*/pipeline.json'))
    results = []
    for p in sorted(folders, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            report = validate_result(p.parent, digest)
            results.append(dict(path=str(p.parent), name=p.parent.parent.name if p.parent.name == 'whole_case' else p.parent.name,
                                seconds=report.get('total_wall_seconds')))
        except (ValueError, OSError, KeyError):
            continue
    return digest, results
