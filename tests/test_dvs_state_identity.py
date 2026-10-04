from src.sources.shared import dvs
from src.state.engine import _aliases, apply_state, empty_state, WRITER_ROLE

def test_dvs_shared_board_url_is_not_identity_alias():
    html='''
    <div><strong>Uni A</strong><br/>Researcher A<br/><a href="https://www.sportwissenschaft.de/fileadmin/pdf/Stellen_PDF/2026/2026_UniA_A.pdf">mehr...</a></div>
    <div><strong>Uni B</strong><br/>Researcher B<br/><a href="https://www.sportwissenschaft.de/fileadmin/pdf/Stellen_PDF/2026/2026_UniB_B.pdf">mehr...</a></div>
    '''
    rows=dvs.parse_listing(html)
    records=[]
    from src.sources.shared.common import make_record
    for row in rows:
        records.append(make_record(
            source_key='dvs',source_kind='THEMATIC_PORTAL',provider='DVS',
            source_job_id=row['id'],listing_url=dvs.LISTING_URL,detail_url=row['url'],
            title=row['title'],institution=row['institution'],detail_status='NOT_ATTEMPTED'
        ))
    for r in records:
        aliases=[a for _,a in _aliases(r)]
        assert 'url:https://sportwissenschaft.de/stellenborse/stellenangebote' not in aliases
    state,_summary=apply_state(records,empty_state(),observed_at='2026-10-04T20:45:00+00:00',run_id='dvs-state-test',writer_role=WRITER_ROLE)
    assert len(state['jobs'])==2
    ids=[r['raw_extra']['state']['state_id'] for r in records]
    assert len(set(ids))==2
    assert all(r['raw_extra']['state']['seen_status']=='NEW' for r in records)
