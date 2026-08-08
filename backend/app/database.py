import logging
from pymongo import MongoClient, uri_parser
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import settings

logger = logging.getLogger(__name__)

class DatabaseConnection:
    def __init__(self):
        self.client = None
        self.db = None
        self._connected = False

    def connect(self):
        try:
            # Setup pymongo client with a short timeout to prevent hanging the startup
            self.client = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=2000)
            # Try to fetch admin info to verify connection
            self.client.admin.command('ping')
            # Extract database name from connection URL, falling back to the configured name
            db_name = uri_parser.parse_uri(settings.MONGODB_URL).get('database') or settings.MONGODB_DB_NAME
            self.db = self.client[db_name]
            self._ensure_db_exists(db_name)
            self._connected = True
            logger.info("Connected successfully to MongoDB database: %s", db_name)
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self._connected = False
            self.client = None
            self.db = None
            logger.error("MongoDB Connection Failed! Make sure MongoDB is running. Error: %s", e)

    def _ensure_db_exists(self, db_name: str):
        # MongoDB creates databases lazily; seed an init collection so the
        # database is created permanently on first connect.
        if db_name not in self.client.list_database_names():
            self.db.create_collection("_init")
            self.db["_init"].insert_one({"_id": "seed", "created": "rapiddoc"})
            logger.info("Created permanent database: %s", db_name)

    def get_db(self):
        if not self._connected or self.db is None:
            # Attempt to reconnect
            self.connect()
        if not self._connected:
            raise ConnectionError("Database is currently unavailable. Please verify MongoDB is running.")
        return self.db

    def is_connected(self) -> bool:
        try:
            if self.client:
                self.client.admin.command('ping')
                return True
        except Exception:
            self._connected = False
        return False

db_conn = DatabaseConnection()

# Automatically connect on import
db_conn.connect()
