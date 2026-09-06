# Stage 1 Feasibility Audit — Architecture Input

Status: **PASS**

Version: `V0.1_FEASIBILITY_AUDIT`

This file records the architecture-relevant conclusions carried into Stage 2. It is not a permanent claim that every portal remains unchanged; source feasibility must be live-validated again at implementation time.

## Shared sources

- EURAXESS — reuse/adapt Spain implementation; primary European backbone.
- LinkedIn via Mads CLI — reuse/adapt transport; redesign query matrix internationally.
- AcademicPositions — reuse/adapt Spain implementation; generalize countries.
- jobs.ac.uk — build as primary United Kingdom portal and Ireland complement.
- ECSS — build high-signal thematic source.
- dvs Stellenbörse — build high-signal Germany/Austria thematic source.
- FENS Job Market — build high-signal neuroscience source.

## Core markets

### Netherlands

Primary: AcademicTransfer.

Direct institutional boards remain backstops unless measured recall shows a gap.

### Germany

Primary: academics.de plus shared sources.

Selected high-value direct backstops: German Sport University Cologne, Ruhr University Bochum, Charité. Other direct sources remain conditional.

### Ireland

UniversityVacancies + generic CoreHR adapter + jobs.ac.uk + shared sources.

CoreHR is high leverage because multiple target universities use the same family.

### United Kingdom

jobs.ac.uk is the backbone. Direct university collectors are deferred until a measured recall gap justifies them.

### Belgium

Shared sources + generic SuccessFactors adapter + selected direct backstops such as KU Leuven and University of Antwerp.

### France

Research/postdoctoral route only. CNRS is primary; ABG is valuable but technically more difficult. Faculty is excluded from initial scope.

### Australia

UniRoles plus generic ATS families. High-priority ATS families identified: PageUp, SmartRecruiters, SuccessFactors where applicable, and Workday despite higher technical risk.

### Austria

Shared sources plus selected direct sources such as University of Innsbruck and University of Vienna. Vienna has a known coverage caveat because not every postdoc is necessarily centralized in the job center.

## Opportunistic markets

Italy, Portugal, Czechia, Poland, Luxembourg: shared-source coverage only in the initial version. No dedicated institutional crawler without observed yield evidence.

## Excluded markets

Sweden, Canada, Switzerland remain outside the initial crawl scope.

## ATS priority

1. CoreHR
2. PageUp
3. SmartRecruiters
4. SuccessFactors
5. Workday

Teamtailor and Personio should be generalized from the Spain production bot rather than rebuilt.

Ubeeo and Oracle Recruiting Cloud are deferred unless later coverage evidence justifies them.

## Donor-first correction

Stage 1 was amended to make ecosystem review mandatory before greenfield source work:

1. Spain production bot;
2. Mads upstream;
3. Mads regional derivatives;
4. other credible implementations;
5. then build using the Mads portal contract if no adequate donor exists.

A donor implementation must still pass current live validation before adoption.

## Initial shard hypothesis

1. EURAXESS Europe
2. AcademicPositions
3. LinkedIn Europe
4. LinkedIn Australia
5. UK/Ireland portals
6. thematic sources
7. Netherlands / AcademicTransfer
8. Germany/France primary
9. CoreHR Ireland
10. SuccessFactors Belgium
11. selected Europe direct backstops
12. Australia UniRoles
13. Australia PageUp
14. Australia SmartRecruiters
15. Australia Workday

This list is intentionally provisional until Stage 4 runtime measurements.
