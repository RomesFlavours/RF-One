from pathlib import Path
s=Path('tmp/build_registry_perf_release.py').read_text(encoding='utf-8').replace("tmp/registry-performance-release","tmp/registry-navigation-release").replace("tag='registry-performance-'","tag='registry-navigation-'")
start=s.index('commands=[');end=s.index('\n# JSON',start)
s=s[:start]+'''commands=['docker build --build-arg RFONE_RELEASE_REVISION='+commit+' -t '+image+' .',
 'docker run --rm -e RFONE_TEST_SKIP_BROWSER=1 -v "$CODEBUILD_SRC_DIR/navigation/test_registry_navigation.py:/app/RF-One Web/tests/test_registry_navigation.py:ro" --entrypoint python '+image+' "/app/RF-One Web/tests/test_registry_navigation.py"',
 'docker run --rm -v "$CODEBUILD_SRC_DIR/navigation/test_role_company_http.py:/app/RF-One Web/tests/test_role_company_http.py:ro" --entrypoint python '+image+' "/app/RF-One Web/tests/test_role_company_http.py"',
 'docker run --rm --entrypoint python '+image+' "/app/RF-One Web/tests/test_registry_clover_confirmation.py"',
 'docker run --rm -v "$CODEBUILD_SRC_DIR/03 Software/RF-One Web/tests/test_registry_performance.py:/app/RF-One Web/tests/test_registry_performance.py:ro" --entrypoint python '+image+' "/app/RF-One Web/tests/test_registry_performance.py"',
 'docker run --rm --entrypoint python '+image+' /app/release_policy_test.py web /app']'''+s[end:]
Path('tmp/build_registry_navigation_release.py').write_text(s,encoding='utf-8',newline='\n')
