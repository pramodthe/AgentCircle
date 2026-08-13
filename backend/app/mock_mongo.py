"""Development-only MongoDB compatibility client.

This module is imported only when USE_MOCK_MONGODB=true. It enables local UI and workflow
preview on machines without MongoDB. It is deliberately excluded from the production path.
"""

from mongomock import MongoClient
from mongomock.collection import BulkOperationBuilder

_mongomock_add_update = BulkOperationBuilder.add_update


def _compatible_add_update(
    self,
    selector,
    doc,
    multi=False,
    upsert=False,
    collation=None,
    array_filters=None,
    hint=None,
    sort=None,
):
    """Bridge PyMongo 4.16's bulk-update signature until mongomock exposes `sort`."""

    del sort
    return _mongomock_add_update(
        self,
        selector,
        doc,
        multi=multi,
        upsert=upsert,
        collation=collation,
        array_filters=array_filters,
        hint=hint,
    )


def create_mock_client():
    BulkOperationBuilder.add_update = _compatible_add_update
    return MongoClient()
