from pathlib import Path
p=Path('tmp/audit_registry_tips_local.py');t=p.read_text(encoding='utf-8').replace("dir=root/'tmp')","dir=root/'tmp',ignore_cleanup_errors=True)").replace('tips=importlib.util.module_from_spec(spec);spec.loader.exec_module(tips)','tips=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tips;spec.loader.exec_module(tips)');p.write_text(t,encoding='utf-8')
