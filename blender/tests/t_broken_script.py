"""Selftest: a script bug must come back as structured JSON with the user's line number + code."""
import rbx_lib as R

obj = R.box("Crate", size=(1, 1, 1), mat=R.material("T_Mat3"))
R.result({"partial": "set before the crash"})
undefined_helper_call(obj)          # NameError on THIS line
