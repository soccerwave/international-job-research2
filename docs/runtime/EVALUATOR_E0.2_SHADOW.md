# Evaluator E0.2 calibrated shadow

E0.2 is a user-facing calibration layer over the accepted E0.1 production evaluator. It exists to correct false-positive scientific-fit behavior discovered during live production review without mutating the frozen V1 production/state path.

Key corrections:
- word-boundary scientific matching, so `cognition` never matches `recognition`;
- generic `training` is not a scientific-fit signal; only contextual exercise/physical training phrases are accepted;
- pure cognitive-neuroscience/cognition roles are adjacent unless coupled to direct exercise/stress/brain-health anchors;
- explicit PhD/doctoral training roles are out of scope;
- high-confidence unrelated title domains are suppressed;
- explicit CORU registration requirements are blocking when not established in the candidate profile.

E0.1 remains preserved in the audit workbook. E0.2 drives only the clean control-plane Excel and user-facing priority counts until the calibration is validated on live samples and deliberately promoted in a later production version.
