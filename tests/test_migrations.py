from pathlib import Path

from alembic import command
from alembic.config import Config
from conceptualize.models import Base
from sqlalchemy import create_engine, inspect


def test_initial_migration_matches_model_tables_and_downgrades(tmp_path, monkeypatch):
    from conceptualize.config import settings

    url = "sqlite:///" + (tmp_path / "migrations.db").as_posix()
    monkeypatch.setattr(settings, "database_url", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "infrastructure/migrations"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    for name, model in Base.metadata.tables.items():
        assert {c["name"] for c in inspector.get_columns(name)} == set(model.columns.keys())
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
