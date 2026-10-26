"""Keep tests independent from the developer's credentials and login settings."""
import pytest

from rinatomo import llm


@pytest.fixture(autouse=True)
def isolated_local_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('RINATOMO_CONFIG_HOME', str(tmp_path / 'profile'))
    monkeypatch.setenv('RINATOMO_NAPCAT_ROOT', str(tmp_path / 'no-napcat'))
    monkeypatch.setenv('RINATOMO_QQ_PATH', str(tmp_path / 'no-qq.exe'))
    for name in ('DASHSCOPE_API_KEY', 'DASHSCOPE_BASE_URL', 'DASHSCOPE_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, 'PROJECT_ENV_PATH', tmp_path / 'no-project.env')
