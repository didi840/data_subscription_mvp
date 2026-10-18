import json
import os
import copy
import time
from datetime import datetime

from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError


# ============================================================
# LOCAL RESULT
# ============================================================

class LocalResult:

    def __init__(
        self,
        inserted_id=None,
        modified_count=0,
        deleted_count=0
    ):

        self.inserted_id = inserted_id
        self.modified_count = modified_count
        self.deleted_count = deleted_count


# ============================================================
# LOCAL CURSOR
# ============================================================

class LocalCursor:

    def __init__(self, documents):

        self.documents = documents

    def sort(self, key, direction=None):

        if isinstance(key, list):

            for field, order in reversed(key):

                self.documents.sort(
                    key=lambda item: (
                        item.get(field)
                        if item.get(field) is not None
                        else ""
                    ),
                    reverse=(order == -1)
                )

        else:

            self.documents.sort(
                key=lambda item: (
                    item.get(key)
                    if item.get(key) is not None
                    else ""
                ),
                reverse=(direction == -1)
            )

        return self

    def limit(self, amount):

        self.documents = self.documents[:amount]

        return self

    def __iter__(self):

        return iter(self.documents)


# ============================================================
# LOCAL COLLECTION
# ============================================================

class LocalCollection:

    def __init__(self, storage, name):

        self.storage = storage
        self.name = name

    def _documents(self):

        return self.storage.data.setdefault(
            self.name,
            []
        )

    def _save(self):

        self.storage.save()

    # --------------------------------------------------------
    # QUERY MATCHING
    # --------------------------------------------------------

    def _matches(self, document, query):

        for field, condition in query.items():

            value = document.get(field)

            # -----------------------------------------------
            # OPERATORS
            # -----------------------------------------------

            if isinstance(condition, dict):

                if "$exists" in condition:

                    exists = field in document

                    if exists != condition["$exists"]:
                        return False

                if "$gte" in condition:

                    if (
                        value is None
                        or value < condition["$gte"]
                    ):
                        return False

                if "$gt" in condition:

                    if (
                        value is None
                        or value <= condition["$gt"]
                    ):
                        return False

                if "$lte" in condition:

                    if (
                        value is None
                        or value > condition["$lte"]
                    ):
                        return False

                if "$lt" in condition:

                    if (
                        value is None
                        or value >= condition["$lt"]
                    ):
                        return False

                if "$ne" in condition:

                    if value == condition["$ne"]:
                        return False

                if "$in" in condition:

                    if value not in condition["$in"]:
                        return False

            # -----------------------------------------------
            # NORMAL VALUE
            # -----------------------------------------------

            else:

                if value != condition:
                    return False

        return True

    # --------------------------------------------------------
    # FIND ONE
    # --------------------------------------------------------

    def find_one(self, query=None):

        query = query or {}

        for document in self._documents():

            if self._matches(
                document,
                query
            ):

                return copy.deepcopy(
                    document
                )

        return None

    # --------------------------------------------------------
    # FIND
    # --------------------------------------------------------

    def find(self, query=None):

        query = query or {}

        results = []

        for document in self._documents():

            if self._matches(
                document,
                query
            ):

                results.append(
                    copy.deepcopy(document)
                )

        return LocalCursor(results)

    # --------------------------------------------------------
    # INSERT
    # --------------------------------------------------------

    def insert_one(self, document):

        document = copy.deepcopy(
            document
        )

        if "_id" not in document:

            document["_id"] = ObjectId()

        self._documents().append(
            document
        )

        self._save()

        return LocalResult(
            inserted_id=document["_id"]
        )

    # --------------------------------------------------------
    # UPDATE ONE
    # --------------------------------------------------------

    def update_one(
        self,
        query,
        update,
        upsert=False
    ):

        documents = self._documents()

        for index, document in enumerate(
            documents
        ):

            if self._matches(
                document,
                query
            ):

                before = copy.deepcopy(
                    document
                )

                self._apply_update(
                    document,
                    update
                )

                documents[index] = document

                self._save()

                changed = (
                    1
                    if before != document
                    else 0
                )

                return LocalResult(
                    modified_count=changed
                )

        # ----------------------------------------------------
        # UPSERT
        # ----------------------------------------------------

        if upsert:

            new_document = {}

            for key, value in query.items():

                if not isinstance(
                    value,
                    dict
                ):

                    new_document[key] = value

            if "$set" in update:

                for key, value in update[
                    "$set"
                ].items():

                    new_document[key] = value

            if "$setOnInsert" in update:

                for key, value in update[
                    "$setOnInsert"
                ].items():

                    new_document[key] = value

            if "_id" not in new_document:

                new_document["_id"] = ObjectId()

            documents.append(
                new_document
            )

            self._save()

            return LocalResult(
                inserted_id=new_document["_id"]
            )

        return LocalResult(
            modified_count=0
        )

    # --------------------------------------------------------
    # UPDATE MANY
    # --------------------------------------------------------

    def update_many(
        self,
        query,
        update
    ):

        documents = self._documents()

        modified = 0

        for index, document in enumerate(
            documents
        ):

            if self._matches(
                document,
                query
            ):

                before = copy.deepcopy(
                    document
                )

                self._apply_update(
                    document,
                    update
                )

                documents[index] = document

                if before != document:

                    modified += 1

        if modified:

            self._save()

        return LocalResult(
            modified_count=modified
        )

    # --------------------------------------------------------
    # UPDATE OPERATORS
    # --------------------------------------------------------

    def _apply_update(
        self,
        document,
        update
    ):

        # $set

        if "$set" in update:

            for key, value in update[
                "$set"
            ].items():

                document[key] = value

        # $inc

        if "$inc" in update:

            for key, value in update[
                "$inc"
            ].items():

                current = document.get(
                    key,
                    0
                )

                document[key] = (
                    current + value
                )

        # $unset

        if "$unset" in update:

            for key in update[
                "$unset"
            ]:

                document.pop(
                    key,
                    None
                )

    # --------------------------------------------------------
    # DELETE ONE
    # --------------------------------------------------------

    def delete_one(self, query):

        documents = self._documents()

        for index, document in enumerate(
            documents
        ):

            if self._matches(
                document,
                query
            ):

                documents.pop(index)

                self._save()

                return LocalResult(
                    deleted_count=1
                )

        return LocalResult(
            deleted_count=0
        )


# ============================================================
# LOCAL DATABASE
# ============================================================

class LocalDatabase:

    def __init__(
        self,
        folder="local_data"
    ):

        self.folder = folder

        os.makedirs(
            self.folder,
            exist_ok=True
        )

        self.data = {}

    # --------------------------------------------------------
    # FILE PATH
    # --------------------------------------------------------

    def _file_path(
        self,
        collection_name
    ):

        return os.path.join(
            self.folder,
            collection_name + ".json"
        )

    # --------------------------------------------------------
    # LOAD COLLECTION
    # --------------------------------------------------------

    def load_collection(
        self,
        collection_name
    ):

        path = self._file_path(
            collection_name
        )

        if not os.path.exists(path):

            return []

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:

                raw_data = json.load(
                    file
                )

            return self._decode(
                raw_data
            )

        except Exception:

            return []

    # --------------------------------------------------------
    # DECODE JSON
    # --------------------------------------------------------

    def _decode(self, value):

        if isinstance(
            value,
            dict
        ):

            # ObjectId

            if (
                len(value) == 1
                and "$oid" in value
            ):

                try:

                    return ObjectId(
                        value["$oid"]
                    )

                except Exception:

                    return value["$oid"]

            # Date

            if (
                len(value) == 1
                and "$date" in value
            ):

                try:

                    return datetime.fromisoformat(
                        value["$date"]
                    )

                except Exception:

                    return value["$date"]

            # Bytes

            if (
                len(value) == 1
                and "$bytes" in value
            ):

                try:

                    import base64

                    return base64.b64decode(
                        value["$bytes"]
                    )

                except Exception:

                    return value["$bytes"]

            return {
                key: self._decode(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            list
        ):

            return [
                self._decode(item)
                for item in value
            ]

        return value

    # --------------------------------------------------------
    # ENCODE JSON
    # --------------------------------------------------------

    def _encode(self, value):

        if isinstance(
            value,
            ObjectId
        ):

            return {
                "$oid": str(value)
            }

        if isinstance(
            value,
            datetime
        ):

            return {
                "$date": value.isoformat()
            }

        if isinstance(
            value,
            bytes
        ):

            import base64

            return {
                "$bytes":
                    base64.b64encode(
                        value
                    ).decode("utf-8")
            }

        if isinstance(
            value,
            dict
        ):

            return {
                key: self._encode(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            list
        ):

            return [
                self._encode(item)
                for item in value
            ]

        return value

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    def save(self):

        for (
            collection_name,
            documents
        ) in self.data.items():

            path = self._file_path(
                collection_name
            )

            encoded = self._encode(
                documents
            )

            with open(
                path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    encoded,
                    file,
                    indent=2,
                    ensure_ascii=False
                )

    # --------------------------------------------------------
    # COLLECTION
    # --------------------------------------------------------

    def collection(self, name):

        if name not in self.data:

            self.data[name] = (
                self.load_collection(
                    name
                )
            )

        return LocalCollection(
            self,
            name
        )


# ============================================================
# HYBRID COLLECTION
# ============================================================

class HybridCollection:

    def __init__(
        self,
        database,
        name
    ):

        self.database = database
        self.name = name

        self.local = database.local_db.collection(
            name
        )

        self.mongo = (
            database.mongo_db[name]
            if database.mongo_db is not None
            else None
        )

    # --------------------------------------------------------
    # FIND ONE
    # --------------------------------------------------------

    def find_one(self, query=None):

        if self.database.mongo_available():

            try:

                result = self.mongo.find_one(
                    query or {}
                )

                self.database.sync_document_to_local(
                    self.name,
                    result
                )

                return result

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.find_one(
            query or {}
        )

    # --------------------------------------------------------
    # FIND
    # --------------------------------------------------------

    def find(self, query=None):

        if self.database.mongo_available():

            try:

                documents = list(
                    self.mongo.find(
                        query or {}
                    )
                )

                self.database.replace_local_collection(
                    self.name,
                    documents
                )

                return MongoSafeCursor(
                    documents
                )

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.find(
            query or {}
        )

    # --------------------------------------------------------
    # INSERT
    # --------------------------------------------------------

    def insert_one(self, document):

        if self.database.mongo_available():

            try:

                result = self.mongo.insert_one(
                    copy.deepcopy(document)
                )

                local_document = copy.deepcopy(
                    document
                )

                local_document["_id"] = (
                    result.inserted_id
                )

                self.local.insert_one(
                    local_document
                )

                return result

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.insert_one(
            document
        )

    # --------------------------------------------------------
    # UPDATE ONE
    # --------------------------------------------------------

    def update_one(
        self,
        query,
        update,
        upsert=False
    ):

        if self.database.mongo_available():

            try:

                result = self.mongo.update_one(
                    query,
                    update,
                    upsert=upsert
                )

                self.refresh_local_collection()

                return result

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.update_one(
            query,
            update,
            upsert=upsert
        )

    # --------------------------------------------------------
    # UPDATE MANY
    # --------------------------------------------------------

    def update_many(
        self,
        query,
        update
    ):

        if self.database.mongo_available():

            try:

                result = self.mongo.update_many(
                    query,
                    update
                )

                self.refresh_local_collection()

                return result

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.update_many(
            query,
            update
        )

    # --------------------------------------------------------
    # DELETE ONE
    # --------------------------------------------------------

    def delete_one(self, query):

        if self.database.mongo_available():

            try:

                result = self.mongo.delete_one(
                    query
                )

                self.refresh_local_collection()

                return result

            except PyMongoError as error:

                self.database.switch_to_local(
                    error
                )

            except Exception as error:

                self.database.switch_to_local(
                    error
                )

        return self.local.delete_one(
            query
        )

    # --------------------------------------------------------
    # REFRESH LOCAL
    # --------------------------------------------------------

    def refresh_local_collection(self):

        if not self.database.mongo_available():

            return

        try:

            documents = list(
                self.mongo.find({})
            )

            self.database.replace_local_collection(
                self.name,
                documents
            )

        except Exception as error:

            self.database.switch_to_local(
                error
            )


# ============================================================
# MONGO CURSOR WRAPPER
# ============================================================

class MongoSafeCursor:

    def __init__(self, documents):

        self.documents = documents

    def sort(
        self,
        key,
        direction=None
    ):

        if isinstance(
            key,
            list
        ):

            for field, order in reversed(
                key
            ):

                self.documents.sort(
                    key=lambda item: (
                        item.get(field)
                        if item.get(field) is not None
                        else ""
                    ),
                    reverse=(order == -1)
                )

        else:

            self.documents.sort(
                key=lambda item: (
                    item.get(key)
                    if item.get(key) is not None
                    else ""
                ),
                reverse=(direction == -1)
            )

        return self

    def limit(self, amount):

        self.documents = (
            self.documents[:amount]
        )

        return self

    def __iter__(self):

        return iter(
            self.documents
        )


# ============================================================
# HYBRID DATABASE
# ============================================================

class HybridDatabase:

    def __init__(
        self,
        mongo_client,
        mongo_db,
        local_db
    ):

        self.mongo_client = mongo_client
        self.mongo_db = mongo_db
        self.local_db = local_db

        self.online = (
            mongo_client is not None
            and mongo_db is not None
        )

        self.last_connection_check = 0

        self.reconnect_interval = 5

    # --------------------------------------------------------
    # COLLECTION ACCESS
    # --------------------------------------------------------

    def __getitem__(self, name):

        return HybridCollection(
            self,
            name
        )

    def collection(self, name):

        return HybridCollection(
            self,
            name
        )

    # --------------------------------------------------------
    # CHECK MONGO
    # --------------------------------------------------------

    def mongo_available(self):

        # Already offline

        if not self.online:

            now = time.time()

            if (
                now
                - self.last_connection_check
                < self.reconnect_interval
            ):

                return False

            self.last_connection_check = now

            if self.mongo_client is None:

                return False

            try:

                self.mongo_client.admin.command(
                    "ping"
                )

                self.online = True

                print(
                    "MongoDB connection restored."
                )

                return True

            except Exception:

                return False

        return True

    # --------------------------------------------------------
    # SWITCH TO LOCAL
    # --------------------------------------------------------

    def switch_to_local(
        self,
        error=None
    ):

        if self.online:

            print("")
            print(
                "MongoDB connection lost."
            )
            print(
                "Switching to local JSON storage."
            )

            if error:

                print(
                    "Reason:",
                    str(error)[:200]
                )

            print("")

        self.online = False

        self.last_connection_check = (
            time.time()
        )

    # --------------------------------------------------------
    # REPLACE LOCAL COLLECTION
    # --------------------------------------------------------

    def replace_local_collection(
        self,
        collection_name,
        documents
    ):

        self.local_db.data[
            collection_name
        ] = copy.deepcopy(
            documents
        )

        self.local_db.save()

    # --------------------------------------------------------
    # SYNC ONE DOCUMENT
    # --------------------------------------------------------

    def sync_document_to_local(
        self,
        collection_name,
        document
    ):

        if document is None:

            return

        local_documents = (
            self.local_db.data.setdefault(
                collection_name,
                []
            )
        )

        document_id = document.get(
            "_id"
        )

        if document_id is None:

            return

        found = False

        for index, local_document in enumerate(
            local_documents
        ):

            if (
                local_document.get("_id")
                == document_id
            ):

                local_documents[index] = (
                    copy.deepcopy(document)
                )

                found = True

                break

        if not found:

            local_documents.append(
                copy.deepcopy(document)
            )

        self.local_db.save()


# ============================================================
# CONNECT DATABASE
# ============================================================

def connect_database(
    mongo_uri,
    database_name
):

    print("")
    print(
        "Checking MongoDB connection..."
    )

    # --------------------------------------------------------
    # LOCAL DATABASE
    # --------------------------------------------------------

    local_db = LocalDatabase(
        folder="local_data"
    )

    # --------------------------------------------------------
    # MONGO
    # --------------------------------------------------------

    try:

        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=5000
        )

        client.admin.command(
            "ping"
        )

        mongo_db = client[
            database_name
        ]

        print(
            "MongoDB connection successful."
        )

        print(
            "Using MongoDB Atlas."
        )

        print("")

        database = HybridDatabase(
            client,
            mongo_db,
            local_db
        )

        # ----------------------------------------------------
        # CREATE LOCAL BACKUP
        # ----------------------------------------------------

        collections = [
            "users",
            "data_plans",
            "transactions",
            "webauthn_credentials"
        ]

        for collection_name in collections:

            try:

                documents = list(
                    mongo_db[
                        collection_name
                    ].find({})
                )

                if documents:

                    database.replace_local_collection(
                        collection_name,
                        documents
                    )

            except Exception:

                pass

        return (
            client,
            database,
            True
        )

    except Exception as error:

        print("")
        print(
            "MongoDB is unavailable."
        )

        print(
            "Switching to local JSON storage."
        )

        print(
            "Reason:",
            str(error)[:200]
        )

        print("")

        database = HybridDatabase(
            None,
            None,
            local_db
        )

        return (
            None,
            database,
            False
        )