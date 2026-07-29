WRITE_OPERATORS = {
    "$set", "$unset", "$push", "$pull", "$addToSet", "$pop",
    "$inc", "$rename", "$currentDate", "$min", "$max",
    "$mul", "$bit", "$xor", "$each", "$slice", "$sort",
    "$position", "$isolated"
}

WRITE_METHODS = {
    "insertOne", "insertMany", "updateOne", "updateMany",
    "deleteOne", "deleteMany", "replaceOne", "bulkWrite",
    "findOneAndUpdate", "findOneAndDelete", "findOneAndReplace"
}

TIMEOUT_SECONDS = 10


def validate_query(query: dict) -> tuple[bool, str]:
    if not isinstance(query, dict):
        return False, "Query must be a dictionary"

    # Check for write operators in the update section
    if "update" in query:
        update = query["update"]
        if isinstance(update, dict):
            for key in update:
                if key in WRITE_OPERATORS:
                    return False, f"Write operator '{key}' not allowed in custom queries"

    # Check for write methods
    method = query.get("method", "")
    if method in WRITE_METHODS:
        return False, f"Write method '{method}' not allowed in custom queries"

    # Reject if contains $set anywhere (common in updates)
    query_str = str(query)
    for op in WRITE_OPERATORS:
        if op in query_str:
            return False, f"Write operator '{op}' detected in query"

    return True, "OK"


def build_mongo_query(func_name: str, params: dict, allowed_collections: list) -> dict:
    return {
        "collection": params.get("collection", ""),
        "method": params.get("method", "find"),
        "filter": params.get("filter", {}),
        "projection": params.get("projection", None),
        "sort": params.get("sort", None),
        "limit": min(params.get("limit", 100), 500),
        "timeout": TIMEOUT_SECONDS
    }
