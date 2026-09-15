from flask import current_app
from flask_migrate import Migrate
from alembic import context
from sqlalchemy import engine_from_config, pool
from models import *

target_metadata = current_app.extensions["migrate"].db.metadata
config = context.config

def run_migrations_offline():
    context.configure(url=current_app.config["SQLALCHEMY_DATABASE_URI"], target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable = current_app.extensions["migrate"].db.engine
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
