"""Drive the normal Streamlit entry point through both human checkpoints."""

from streamlit.testing.v1 import AppTest

from rivalscope import ui
from rivalscope.config import ROOT, Settings


def _click(app, label):
    button = next(button for button in app.button if button.label == label)
    app = button.click().run()
    assert not app.exception
    return app


def test_streamlit_approval_unlocks_downloads_and_documentation(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "CHECKPOINTS", tmp_path / "streamlit.sqlite3")
    monkeypatch.setattr(ui.Settings, "load", lambda: Settings())
    app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "RivalScope"
    app.radio[0].set_value("live").run()
    assert not app.exception
    assert app.warning
    app.radio[0].set_value("demo").run()

    _click(app, "Find competitors")
    assert app.subheader[0].value == "Review the competitor shortlist"
    _click(app, "Confirm and research")
    assert app.metric[1].value == "12 / 12"
    assert len(app.get("download_button")) == 0
    _click(app, "Approve briefing")
    assert len(app.get("download_button")) == 2

    app.switch_page("pages/documentation.py").run()
    assert not app.exception
    assert app.title[0].value == "RivalScope documentation"
    assert "Set up the API keys" in app.markdown[0].value
