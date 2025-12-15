import sys, os, importlib
print('cwd=', os.getcwd())
print('sys.path sample:', sys.path[:5])
print('project root exists:', os.path.isdir(os.path.join(os.getcwd(), 'src')))
print('src_spec:', importlib.util.find_spec('src'))
try:
    import src.app as m
    print('imported src.app', m)
except Exception as e:
    print('import error:', type(e), e)
