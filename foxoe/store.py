"""SQLite transactions preserve the previous configuration if a save fails."""
import json
import os
import secrets
import sqlite3
import hashlib
import hmac
from contextlib import contextmanager
from pathlib import Path

from .models import Configuration


class Conflict(Exception):
    pass


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "foxoe.sqlite"
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO settings VALUES (1, ?)", (Configuration().model_dump_json(),))
            db.execute("CREATE TABLE IF NOT EXISTS app_credentials (id TEXT PRIMARY KEY, digest TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS images (digest TEXT PRIMARY KEY, data BLOB NOT NULL)")
            # Migrate under the same transaction as initialization. A failed
            # validation leaves the original JSON intact; updates back up this DB.
            value = json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
            if value.get('gridVersion', 1) == 1:
                for widget in value.get('widgets', []):
                    for field, default in (('x', 0), ('y', 0), ('w', 4), ('h', 2)):
                        number = widget.get(field, default)
                        if type(number) is not int:
                            raise ValueError('invalid_legacy_grid')
                        widget[field] = number * 2
                value['gridVersion'] = 2
                value['revision'] = value.get('revision', 0) + 1
                migrated = Configuration.model_validate(value)
                db.execute('UPDATE settings SET value=? WHERE id=1', (migrated.model_dump_json(),))
        self.path.chmod(0o600)
        # Exclusive creation never replaces an existing installation's credential.
        self.token = self.credential(directory / "bridge-token")
        self.registration_token = self.credential(directory / "registration-token")

    @staticmethod
    def credential(token_path):
        try:
            with open(token_path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
                file.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
        token = token_path.read_text().strip()
        if len(token) < 32:
            raise ValueError("Invalid bridge credential file")
        return token

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self) -> Configuration:
        with self.connect() as db:
            return Configuration.model_validate_json(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])

    def save(self, config: Configuration) -> Configuration:
        with self.connect() as db:
            # Acquire the write lock before reading the revision, including when
            # another process writes to this database at the same time.
            db.execute("BEGIN IMMEDIATE")
            old = json.loads(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])
            if old["revision"] != config.revision:
                raise Conflict()
            saved = config.model_copy(update={"revision": config.revision + 1})
            db.execute("UPDATE settings SET value=? WHERE id=1", (saved.model_dump_json(),))
            keep = {app.id for app in saved.apps}
            for row in db.execute("SELECT id FROM app_credentials").fetchall():
                if row[0] not in keep:
                    db.execute("DELETE FROM app_credentials WHERE id=?", row)
            self.prune_images(db, saved)
            return saved

    @staticmethod
    def prune_images(db, config):
        used = {digest for app in config.apps for digest in app.images.values()}
        for row in db.execute("SELECT digest FROM images").fetchall():
            if row[0] not in used:
                db.execute("DELETE FROM images WHERE digest=?", row)

    def authorize_app(self, app_id, token):
        with self.connect() as db:
            row = db.execute("SELECT digest FROM app_credentials WHERE id=?", (app_id,)).fetchone()
        digest = hashlib.sha256(token.encode()).hexdigest()
        return bool(row and hmac.compare_digest(row[0], digest))

    def register(self, app, assets, credential, updating=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            config = Configuration.model_validate_json(db.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])
            index = next((index for index, item in enumerate(config.apps) if item.id == app.id), None)
            if updating and index is None:
                raise ValueError("app_not_found")
            if updating:
                row = db.execute("SELECT digest FROM app_credentials WHERE id=?", (app.id,)).fetchone()
                if not row or not hmac.compare_digest(row[0], hashlib.sha256(credential.encode()).hexdigest()):
                    raise ValueError("app_credential_changed")
            if not updating and index is not None:
                raise ValueError("app_already_registered")
            if index is None:
                if len(config.apps) >= 14:
                    raise ValueError("app_limit")
                config.apps.append(app)
            else:
                config.apps[index] = app
            if credential and not updating:
                db.execute("INSERT INTO app_credentials VALUES (?, ?)", (app.id, hashlib.sha256(credential.encode()).hexdigest()))
            for digest, data in assets.items():
                db.execute("INSERT OR IGNORE INTO images VALUES (?, ?)", (digest, data))
            config.revision += 1
            db.execute("UPDATE settings SET value=? WHERE id=1", (config.model_dump_json(),))
            self.prune_images(db, config)
            return config

    def image(self, digest):
        with self.connect() as db:
            row = db.execute("SELECT data FROM images WHERE digest=?", (digest,)).fetchone()
        return row[0] if row else None
