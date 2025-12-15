import traceback
try:
    import issue_project.src as pkg
    print('pkg', pkg)
    print('has_appointments', hasattr(pkg, 'appointments'))
    import issue_project.src.appointments as mod
    print('appointments module', mod)
except Exception:
    traceback.print_exc()
