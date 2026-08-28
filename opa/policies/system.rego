package finassist.system

# Always-true decision document used solely to prove that OPA has this bundle
# loaded and is evaluating policy, not just that the process is alive. The
# application's readiness probe queries this exact path
# (see FINASSIST_OPA__DECISION_PATH / OPASettings.decision_path) and requires
# `result` to be the boolean `true`; an unreachable OPA, an empty policy set,
# or a renamed package would all make this undefined instead.
default ready := false

ready if {
	true
}
